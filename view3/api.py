"""View 3 API (FastAPI). Reads precomputed results from Supabase; re-solves the budget slider live.
   DATABASE_URL=... uvicorn api:app --port 8000
"""
import json, pathlib, sys
from functools import lru_cache
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import allocator, view3_pipeline as vp
from db import engine

app = FastAPI(title="Follow the Rupee: View 3")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
ENG = engine()


@lru_cache(maxsize=1)
def model_inputs():
    d, _ = vp.load(None)            # builds features from Supabase once at startup
    items, opts, _ = allocator.build_items(d)
    return items, opts


def rows(sql, **params):
    return json.loads(pd.read_sql_query(sql, ENG, params=params).to_json(orient="records"))


@app.on_event("startup")
def warm():
    model_inputs()


@app.get("/api/v3/contractors")
def contractors():
    return rows("SELECT * FROM v3_contractor_scorecard ORDER BY risk_adjusted_score DESC")


@app.get("/api/v3/wards")
def wards():
    return rows("SELECT * FROM v3_ward_allocation ORDER BY harm_avoided_per_next_lakh DESC")


@app.get("/api/v3/next-rupee/{ward_code:path}")
def next_rupee(ward_code: str):
    r = rows("SELECT * FROM v3_next_rupee WHERE ward_code = %(w)s "
             "ORDER BY bucket, funded DESC, priority_score DESC", w=ward_code)
    if not r:
        raise HTTPException(404, f"unknown ward {ward_code}")
    return r


class AllocateReq(BaseModel):
    ward_code: str
    budget_inr: float = Field(ge=0, le=5e8)


@app.post("/api/v3/allocate")
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
