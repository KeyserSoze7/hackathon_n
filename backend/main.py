"""Backend API (FastAPI) for all four views. Reads precomputed results from Supabase/Postgres;
re-solves the View 3 budget slider live; accepts Right-of-Reply and citizen reports.

Run from the repo root (DATABASE_URL from the environment or the repo-root .env):
    uvicorn backend.main:app --port 8000
Routes live in backend/routes/, one file per view; models in backend/schemas.py.
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.features.contractor_performance import router as contractor_performance
from backend.routes import accounts, admin, citizen, citizen_accounts, city_overview, health, road_story, scorecard_planner, uploads

app = FastAPI(
    title="Follow the Rupee: Backend",
    version="0.1.0",
    description=(
        "Pre-Payment Audit Gate + Citizen Rupee Receipt for Mumbai monsoon road repairs (synthetic dataset).\n\n"
        "Every number is computed by the pipelines (`audit_engine/run_audit.py`, `scorecard_planner/run_pipeline.py`); "
        "endpoints only select and shape. Flags are labelled *Needs Explanation* or *Recoverable under DLP*, "
        "and every flag carries `evidence_row_ids`. Amounts are whole rupees (INR). No login wall for citizens: an anonymous account (POST /api/citizens) gives a "
        "bearer token for 'my reports'. Officers sign in at POST /api/admin/login."
    ),
    openapi_tags=[
        {"name": "Meta", "description": "Health check."},
        {"name": "View 1: City & Ward Overview", "description": "KPI strip, ward map, flagged bills queue."},
        {"name": "View 2: Road Story", "description": "Rupee receipt, connected trail, flags, Right-of-Reply."},
        {"name": "View 3: Scorecard & Next Rupee", "description": "Context-adjusted contractor scorecard, budget allocation, live slider."},
        {"name": "View 4: Citizen Layer", "description": "Landmark lookup, citizen accounts (anonymous bearer token), "
                                                       "citizen reports with accountability tracker."},
        {"name": "Accounts", "description": "One email + password sign-in for citizens and officers "
                                            "(POST /api/auth/signup, POST /api/auth/login); the role decides ward-office access."},
        {"name": "Admin", "description": "Ward-officer / admin dashboard: access requests, login, report queue and "
                                         "triage, contractor notices, flags awaiting reply. Bearer token from "
                                         "POST /api/admin/login."},
    ],
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-Total-Count", "X-Page", "X-Page-Size"])  # admin list paging
MAX_UPLOAD_BODY = 9 * 1024 * 1024  # 8 MB photo + multipart overhead


@app.middleware("http")
async def cap_upload_size(request: Request, call_next):
    """Reject oversized uploads before the body is read (the route's own 8 MB check runs after buffering)."""
    if request.url.path.startswith("/api/uploads"):
        declared = request.headers.get("content-length")
        if declared is None and request.method == "POST":
            return JSONResponse({"detail": "Content-Length required for uploads"}, status_code=411)
        if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BODY:
            return JSONResponse({"detail": "file too large (max 8 MB)"}, status_code=413)
    return await call_next(request)

for module in (health, city_overview, road_story, scorecard_planner, citizen, citizen_accounts, uploads, accounts, admin):
    app.include_router(module.router)
app.include_router(contractor_performance.router)  # monthly contractor scorecards (backend/features/contractor_performance)


@app.on_event("startup")
def warm():
    scorecard_planner.model_inputs()  # build View 3 slider inputs once, before the first request
