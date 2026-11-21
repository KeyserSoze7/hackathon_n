# Backend API (FastAPI)

One FastAPI app (`api.py`) serves all four views. All backend endpoints go here; don't add a second server.

## Run locally
From the repo root, with the database already loaded (see `view3/README.md` → Supabase / Postgres integration):
```bash
pip install -r view3/requirements.txt     # Python 3.12/3.13; macOS: brew install libomp (xgboost)
cd backend
DATABASE_URL=postgresql://... uvicorn api:app --port 8000 --reload
```
Interactive docs: http://127.0.0.1:8000/docs

## Endpoints
| View | Method + path | Reads |
|---|---|---|
| — | `GET /api/health` | row counts |
| 1 | `GET /api/city` | `city_kpis` |
| 1 | `GET /api/wards` | `ward_overview` |
| 1 | `GET /api/flagged-queue?ward=K/W&tier=1&limit=20` | `flagged_queue` |
| 2 | `GET /api/roads/{road_id}` | `road_audit`, `work_orders`, `flags`, `flag_replies` |
| 2 | `GET /api/roads/{road_id}/timeline` | `road_timeline` |
| 2 | `GET /api/flags/{flag_id}` | `flags`, `flag_replies` |
| 2 | `POST /api/flags/{flag_id}/replies` | writes `flag_replies` (Right-of-Reply) |
| 3 | `GET /api/v3/contractors` | `v3_contractor_scorecard` |
| 3 | `GET /api/v3/wards` | `v3_ward_allocation` |
| 3 | `GET /api/v3/next-rupee/{ward}` | `v3_next_rupee` |
| 3 | `POST /api/v3/allocate` | live MILP re-solve (`view3/allocator.py`) |
| 4 | `GET /api/lookup?q=...` | `roads`, `locality_aliases`, `locality_nearest_road`, `road_audit` |
| 4 | `POST /api/citizen-reports` | writes `citizen_reports` (server sets tracker status) |
| 4 | `GET /api/citizen-reports/{id}` | `citizen_reports` |

Not built yet: `POST /api/draft-notice` (View 2) and `POST /api/citizen-query` (View 4), the two Claude endpoints.

## Changing an endpoint (e.g. View 2)
- View 2 routes are the `/api/roads/...` and `/api/flags/...` functions in `api.py`.
- SQL views they read are in `supabase/migrations/20261121000100_audit_views.sql` (`road_audit`, `road_timeline`, `flagged_queue`).
  Change the schema with a **new** migration file rather than editing an applied one.
- Validate request bodies with Pydantic models, query params with `Query(...)`. Use `rows()` / `one()` for reads
  (`%(name)s` params; never format user input into SQL) and `ENG.begin()` + `text()` for writes.
- Numbers come from the database/pipeline; endpoints only select and shape. No arithmetic in prompts or UI.
- Update `postman/backend.postman_collection.json` and run it:
  `postman collection run postman/backend.postman_collection.json`
