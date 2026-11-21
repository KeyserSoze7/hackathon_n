# Backend API (FastAPI)

One FastAPI app serves all four views (frontend-facing endpoint guide: `docs/api_reference.md`). All backend endpoints go here; don't add a second server.

| File | What it does |
|---|---|
| `main.py` | Creates the app (title, tags, CORS), mounts the routers, warms the View 3 slider at startup |
| `database.py` | Reads `DATABASE_URL` (env or repo-root `.env`), shared engine, `rows()` / `one()` / `norm_ward()` helpers |
| `schemas.py` | Every request and response model (the typed OpenAPI contract); timestamps serialise as ISO 8601 IST (`+05:30`) |
| `photos.py` | Photo storage: Supabase Storage bucket `report-photos` over S3 (when `SUPABASE_S3_*` keys are set), else local `uploads/` |
| `claude_writer.py` | The one Claude call (defect notices, RTI drafts, citizen replies): `claude-opus-5-5`, low effort, 25 s timeout, returns `None` so callers serve a template |
| `routes/health.py` | `GET /api/health` |
| `routes/city_overview.py` | View 1: KPI strip, wards, ward map, flagged queue |
| `routes/road_story.py` | View 2: road search, road receipt, timeline, flags, Right-of-Reply, draft notice / RTI |
| `routes/scorecard_planner.py` | View 3: contractor scorecard, ward allocation, next rupee (ward or ALL), summary, budget slider + range |
| `features/contractor_performance/` | View 3: monthly contractor scorecards (four separate ranks, no composite); see below |
| `routes/citizen.py` | View 4: localities, lookup with candidates, livability, citizen query, citizen reports (report form) + tracker |
| `routes/uploads.py` | View 4: photo upload (validated, EXIF read then stripped, HEIC to JPEG) and photo serving |
| `routes/citizen_accounts.py` | View 4: anonymous citizen accounts (bearer token), `GET /api/me` + stats, my reports, confirm / reopen a fix |
| `routes/accounts.py` | One sign-in: `POST /api/auth/signup` (citizen email + password), `POST /api/auth/login` (officer, admin or citizen → token + role) |
| `routes/admin.py` | Admin dashboard: access requests, login, summary, report queue + triage (PATCH), contractor notices, flags awaiting reply |
| `auth.py` | Bearer tokens (citizen `cit_…`, officer `adm_…`; only sha256 stored), scrypt passwords, `require_citizen` / `require_admin()` / ward-scope dependencies |
| `report_lifecycle.py` | Report statuses, allowed transitions, citizen confirmation, `sla_due_at`, tracker steps (pure, unit-tested) |
| `admin_cli.py` | `python -m backend.admin_cli create-admin ...`: create the first admin (or reset an account) |
| `openapi.json` | Exported spec for client generation |

## Configure
Copy `.env.example` to `.env` at the repo root and fill in the Supabase Session pooler URI (or `export DATABASE_URL=...`).

### Citizen accounts + admin dashboard (once per database)
1. Apply `supabase/migrations/20261121000800_citizen_accounts_admin.sql`. It is safe to re-run, and the rollback is in its header.
2. Create the first admin. Nobody can approve the first account, so this happens on the server:
   ```bash
   python -m backend.admin_cli create-admin --email ops@example.org --name "Ops Admin"   # prompts for a password (min 10)
   ```
   Ward officers then ask through `POST /api/admin/access-requests`. An admin approves them, which returns a
   one-time temporary password. The CLI can also create an officer directly
   (`--role ward_officer --ward K/W`); set `ADMIN_PASSWORD` to script it.
3. Optional: `ADMIN_SESSION_HOURS` (default 12).
Accounts are not touched by `load_source_data.sql`. Reports, their history and contractor notices are truncated with the source data.

## Run locally
From the repo root, with the database already loaded (see `scorecard_planner/README.md` → Supabase / Postgres integration):
```bash
pip install -r requirements.txt     # Python 3.12/3.13; macOS: brew install libomp (xgboost)
cp .env.example .env                     # then fill in DATABASE_URL (Supabase Session pooler URI)
uvicorn backend.main:app --port 8000 --reload          # add --host 0.0.0.0 to serve the LAN
```

## API docs (Swagger)
- Swagger UI: http://127.0.0.1:8000/docs (grouped by view, with examples; "Try it out" works against the local DB)
- ReDoc: http://127.0.0.1:8000/redoc
- Spec: `GET /openapi.json`, committed as `backend/openapi.json` (import into Postman or a client generator).
  Regenerate after changing endpoints: `curl -s http://127.0.0.1:8000/openapi.json > backend/openapi.json`
- Every endpoint has a response model (`schemas.py`), so the spec is fully typed (31 schemas, enums for labels/codes,
  typed 404 `{detail}`). Generate a client from `backend/openapi.json`, e.g.
  `npx openapi-typescript backend/openapi.json -o src/api.d.ts` (TS types) or
  `openapi-generator-cli generate -i backend/openapi.json -g typescript-fetch -o src/api` (full client).

## Endpoints
| View | Method + path | Reads |
|---|---|---|
| — | `GET /api/health` | row counts |
| 1 | `GET /api/city` | `city_kpis` (incl. `rupees_at_stake_total`, `wards_over_budget`, `under_reported_wards`, `work_orders_count`, `complaints_count`, `reopened_within_30d_count`, `sla_met_rate`, `dlp_road_spend_inr`, `recoverable_dlp_rule`) |
| 1 | `GET /api/wards` (all, list) · `GET /api/wards?ward=K/W` or header `X-Ward-Code: K/W` (one, object; query wins; case-insensitive; 404 if unknown) | `ward_overview` |
| 1 | `GET /api/wards/{ward}/money-trail` | `wards` budget + `work_orders` by contractor / repair method, 30-day failures (one row per job) |
| 1 | `GET /api/wards/map` | GeoJSON: `data/wards.geojson` polygons + `ward_overview` in properties (colour by `dlp_leakage_rate`) |
| 1 | `GET /api/flagged-queue?ward=K/W&tier=1&detector=REPEAT_BILL_NO_COMPLAINT&limit=20&offset=0` | `flagged_queue` |
| 2 | `GET /api/roads?q=&ward=&limit=&offset=` | `road_audit` (road search / picker) |
| 2 | `GET /api/roads/{road_id}` | `road_audit` (incl. `segment_no`, `length_m`, `dlp_months`, `dlp_expires_on`), `work_orders` (+ `under_dlp_at_billing`), `flags`, `flag_replies` |
| 2 | `GET /api/roads/{road_id}/timeline` | `road_timeline` |
| 2 | `GET /api/roads/{road_id}/reports?limit=20` | citizen reports on the road (newest first, first photo) |
| 2 | `GET /api/flags/{flag_id}` | `flags`, `flag_replies` |
| 2 | `POST /api/flags/{flag_id}/replies` | writes `flag_replies` (Right-of-Reply). **Officer token required**, flag's ward only; stores `admin_id` |
| 2 | `POST /api/draft-notice` | Claude-written defect notice / RTI (en/hi/mr) from the flag's facts; filled template if Claude is slow or down (`generated_by`) |
| 3 | `GET /api/v3/contractors` | `v3_contractor_scorecard` |
| 3 | `GET /api/v3/wards` | `v3_ward_allocation` |
| 3 | `GET /api/v3/next-rupee/{ward}` | `v3_next_rupee` (`ward` = code or `ALL`) |
| 3 | `GET /api/v3/budget-range/{ward}` | slider min / max / default / step for a ward or `ALL` |
| 3 | `GET /api/v3/summary` | `v3_model_meta` (model quality + budget curve for the demo chart) |
| 3 | `GET /api/v3/contractor-performance/monthly?from=2025-06&to=2025-09&sort_by=speed_rank&min_jobs=0` | `contractor_monthly_scorecards`, `contractor_scorecard_runs` |
| 3 | `GET /api/v3/contractor-performance/contractors/{contractor_id}?from=&to=` | same (one contractor's monthly series; 404 if unknown) |
| 3 | `GET /api/v3/contractor-performance/methodology` | static: metric definitions, ranking rules, limitations |
| 3 | `POST /api/v3/allocate` | live MILP re-solve for a ward or `ALL` (`scorecard_planner/budget_allocator.py`) |
| 4 | `GET /api/localities?ward=` | `locality_list` (aliases as an array) |
| 4 | `GET /api/lookup?q=&language=` | road / locality match + `candidates` (nearest 3 roads, each with its latest work order) |
| 4 | `GET /api/livability?locality=` | `locality_livability` (1.5 km radius: flood spots, failure rate, jobs, hospital access roads) |
| 4 | `POST /api/citizen-query` | Claude plain-language reply (street_check / move_in) grounded in the lookup; template fallback |
| 4 | `POST /api/uploads/photo` | multipart `file` (JPEG/PNG/WebP/HEIC, max 8 MB; 413 / 415) → `{photo_id, photo_url, width, height, taken_at, exif_lat, exif_lon}` |
| 4 | `GET /api/uploads/photo/{photo_id}` | the stored photo (local) or a redirect to its Supabase public URL |
| 4 | `POST /api/citizen-reports` | report form: issue_type, photo_ids (≤3), location, landmark, flag_id, contact_phone (private) → road, duplicate_of, linked work order, responsible party, SLA, photos, tracker |
| 4 | `GET /api/citizen-reports/{id}` | same shape as the POST (incl. `tracker[]` {step, label, status, at}, `events[]`, `sla_due_at`, `rejection_reason`) |
| 4 | `POST /api/citizens` | anonymous account → `{citizen_id, token, display_name}` (token shown once) |
| 4 | `GET /api/me` · `GET /api/me/reports?status=` | citizen token: profile + stats (rupees from `flagged_queue`, each bill once) · own reports with history |
| 4 | `POST /api/citizen-reports/{id}/confirm` | citizen token (owner): `{fixed}` resolved → confirmed_fixed, or → reopened |
| A | `POST /api/admin/access-requests` · `GET /api/admin/access-requests?status=` · `POST …/{id}/approve` · `POST …/{id}/reject` | `admin_access_requests`, `admin_users` (approve/list: admin role) |
| A | `POST /api/auth/signup` · `POST /api/auth/login` | unified sign-in → `{token, role, ward_codes, name, email, …}` (`citizens` + `citizen_sessions`, or `admin_users` + `admin_sessions`) |
| A | `POST /api/admin/login` · `POST /api/admin/logout` · `GET /api/admin/me` | `admin_users`, `admin_sessions` |
| A | `GET /api/admin/summary?ward=` | report counts by status, new today, overdue SLA, median hours to resolve, rupees held, flags awaiting reply |
| A | `GET /api/admin/reports?ward=&status=&kind=&issue_type=&q=&sort=&page=` · `GET /api/admin/reports/{id}` | report queue (array; `X-Total-Count` / `X-Page` / `X-Page-Size` headers) · full triage detail |
| A | `PATCH /api/admin/reports/{id}` | status transition (`report_lifecycle.py`), note, duplicate_of, rejection_reason, repair_due_at → `citizen_report_events` |
| A | `POST /api/admin/reports/{id}/notify-contractor` | records a `contractor_notices` row (drafted via draft-notice when no message); nothing is sent |
| A | `GET /api/admin/flags?ward=&awaiting_reply=` | flags in scope with reply counts |

View `A` = Admin (officer/admin bearer token from `POST /api/admin/login`; ward officers see only their wards).
Lifecycle, auth rules and examples for the frontend: `docs/api_reference.md`.

Ward codes are accepted as `K/W`, `K-W` or `k_w` everywhere (the frontend contract uses `K-W`; the database stores `K/W`).

Claude endpoints need credentials: `ANTHROPIC_API_KEY` in the environment or repo-root `.env` (or an `ant auth login` profile). Without them they serve templates. `CLAUDE_TIMEOUT_S` (default 25; Claude drafts take ~12-14 s) sets the cut-over to the template.

## Monthly contractor scorecards (`backend/features/contractor_performance/`)
Separate, explainable **monthly** ranks for comparing contractors on future work: speed, SLA, durability and
rate-card cost alignment. There is **no composite score**. This sits next to the season-level, context-adjusted
`GET /api/v3/contractors` and does not change it.

| File | Role |
|---|---|
| `router.py` | FastAPI routes (read-only), registered in `main.py` |
| `schemas.py` | response models (in `/openapi.json`) |
| `service.py` | refresh orchestration, read/shape, methodology text |
| `repository.py` | Postgres reads/upsert, CSV source (debug), in-memory store (tests) |
| `processor.py` | pure, deterministic aggregation and ranking (no I/O) |
| `config.py` | versioned parameters (`v1`: tolerance 30%, min sample 5, min cohort 3) |
| `exporter.py`, `refresh.py` | JSON snapshot (debugging only), refresh CLI |

**Setup / refresh.** Apply `supabase/migrations/20261121000700_contractor_monthly_scorecards.sql` (safe to re-run;
rollback is in its header), load the sources as usual, then recompute and upsert from the repo root:
```bash
python -m backend.features.contractor_performance.refresh                     # upsert methodology v1 (DATABASE_URL from .env)
python -m backend.features.contractor_performance.refresh --csv-dir data --dry-run --export /tmp/cp.json   # no DB
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

Tests (no database): `pytest backend/tests -q` (from the repo root).

## Changing an endpoint (e.g. View 2)
- Each view's routes are in `routes/<view>.py` (View 2: `routes/road_story.py`). New endpoint for a view → add it to that file.
- SQL views they read are in `supabase/migrations/20261121000100_audit_views.sql` (`road_audit`, `road_timeline`, `flagged_queue`).
  Change the schema with a **new** migration file rather than editing an applied one (all three are applied on Supabase).
- Full schema at a glance (every table, view, constraint, RLS policy): `supabase/schema_snapshot.sql`. Reference snapshot
  dumped from Supabase; don't run it. Regenerate it after a schema change (command in its header).
- Every route declares `response_model=` from `schemas.py`. Change the model with the SQL view/table it mirrors.
  Run with `STRICT_MODELS=1` while developing/testing: an undeclared or mistyped field then fails loudly (500)
  instead of being silently dropped from the response.
- Validate request bodies with Pydantic models, query params with `Query(...)`. Use `rows()` / `one()` for reads
  (`%(name)s` params; never format user input into SQL) and `ENG.begin()` + `text()` for writes.
- Numbers come from the database/pipeline; endpoints only select and shape. No arithmetic in prompts or UI.
- Update `postman/backend.postman_collection.json` and run it against an API started with `STRICT_MODELS=1`:
  `postman collection run postman/backend.postman_collection.json --working-dir .` (counts in the run summary).
  The Admin folder logs in with the `adminEmail` / `adminPassword` collection variables, so create that admin with
  `admin_cli` first (default variables: `ops@example.org` / `change-me-please`; change both for a shared database).
  Last full run: 122 requests, 290 assertions, 0 failures.
- Unit tests (no database): `pytest backend/tests -q`.
