"""Backend API (FastAPI) for all four views. Reads precomputed results from Supabase/Postgres;
re-solves the View 3 budget slider live; accepts Right-of-Reply and citizen reports.
   DATABASE_URL=... uvicorn api:app --port 8000      (run from backend/; see backend/README.md)
"""
import json, pathlib, sys
from functools import lru_cache
import pandas as pd
from fastapi import FastAPI, Header, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field
from sqlalchemy import text

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "view3"))  # View 3 model code (allocator, feature pipeline)
import allocator, view3_pipeline as vp
from db import engine
import models as m

app = FastAPI(
    title="Follow the Rupee: Backend",
    version="0.1.0",
    description=(
        "Pre-Payment Audit Gate + Citizen Rupee Receipt for Mumbai monsoon road repairs (synthetic dataset).\n\n"
        "Every number is computed by the audit pipelines (`pipeline/build.py`, `view3/view3_pipeline.py`); "
        "endpoints only select and shape. Flags are labelled *Needs Explanation* or *Recoverable under DLP*, "
        "and every flag carries `evidence_row_ids`. Amounts are whole rupees (INR). No login."
    ),
    openapi_tags=[
        {"name": "Meta", "description": "Health check."},
        {"name": "View 1: City & Ward Overview", "description": "KPI strip, ward map, flagged bills queue."},
        {"name": "View 2: Road Story", "description": "Rupee receipt, connected trail, flags, Right-of-Reply."},
        {"name": "View 3: Scorecard & Next Rupee", "description": "Context-adjusted contractor scorecard, budget allocation, live slider."},
        {"name": "View 4: Citizen Layer", "description": "Landmark lookup and citizen reports with accountability tracker."},
    ],
)
NOT_FOUND = {404: {"model": m.Error}}
V1, V2, V3, V4 = ("View 1: City & Ward Overview", "View 2: Road Story",
                  "View 3: Scorecard & Next Rupee", "View 4: Citizen Layer")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
ENG = engine()


@lru_cache(maxsize=1)
def model_inputs():
    d, _ = vp.load(None)            # builds features from Supabase once at startup
    items, opts, _ = allocator.build_items(d)
    return items, opts


def rows(sql, **params):
    return json.loads(pd.read_sql_query(sql, ENG, params=params).to_json(orient="records", date_format="iso"))


def one(sql, what, **params):
    r = rows(sql, **params)
    if not r:
        raise HTTPException(404, f"unknown {what}")
    return r[0]


@app.on_event("startup")
def warm():
    model_inputs()


@app.get("/api/v3/contractors", response_model=list[m.ContractorScore], tags=[V3], summary="Contractor scorecard (context-adjusted)")
def contractors():
    return rows("SELECT * FROM v3_contractor_scorecard ORDER BY risk_adjusted_score DESC")


@app.get("/api/v3/wards", response_model=list[m.WardAllocation], tags=[V3], summary="Ward allocation: where the next lakh does most good")
def wards():
    return rows("SELECT * FROM v3_ward_allocation ORDER BY harm_avoided_per_next_lakh DESC")


@app.get("/api/v3/next-rupee/{ward_code:path}", response_model=list[m.NextRupeeItem], responses=NOT_FOUND, tags=[V3], summary="Next-rupee items for one ward (Bucket A = DLP, Rs 0)")
def next_rupee(ward_code: str = Path(examples=["K/W"])):
    r = rows("SELECT * FROM v3_next_rupee WHERE ward_code = %(w)s "
             "ORDER BY bucket, funded DESC, priority_score DESC", w=ward_code)
    if not r:
        raise HTTPException(404, f"unknown ward {ward_code}")
    return r


class AllocateReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"ward_code": "K/W", "budget_inr": 500000}]}}
    ward_code: str
    budget_inr: float = Field(ge=0, le=5e8)


@app.post("/api/v3/allocate", response_model=m.Allocation, responses=NOT_FOUND, tags=[V3], summary="Budget slider: exact re-solve for one ward")
def allocate(req: AllocateReq):
    items, opts = model_inputs()
    if req.ward_code not in set(items.ward_code):
        raise HTTPException(404, f"unknown ward {req.ward_code}")
    res = allocator.allocate_ward(items, opts, req.ward_code, req.budget_inr)
    detail = {r["item_id"]: r for r in rows(
        "SELECT item_id, road_name, issue, reason_codes, evidence_wo_ids FROM v3_next_rupee WHERE ward_code = %(w)s",
        w=req.ward_code)}
    for f in res["funded"]:
        f.update({k: v for k, v in detail.get(f["item_id"], {}).items() if k != "item_id"})
    res["bucket_a_dlp"] = rows(
        "SELECT item_id, road_name, issue, estimated_repair_cost_inr, explanation FROM v3_next_rupee "
        "WHERE ward_code = %(w)s AND bucket = 'A_OWED_BY_CONTRACTOR_DLP'", w=req.ward_code)
    return res


# ---------------------------------------------------------------- Views 1, 2, 4 (audit engine tables/views)
@app.get("/api/health", response_model=m.Health, tags=["Meta"], summary="Health + row counts")
def health():
    return one("SELECT (SELECT count(*) FROM work_orders) AS work_orders, (SELECT count(*) FROM flags) AS flags, "
               "(SELECT count(*) FROM v3_next_rupee) AS v3_items", "db")


@app.get("/api/city", response_model=m.CityKPIs, tags=[V1], summary="City KPI strip")
def city():
    """View 1 KPI strip."""
    return one("SELECT * FROM city_kpis", "city")


@app.get("/api/wards", response_model=Union[m.Ward, list[m.Ward]], responses=NOT_FOUND, tags=[V1], summary="All wards, or one ward via ?ward= / X-Ward-Code")
def ward_list(ward: Optional[str] = Query(None, description="Ward code, e.g. K/W. Returns that ward only."),
              x_ward_code: Optional[str] = Header(None, description="Same as ?ward=; the query param wins if both are sent.")):
    """View 1 ward map: all wards as a list, or one ward as an object when a ward code is given
    (query param or X-Ward-Code header). Colour the map by dlp_leakage_rate; join to wards.geojson on ward_code."""
    code = (ward or x_ward_code or "").strip().upper()
    if code:
        return one("SELECT * FROM ward_overview WHERE ward_code = %(w)s", f"ward {code}", w=code)
    return rows("SELECT * FROM ward_overview ORDER BY ward_code")


@app.get("/api/flagged-queue", response_model=list[m.FlaggedBill], tags=[V1], summary="Flagged bills ranked by rupees at stake")
def flagged_queue(ward: Optional[str] = Query(None, description="Ward code filter", examples=["K/W"]),
                  tier: Optional[int] = Query(None, ge=1, le=3, description="Top tier filter: 1 contractual, 2 implausible, 3 lead"),
                  limit: int = Query(50, ge=1, le=500)):
    """View 1 flagged bills, ranked by rupees at stake. ?ward=K/W&tier=1&limit=20"""
    return rows("SELECT * FROM flagged_queue WHERE (%(w)s IS NULL OR ward_code = %(w)s) "
                "AND (%(t)s IS NULL OR top_tier = %(t)s) ORDER BY rupees_at_stake DESC, work_order_id LIMIT %(n)s",
                w=ward, t=tier, n=max(1, min(limit, 500)))


@app.get("/api/roads/{road_id}", response_model=m.RoadReceipt, responses=NOT_FOUND, tags=[V2], summary="Road receipt: header, work orders, flags + replies")
def road(road_id: str = Path(examples=["RD0058"])):
    """View 2 header card + work orders + flags (with replies)."""
    r = one("SELECT * FROM road_audit WHERE road_id = %(r)s", f"road {road_id}", r=road_id)
    r["work_orders"] = rows(
        "SELECT wo.work_order_id, wo.contractor_id, c.contractor_name, wo.work_type, wo.repair_method, wo.cost_inr, "
        "wo.assigned_at, wo.completed_at, wo.sla_met, wo.reopened_within_30d, wo.engineer_remark "
        "FROM work_orders wo JOIN contractors c USING (contractor_id) WHERE wo.road_id = %(r)s ORDER BY wo.assigned_at",
        r=road_id)
    r["flags"] = rows(
        "SELECT f.*, COALESCE((SELECT json_agg(rp ORDER BY rp.created_at) FROM flag_replies rp "
        "WHERE rp.flag_id = f.flag_id), '[]') AS replies FROM flags f WHERE f.road_id = %(r)s "
        "ORDER BY f.tier, f.rupees_at_stake DESC", r=road_id)
    return r


@app.get("/api/roads/{road_id}/timeline", response_model=list[m.TimelineEvent], responses=NOT_FOUND, tags=[V2], summary="Connected trail: complaints -> work orders -> accidents -> reports")
def road_timeline(road_id: str = Path(examples=["RD0058"])):
    """View 2 connected trail, chronological."""
    one("SELECT 1 FROM roads WHERE road_id = %(r)s", f"road {road_id}", r=road_id)
    return rows("SELECT * FROM road_timeline WHERE road_id = %(r)s ORDER BY event_at, event_type", r=road_id)


@app.get("/api/flags/{flag_id}", response_model=m.FlagWithReplies, responses=NOT_FOUND, tags=[V2], summary="One flag with its replies")
def flag(flag_id: str = Path(description="<DETECTOR>:<work_order_id>", examples=["DLP_PAID_TWICE:WO25-01994"])):
    f = one("SELECT * FROM flags WHERE flag_id = %(f)s", f"flag {flag_id}", f=flag_id)
    f["replies"] = rows("SELECT * FROM flag_replies WHERE flag_id = %(f)s ORDER BY created_at", f=flag_id)
    return f


class ReplyReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"author_role": "ward_engineer", "author_name": "AE Roads K/W",
                                                         "body": "MGL utility trench reopened this stretch; contractor liable under DLP."}]}}
    author_role: Literal["ward_engineer", "contractor", "other"]
    author_name: Optional[str] = Field(None, max_length=120)
    body: str = Field(min_length=1, max_length=4000)


@app.post("/api/flags/{flag_id}/replies", status_code=201, response_model=m.Reply, responses=NOT_FOUND, tags=[V2], summary="Add Right-of-Reply to a flag")
def add_reply(flag_id: str, req: ReplyReq):
    """View 2 Right-of-Reply."""
    one("SELECT 1 FROM flags WHERE flag_id = %(f)s", f"flag {flag_id}", f=flag_id)
    with ENG.begin() as c:
        r = c.execute(text("INSERT INTO flag_replies (flag_id, author_role, author_name, body) "
                           "VALUES (:f, :role, :name, :body) RETURNING id, flag_id, author_role, author_name, body, created_at"),
                      {"f": flag_id, "role": req.author_role, "name": req.author_name, "body": req.body}).mappings().one()
    return dict(r)


@app.get("/api/lookup", response_model=m.Lookup, responses=NOT_FOUND, tags=[V4], summary="Free-text landmark/road lookup -> road receipt")
def lookup(q: str = Query(min_length=2, max_length=200, description="Free text: road name, locality, alias or Devanagari",
                          examples=["Andheri subway ke bahar wapas khadda ho gaya, paisa kahan gaya?"])):
    """View 4 deterministic lookup: free text -> road receipt.
    Tries a road name in the text first ("Andheri subway ke bahar..."), then any locality name/alias/Devanagari.
    Fuzzy/vernacular parsing beyond this is the Claude /api/citizen-query layer's job."""
    m = rows("SELECT r.road_id, r.road_name AS matched_text, r.ward_code, NULL::text AS locality, 0 AS approx_m "
             "FROM roads r WHERE position(lower(r.road_name) in lower(%(q)s)) > 0 "
             "ORDER BY length(r.road_name) DESC, r.segment_no LIMIT 1", q=q)
    via = "road_name"
    if not m:
        m = rows("SELECT n.road_id, a.alias AS matched_text, n.ward_code, n.locality, n.approx_m "
                 "FROM locality_aliases a JOIN locality_nearest_road n USING (locality) "
                 "WHERE position(a.alias in lower(%(q)s)) > 0 ORDER BY length(a.alias) DESC LIMIT 1", q=q)
        via = "locality"
    if not m:
        raise HTTPException(404, "no road or locality matched; try a road name or area name")
    m = m[0]
    receipt = one("SELECT * FROM road_audit WHERE road_id = %(r)s", "road", r=m["road_id"])
    return {"matched_via": via, "matched_text": m["matched_text"], "matched_locality": m["locality"],
            "ward_code": m["ward_code"], "matched_road_id": m["road_id"], "road_distance_m": m["approx_m"],
            "warranty_status": "UNDER_DLP" if receipt["under_dlp"] else "OUT_OF_DLP", "road": receipt}


class CitizenReportReq(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"kind": "still_broken", "input_mode": "voice", "language": "hi",
                                                         "text": "Andheri subway ke bahar wapas khadda ho gaya", "road_id": "RD0153"}]}}
    kind: Literal["still_broken", "verified_fixed", "new_issue"]
    input_mode: Literal["text", "voice", "photo", "qr"] = "text"
    text: Optional[str] = Field(None, max_length=4000)
    language: Optional[Literal["en", "hi", "mr"]] = None
    photo_url: Optional[str] = Field(None, max_length=1000)
    road_id: Optional[str] = None
    work_order_id: Optional[str] = None
    matched_locality: Optional[str] = None


TRACKER = ["reported", "matched_to_contract", "payment_held", "contractor_notified"]


@app.post("/api/citizen-reports", status_code=201, response_model=m.CitizenReport, responses=NOT_FOUND, tags=[V4], summary="Submit citizen report (server sets tracker status)")
def add_citizen_report(req: CitizenReportReq):
    """View 4 report. Tracker status is set deterministically here (anon clients cannot set it)."""
    status, flag_id = "reported", None
    if req.road_id:
        road = one("SELECT road_id, under_dlp FROM roads WHERE road_id = %(r)s", f"road {req.road_id}", r=req.road_id)
        status = "matched_to_contract"
        if road["under_dlp"] and req.kind == "still_broken":
            status = "payment_held"  # DLP road: the original contractor owes the fix, BMC holds payment
            f = rows("SELECT flag_id FROM flags WHERE road_id = %(r)s AND detector = 'DLP_PAID_TWICE' "
                     "ORDER BY rupees_at_stake DESC LIMIT 1", r=req.road_id)
            flag_id = f[0]["flag_id"] if f else None
    with ENG.begin() as c:
        r = c.execute(text(
            "INSERT INTO citizen_reports (kind, input_mode, text, language, photo_url, matched_locality, road_id, "
            "work_order_id, flag_id, status) VALUES (:kind, :input_mode, :text, :language, :photo_url, "
            ":matched_locality, :road_id, :work_order_id, :flag_id, :status) RETURNING *"),
            {**req.model_dump(), "flag_id": flag_id, "status": status}).mappings().one()
    out = dict(r)
    out["tracker"] = [{"step": s_, "done": TRACKER.index(s_) <= TRACKER.index(status)} for s_ in TRACKER]
    return out


@app.get("/api/citizen-reports/{report_id}", response_model=m.CitizenReport, responses=NOT_FOUND, tags=[V4], summary="Citizen report status + tracker")
def citizen_report(report_id: int):
    r = one("SELECT * FROM citizen_reports WHERE id = %(i)s", f"report {report_id}", i=report_id)
    r["tracker"] = [{"step": s_, "done": TRACKER.index(s_) <= TRACKER.index(r["status"])} for s_ in TRACKER]
    return r
