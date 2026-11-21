"""View 3: Fair Accountability & Next-Rupee Planner. Contractor scorecard, ward allocation, live budget slider.

Numbers come from scorecard_planner/run_pipeline.py (v3_* tables); the slider re-solves live with
scorecard_planner/budget_allocator.py.
"""
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
    return items, opts


@router.get("/api/v3/contractors", response_model=list[s.ContractorScore], summary="Contractor scorecard (context-adjusted)")
def contractors():
    return rows("SELECT * FROM v3_contractor_scorecard ORDER BY risk_adjusted_score DESC")


@router.get("/api/v3/wards", response_model=list[s.WardAllocation], summary="Ward allocation: where the next lakh does most good")
def wards():
    return rows("SELECT * FROM v3_ward_allocation ORDER BY harm_avoided_per_next_lakh DESC")


@router.get("/api/v3/next-rupee/{ward_code:path}", response_model=list[s.NextRupeeItem], responses=s.NOT_FOUND, summary="Next-rupee items for one ward (Bucket A = DLP, Rs 0)")
def next_rupee(ward_code: str = Path(examples=["K/W"])):
    r = rows("SELECT * FROM v3_next_rupee WHERE ward_code = %(w)s "
             "ORDER BY bucket, funded DESC, priority_score DESC", w=norm_ward(ward_code))
    if not r:
        raise HTTPException(404, f"unknown ward {ward_code}")
    return r


@router.get("/api/v3/summary", response_model=s.V3Summary, responses=s.NOT_FOUND, summary="Model quality + budget curve (optimizer vs simple rules)")
def v3_summary():
    """View 3 demo chart: harm avoided by the optimizer vs simple rules at each budget level, plus model quality."""
    r = one("SELECT meta, updated_at FROM v3_model_meta WHERE id = 1", "v3 summary (run python -m scorecard_planner.run_pipeline)")
    return {**r["meta"], "updated_at": r["updated_at"]}


@router.post("/api/v3/allocate", response_model=s.Allocation, responses=s.NOT_FOUND, summary="Budget slider: exact re-solve for one ward")
def allocate(req: s.AllocateReq):
    items, opts = model_inputs()
    ward = norm_ward(req.ward_code)
    if ward not in set(items.ward_code):
        raise HTTPException(404, f"unknown ward {req.ward_code}")
    res = allocator.allocate_ward(items, opts, ward, req.budget_inr)
    detail = {r["item_id"]: r for r in rows(
        "SELECT item_id, road_name, issue, reason_codes, evidence_wo_ids FROM v3_next_rupee WHERE ward_code = %(w)s",
        w=ward)}
    for f in res["funded"]:
        f.update({k: v for k, v in detail.get(f["item_id"], {}).items() if k != "item_id"})
    res["bucket_a_dlp"] = rows(
        "SELECT item_id, road_name, issue, estimated_repair_cost_inr, explanation FROM v3_next_rupee "
        "WHERE ward_code = %(w)s AND bucket = 'A_OWED_BY_CONTRACTOR_DLP'", w=ward)
    return res
