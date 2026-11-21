"""I/O for contractor scorecards. Sources: Supabase/Postgres (production) or data/*.csv (local debugging).
Store: contractor_scorecard_runs + contractor_monthly_scorecards (Postgres) or in-memory (tests, dry runs).

Narrow reads (only the columns the processor uses):
  work_orders            work_order_id, ward_code, road_id, work_type, repair_method, contractor_id,
                         assigned_at, work_started_at, completed_at, area_sqm, cost_inr, sla_met, reopened_within_30d
  contractors            contractor_id, contractor_name
  rate_card              repair_method, unit, standard_rate_inr
  roads                  road_id, ward_code
  complaint_work_orders  work_order_id, complaint_id  (+ complaints.received_at, LEFT JOIN: one row per link)
  context (optional)     rainfall_daily, tides, flood_hotspots, traffic, accidents, facilities
"""
from __future__ import annotations

import json
import logging
import pathlib
from datetime import date
from decimal import Decimal
from typing import Optional, Protocol

import pandas as pd
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from .processor import ProcessResult, SourceData

log = logging.getLogger(__name__)

SOURCE_SQL = {
    "work_orders": "SELECT work_order_id, ward_code, road_id, work_type, repair_method, contractor_id, assigned_at, "
                   "work_started_at, completed_at, area_sqm, cost_inr, sla_met, reopened_within_30d FROM work_orders",
    "contractors": "SELECT contractor_id, contractor_name FROM contractors",
    "rate_card": "SELECT repair_method, unit, standard_rate_inr FROM rate_card",
    "roads": "SELECT road_id, ward_code FROM roads",
    "complaint_links": "SELECT cwo.work_order_id, cwo.complaint_id, c.received_at FROM complaint_work_orders cwo "
                       "LEFT JOIN complaints c ON c.complaint_id = cwo.complaint_id",
}
CONTEXT_SQL = {
    "rainfall_daily": "SELECT date, station, rainfall_mm, imd_category FROM rainfall_daily",
    "tides": "SELECT date, high_tide_time, height_m, big_tide_flag FROM tides",
    "flood_hotspots": "SELECT hotspot_id, ward_code, flood_threshold_mm_per_day, tide_sensitive FROM flood_hotspots",
    "traffic": "SELECT road_id, peak_hour_vehicles, congestion_index_0_10 FROM traffic",
    "accidents": "SELECT accident_id, road_id, occurred_at, severity FROM accidents",
    "facilities": "SELECT facility_id, type, ambulance_entry_road FROM facilities",
}

SCORE_COLS = [
    "contractor_id", "month", "methodology_version", "computed_at", "completed_jobs", "total_billed_inr",
    "sla_known", "sla_met", "sla_missing", "sla_rate", "sla_rank",
    "reopen_known", "reopened", "reopen_missing", "reopen_rate", "durability_rank",
    "speed_sample", "speed_missing", "speed_raw_sample", "speed_median_hours", "speed_cohort_median_hours",
    "speed_relative_index", "speed_rank", "assigned_to_completed_median_hours",
    "cost_sample", "cost_missing", "cost_median_abs_pct_dev", "cost_over_tolerance_count",
    "cost_over_tolerance_share", "cost_under_tolerance_count", "cost_rank",
]
JSON_COLS = ["rank_eligibility", "rank_cohort_sizes", "workload_mix", "context", "data_quality"]


class StoreUnavailable(RuntimeError):
    """Raised when the scorecard tables cannot be read or written (DB down, migration not applied)."""


class SourceRepository(Protocol):
    def load_sources(self) -> SourceData: ...


class ScorecardStore(Protocol):
    def write(self, result: ProcessResult) -> int: ...
    def read_run(self, version: str) -> Optional[dict]: ...
    def read_rows(self, version: str, month_from: Optional[date], month_to: Optional[date],
                  contractor_id: Optional[str] = None) -> list[dict]: ...
    def contractor_exists(self, contractor_id: str) -> bool: ...


def _plain(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return v


# ── Postgres / Supabase ──────────────────────────────────────────────────────
class PostgresRepository:
    """Source + store over the shared SQLAlchemy engine (backend/db.py, DATABASE_URL)."""

    def __init__(self, engine):
        self.engine = engine

    def load_sources(self) -> SourceData:
        frames = {k: pd.read_sql_query(text(sql), self.engine) for k, sql in SOURCE_SQL.items()}
        for k, sql in CONTEXT_SQL.items():
            try:
                frames[k] = pd.read_sql_query(text(sql), self.engine)
            except ProgrammingError as e:  # table absent: context block becomes null + note
                log.warning("context table %s unavailable: %s", k, e.orig)
                frames[k] = None
        return SourceData(**frames)

    def write(self, result: ProcessResult) -> int:
        run = result.run
        v = run["methodology_version"]
        keys = [f"{r['contractor_id']}|{r['month'].isoformat()}" for r in result.rows]
        cols = SCORE_COLS + JSON_COLS + ["evidence_work_order_ids"]
        values = ", ".join(f"CAST(:{c} AS jsonb)" if c in JSON_COLS else f":{c}" for c in cols)
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in ("contractor_id", "month", "methodology_version"))
        upsert = text(f"INSERT INTO contractor_monthly_scorecards ({', '.join(cols)}) VALUES ({values}) "
                      f"ON CONFLICT (contractor_id, month, methodology_version) DO UPDATE SET {updates}")
        params = [{**{c: r.get(c) for c in SCORE_COLS},
                   **{c: json.dumps(r.get(c), sort_keys=True) for c in JSON_COLS},
                   "evidence_work_order_ids": r["evidence_work_order_ids"]} for r in result.rows]
        try:
            with self.engine.begin() as c:  # one transaction: run row, stale-row cleanup, upsert
                c.execute(text(
                    "INSERT INTO contractor_scorecard_runs (methodology_version, computed_at, params, source_counts, data_quality) "
                    "VALUES (:v, :t, CAST(:p AS jsonb), CAST(:s AS jsonb), CAST(:d AS jsonb)) "
                    "ON CONFLICT (methodology_version) DO UPDATE SET computed_at = EXCLUDED.computed_at, "
                    "params = EXCLUDED.params, source_counts = EXCLUDED.source_counts, data_quality = EXCLUDED.data_quality"),
                    {"v": v, "t": run["computed_at"], "p": json.dumps(run["params"], sort_keys=True),
                     "s": json.dumps(run["source_counts"], sort_keys=True),
                     "d": json.dumps(run["data_quality"], sort_keys=True)})
                c.execute(text("DELETE FROM contractor_monthly_scorecards WHERE methodology_version = :v "
                               "AND NOT (contractor_id || '|' || to_char(month, 'YYYY-MM-DD') = ANY(:keys))"),
                          {"v": v, "keys": keys})
                if params:
                    c.execute(upsert, params)
        except Exception as e:
            raise StoreUnavailable(f"could not write contractor scorecards: {e}") from e
        return len(params)

    def _query(self, sql: str, **p) -> list[dict]:
        try:
            with self.engine.connect() as c:
                return [{k: _plain(v) for k, v in r.items()} for r in c.execute(text(sql), p).mappings()]
        except Exception as e:
            raise StoreUnavailable(f"could not read contractor scorecards: {e}") from e

    def read_run(self, version: str) -> Optional[dict]:
        r = self._query("SELECT methodology_version, computed_at, params, source_counts, data_quality "
                        "FROM contractor_scorecard_runs WHERE methodology_version = :v", v=version)
        return r[0] if r else None

    def read_rows(self, version, month_from, month_to, contractor_id=None) -> list[dict]:
        return self._query(
            "SELECT s.*, c.contractor_name FROM contractor_monthly_scorecards s "
            "JOIN contractors c ON c.contractor_id = s.contractor_id "
            "WHERE s.methodology_version = :v "
            "AND (CAST(:f AS date) IS NULL OR s.month >= CAST(:f AS date)) "
            "AND (CAST(:t AS date) IS NULL OR s.month <= CAST(:t AS date)) "
            "AND (CAST(:cid AS text) IS NULL OR s.contractor_id = CAST(:cid AS text)) "
            "ORDER BY s.month, s.contractor_id",
            v=version, f=month_from, t=month_to, cid=contractor_id)

    def contractor_exists(self, contractor_id: str) -> bool:
        return bool(self._query("SELECT 1 FROM contractors WHERE contractor_id = :c", c=contractor_id))


# ── CSV source (local debugging; same hygiene as supabase/load_source.sql) ──
class CsvRepository:
    def __init__(self, data_dir: str | pathlib.Path):
        self.dir = pathlib.Path(data_dir)

    def _read(self, name: str, cols: list[str]) -> Optional[pd.DataFrame]:
        p = self.dir / f"{name}.csv"
        if not p.exists():
            return None
        return pd.read_csv(p, usecols=cols, dtype=str, keep_default_na=False, na_values=[""])

    def load_sources(self) -> SourceData:
        wo = self._read("work_orders", ["work_order_id", "linked_complaint_ids", "ward_code", "road_id", "work_type",
                                        "repair_method", "contractor_id", "assigned_at", "work_started_at",
                                        "completed_at", "area_sqm", "cost_inr", "sla_met", "reopened_within_30d"])
        complaints = self._read("complaints", ["complaint_id", "received_at"])
        links = (wo[["work_order_id", "linked_complaint_ids"]].dropna()
                 .assign(complaint_id=lambda d: d["linked_complaint_ids"].str.split("|"))
                 .explode("complaint_id"))
        links["complaint_id"] = links["complaint_id"].str.strip()
        links = links[links["complaint_id"] != ""].drop_duplicates(["work_order_id", "complaint_id"])
        links = links[["work_order_id", "complaint_id"]].merge(complaints, on="complaint_id", how="left",
                                                               validate="many_to_one")
        return SourceData(
            work_orders=wo.drop(columns=["linked_complaint_ids"]),
            contractors=self._read("contractors", ["contractor_id", "contractor_name"]),
            rate_card=self._read("rate_card", ["repair_method", "unit", "standard_rate_inr"]),
            roads=self._read("roads", ["road_id", "ward_code"]),
            complaint_links=links.reset_index(drop=True),
            rainfall_daily=self._read("rainfall_daily", ["date", "station", "rainfall_mm", "imd_category"]),
            tides=self._read("tides", ["date", "high_tide_time", "height_m", "big_tide_flag"]),
            flood_hotspots=self._read("flood_hotspots", ["hotspot_id", "ward_code", "flood_threshold_mm_per_day",
                                                         "tide_sensitive"]),
            traffic=self._read("traffic", ["road_id", "peak_hour_vehicles", "congestion_index_0_10"]),
            accidents=self._read("accidents", ["accident_id", "road_id", "occurred_at", "severity"]),
            facilities=self._read("facilities", ["facility_id", "type", "ambulance_entry_road"]),
        )


# ── In-memory store (tests, --dry-run) ───────────────────────────────────────
class MemoryStore:
    """Mirrors the Postgres store's keying and upsert semantics without a database."""

    def __init__(self, contractor_names: Optional[dict[str, str]] = None):
        self.runs: dict[str, dict] = {}
        self.rows: dict[tuple, dict] = {}
        self.names = dict(contractor_names or {})

    def write(self, result: ProcessResult) -> int:
        v = result.run["methodology_version"]
        self.runs[v] = dict(result.run)
        new = {(r["contractor_id"], r["month"], v): r for r in result.rows}
        self.rows = {k: r for k, r in self.rows.items() if k[2] != v or k in new}
        for k, r in new.items():
            self.names.setdefault(r["contractor_id"], r.get("contractor_name"))
            self.rows[k] = {c: r.get(c) for c in SCORE_COLS + JSON_COLS + ["evidence_work_order_ids"]}
        return len(new)

    def read_run(self, version):
        return self.runs.get(version)

    def read_rows(self, version, month_from, month_to, contractor_id=None):
        out = []
        for (cid, month, v), r in sorted(self.rows.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            if v != version or (month_from and month < month_from) or (month_to and month > month_to):
                continue
            if contractor_id and cid != contractor_id:
                continue
            out.append({**r, "contractor_name": self.names.get(cid)})
        return out

    def contractor_exists(self, contractor_id):
        return contractor_id in self.names
