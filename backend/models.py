"""Response models: the typed contract in /openapi.json (for generated clients).

Field names/types mirror the SQL views and v3_* tables. When you change a view or table,
change the model here too. Run the API with STRICT_MODELS=1 (as the Postman run does) to make any
undeclared or mistyped field a 500 instead of being silently dropped.
"""
import os
from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid" if os.environ.get("STRICT_MODELS") else "ignore")


StatusLabel = Literal["Needs Explanation", "Recoverable under DLP"]
Detector = Literal["DLP_PAID_TWICE", "RATE_INFLATION", "OVERLAPPING_WORK_ORDER", "RAIN_DAY_WORK"]
AuthorRole = Literal["ward_engineer", "contractor", "other"]
ReportKind = Literal["still_broken", "verified_fixed", "new_issue"]
InputMode = Literal["text", "voice", "photo", "qr"]
Language = Literal["en", "hi", "mr"]
TrackerStatus = Literal["reported", "matched_to_contract", "payment_held", "contractor_notified"]
Verdict = Literal["better than expected", "within the normal range", "worse than expected"]
Bucket = Literal["A_OWED_BY_CONTRACTOR_DLP", "B_NEXT_RUPEE"]
ReasonCode = Literal["FLOOD_SPOT", "AMBULANCE_ROUTE", "SCHOOL_ZONE", "HIGH_TRAFFIC", "ACCIDENT_PRONE",
                     "REPEAT_FAILURE", "OPEN_COMPLAINTS", "UNDER_DLP", "UNDER_REPORTED_WARD"]


# ── Meta ────────────────────────────────────────────────────────────────────
class Health(Out):
    work_orders: int
    flags: int
    v3_items: int


# ── View 1 ──────────────────────────────────────────────────────────────────
class CityKPIs(Out):
    total_budget_inr: int
    total_spend_inr: int
    recoverable_dlp_inr: int  # already paid for DLP-covered repairs
    flagged_bills_count: int
    flags_by_detector: dict[str, int]


class Ward(Out):
    ward_code: str
    ward_name: str
    zone: Optional[str]
    centroid_lat: float
    centroid_lon: float
    budget_inr: int
    spend_inr: int
    recoverable_dlp_inr: int
    flagged_bills_count: int
    warranty_enforcement_rate: Optional[float]  # null when the ward has no DLP-eligible jobs
    dlp_eligible_jobs: int
    dlp_leakage_rate: float  # recoverable / spend; colour the map by this
    physical_risk_score: float
    complaints_per_lakh: float
    under_reported_flag: bool
    flood_hotspots_count: int
    accidents_count: int


class FlaggedBill(Out):
    work_order_id: str
    road_id: str
    road_name: str
    ward_code: str
    contractor_id: str
    contractor_name: str
    repair_method: str
    cost_inr: float
    completed_at: Optional[datetime]
    top_tier: int
    rupees_at_stake: int  # max over the bill's flags (never double-counted)
    status_label: StatusLabel
    flag_ids: list[str]
    detectors: list[Detector]
    replies_count: int


# ── View 2 ──────────────────────────────────────────────────────────────────
class Reply(Out):
    id: int
    flag_id: str
    author_role: AuthorRole
    author_name: Optional[str]
    body: str
    created_at: datetime


class FlagWithReplies(Out):
    flag_id: str  # <DETECTOR>:<work_order_id>
    tier: int
    detector: Detector
    status_label: StatusLabel
    ward_code: str
    road_id: str
    work_order_id: str
    contractor_id: str
    rupees_at_stake: int
    evidence_row_ids: list[str]
    rule_text: str
    replies: list[Reply]


class RoadSummary(Out):
    road_id: str
    road_name: str
    ward_code: str
    road_type: Optional[str]
    surface: Optional[str]
    under_dlp: bool
    last_resurfaced: Optional[date]
    total_billed_inr: float
    work_orders_count: int
    rupees_at_stake: float
    flagged_bills_count: int


class RoadWorkOrder(Out):
    work_order_id: str
    contractor_id: str
    contractor_name: str
    work_type: Optional[str]
    repair_method: str
    cost_inr: float
    assigned_at: Optional[datetime]
    completed_at: Optional[datetime]
    sla_met: Optional[bool]
    reopened_within_30d: Optional[bool]
    engineer_remark: Optional[str]


class RoadReceipt(RoadSummary):
    work_orders: list[RoadWorkOrder]
    flags: list[FlagWithReplies]


class TimelineEvent(Out):
    road_id: str
    event_at: datetime
    event_type: Literal["complaint", "work_order_assigned", "work_order_completed", "accident", "citizen_report"]
    ref_id: str  # complaint_id / work_order_id / accident_id / citizen report id
    detail: dict[str, Any]  # keys depend on event_type (see road_timeline view)


# ── View 3 ──────────────────────────────────────────────────────────────────
class ContractorContext(Out):
    avg_rain_next7_mm: float
    city_avg_rain_next7_mm: float
    avg_big_tides_next7: float
    avg_low_lying_index: float
    flood_prone_share: float
    avg_peak_vehicles: int


class Driver(Out):
    feature: str
    plain: str
    direction: str
    effect_logodds: float


class ContractorScore(Out):
    contractor_id: str
    contractor_name: str
    jobs_count: int
    total_billed_inr: int
    reopen_rate_30d: float
    expected_reopen_rate_30d: float
    sla_met_rate: float
    expected_sla_met_rate: float
    durability_index: float  # 0-100, 50 = as expected for conditions
    durability_verdict: Verdict
    durability_ratio_obs_over_exp: Optional[float]
    durability_ratio_ci90: list[float]
    speed_index: float
    speed_verdict: Verdict
    risk_adjusted_score: float  # 60% durability + 40% speed
    cost_vs_rate_median: Optional[float]
    jobs_over_130pct_rate: Optional[int]
    method_mix_top3: dict[str, float]
    context: ContractorContext
    drivers: list[Driver]
    evidence_reopened_wo_ids: list[str]
    explanation: Optional[str]


class WardAllocation(Out):
    ward_code: str
    ward_name: Optional[str]
    budget_2025_inr: int
    spend_2025_inr: int
    remaining_2025_inr: int
    recommended_budget_inr: int
    equity_floor_inr: int
    harm_avoided: float
    harm_avoided_per_next_lakh: float
    dlp_items_owed_by_contractor: int
    dlp_value_owed_inr: int  # future surface fixes owed (rate card), not CityKPIs.recoverable_dlp_inr


class ItemInputs(Out):
    repairs_this_season: int
    open_complaints_attached: int
    severity: float
    impact: float
    spent_2025_inr: int
    reopens_2025: int


class NextRupeeItem(Out):
    item_id: str  # <road_id>|<issue>
    road_id: str
    road_name: Optional[str]
    ward_code: str
    issue: str
    under_dlp: bool
    bucket: Bucket
    funded: bool
    recommended_method: Optional[str]
    method_reopen_rate: Optional[float]
    estimated_repair_cost_inr: Optional[int]
    cost_to_bmc_inr: Optional[int]
    harm_avoided: Optional[float]
    harm_per_lakh: Optional[float]
    priority_score: Optional[float]
    reason_codes: list[ReasonCode]
    inputs: ItemInputs
    evidence_wo_ids: list[str]
    explanation: Optional[str]


class FundedItem(Out):
    item_id: str
    method: str
    cost: float
    benefit: float
    road_name: Optional[str] = None
    issue: Optional[str] = None
    reason_codes: list[ReasonCode] = []
    evidence_wo_ids: list[str] = []


class BucketAItem(Out):
    item_id: str
    road_name: Optional[str]
    issue: str
    estimated_repair_cost_inr: Optional[int]
    explanation: Optional[str]


class Allocation(Out):
    ward_code: str
    budget_inr: float
    spend_inr: int
    harm_avoided: float
    funded: list[FundedItem]
    bucket_a_dlp: list[BucketAItem]


# ── View 4 ──────────────────────────────────────────────────────────────────
class Lookup(Out):
    matched_via: Literal["road_name", "locality"]
    matched_text: str
    matched_locality: Optional[str]
    ward_code: str
    matched_road_id: str
    road_distance_m: int
    warranty_status: Literal["UNDER_DLP", "OUT_OF_DLP"]
    road: RoadSummary


class TrackerStep(Out):
    step: TrackerStatus
    done: bool


class CitizenReport(Out):
    id: int
    kind: ReportKind
    input_mode: InputMode
    text: Optional[str]
    language: Optional[Language]
    photo_url: Optional[str]
    matched_locality: Optional[str]
    road_id: Optional[str]
    work_order_id: Optional[str]
    flag_id: Optional[str]
    status: TrackerStatus
    status_updated_at: datetime
    created_at: datetime
    tracker: list[TrackerStep]


class Error(Out):
    detail: str
