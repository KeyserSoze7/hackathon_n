"""Deterministic contractor x completion-month scorecards. Pure functions over DataFrames: no I/O.

Grain: one row per (contractor_id, month of work_orders.completed_at, methodology_version).
Every job contributes to exactly one row; context tables are pre-aggregated to their own grain
(date, ward, road) and joined at most once per job, so no complaint, rain station, tide, facility
or accident row can multiply jobs or billed INR.

Four dimensions are ranked separately (never combined):
  speed       median(job hours / same-month same-method city median)    lower = faster
  sla         sla_met / sla_known                                       higher = better
  durability  reopened / reopen_known                                   lower = better
  cost        median |cost - benchmark| / benchmark                     lower = closer to rate card
Context (rain, tides, hotspots, traffic, accidents, facilities) is descriptive only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from .config import HEAVY_RAIN_CATEGORIES, Methodology

DIMENSIONS = {
    # dimension: (rank column, value column, sample column, ascending)
    "speed": ("speed_rank", "speed_relative_index", "speed_sample", True),
    "sla": ("sla_rank", "sla_rate", "sla_known", False),
    "durability": ("durability_rank", "reopen_rate", "reopen_known", True),
    "cost_alignment": ("cost_rank", "cost_median_abs_pct_dev", "cost_sample", True),
}

WORK_ORDER_COLS = ["work_order_id", "ward_code", "road_id", "work_type", "repair_method", "contractor_id",
                   "assigned_at", "work_started_at", "completed_at", "area_sqm", "cost_inr",
                   "sla_met", "reopened_within_30d"]
CONTEXT_TABLES = ("rainfall_daily", "tides", "flood_hotspots", "traffic", "accidents", "facilities")


@dataclass
class SourceData:
    """Narrow source extracts. Context tables are None when absent from the database."""
    work_orders: pd.DataFrame
    contractors: pd.DataFrame        # contractor_id, contractor_name
    rate_card: pd.DataFrame          # repair_method, unit, standard_rate_inr
    roads: pd.DataFrame              # road_id, ward_code
    complaint_links: pd.DataFrame    # work_order_id, complaint_id, received_at (null if complaint missing)
    rainfall_daily: Optional[pd.DataFrame] = None   # date, station, rainfall_mm, imd_category
    tides: Optional[pd.DataFrame] = None            # date, high_tide_time, height_m, big_tide_flag
    flood_hotspots: Optional[pd.DataFrame] = None   # hotspot_id, ward_code, flood_threshold_mm_per_day, tide_sensitive
    traffic: Optional[pd.DataFrame] = None          # road_id, peak_hour_vehicles, congestion_index_0_10
    accidents: Optional[pd.DataFrame] = None        # accident_id, road_id, occurred_at, severity
    facilities: Optional[pd.DataFrame] = None       # facility_id, type, ambulance_entry_road


@dataclass
class ProcessResult:
    rows: list[dict]
    run: dict
    notes: list[str] = field(default_factory=list)


# ── small helpers ────────────────────────────────────────────────────────────
def to_bool(s: pd.Series) -> pd.Series:
    """Y/N/true/false/1/0 -> nullable boolean. Anything else (blank, null) stays <NA> (unknown)."""
    def conv(v):
        if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
            return pd.NA
        if isinstance(v, (bool, np.bool_)):
            return bool(v)
        t = str(v).strip().lower()
        if t in ("y", "yes", "true", "t", "1"):
            return True
        if t in ("n", "no", "false", "f", "0"):
            return False
        return pd.NA
    return s.map(conv).astype("boolean")


def _ts(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def _num(v, nd: int):
    """JSON/DB-friendly rounded number; None for missing."""
    if v is None or v is pd.NA or (isinstance(v, (float, np.floating)) and np.isnan(v)):
        return None
    v = round(float(v), nd)
    return int(v) if v.is_integer() and abs(v) < 2**53 else v


def _median(s: pd.Series):
    s = s.dropna()
    return float(s.median()) if len(s) else None


def _merge_1to1(left: pd.DataFrame, right: pd.DataFrame, on: str, **kw) -> pd.DataFrame:
    """Left join to a lookup keyed by `on`; fails loudly if the lookup key is not unique (fan-out guard)."""
    out = left.merge(right, on=on, how="left", validate="many_to_one", **kw)
    assert len(out) == len(left), f"join on {on} changed row count"
    return out


# ── normalization ────────────────────────────────────────────────────────────
def normalize_jobs(src: SourceData, run_dq: dict) -> pd.DataFrame:
    wo = src.work_orders[[c for c in WORK_ORDER_COLS if c in src.work_orders.columns]].copy()
    missing_cols = sorted(set(WORK_ORDER_COLS) - set(wo.columns))
    if missing_cols:
        raise ValueError(f"work_orders missing columns: {missing_cols}")
    wo["work_order_id"] = wo["work_order_id"].astype(str).str.strip()
    dup = wo["work_order_id"][wo["work_order_id"].duplicated()]
    if len(dup):
        raise ValueError(f"duplicate work_order_id in source: {sorted(dup.unique())[:10]}")
    for c in ("contractor_id", "repair_method", "road_id", "ward_code", "work_type"):
        wo[c] = wo[c].astype("string").str.strip()
    for c in ("assigned_at", "work_started_at", "completed_at"):
        wo[c] = _ts(wo[c])
    for c in ("area_sqm", "cost_inr"):
        wo[c] = pd.to_numeric(wo[c], errors="coerce")
    for c in ("sla_met", "reopened_within_30d"):
        wo[c] = to_bool(wo[c])

    contractors = src.contractors[["contractor_id", "contractor_name"]].astype({"contractor_id": "string"})
    known = set(contractors["contractor_id"])
    unknown = wo[~wo["contractor_id"].isin(known)]
    run_dq["unknown_contractor_work_order_ids"] = sorted(unknown["work_order_id"])
    wo = wo[wo["contractor_id"].isin(known)].copy()
    wo = _merge_1to1(wo, contractors, "contractor_id")

    rc = src.rate_card[["repair_method", "unit", "standard_rate_inr"]].copy()
    rc["repair_method"] = rc["repair_method"].astype("string").str.strip()
    rc["standard_rate_inr"] = pd.to_numeric(rc["standard_rate_inr"], errors="coerce")
    wo = _merge_1to1(wo, rc, "repair_method")

    roads = src.roads[["road_id", "ward_code"]].rename(columns={"ward_code": "road_ward_code"})
    roads = roads.astype({"road_id": "string", "road_ward_code": "string"})
    wo = _merge_1to1(wo, roads, "road_id")
    wo["ward_mismatch"] = wo["road_ward_code"].notna() & (wo["road_ward_code"] != wo["ward_code"])

    # Month = calendar month of completed_at. Jobs without a completion date get no month row.
    no_done = wo["completed_at"].isna()
    run_dq["jobs_without_completed_at"] = {"count": int(no_done.sum()),
                                          "work_order_ids": sorted(wo.loc[no_done, "work_order_id"])}
    wo = wo[~no_done].copy()
    wo["month"] = wo["completed_at"].dt.to_period("M").dt.to_timestamp().dt.date
    return wo.sort_values("work_order_id").reset_index(drop=True)


def add_complaint_clock(jobs: pd.DataFrame, links: pd.DataFrame, run_dq: dict) -> pd.DataFrame:
    """Earliest linked complaint -> completed_at, in hours. One row per job (min over links)."""
    lk = links[["work_order_id", "complaint_id", "received_at"]].copy()
    lk["received_at"] = _ts(lk["received_at"])
    lk = lk.drop_duplicates(["work_order_id", "complaint_id"])
    run_dq["complaint_links_without_timestamp"] = int(lk["received_at"].isna().sum())
    first = lk.groupby("work_order_id", as_index=False).agg(
        first_complaint_at=("received_at", "min"), linked_complaints=("complaint_id", "nunique"))
    jobs = _merge_1to1(jobs, first, "work_order_id")
    jobs["linked_complaints"] = jobs["linked_complaints"].fillna(0).astype(int)
    hrs = (jobs["completed_at"] - jobs["first_complaint_at"]).dt.total_seconds() / 3600.0
    reason = np.select(
        [jobs["first_complaint_at"].isna() & (jobs["linked_complaints"] == 0),
         jobs["first_complaint_at"].isna(),
         hrs < 0],
        ["no_linked_complaint", "linked_complaint_without_timestamp", "complaint_after_completion"],
        default="")
    jobs["speed_reason"] = reason
    jobs["complaint_hours"] = hrs.where(reason == "")
    start = jobs["assigned_at"]
    proxy = (jobs["completed_at"] - start).dt.total_seconds() / 3600.0
    jobs["assigned_hours"] = proxy.where(proxy >= 0)
    return jobs


def add_speed_cohort(jobs: pd.DataFrame, m: Methodology) -> pd.DataFrame:
    """Cohort = same completion month + same repair_method, across all contractors."""
    valid = jobs[jobs["complaint_hours"].notna()]
    coh = valid.groupby(["month", "repair_method"], as_index=False).agg(
        cohort_n=("complaint_hours", "size"), cohort_median_hours=("complaint_hours", "median"))
    jobs = jobs.merge(coh, on=["month", "repair_method"], how="left", validate="many_to_one")
    usable = jobs["complaint_hours"].notna() & (jobs["cohort_n"] >= m.min_cohort) & (jobs["cohort_median_hours"] > 0)
    jobs.loc[jobs["complaint_hours"].notna() & ~usable, "speed_reason"] = "cohort_too_small"
    jobs["speed_ratio"] = (jobs["complaint_hours"] / jobs["cohort_median_hours"]).where(usable)
    return jobs


def add_cost(jobs: pd.DataFrame, m: Methodology) -> pd.DataFrame:
    per_sqm = jobs["unit"] == "per sqm"
    per_job = jobs["unit"] == "per job"
    expected = pd.Series(np.nan, index=jobs.index)
    expected[per_sqm] = jobs.loc[per_sqm, "area_sqm"] * jobs.loc[per_sqm, "standard_rate_inr"]
    expected[per_job] = jobs.loc[per_job, "standard_rate_inr"]
    reason = np.select(
        [jobs["unit"].isna() | jobs["standard_rate_inr"].isna(),
         per_sqm & ~(jobs["area_sqm"] > 0),
         jobs["cost_inr"].isna(),
         ~(expected > 0)],
        ["no_rate_card", "missing_area", "missing_cost", "non_positive_benchmark"], default="")
    jobs["cost_reason"] = reason
    ok = reason == ""
    jobs["expected_cost_inr"] = expected.where(ok)
    jobs["abs_pct_dev"] = ((jobs["cost_inr"] - expected).abs() / expected).where(ok)
    jobs["over_tol"] = ok & (jobs["cost_inr"] > expected * (1 + m.cost_tolerance))
    jobs["under_tol"] = ok & (jobs["cost_inr"] < expected * (1 - m.cost_tolerance))
    return jobs


# ── context (pre-aggregated to own grain, joined once per job) ──────────────
def add_weather_context(jobs: pd.DataFrame, src: SourceData) -> pd.DataFrame:
    start = jobs["work_started_at"].fillna(jobs["assigned_at"]).fillna(jobs["completed_at"]).dt.normalize()
    end = jobs["completed_at"].dt.normalize()
    start = start.where(start <= end, end)
    win = pd.DataFrame({"work_order_id": jobs["work_order_id"],
                        "date": [pd.date_range(s, e, freq="D") for s, e in zip(start, end)]}).explode("date")
    win["date"] = pd.to_datetime(win["date"]).dt.date

    for col in ("rain_days_known", "rain_window_max_mm", "rain_heavy_day", "tide_days_known",
                "tide_window_max_m", "tide_big_day"):
        jobs[col] = np.nan
    if src.rainfall_daily is not None and len(src.rainfall_daily):
        r = src.rainfall_daily.copy()
        r["date"] = pd.to_datetime(r["date"]).dt.date
        r["rainfall_mm"] = pd.to_numeric(r["rainfall_mm"], errors="coerce")
        r["heavy"] = r["imd_category"].isin(HEAVY_RAIN_CATEGORIES)
        daily = r.groupby("date", as_index=False).agg(max_mm=("rainfall_mm", "max"), heavy=("heavy", "any"))
        w = win.merge(daily, on="date", how="inner")
        agg = w.groupby("work_order_id", as_index=False).agg(
            rain_days_known=("date", "nunique"), rain_window_max_mm=("max_mm", "max"), rain_heavy_day=("heavy", "any"))
        jobs = _merge_1to1(jobs.drop(columns=["rain_days_known", "rain_window_max_mm", "rain_heavy_day"]), agg,
                           "work_order_id")
    if src.tides is not None and len(src.tides):
        t = src.tides.copy()
        t["date"] = pd.to_datetime(t["date"]).dt.date
        t["height_m"] = pd.to_numeric(t["height_m"], errors="coerce")
        t["big"] = to_bool(t["big_tide_flag"]).fillna(False).astype(bool)
        daily = t.groupby("date", as_index=False).agg(max_m=("height_m", "max"), big=("big", "any"))
        w = win.merge(daily, on="date", how="inner")
        agg = w.groupby("work_order_id", as_index=False).agg(
            tide_days_known=("date", "nunique"), tide_window_max_m=("max_m", "max"), tide_big_day=("big", "any"))
        jobs = _merge_1to1(jobs.drop(columns=["tide_days_known", "tide_window_max_m", "tide_big_day"]), agg,
                           "work_order_id")
    return jobs


def add_place_context(jobs: pd.DataFrame, src: SourceData) -> pd.DataFrame:
    if src.flood_hotspots is not None and len(src.flood_hotspots):
        h = src.flood_hotspots.copy()
        h["tide_sensitive"] = to_bool(h["tide_sensitive"]).fillna(False).astype(bool)
        h["flood_threshold_mm_per_day"] = pd.to_numeric(h["flood_threshold_mm_per_day"], errors="coerce")
        hw = h.groupby("ward_code", as_index=False).agg(
            ward_hotspots=("hotspot_id", "nunique"), ward_tide_sensitive=("tide_sensitive", "any"),
            ward_min_flood_threshold=("flood_threshold_mm_per_day", "min")).astype({"ward_code": "string"})
        jobs = _merge_1to1(jobs, hw, "ward_code")
        jobs["ward_hotspots"] = jobs["ward_hotspots"].fillna(0)
        jobs["ward_tide_sensitive"] = jobs["ward_tide_sensitive"].astype("boolean").fillna(False).astype(bool)
    if src.traffic is not None and len(src.traffic):
        tr = src.traffic[["road_id", "peak_hour_vehicles", "congestion_index_0_10"]].copy()
        tr["road_id"] = tr["road_id"].astype("string")
        for c in ("peak_hour_vehicles", "congestion_index_0_10"):
            tr[c] = pd.to_numeric(tr[c], errors="coerce")
        jobs = _merge_1to1(jobs, tr, "road_id")
    if src.facilities is not None and len(src.facilities):
        f = src.facilities.dropna(subset=["ambulance_entry_road"])
        fr = f.groupby("ambulance_entry_road", as_index=False).agg(road_facilities=("facility_id", "nunique"))
        fr = fr.rename(columns={"ambulance_entry_road": "road_id"}).astype({"road_id": "string"})
        jobs = _merge_1to1(jobs, fr, "road_id")
        jobs["road_facilities"] = jobs["road_facilities"].fillna(0)
    return jobs


def _context_block(g: pd.DataFrame, src: SourceData, accidents_by_road_month: Optional[pd.DataFrame],
                   facilities: Optional[pd.DataFrame], nd: int) -> dict:
    n = len(g)
    ctx: dict = {}
    if "rain_days_known" in g and g["rain_days_known"].notna().any():
        cov = g["rain_days_known"].notna()
        ctx["rainfall"] = {
            "scope": "regional daily max across stations (Santacruz, Colaba); not ward-specific",
            "window": "work_started_at (else assigned_at) to completed_at, by date",
            "jobs_covered": int(cov.sum()), "coverage": _num(cov.sum() / n, nd),
            "jobs_with_heavy_rain_day": int(g.loc[cov, "rain_heavy_day"].astype(bool).sum()),
            "share_with_heavy_rain_day": _num(g.loc[cov, "rain_heavy_day"].astype(bool).mean(), nd),
            "median_window_max_rainfall_mm": _num(_median(g["rain_window_max_mm"]), nd),
        }
    else:
        ctx["rainfall"] = None
    if "tide_days_known" in g and g["tide_days_known"].notna().any():
        cov = g["tide_days_known"].notna()
        ctx["tides"] = {
            "scope": "city tide gauge by date; not road-specific",
            "jobs_covered": int(cov.sum()), "coverage": _num(cov.sum() / n, nd),
            "jobs_with_big_tide_day": int(g.loc[cov, "tide_big_day"].astype(bool).sum()),
            "share_with_big_tide_day": _num(g.loc[cov, "tide_big_day"].astype(bool).mean(), nd),
        }
    else:
        ctx["tides"] = None
    if "ward_hotspots" in g:
        in_hot = g["ward_hotspots"] > 0
        ctx["flood_hotspots"] = {
            "scope": "jobs in wards with >= 1 flood hotspot (ward-level, not distance-based)",
            "jobs_in_hotspot_wards": int(in_hot.sum()), "share_in_hotspot_wards": _num(in_hot.mean(), nd),
            "jobs_in_tide_sensitive_hotspot_wards": int(g["ward_tide_sensitive"].sum()),
            "min_flood_threshold_mm_per_day": _num(g["ward_min_flood_threshold"].min(), nd),
        }
    else:
        ctx["flood_hotspots"] = None
    if "peak_hour_vehicles" in g:
        cov = g["peak_hour_vehicles"].notna()
        ctx["traffic"] = {
            "scope": "job-weighted mean over jobs whose road has a traffic row",
            "jobs_covered": int(cov.sum()), "coverage": _num(cov.mean(), nd),
            "mean_peak_hour_vehicles": _num(g["peak_hour_vehicles"].mean(), nd),
            "mean_congestion_index_0_10": _num(g["congestion_index_0_10"].mean(), nd),
        }
    else:
        ctx["traffic"] = None
    if accidents_by_road_month is not None:
        roads = set(g["road_id"].dropna())
        a = accidents_by_road_month[(accidents_by_road_month["month"] == g["month"].iloc[0])
                                    & accidents_by_road_month["road_id"].isin(roads)]
        ctx["accidents"] = {
            "scope": "distinct accidents on roads this contractor serviced, occurring in the same calendar month; "
                     "exposure context only, not attributed to the contractor",
            "roads_serviced": len(roads), "accidents": int(a["accident_id"].nunique()),
            "by_severity": {k: int(v) for k, v in sorted(a.groupby("severity")["accident_id"].nunique().items())},
        }
    else:
        ctx["accidents"] = None
    if facilities is not None and "road_facilities" in g:
        on_amb = g["road_facilities"] > 0
        f = facilities[facilities["ambulance_entry_road"].isin(set(g["road_id"].dropna()))]
        ctx["facility_access"] = {
            "scope": "jobs on roads listed as a hospital/school ambulance_entry_road",
            "jobs_on_ambulance_entry_roads": int(on_amb.sum()), "share_on_ambulance_entry_roads": _num(on_amb.mean(), nd),
            "distinct_facilities_by_type": {k: int(v) for k, v in sorted(f.groupby("type")["facility_id"].nunique().items())},
        }
    else:
        ctx["facility_access"] = None
    return ctx


# ── per contractor-month aggregation ─────────────────────────────────────────
def _row(g: pd.DataFrame, src, acc, fac, m: Methodology) -> dict:
    nd = m.rank_decimals
    n = len(g)
    sla_known = int(g["sla_met"].notna().sum())
    rep_known = int(g["reopened_within_30d"].notna().sum())
    speed_ok = g["speed_ratio"].notna()
    cost_ok = g["abs_pct_dev"].notna()
    cost_n = int(cost_ok.sum())

    per_method = {}
    for meth, mg in sorted(g.groupby("repair_method"), key=lambda kv: kv[0]):
        per_method[meth] = {
            "jobs": len(mg),
            "speed_sample": int(mg["speed_ratio"].notna().sum()),
            "median_complaint_to_completion_hours": _num(_median(mg["complaint_hours"]), nd),
            "cohort_median_hours": _num(_median(mg["cohort_median_hours"].where(mg["speed_ratio"].notna())), nd),
        }
    speed_reasons = g.loc[g["speed_reason"] != "", "speed_reason"].value_counts().sort_index()
    cost_reasons = g.loc[g["cost_reason"] != "", "cost_reason"].value_counts().sort_index()
    mismatch = sorted(g.loc[g["ward_mismatch"], "work_order_id"])

    return {
        "contractor_id": g["contractor_id"].iloc[0],
        "contractor_name": g["contractor_name"].iloc[0],
        "month": g["month"].iloc[0],
        "methodology_version": m.version,
        "completed_jobs": n,
        "total_billed_inr": _num(g["cost_inr"].sum(min_count=1), 2) or 0,
        "sla_known": sla_known, "sla_met": int(g["sla_met"].fillna(False).sum()), "sla_missing": n - sla_known,
        "sla_rate": _num(g["sla_met"].fillna(False).sum() / sla_known, nd) if sla_known else None,
        "reopen_known": rep_known, "reopened": int(g["reopened_within_30d"].fillna(False).sum()),
        "reopen_missing": n - rep_known,
        "reopen_rate": _num(g["reopened_within_30d"].fillna(False).sum() / rep_known, nd) if rep_known else None,
        "speed_sample": int(speed_ok.sum()), "speed_missing": n - int(speed_ok.sum()),
        "speed_raw_sample": int(g["complaint_hours"].notna().sum()),
        "speed_median_hours": _num(_median(g["complaint_hours"]), nd),
        "speed_cohort_median_hours": _num(_median(g.loc[speed_ok, "cohort_median_hours"]), nd),
        "speed_relative_index": _num(_median(g["speed_ratio"]), nd),
        "assigned_to_completed_median_hours": _num(_median(g["assigned_hours"]), nd),
        "cost_sample": cost_n, "cost_missing": n - cost_n,
        "cost_median_abs_pct_dev": _num(_median(g["abs_pct_dev"]), nd),
        "cost_over_tolerance_count": int(g["over_tol"].sum()),
        "cost_over_tolerance_share": _num(g["over_tol"].sum() / cost_n, nd) if cost_n else None,
        "cost_under_tolerance_count": int(g["under_tol"].sum()),
        "workload_mix": {
            "repair_methods": {k: int(v) for k, v in sorted(g["repair_method"].value_counts().items())},
            "work_types": {k: int(v) for k, v in sorted(g["work_type"].dropna().value_counts().items())},
            "wards": {k: int(v) for k, v in sorted(g["ward_code"].value_counts().items())},
            "speed_by_repair_method": per_method,
        },
        "context": _context_block(g, src, acc, fac, nd),
        "data_quality": {
            "speed_missing_reasons": {k: int(v) for k, v in speed_reasons.items()},
            "cost_missing_reasons": {k: int(v) for k, v in cost_reasons.items()},
            "ward_mismatch_work_order_ids": mismatch,
        },
        "evidence_work_order_ids": sorted(g["work_order_id"]),
    }


def rank_month(rows: list[dict], m: Methodology) -> None:
    """In place: separate competition ranks (1,2,2,4) per dimension among eligible contractors."""
    for dim, (rank_col, val_col, n_col, asc) in DIMENSIONS.items():
        eligible = [r for r in rows if r[n_col] >= m.min_sample and r[val_col] is not None]
        eligible_ids = {id(r) for r in eligible}
        vals = sorted(round(r[val_col], m.rank_decimals) for r in eligible)
        if not asc:
            vals = vals[::-1]
        first_pos = {}
        for i, v in enumerate(vals):
            first_pos.setdefault(v, i + 1)
        for r in rows:
            r.setdefault("rank_eligibility", {})
            r.setdefault("rank_cohort_sizes", {})
            r["rank_cohort_sizes"][dim] = len(eligible)
            if id(r) in eligible_ids:
                r[rank_col] = first_pos[round(r[val_col], m.rank_decimals)]
                r["rank_eligibility"][dim] = {"eligible": True, "sample": r[n_col], "min_sample": m.min_sample,
                                              "reason": None}
            else:
                reason = ("no known values" if r[n_col] == 0 else
                          f"sample {r[n_col]} < min {m.min_sample}" if r[n_col] < m.min_sample else
                          "metric undefined")
                r[rank_col] = None
                r["rank_eligibility"][dim] = {"eligible": False, "sample": r[n_col], "min_sample": m.min_sample,
                                              "reason": reason}


def process(src: SourceData, m: Methodology, computed_at: Optional[datetime] = None) -> ProcessResult:
    computed_at = computed_at or datetime.now(timezone.utc).replace(microsecond=0)
    run_dq: dict = {}
    jobs = normalize_jobs(src, run_dq)
    jobs = add_complaint_clock(jobs, src.complaint_links, run_dq)
    jobs = add_speed_cohort(jobs, m)
    jobs = add_cost(jobs, m)
    jobs = add_weather_context(jobs, src)
    jobs = add_place_context(jobs, src)

    acc = None
    if src.accidents is not None and len(src.accidents):
        acc = src.accidents[["accident_id", "road_id", "occurred_at", "severity"]].copy()
        acc["month"] = _ts(acc["occurred_at"]).dt.to_period("M").dt.to_timestamp().dt.date
        acc = acc.drop_duplicates("accident_id")
    fac = None
    if src.facilities is not None and len(src.facilities):
        fac = src.facilities[["facility_id", "type", "ambulance_entry_road"]].drop_duplicates("facility_id")

    rows: list[dict] = []
    for month, mg in jobs.groupby("month", sort=True):
        month_rows = [_row(g, src, acc, fac, m) for _, g in mg.groupby("contractor_id", sort=True)]
        rank_month(month_rows, m)
        rows.extend(month_rows)
    for r in rows:
        r["computed_at"] = computed_at

    missing_ctx = [t for t in CONTEXT_TABLES if getattr(src, t) is None or not len(getattr(src, t))]
    run_dq.update({
        "ward_mismatch_count": int(jobs["ward_mismatch"].sum()),
        "context_tables_missing": missing_ctx,
        "ward_mismatch_rule": "work_orders.ward_code is used for ward mix; mismatches vs roads.ward_code are listed",
    })
    run = {
        "methodology_version": m.version,
        "computed_at": computed_at,
        "params": m.params(),
        "source_counts": {
            "work_orders": int(len(src.work_orders)), "jobs_scored": int(len(jobs)),
            "contractors": int(len(src.contractors)), "complaint_links": int(len(src.complaint_links)),
            **{t: (None if getattr(src, t) is None else int(len(getattr(src, t)))) for t in CONTEXT_TABLES},
        },
        "data_quality": run_dq,
    }
    notes = [f"context table missing or empty: {t}" for t in missing_ctx]
    return ProcessResult(rows=rows, run=run, notes=notes)
