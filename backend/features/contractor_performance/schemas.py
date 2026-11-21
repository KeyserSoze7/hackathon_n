"""Typed response contract for /api/v3/contractor-performance (shows up in /openapi.json).
Reuses `Out` from backend/models.py, so STRICT_MODELS=1 makes undeclared fields fail loudly."""
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import Field

from backend.schemas import Out

SortBy = Literal["speed_rank", "sla_rank", "durability_rank", "cost_rank", "completed_jobs", "contractor_id"]
Dimension = Literal["speed", "sla", "durability", "cost_alignment"]


class Eligibility(Out):
    eligible: bool
    sample: int
    min_sample: int
    reason: Optional[str] = Field(None, description="Why rank is null, e.g. 'sample 3 < min 5'")


class SpeedMetric(Out):
    relative_index: Optional[float] = Field(None, description="Ranked value: median of job hours / same-month same-repair-method city median. 1.0 = typical, lower = faster")
    median_complaint_to_completion_hours: Optional[float] = Field(None, description="Raw median, earliest linked complaint -> completed_at")
    cohort_median_hours: Optional[float] = Field(None, description="Median of the matched cohort medians for this contractor's jobs (peer value)")
    sample_count: int = Field(description="Jobs in the normalized (ranked) sample")
    raw_sample_count: int = Field(description="Jobs with a valid complaint -> completion time")
    missing_count: int
    assigned_to_completed_median_hours_proxy: Optional[float] = Field(None, description="Proxy only (assigned_at -> completed_at); not ranked")
    rank: Optional[int] = None
    cohort_size: int = Field(description="Contractors eligible for this rank in this month")


class RateMetric(Out):
    count: int = Field(description="sla: jobs with sla_met = true; durability: jobs reopened within 30 days")
    known: int
    missing: int
    rate: Optional[float] = None
    rank: Optional[int] = None
    cohort_size: int


class CostMetric(Out):
    median_abs_pct_deviation: Optional[float] = Field(None, description="Median |cost - rate-card benchmark| / benchmark. 0.25 = 25%")
    sample_count: int
    missing_count: int
    over_tolerance_count: int
    over_tolerance_share: Optional[float] = None
    under_tolerance_count: int = Field(description="Descriptive only; cheap jobs are not rewarded")
    rank: Optional[int] = None
    cohort_size: int


class ContractorMonth(Out):
    contractor_id: str
    contractor_name: Optional[str]
    month: str = Field(description="YYYY-MM (calendar month of completed_at)", examples=["2025-07"])
    methodology_version: str
    computed_at: datetime
    completed_jobs: int
    total_billed_inr: float
    speed: SpeedMetric
    sla: RateMetric
    durability: RateMetric
    cost_alignment: CostMetric
    rank_eligibility: dict[str, Eligibility]
    workload_mix: dict[str, Any]
    context: dict[str, Any] = Field(description="Descriptive exposure context; never evidence of contractor fault")
    data_quality: dict[str, Any]
    evidence_work_order_ids: list[str]


class RunInfo(Out):
    methodology_version: str
    computed_at: datetime
    params: dict[str, Any]
    source_counts: dict[str, Any]
    data_quality: dict[str, Any]


class MonthBlock(Out):
    month: str
    contractors: list[ContractorMonth]


class MonthlyResponse(Out):
    methodology_version: str
    sort_by: SortBy
    run: RunInfo
    months: list[MonthBlock]


class ContractorSeries(Out):
    contractor_id: str
    contractor_name: Optional[str]
    methodology_version: str
    run: RunInfo
    months: list[ContractorMonth]


class DimensionDef(Out):
    key: Dimension
    rank_field: str
    metric: str
    direction: Literal["lower is better", "higher is better"]
    sample: str
    source: str


class MethodologyDoc(Out):
    methodology_version: str
    known_versions: list[str]
    params: dict[str, Any]
    grain: str
    month_rule: str
    dimensions: list[DimensionDef]
    ranking: dict[str, str]
    context: str
    limitations: list[str]
