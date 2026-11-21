# Follow the Rupee: Contractor Accountability Platform

Pre-Payment Audit Gate + Citizen Rupee Receipt for Mumbai's monsoon road repairs, built for Claude Impact Lab Mumbai.
All data is synthetic and all contractors are fictional (see `docs/dataset_readme.md`).

Code computes every number; Claude only explains them. Flags read *Needs Explanation* or *Recoverable under DLP*,
and every flag carries the row IDs that prove it.

## Repository layout

| Path | What it is |
|---|---|
| `data/` | Source dataset (CSV + GeoJSON). Read-only input. |
| `audit_engine/` | Flag detectors and ward/road audit (stdlib Python). Powers Views 1 and 2. |
| `audit_engine/detectors.py` | The audit rules: DLP paid twice, overlapping work orders, rate inflation, rain-day asphalt, repeat bill with no complaint |
| `audit_engine/run_audit.py` | Runs the detectors over `data/`, builds the ward audit and road receipts, writes `audit_engine/output/` |
| `scorecard_planner/` | View 3: context-adjusted contractor scorecard (XGBoost + SHAP) and next-rupee budget allocation (exact MILP) |
| `scorecard_planner/run_pipeline.py` | Builds features, trains, solves; writes `scorecard_planner/output/` and the `v3_*` tables |
| `scorecard_planner/budget_allocator.py` | The budget optimizer behind Bucket A/B and the live slider |
| `backend/` | FastAPI app for all four views (`main.py`, `routes/` per view, `schemas.py`, `database.py`) |
| `supabase/migrations/` | Database schema, applied in filename order |
| `supabase/load_source_data.sql`, `supabase/load_audit_outputs.sql` | Load `data/` and the audit outputs into the database |
| `supabase/schema_snapshot.sql` | Whole schema in one readable file (reference only, don't run) |
| `postman/` | API test collection |
| `docs/` | Dataset readme, data dictionary, project context, frontend/backend handoff plan, DB mapping |

## Quick start (from the repo root)

```bash
pip install -r requirements.txt            # Python 3.12/3.13; macOS: brew install libomp (xgboost)
cp .env.example .env                       # fill in DATABASE_URL (Supabase -> Connect -> Session pooler)

python3 -m audit_engine.run_audit          # 1. flags + ward audit -> audit_engine/output/
# 2. database (first time only; run the migrations in order)
for f in supabase/migrations/*.sql; do psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"; done
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/load_source_data.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/load_audit_outputs.sql
python -m scorecard_planner.run_pipeline   # 3. View 3 tables
uvicorn backend.main:app --port 8000       # 4. API; Swagger at http://127.0.0.1:8000/docs
```

More detail: `backend/README.md` (endpoints, how to change one), `scorecard_planner/README.md` (View 3 method).
