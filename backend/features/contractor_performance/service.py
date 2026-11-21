"""Orchestration: refresh (load -> process -> persist) and read/shape for the API.
GET requests only read stored rows; nothing is recomputed per request."""
from __future__ import annotations

from datetime import date
from typing import Optional

from .config import METHODOLOGIES, get_methodology
from .processor import DIMENSIONS, ProcessResult, process
from .repository import ScorecardStore, SourceRepository


class NotFound(LookupError):
    pass


def parse_month(s: Optional[str]) -> Optional[date]:
    """'YYYY-MM' -> first day of month. Format is validated by the router's regex."""
    return None if s is None else date(int(s[:4]), int(s[5:7]), 1)


def month_str(d) -> str:
    return d.strftime("%Y-%m") if hasattr(d, "strftime") else str(d)[:7]


def shape_row(r: dict) -> dict:
    """Flat stored row -> nested API row."""
    sizes = r.get("rank_cohort_sizes") or {}
    return {
        "contractor_id": r["contractor_id"],
        "contractor_name": r.get("contractor_name"),
        "month": month_str(r["month"]),
        "methodology_version": r["methodology_version"],
        "computed_at": r["computed_at"],
        "completed_jobs": r["completed_jobs"],
        "total_billed_inr": r["total_billed_inr"],
        "speed": {
            "relative_index": r["speed_relative_index"],
            "median_complaint_to_completion_hours": r["speed_median_hours"],
            "cohort_median_hours": r["speed_cohort_median_hours"],
            "sample_count": r["speed_sample"], "raw_sample_count": r["speed_raw_sample"],
            "missing_count": r["speed_missing"],
            "assigned_to_completed_median_hours_proxy": r["assigned_to_completed_median_hours"],
            "rank": r["speed_rank"], "cohort_size": sizes.get("speed", 0),
        },
        "sla": {"count": r["sla_met"], "known": r["sla_known"], "missing": r["sla_missing"],
                "rate": r["sla_rate"], "rank": r["sla_rank"], "cohort_size": sizes.get("sla", 0)},
        "durability": {"count": r["reopened"], "known": r["reopen_known"], "missing": r["reopen_missing"],
                       "rate": r["reopen_rate"], "rank": r["durability_rank"],
                       "cohort_size": sizes.get("durability", 0)},
        "cost_alignment": {
            "median_abs_pct_deviation": r["cost_median_abs_pct_dev"], "sample_count": r["cost_sample"],
            "missing_count": r["cost_missing"], "over_tolerance_count": r["cost_over_tolerance_count"],
            "over_tolerance_share": r["cost_over_tolerance_share"],
            "under_tolerance_count": r["cost_under_tolerance_count"],
            "rank": r["cost_rank"], "cohort_size": sizes.get("cost_alignment", 0),
        },
        "rank_eligibility": r.get("rank_eligibility") or {},
        "workload_mix": r.get("workload_mix") or {},
        "context": r.get("context") or {},
        "data_quality": r.get("data_quality") or {},
        "evidence_work_order_ids": list(r.get("evidence_work_order_ids") or []),
    }


def sort_key(sort_by: str):
    """Null ranks last; ties and nulls broken by contractor_id. completed_jobs sorts descending."""
    if sort_by == "contractor_id":
        return lambda r: r["contractor_id"]
    if sort_by == "completed_jobs":
        return lambda r: (-r["completed_jobs"], r["contractor_id"])
    return lambda r: (r[sort_by] is None, r[sort_by] or 0, r["contractor_id"])


class ScorecardService:
    def __init__(self, store: ScorecardStore, source: Optional[SourceRepository] = None):
        self.store = store
        self.source = source

    # refresh path (CLI)
    def refresh(self, version: str, dry_run: bool = False) -> ProcessResult:
        if self.source is None:
            raise RuntimeError("refresh needs a source repository")
        result = process(self.source.load_sources(), get_methodology(version))
        if not dry_run:
            self.store.write(result)
        return result

    # read path (API)
    def _run(self, version: str) -> dict:
        run = self.store.read_run(version)
        if run is None:
            raise NotFound(f"no scorecards stored for methodology_version {version!r}; run the refresh CLI")
        return run

    def monthly(self, version: str, month_from: Optional[str], month_to: Optional[str],
                min_jobs: int, sort_by: str) -> dict:
        run = self._run(version)
        stored = self.store.read_rows(version, parse_month(month_from), parse_month(month_to))
        by_month: dict[str, list] = {}
        for r in stored:
            if r["completed_jobs"] >= min_jobs:
                by_month.setdefault(month_str(r["month"]), []).append(r)
        months = [{"month": mth, "contractors": [shape_row(r) for r in sorted(rs, key=sort_key(sort_by))]}
                  for mth, rs in sorted(by_month.items())]
        return {"methodology_version": version, "sort_by": sort_by, "run": run, "months": months}

    def contractor(self, contractor_id: str, version: str, month_from: Optional[str], month_to: Optional[str]) -> dict:
        if not self.store.contractor_exists(contractor_id):
            raise NotFound(f"unknown contractor {contractor_id}")
        run = self._run(version)
        stored = self.store.read_rows(version, parse_month(month_from), parse_month(month_to), contractor_id)
        rows = [shape_row(r) for r in stored]
        name = rows[0]["contractor_name"] if rows else None
        return {"contractor_id": contractor_id, "contractor_name": name, "methodology_version": version,
                "run": run, "months": rows}


def methodology_doc(version: str) -> dict:
    m = get_methodology(version)
    return {
        "methodology_version": m.version,
        "known_versions": sorted(METHODOLOGIES),
        "params": m.params(),
        "grain": "one row per contractor_id x calendar month of work_orders.completed_at x methodology_version",
        "month_rule": "A job belongs to the month of completed_at. Jobs without completed_at get no month row and are "
                      "counted in run.data_quality.jobs_without_completed_at.",
        "dimensions": [
            {"key": "speed", "rank_field": "speed_rank",
             "metric": "median over jobs of (earliest linked complaints.received_at -> completed_at hours) / "
                       "(median of that quantity for the same completion month and repair_method, all contractors)",
             "direction": "lower is better",
             "sample": f"jobs with a linked complaint timestamp <= completed_at and a cohort of >= {m.min_cohort} jobs",
             "source": "complaint_work_orders, complaints.received_at, work_orders.completed_at, work_orders.repair_method"},
            {"key": "sla", "rank_field": "sla_rank", "metric": "sla_met = true / jobs with known sla_met",
             "direction": "higher is better", "sample": "jobs with non-null sla_met",
             "source": "work_orders.sla_met (recorded value, not recomputed)"},
            {"key": "durability", "rank_field": "durability_rank",
             "metric": "reopened_within_30d = true / jobs with known reopened_within_30d",
             "direction": "lower is better", "sample": "jobs with non-null reopened_within_30d",
             "source": "work_orders.reopened_within_30d (recorded value)"},
            {"key": "cost_alignment", "rank_field": "cost_rank",
             "metric": "median |cost_inr - benchmark| / benchmark, benchmark = area_sqm x standard_rate_inr (per sqm) "
                       "or standard_rate_inr (per job)",
             "direction": "lower is better",
             "sample": "jobs with a rate-card match, positive benchmark (and area for per-sqm methods)",
             "source": "work_orders.cost_inr, area_sqm, rate_card"},
        ],
        "ranking": {
            "scope": "each dimension ranked separately within one month and methodology_version; no composite score",
            "eligibility": f"a contractor-month is ranked on a dimension only if that dimension's sample >= {m.min_sample}; "
                           "otherwise rank is null with a reason. Eligibility is per dimension.",
            "ties": f"values rounded to {m.rank_decimals} decimals; equal values share the best rank (1, 2, 2, 4); "
                    "display order then by contractor_id",
            "cohort_size": "number of contractors eligible for that rank in that month",
            "min_jobs_param": "the API min_jobs filter only hides rows; it never changes stored ranks",
            "tolerance": f"+/-{int(m.cost_tolerance * 100)}% around the benchmark is ordinary variation (rate card notes "
                         "20-30%); jobs above it are counted as over_tolerance, jobs below as under_tolerance (descriptive)",
        },
        "context": "Rain, tides, flood-hotspot wards, traffic, accidents and ambulance-entry roads are shown as descriptive "
                   "exposure context next to the raw ranks. Ranks are NOT context-adjusted in this version, and context "
                   "is not evidence of contractor fault. See GET /api/v3/contractors for the context-adjusted season view.",
        "limitations": [
            "Synthetic dataset; all contractors are fictional.",
            "Rainfall is regional (Santacruz/Colaba daily max) and tides are city-level; neither is ward- or road-specific.",
            "Flood-hotspot exposure is ward-level, not distance-based.",
            "Jobs without a linked complaint have no complaint clock and are excluded from speed.",
            "Small monthly samples are left unranked rather than ranked with high uncertainty.",
            "Labels are neutral: ranks describe recorded outcomes and need explanation, not accusation.",
        ],
    }


__all__ = ["ScorecardService", "NotFound", "methodology_doc", "DIMENSIONS"]
