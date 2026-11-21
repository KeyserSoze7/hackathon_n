# Backend API (FastAPI)

One FastAPI app (`api.py`) serves all four views. All backend endpoints go here; don't add a second server.

## Run locally
From the repo root, with the database already loaded (see `view3/README.md` → Supabase / Postgres integration):
```bash
pip install -r view3/requirements.txt     # Python 3.12/3.13; macOS: brew install libomp (xgboost)
cd backend
DATABASE_URL=postgresql://... uvicorn api:app --port 8000 --reload
```

## API docs (Swagger)
- Swagger UI: http://127.0.0.1:8000/docs (grouped by view, with examples; "Try it out" works against the local DB)
- ReDoc: http://127.0.0.1:8000/redoc
- Spec: `GET /openapi.json`, committed as `backend/openapi.json` (import into Postman or a client generator).
  Regenerate after changing endpoints: `curl -s http://127.0.0.1:8000/openapi.json > backend/openapi.json`
- Every endpoint has a response model (`models.py`), so the spec is fully typed (28 schemas, enums for labels/codes,
  typed 404 `{detail}`). Generate a client from `backend/openapi.json`, e.g.
  `npx openapi-typescript backend/openapi.json -o src/api.d.ts` (TS types) or
  `openapi-generator-cli generate -i backend/openapi.json -g typescript-fetch -o src/api` (full client).

## Endpoints
| View | Method + path | Reads |
|---|---|---|
| — | `GET /api/health` | row counts |
| 1 | `GET /api/city` | `city_kpis` |
| 1 | `GET /api/wards` (all, list) · `GET /api/wards?ward=K/W` or header `X-Ward-Code: K/W` (one, object; query wins; case-insensitive; 404 if unknown) | `ward_overview` |
| 1 | `GET /api/flagged-queue?ward=K/W&tier=1&limit=20` | `flagged_queue` |
| 2 | `GET /api/roads/{road_id}` | `road_audit`, `work_orders`, `flags`, `flag_replies` |
| 2 | `GET /api/roads/{road_id}/timeline` | `road_timeline` |
| 2 | `GET /api/flags/{flag_id}` | `flags`, `flag_replies` |
| 2 | `POST /api/flags/{flag_id}/replies` | writes `flag_replies` (Right-of-Reply) |
| 3 | `GET /api/v3/contractors` | `v3_contractor_scorecard` |
| 3 | `GET /api/v3/wards` | `v3_ward_allocation` |
| 3 | `GET /api/v3/next-rupee/{ward}` | `v3_next_rupee` |
| 3 | `POST /api/v3/allocate` | live MILP re-solve (`view3/allocator.py`) |
| 3 | `GET /api/v3/contractor-performance/monthly?from=2025-06&to=2025-09&sort_by=speed_rank&min_jobs=0` | `contractor_monthly_scorecards`, `contractor_scorecard_runs` |
| 3 | `GET /api/v3/contractor-performance/contractors/{contractor_id}?from=&to=` | same (one contractor's monthly series; 404 if unknown) |
| 3 | `GET /api/v3/contractor-performance/methodology` | static: metric definitions, ranking rules, limitations |
| 4 | `GET /api/lookup?q=...` | `roads`, `locality_aliases`, `locality_nearest_road`, `road_audit` |
| 4 | `POST /api/citizen-reports` | writes `citizen_reports` (server sets tracker status) |
| 4 | `GET /api/citizen-reports/{id}` | `citizen_reports` |

Not built yet: `POST /api/draft-notice` (View 2) and `POST /api/citizen-query` (View 4), the two Claude endpoints.

## Monthly contractor scorecards (`features/contractor_performance/`)
Separate, explainable **monthly** ranks for comparing contractors on future work: speed, SLA, durability and
rate-card cost alignment. There is **no composite score**. This sits next to the season-level, context-adjusted
`GET /api/v3/contractors` and does not change it.

| File | Role |
|---|---|
| `router.py` | FastAPI routes (read-only), registered in `api.py` |
| `schemas.py` | response models (in `/openapi.json`) |
| `service.py` | refresh orchestration, read/shape, methodology text |
| `repository.py` | Postgres reads/upsert, CSV source (debug), in-memory store (tests) |
| `processor.py` | pure, deterministic aggregation and ranking (no I/O) |
| `config.py` | versioned parameters (`v1`: tolerance 30%, min sample 5, min cohort 3) |
| `exporter.py`, `refresh.py` | JSON snapshot (debugging only), refresh CLI |

**Setup / refresh.** Apply `supabase/migrations/20261121000200_contractor_monthly_scorecards.sql` (safe to re-run;
rollback is in its header), load the sources as usual, then recompute and upsert from `backend/`:
```bash
DATABASE_URL=... python -m features.contractor_performance.refresh            # upsert methodology v1
python -m features.contractor_performance.refresh --csv-dir ../data --dry-run --export /tmp/cp.json   # no DB
```
The refresh is CLI-only (no write route on the public API). It is idempotent: one transaction upserts the run row,
removes stale rows of that methodology version, and upserts `(contractor_id, month, methodology_version)` rows.
GET requests only read stored rows. Re-run it after `load_source.sql` (which truncates these tables).
The new tables have RLS on with **no anon policy**: the React app reads them through FastAPI only.

**Grain and month.** One row per contractor x calendar month of `work_orders.completed_at` x methodology version.
Jobs without `completed_at` get no month row; they are counted in `run.data_quality`.

| Dimension (rank field) | Metric | Better | Sample |
|---|---|---|---|
| speed (`speed.rank`) | median of job hours / same-month same-`repair_method` city median, where hours = earliest linked `complaints.received_at` -> `completed_at` | lower | jobs with a linked complaint timestamp <= completion and a cohort of >= 3 jobs |
| sla (`sla.rank`) | `sla_met` true / known | higher | non-null `sla_met` |
| durability (`durability.rank`) | `reopened_within_30d` true / known | lower | non-null `reopened_within_30d` |
| cost_alignment (`cost_alignment.rank`) | median abs(cost - benchmark) / benchmark; benchmark = `area_sqm x rate` (per sqm) or `rate` (per job) | lower | rate-card match, positive benchmark, area for per-sqm methods |

- Raw median complaint-to-completion hours, the peer cohort median, a per-method breakdown and an
  `assigned_at -> completed_at` **proxy** (never ranked) sit next to the speed index, so method mix is visible.
- Cost: +/-30% around the benchmark is ordinary variation. `over_tolerance_count/share` is reported, and
  `under_tolerance_count` is descriptive only, so cheap jobs are not rewarded.
- Ranks are computed per dimension and per month among contractors whose sample for **that** dimension is >= 5.
  Otherwise `rank` is null and `rank_eligibility[dim].reason` says why (e.g. `sample 3 < min 5`).
- Ties: values are rounded to 6 decimals, then share the best rank (1, 2, 2, 4). Display order then goes by `contractor_id`.
  `min_jobs` only hides rows; it never changes stored ranks. `cohort_size` = contractors eligible that month.
- Null `sla_met` / `reopened_within_30d` count as `missing`, never as a success or failure.
- `context` is **descriptive exposure, not adjustment and not evidence of fault**. It covers:
  - regional rain (daily max across Santacruz/Colaba over the work window; not ward-specific)
  - big-tide days (city-level)
  - jobs in flood-hotspot wards (ward-level)
  - job-weighted traffic
  - distinct same-month accidents on serviced roads (not attributed to the contractor)
  - jobs on ambulance-entry roads

  Each block reports its coverage and is `null` if its source table is missing.
- Data quality: a work order's ward is checked against `roads.ward_code`. Any mismatch is listed in `data_quality`
  rather than resolved silently.
- Evidence: `evidence_work_order_ids` lists every job in the contractor-month.
- Changing any parameter means adding a new version in `config.py`, so old rankings stay reproducible.

Tests (no database): `cd backend && pytest tests -q`.

## Changing an endpoint (e.g. View 2)
- View 2 routes are the `/api/roads/...` and `/api/flags/...` functions in `api.py`.
- SQL views they read are in `supabase/migrations/20261121000100_audit_views.sql` (`road_audit`, `road_timeline`, `flagged_queue`).
  Change the schema with a **new** migration file rather than editing an applied one (all three are applied on Supabase).
- Full schema at a glance (every table, view, constraint, RLS policy): `supabase/schema.sql`. Reference snapshot
  dumped from Supabase; don't run it. Regenerate it after a schema change (command in its header).
- Every route declares `response_model=` from `models.py`. Change the model with the SQL view/table it mirrors.
  Run with `STRICT_MODELS=1` while developing/testing: an undeclared or mistyped field then fails loudly (500)
  instead of being silently dropped from the response.
- Validate request bodies with Pydantic models, query params with `Query(...)`. Use `rows()` / `one()` for reads
  (`%(name)s` params; never format user input into SQL) and `ENG.begin()` + `text()` for writes.
- Numbers come from the database/pipeline; endpoints only select and shape. No arithmetic in prompts or UI.
- Update `postman/backend.postman_collection.json` and run it against an API started with `STRICT_MODELS=1`:
  `postman collection run postman/backend.postman_collection.json` (33 requests, 83 assertions)
