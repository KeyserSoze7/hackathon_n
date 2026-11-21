"""Backend API (FastAPI) for all four views. Reads precomputed results from Supabase/Postgres;
re-solves the View 3 budget slider live; accepts Right-of-Reply and citizen reports.

Run from the repo root (DATABASE_URL from the environment or the repo-root .env):
    uvicorn backend.main:app --port 8000
Routes live in backend/routes/, one file per view; models in backend/schemas.py.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import citizen, city_overview, health, road_story, scorecard_planner

app = FastAPI(
    title="Follow the Rupee: Backend",
    version="0.1.0",
    description=(
        "Pre-Payment Audit Gate + Citizen Rupee Receipt for Mumbai monsoon road repairs (synthetic dataset).\n\n"
        "Every number is computed by the pipelines (`audit_engine/run_audit.py`, `scorecard_planner/run_pipeline.py`); "
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
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

for module in (health, city_overview, road_story, scorecard_planner, citizen):
    app.include_router(module.router)


@app.on_event("startup")
def warm():
    scorecard_planner.model_inputs()  # build View 3 slider inputs once, before the first request
