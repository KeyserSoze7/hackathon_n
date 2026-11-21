"""Request and response models: the typed contract in /openapi.json (for generated clients).

Field names/types mirror the SQL views and v3_* tables. When you change a view or table,
change the model here too. Run the API with STRICT_MODELS=1 (as the Postman run does) to make any
undeclared or mistyped field a 500 instead of being silently dropped.
"""
import json
import os
import pathlib
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, WithJsonSchema, model_validator

IST = timezone(timedelta(hours=5, minutes=30))
# Real responses captured from the API, shown as examples in /openapi.json (POST endpoints).
_EXAMPLES = json.loads((pathlib.Path(__file__).parent / "response_examples.json").read_text(encoding="utf-8"))


def _example(name):
    return ConfigDict(json_schema_extra={"examples": [_EXAMPLES[name]]})


def _to_ist(d: datetime) -> str:
    """One timestamp format everywhere: ISO 8601 in IST with offset. Naive values are IST (dataset convention)."""
    return (d if d.tzinfo else d.replace(tzinfo=IST)).astimezone(IST).isoformat(timespec="seconds")


ISTDateTime = Annotated[datetime, PlainSerializer(_to_ist, return_type=str),
                        WithJsonSchema({"type": "string", "format": "date-time", "example": "2025-06-22T02:59:00+05:30"})]


class Out(BaseModel):
    model_config = ConfigDict(extra="forbid" if os.environ.get("STRICT_MODELS") else "ignore")


StatusLabel = Literal["Needs Explanation", "Recoverable under DLP"]
Detector = Literal["DLP_PAID_TWICE", "RATE_INFLATION", "OVERLAPPING_WORK_ORDER", "RAIN_DAY_WORK",
                   "REPEAT_BILL_NO_COMPLAINT"]
AuthorRole = Literal["ward_engineer", "contractor", "other"]
ReportKind = Literal["still_broken", "verified_fixed", "new_issue"]
InputMode = Literal["text", "voice", "photo", "qr"]
Language = Literal["en", "hi", "mr"]
# Report lifecycle (backend/report_lifecycle.py). TrackerStatus is kept as an alias for older clients.
ReportStatus = Literal["reported", "matched_to_contract", "payment_held", "contractor_notified",
                       "resolved", "confirmed_fixed", "reopened", "rejected", "duplicate"]
TrackerStatus = ReportStatus
TrackerStep = Literal["reported", "matched_to_contract", "payment_held", "contractor_notified",
                      "resolved", "confirmed_fixed"]
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
    rupees_at_stake_total: int  # every flagged bill once (flagged_queue grain)
    wards_over_budget: int
    under_reported_wards: list[str]
    work_orders_count: int
    complaints_count: int
    reopened_within_30d_count: int  # failed-repairs tile
    sla_met_rate: float
    dlp_road_spend_inr: int  # everything paid on DLP roads; recoverable_dlp_inr is the surface-repair part
    recoverable_dlp_rule: str  # one sentence: why recoverable < dlp_road_spend


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
    cost_inr: int  # whole rupees
    completed_at: Optional[ISTDateTime]
    top_tier: int
    rupees_at_stake: int  # max over the bill's flags (never double-counted)
    status_label: StatusLabel
    flag_ids: list[str]
    detectors: list[Detector]
    replies_count: int


# ── View 2 ──────────────────────────────────────────────────────────────────
class Reply(Out):
    model_config = _example("Reply")
    id: int
    flag_id: str
    author_role: AuthorRole
    author_name: Optional[str]
    body: str
    created_at: ISTDateTime


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
    total_billed_inr: int  # whole rupees
    work_orders_count: int
    rupees_at_stake: int  # whole rupees
    flagged_bills_count: int
    segment_no: Optional[int] = None
    length_m: Optional[float] = None
    dlp_months: Optional[int] = Field(None, description="DLP length. Assumed 36 months (dataset has no expiry); null when not under DLP")
    dlp_expires_on: Optional[date] = Field(None, description="Estimate: last_resurfaced + dlp_months; null when not under DLP")


class RoadListItem(Out):
    road_id: str
    road_name: str
    segment_no: Optional[int]
    ward_code: str
    under_dlp: bool
    total_billed_inr: int  # whole rupees
    rupees_at_stake: int  # whole rupees
    flagged_bills_count: int


class RoadWorkOrder(Out):
    work_order_id: str
    contractor_id: str
    contractor_name: str
    work_type: Optional[str]
    repair_method: str
    cost_inr: int  # whole rupees
    assigned_at: Optional[ISTDateTime]
    completed_at: Optional[ISTDateTime]
    sla_met: Optional[bool]
    reopened_within_30d: Optional[bool]
    engineer_remark: Optional[str]
    under_dlp_at_billing: bool  # road was under DLP when this job was completed (completed_at <= dlp_expires_on)


class RoadReceipt(RoadSummary):
    work_orders: list[RoadWorkOrder]
    flags: list[FlagWithReplies]
    dlp_rule: str  # one line: how dlp_months / dlp_expires_on are derived


class RoadReport(Out):
    model_config = _example("RoadReport")
    report_id: int
    kind: ReportKind
    issue_type: Optional[str]
    created_at: ISTDateTime
    status: TrackerStatus
    photo_url: Optional[str]  # first photo, if any


class TimelineEvent(Out):
    road_id: str
    event_at: ISTDateTime
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
    ward_code: Optional[str] = None  # which ward the item is in (needed for ward_code=ALL allocations)
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
    model_config = _example("Allocation")
    ward_code: str
    budget_inr: float
    spend_inr: int
    harm_avoided: float
    funded: list[FundedItem]
    bucket_a_dlp: list[BucketAItem]


class BudgetRange(Out):
    ward_code: str  # ward code or "ALL"
    min_inr: int
    max_inr: int  # rate-card cost to fix every BMC-paid (bucket B) item
    default_inr: int
    step_inr: int
    remaining_2025_inr: int
    default_basis: Literal["remaining_2025", "optimizer_recommendation", "share_of_need"]


# ── View 2: Claude-written documents ────────────────────────────────────────
class DraftNotice(Out):
    model_config = _example("DraftNotice")
    title: str
    body: str
    cited_row_ids: list[str]  # computed from the flag's evidence, never by the model
    flag_id: str
    road_id: str
    language: Language
    doc_type: Literal["defect_notice", "rti"]
    generated_by: Literal["claude", "template"]  # "template" when Claude is slow, failing or not configured


# ── View 4 ──────────────────────────────────────────────────────────────────
class Locality(Out):
    locality: str
    ward_code: str
    lat: float
    lon: float
    aliases: list[str]


class LatestWorkOrder(Out):
    work_order_id: str
    contractor_id: str
    contractor_name: str
    cost_inr: int  # whole rupees
    completed_at: Optional[ISTDateTime]
    sla_met: Optional[bool]
    reopened_within_30d: Optional[bool]


class RoadCandidate(Out):
    road_id: str
    road_name: str
    ward_code: str
    under_dlp: bool
    road_distance_m: int
    latest_work_order: Optional[LatestWorkOrder]


class Lookup(Out):
    matched_via: Literal["road_name", "locality"]
    matched_text: str
    matched_locality: Optional[str]  # always set when a locality can be resolved (also for road-name matches)
    ward_code: str
    matched_road_id: str
    road_distance_m: int
    warranty_status: Literal["UNDER_DLP", "OUT_OF_DLP"]
    road: RoadSummary
    language: Optional[Language] = None
    candidates: list[RoadCandidate] = []  # nearest 3 roads to the matched point, each with its latest work order


class Livability(Out):
    locality: str
    ward_code: str
    lat: float
    lon: float
    radius_m: int
    flood_hotspots_1500m: int
    failure_rate_30d_1500m: Optional[float]  # share of repair jobs within 1.5 km that failed within 30 days
    jobs_1500m: int
    hospital_access_roads_1500m: int  # roads within 1.5 km that are a hospital's ambulance entry road
    ward_dlp_leakage_rate: Optional[float]
    nearby_road_ids: list[str]  # nearest first


class CitizenQueryReply(Out):
    model_config = _example("CitizenQueryReply")
    matched_locality: Optional[str]
    matched_road_id: Optional[str]
    plain_language_reply: str
    warranty_status: Optional[Literal["UNDER_DLP", "OUT_OF_DLP"]]
    mode: Literal["street_check", "move_in"]
    language: Language
    generated_by: Literal["claude", "template"]
    lookup: Optional[Lookup] = None
    livability: Optional[Livability] = None


class TrackerStepDetail(Out):
    step: TrackerStep
    label: str
    status: Literal["done", "current", "pending", "skipped", "stopped"]  # skipped: no DLP hold; stopped: rejected/duplicate
    at: Optional[ISTDateTime]


EventType = Literal["created", "status_change", "note", "confirm", "duplicate", "contractor_notified"]


class ReportEvent(Out):
    at: ISTDateTime
    event_type: EventType
    actor: Literal["citizen", "ward_office", "system"]  # never an officer's name or email
    from_status: Optional[ReportStatus]
    to_status: Optional[ReportStatus]
    note: Optional[str]
    photo_ids: list[str]
    status: Optional[ReportStatus]  # = to_status (frontend Tracker reads `status`)
    by_role: Literal["citizen", "ward_office", "system"]  # = actor


IssueType = Literal["pothole", "waterlogging", "open_manhole", "broken_paver", "cave_in", "choked_drain", "other"]
LocationSource = Literal["gps", "map_pin", "exif", "landmark", "manual"]


class PhotoUpload(Out):
    model_config = _example("PhotoUpload")
    photo_id: str
    photo_url: str
    width: Optional[int]
    height: Optional[int]
    taken_at: Optional[ISTDateTime]  # EXIF DateTimeOriginal
    exif_lat: Optional[float]
    exif_lon: Optional[float]


class ReportLocation(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: Optional[float] = Field(None, ge=0)
    source: LocationSource = "gps"


class ReportRoad(Out):
    road_id: str
    road_name: str
    ward_code: str
    under_dlp: bool


class Responsible(Out):
    party: Literal["contractor_under_dlp", "bmc_ward"]
    name: Optional[str]  # contractor who last billed this issue on the road (DLP case), or the ward office
    ward_office: Optional[str]
    basis: str  # one line: why this party is responsible


class ReportPhoto(Out):
    photo_id: str
    photo_url: str
    width: Optional[int]
    height: Optional[int]


class CitizenReport(Out):
    model_config = _example("CitizenReport")
    report_id: int
    kind: ReportKind
    issue_type: Optional[IssueType]
    status: TrackerStatus
    road: Optional[ReportRoad]
    duplicate_of: Optional[int]  # earlier open report for the same road + issue in the last 7 days
    linked_work_order_id: Optional[str]  # latest work order for this road + issue
    responsible: Optional[Responsible]
    sla_hours: Optional[int]  # typical SLA for this issue type (median of matching work orders)
    photos: list[ReportPhoto]
    tracker: list[TrackerStepDetail]
    flag_id: Optional[str]
    landmark: Optional[str]
    location: Optional[ReportLocation]
    input_mode: InputMode
    language: Optional[Language]
    text: Optional[str]
    matched_locality: Optional[str]
    created_at: ISTDateTime
    events: list[ReportEvent]  # history, oldest first
    sla_due_at: Optional[ISTDateTime]  # repair_due_at if an officer set one, else created_at + sla_hours
    repair_due_at: Optional[ISTDateTime]
    resolved_at: Optional[ISTDateTime]
    rejection_reason: Optional[str]
    payment_hold_eligible: bool  # DLP surface defect: an officer may move it to payment_held


class Error(Out):
    detail: str


# ── View 1 map ──────────────────────────────────────────────────────────────
class WardFeature(Out):
    type: Literal["Feature"]
    properties: Ward
    geometry: Optional[dict[str, Any]]  # GeoJSON Polygon from data/wards.geojson


class WardMap(Out):
    type: Literal["FeatureCollection"]
    features: list[WardFeature]


# ── View 3 summary ──────────────────────────────────────────────────────────
class V3Summary(Out):
    scorecard: dict[str, Any]   # model quality (out-of-fold AUCs, prior)
    allocation: dict[str, Any]  # budget curve + optimizer vs simple-rule comparison
    updated_at: ISTDateTime


NOT_FOUND = {404: {"model": Error}}  # shared `responses=` for routes that can 404
AUTH = {401: {"model": Error, "description": "Missing, invalid or expired bearer token"},
        403: {"model": Error, "description": "Signed in, but not allowed (role or ward)"}}
CONFLICT = {409: {"model": Error, "description": "Conflicts with the current state"}}


# ── Request bodies ──────────────────────────────────────────────────────────
class AllocateReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"ward_code": "K/W", "budget_inr": 500000}]}}
    ward_code: str
    budget_inr: float = Field(ge=0, le=5e8)


class ReplyReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"author_role": "ward_engineer", "author_name": "AE Roads K/W",
                                                         "body": "MGL utility trench reopened this stretch; contractor liable under DLP."}]}}
    author_role: Literal["ward_engineer", "contractor", "other"]
    author_name: Optional[str] = Field(None, max_length=120)
    body: str = Field(min_length=1, max_length=4000)


class CitizenReportReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{
        "issue_type": "pothole", "kind": "still_broken", "photo_ids": ["<photo_id from POST /api/uploads/photo>"],
        "location": {"lat": 19.1197, "lon": 72.8468, "accuracy_m": 12, "source": "gps"},
        "landmark": "Andheri subway, west exit", "input_mode": "photo", "language": "hi",
        "text": "Andheri subway ke bahar wapas khadda ho gaya", "contact_phone": "+91 98200 00000"}]}}
    issue_type: Optional[IssueType] = None
    kind: Optional[ReportKind] = Field(None, description=(
        "still_broken: repair failed / problem back (on a DLP road, a surface issue auto-holds payment); "
        "verified_fixed: citizen confirms the repair holds (two-key verification); "
        "new_issue: a problem with no existing work order. Default: still_broken if a matching work order exists, else new_issue"))
    photo_ids: list[str] = Field([], max_length=3, description="Up to 3 ids from POST /api/uploads/photo")
    location: Optional[ReportLocation] = None
    landmark: Optional[str] = Field(None, max_length=200)
    road_id: Optional[str] = Field(None, description="Known road. Otherwise resolved from location, then landmark/text")
    flag_id: Optional[str] = None
    work_order_id: Optional[str] = None
    contact_phone: Optional[str] = Field(None, pattern=r"^\+?[0-9 -]{6,20}$",
                                         description="Stored privately; never returned by the API or readable with the public key")
    input_mode: InputMode = "text"
    text: Optional[str] = Field(None, max_length=4000)
    language: Optional[Language] = None
    matched_locality: Optional[str] = None


class DraftNoticeReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"flag_id": "DLP_PAID_TWICE:WO25-01994", "language": "en", "doc_type": "defect_notice"}]}}
    flag_id: Optional[str] = Field(None, description="Flag to draft for. Either flag_id or road_id is required.")
    road_id: Optional[str] = Field(None, description="Road to draft for: uses its highest-stakes flag (DLP first).")
    language: Language = "en"
    doc_type: Literal["defect_notice", "rti"] = "defect_notice"

    @model_validator(mode="after")
    def _one_target(self):
        if not (self.flag_id or self.road_id):
            raise ValueError("flag_id or road_id is required")
        return self


class CitizenQueryReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"text": "Andheri subway ke bahar wapas khadda ho gaya, paisa kahan gaya?",
                                                         "language": "hi", "mode": "street_check"}]}}
    text: str = Field(min_length=2, max_length=1000)
    language: Language = "en"
    mode: Literal["street_check", "move_in"] = "street_check"


# ── Citizen accounts (anonymous, bearer token) ──────────────────────────────
PHONE_RE = r"^\+?[0-9 -]{6,20}$"
EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class CitizenCreateReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"display_name": "Andheri walker", "phone": "+91 98200 00000"}]}}
    display_name: Optional[str] = Field(None, min_length=1, max_length=60, description="Default: 'Citizen XXXX'")
    phone: Optional[str] = Field(None, pattern=PHONE_RE, description="Optional, for SMS later. Stored privately, never returned")


class CitizenToken(Out):
    model_config = _example("CitizenToken")
    citizen_id: str
    token: str  # shown once: store it and send `Authorization: Bearer <token>` on citizen calls
    display_name: str


class CitizenStats(Out):
    reports: int
    roads: int  # distinct roads reported on
    open: int
    resolved: int  # resolved + confirmed_fixed
    confirmed_fixed: int
    rupees_flagged_inr: int  # rupees at stake on the bills matched to this citizen's reports (each bill once)
    rupees_held_inr: int  # same, for reports currently in payment_held


class Me(Out):
    citizen_id: str
    display_name: str
    joined_at: ISTDateTime
    stats: CitizenStats


class ReportFlagRef(Out):
    flag_id: str
    rupees_at_stake: int


class MyReport(Out):
    id: int
    kind: ReportKind
    issue_type: Optional[IssueType]
    road: Optional[ReportRoad]
    status: ReportStatus
    created_at: ISTDateTime
    photo_url: Optional[str]  # first photo
    flag: Optional[ReportFlagRef]
    events: list[ReportEvent]


class ConfirmReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"fixed": True, "note": "Patched and holding after rain"}]}}
    fixed: bool = Field(description="true: the repair holds (resolved -> confirmed_fixed); "
                                    "false: still broken (resolved / confirmed_fixed -> reopened)")
    note: Optional[str] = Field(None, max_length=2000)
    photo_ids: list[str] = Field([], max_length=3, description="Up to 3 ids from POST /api/uploads/photo")


# ── Admin / ward officer ────────────────────────────────────────────────────
AdminRole = Literal["ward_officer", "admin"]
NoticeChannel = Literal["email", "sms", "letter"]
AdminSort = Literal["newest", "oldest", "sla_due"]  # sla_due: soonest due first, no SLA last


class AccessRequestReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{
        "name": "A. Patil", "email": "a.patil@example.org", "designation": "Assistant Engineer (Roads)",
        "ward_code": "K/W", "reason": "Triage citizen reports for K/W during the monsoon"}]}}
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(pattern=EMAIL_RE, max_length=254)
    designation: str = Field(min_length=1, max_length=120)
    ward_code: str = Field(description="K/W, K-W or k_w")
    reason: str = Field(min_length=1, max_length=2000)


class AccessRequestCreated(Out):
    model_config = _example("AccessRequestCreated")
    request_id: int
    status: Literal["pending"]


class AccessRequest(Out):
    request_id: int
    name: str
    email: str
    designation: str
    ward_code: str
    reason: str
    status: Literal["pending", "approved", "rejected"]
    created_at: ISTDateTime
    decided_at: Optional[ISTDateTime]
    decision_note: Optional[str]
    admin_id: Optional[str]  # account created on approval


class AccessDecision(Out):
    model_config = _example("AccessDecision")
    request_id: int
    status: Literal["approved", "rejected"]
    email: str
    admin_id: Optional[str]
    temporary_password: Optional[str]  # approve only, shown once: pass it to the officer


class RejectReq(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class LoginReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"email": "a.patil@example.org", "password": "<password>"}]}}
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=200)


class AdminSession(Out):
    model_config = _example("AdminSession")
    token: str  # send `Authorization: Bearer <token>` on admin calls
    role: AdminRole
    ward_codes: list[str]  # admin: [] means every ward
    expires_at: ISTDateTime


class AdminMe(Out):
    admin_id: str
    email: str
    name: str
    designation: Optional[str]
    role: AdminRole
    ward_codes: list[str]
    session_expires_at: ISTDateTime


class AdminSummary(Out):
    ward_codes: Optional[list[str]]  # scope of these numbers; null = every ward
    reports_by_status: dict[str, int]  # every status, 0 when none
    new_today: int  # created today (IST)
    overdue_sla: int  # open reports past sla_due_at
    median_hours_to_resolve: Optional[float]  # created -> first resolved, over resolved reports
    rupees_held_inr: int  # rupees at stake on bills of reports in payment_held (each bill once)
    flags_awaiting_reply: int  # flags with no Right-of-Reply yet


class ReportCard(Out):
    id: int
    created_at: ISTDateTime
    age_hours: float
    sla_due_at: Optional[ISTDateTime]
    status: ReportStatus
    kind: ReportKind
    issue_type: Optional[IssueType]
    road: Optional[ReportRoad]
    flag: Optional[ReportFlagRef]
    photo_url: Optional[str]  # first photo
    citizen: str  # pseudonym (display name) or "Anonymous"; never a phone number


class AdminFlag(Out):
    flag_id: str
    tier: int
    detector: Detector
    status_label: StatusLabel
    ward_code: str
    road_id: str
    road_name: str
    work_order_id: str
    contractor_id: str
    contractor_name: str
    rupees_at_stake: int
    rule_text: str
    replies_count: int
    last_reply_at: Optional[ISTDateTime]


class AdminWorkOrder(Out):
    work_order_id: str
    contractor_id: str
    contractor_name: str
    work_type: Optional[str]
    repair_method: str
    cost_inr: int
    completed_at: Optional[ISTDateTime]
    sla_met: Optional[bool]
    reopened_within_30d: Optional[bool]
    linked: bool  # the work order linked to this report


class DuplicateCandidate(Out):
    id: int
    created_at: ISTDateTime
    status: ReportStatus
    issue_type: Optional[IssueType]
    road_id: Optional[str]
    distance_m: Optional[float]
    reason: Literal["same_road_and_issue_7d", "within_200m"]


class ContractorNotice(Out):
    model_config = _example("ContractorNotice")
    id: int
    report_id: int
    channel: NoticeChannel
    flag_id: Optional[str]
    work_order_id: Optional[str]
    contractor_id: Optional[str]
    contractor_name: Optional[str]
    message: str
    generated_by: Literal["claude", "template", "officer"]
    sent_by: str  # officer name
    created_at: ISTDateTime
    delivery: Literal["recorded"]  # the API records the notice; it does not send email / SMS / letters


class AdminReportDetail(CitizenReport):
    citizen: str
    confirm_photos: list[ReportPhoto]  # photos the citizen attached when confirming / reopening
    flags: list[AdminFlag]  # the report's flag first, then every flag on the road
    work_orders: list[AdminWorkOrder]  # the road's work orders, linked one first
    duplicate_candidates: list[DuplicateCandidate]
    notices: list[ContractorNotice]
    allowed_next: list[ReportStatus]  # statuses PATCH accepts from here


class ReportPatchReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [
        {"status": "contractor_notified", "note": "Defect notice issued to the DLP contractor"},
        {"status": "rejected", "rejection_reason": "Private society road, not BMC"},
        {"status": "duplicate", "duplicate_of": 12},
        {"note": "Site visit booked", "repair_due_at": "2025-07-20T18:00:00+05:30"}]}}
    status: Optional[ReportStatus] = None
    note: Optional[str] = Field(None, max_length=2000)
    duplicate_of: Optional[int] = Field(None, description="Required with status=duplicate")
    rejection_reason: Optional[str] = Field(None, min_length=1, max_length=500, description="Required with status=rejected")
    repair_due_at: Optional[datetime] = Field(None, description="Overrides sla_due_at (ISO 8601; naive = IST)")

    @model_validator(mode="after")
    def _something(self):
        if not self.model_fields_set:
            raise ValueError("send at least one of status, note, duplicate_of, rejection_reason, repair_due_at")
        return self


class NotifyReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"channel": "letter", "language": "en"}]}}
    channel: NoticeChannel
    message: Optional[str] = Field(None, min_length=1, max_length=20000,
                                   description="Omit to draft one from the report's flag (Claude, template fallback)")
    language: Language = "en"


# ── Unified sign-in (frontend: one email/password account; role decides ward-office access) ─────────────────
class SignupReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"name": "Priya", "email": "priya@example.org", "password": "<min 8 chars>"}]}}
    name: str = Field(min_length=1, max_length=60)
    email: str = Field(pattern=EMAIL_RE, max_length=254)
    password: str = Field(min_length=8, max_length=200)


class AuthSession(Out):
    model_config = _example("AuthSession")
    token: str  # citizen: cit_... (no expiry) · officer/admin: adm_... (expires_at)
    role: Literal["citizen", "ward_officer", "admin"]
    ward_codes: list[str]  # officer: their wards; citizen / admin: []
    name: str
    email: str
    expires_at: Optional[ISTDateTime]  # officer/admin sessions only
    citizen_id: Optional[str]
    admin_id: Optional[str]


# ── View 1: ward money trail ────────────────────────────────────────────────
class MoneyTrailContractor(Out):
    contractor_id: str
    contractor_name: str
    jobs: int
    spend_inr: int
    failed_30d: int  # jobs reopened within 30 days
    failed_spend_inr: int  # billed on those jobs


class MoneyTrailMethod(Out):
    repair_method: str
    jobs: int
    spend_inr: int
    failed_30d: int


class FailedWithin30d(Out):
    jobs: int
    spend_inr: int


class MoneyTrail(Out):
    ward_code: str
    budget_inr: int
    spend_inr: int
    by_contractor: list[MoneyTrailContractor]  # highest spend first
    by_repair_method: list[MoneyTrailMethod]  # highest spend first
    failed_within_30d: FailedWithin30d
    summary: str  # one sentence built from the numbers above (no model text)
