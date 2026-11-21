"""View 3: Fair Accountability & Next-Rupee Planner. Contractor scorecard, ward allocation, live budget slider.

Numbers come from scorecard_planner/run_pipeline.py (v3_* tables); the slider re-solves live with
scorecard_planner/budget_allocator.py.
"""
import math
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Path

from backend import schemas as s
from backend.database import norm_ward, one, rows
from scorecard_planner import budget_allocator as allocator
from scorecard_planner import run_pipeline as vp

router = APIRouter(tags=["View 3: Scorecard & Next Rupee"])


@lru_cache(maxsize=1)
def model_inputs():
    d, _ = vp.load(None)            # builds features from Supabase once at startup
    items, opts, _ = allocator.build_items(d)
    return items, opts, d           # d is needed for city-wide equity floors


def ward_or_all(code):
    """norm_ward(), but 'ALL' (any case) -> None, meaning every ward."""
    w = norm_ward(code)
    return None if w == "ALL" else w


def bucket_b(items, opts, ward):
    """BMC-paid items (not owed by a DLP contractor) and their method options, for one ward or all (ward=None)."""
    bi = items[~items.dlp_owed & ((items.ward_code == ward) if ward else True)]
    return bi, opts[opts.item_id.isin(bi.item_id)]


@router.get("/api/v3/contractors", response_model=list[s.ContractorScore], summary="Contractor scorecard (context-adjusted)")
def contractors():
    return rows("SELECT * FROM v3_contractor_scorecard ORDER BY risk_adjusted_score DESC")


@router.get("/api/v3/wards", response_model=list[s.WardAllocation], summary="Ward allocation: where the next lakh does most good")
def wards():
    return rows("SELECT * FROM v3_ward_allocation ORDER BY harm_avoided_per_next_lakh DESC")


@router.get("/api/v3/next-rupee/{ward_code:path}", response_model=list[s.NextRupeeItem], responses=s.NOT_FOUND, summary="Next-rupee items for one ward, or ALL (Bucket A = DLP, Rs 0)")
def next_rupee(ward_code: str = Path(examples=["K/W", "ALL"])):
    r = rows("SELECT * FROM v3_next_rupee WHERE (%(w)s::text IS NULL OR ward_code = %(w)s) "
             "ORDER BY bucket, funded DESC, priority_score DESC", w=ward_or_all(ward_code))
    if not r:
        raise HTTPException(404, f"unknown ward {ward_code}")
    return r


@router.get("/api/v3/summary", response_model=s.V3Summary, responses=s.NOT_FOUND, summary="Model quality + budget curve (optimizer vs simple rules)")
def v3_summary():
    """View 3 demo chart: harm avoided by the optimizer vs simple rules at each budget level, plus model quality."""
    r = one("SELECT meta, updated_at FROM v3_model_meta WHERE id = 1", "v3 summary (run python -m scorecard_planner.run_pipeline)")
    return {**r["meta"], "updated_at": r["updated_at"]}


@router.post("/api/v3/allocate", response_model=s.Allocation, responses=s.NOT_FOUND, summary="Budget slider: exact re-solve for one ward, or ALL (city-wide with equity floors)")
def allocate(req: s.AllocateReq):
    items, opts, d = model_inputs()
    ward = ward_or_all(req.ward_code)
    if ward is None:
        bi, bo = bucket_b(items, opts, None)
        ch = allocator.solve(bi, bo, req.budget_inr, allocator.equity_floors(bi, bo, d, req.budget_inr))
        res = {"ward_code": "ALL", "budget_inr": req.budget_inr, "spend_inr": int(ch.cost.sum()),
               "harm_avoided": round(float(ch.benefit.sum()), 1),
               "funded": ch[["item_id", "method", "cost", "benefit"]].round(1).to_dict(orient="records")}
    elif ward not in set(items.ward_code):
        raise HTTPException(404, f"unknown ward {req.ward_code}")
    else:
        res = allocator.allocate_ward(items, opts, ward, req.budget_inr)
    where = "(%(w)s::text IS NULL OR ward_code = %(w)s)"
    detail = {r["item_id"]: r for r in rows(
        f"SELECT item_id, ward_code, road_name, issue, reason_codes, evidence_wo_ids FROM v3_next_rupee WHERE {where}", w=ward)}
    for f in res["funded"]:
        f.update({k: v for k, v in detail.get(f["item_id"], {}).items() if k != "item_id"})
    res["bucket_a_dlp"] = rows(
        "SELECT item_id, road_name, issue, estimated_repair_cost_inr, explanation FROM v3_next_rupee "
        f"WHERE {where} AND bucket = 'A_OWED_BY_CONTRACTOR_DLP'", w=ward)
    return res


@router.get("/api/v3/budget-range/{ward_code:path}", response_model=s.BudgetRange, responses=s.NOT_FOUND, summary="Budget slider bounds for one ward, or ALL")
def budget_range(ward_code: str = Path(examples=["K/W", "ALL"])):
    """max = rate-card cost to fix every bucket-B item (cheapest method each); default = 2025 money left,
    else the optimizer's recommendation, else 10% of max."""
    ward = ward_or_all(ward_code)
    a = one("SELECT COALESCE(SUM(remaining_2025_inr), 0) AS remaining, "
            "COALESCE(SUM(recommended_budget_inr), 0) AS recommended, COUNT(*) AS n "
            "FROM v3_ward_allocation WHERE (%(w)s::text IS NULL OR ward_code = %(w)s)", "ward", w=ward)
    if not a["n"]:
        raise HTTPException(404, f"unknown ward {ward_code}")
    items, opts, _ = model_inputs()
    _, bo = bucket_b(items, opts, ward)
    step = 100_000 if ward is None else 10_000
    max_inr = int(math.ceil(bo.groupby("item_id").cost.min().sum() / step) * step)
    remaining, recommended = int(a["remaining"]), int(a["recommended"])
    if remaining > 0:
        default, basis = remaining, "remaining_2025"
    elif recommended > 0:
        default, basis = recommended, "optimizer_recommendation"
    else:
        default, basis = 0.1 * max_inr, "share_of_need"
    default = min(max(int(round(default / step) * step), 0), max_inr)
    return {"ward_code": ward or "ALL", "min_inr": 0, "max_inr": max_inr, "default_inr": default, "step_inr": step,
            "remaining_2025_inr": remaining, "default_basis": basis}
