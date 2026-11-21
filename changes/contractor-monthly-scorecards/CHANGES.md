# Change log: monthly contractor scorecards

**Branch:** `feat/contractor-monthly-scorecards` (from `origin/main` @ `d6f6568`)
**Scope:** backend only (FastAPI + Supabase). No UI changes. The View 2 audit rules and the existing View 3 scorecard (`GET /api/v3/contractors`) are unchanged.

## What this adds
The backend now has **monthly, per-contractor scorecards** to help compare contractors for future work. Each contractor-month gets four **separate** ranks: speed, SLA, durability and rate-card cost alignment. **There is no composite score or "best contractor" verdict.**

Rows are computed deterministically by a CLI and stored in Supabase. FastAPI serves them, and the React app reads them **only through FastAPI**, never from Supabase directly.

How this differs from the existing `GET /api/v3/contractors`:

| | `/api/v3/contractors` (existing) | `/api/v3/contractor-performance/*` (new) |
|---|---|---|
| Grain | whole season | contractor × calendar month |
| Method | XGBoost context-adjusted, composite `risk_adjusted_score` | raw recorded outcomes, 4 independent ranks |
| Context | used for adjustment | descriptive only, never adjusts ranks |

## Where the files are
The code stays in its working locations, because the API imports it from `backend/` and Supabase applies files from `supabase/migrations/`. This folder holds only this log and a patch.

### New files
| File | Purpose |
|---|---|
| [backend/features/contractor_performance/router.py](../../backend/features/contractor_performance/router.py) | FastAPI routes (read-only) |
| [backend/features/contractor_performance/schemas.py](../../backend/features/contractor_performance/schemas.py) | Pydantic response models (typed OpenAPI) |
| [backend/features/contractor_performance/service.py](../../backend/features/contractor_performance/service.py) | Refresh orchestration, read and shape, methodology text |
| [backend/features/contractor_performance/repository.py](../../backend/features/contractor_performance/repository.py) | Postgres reads and upsert; CSV source (debugging); in-memory store (tests) |
| [backend/features/contractor_performance/processor.py](../../backend/features/contractor_performance/processor.py) | Pure, deterministic aggregation and ranking (no I/O) |
| [backend/features/contractor_performance/config.py](../../backend/features/contractor_performance/config.py) | Versioned methodology parameters |
| [backend/features/contractor_performance/refresh.py](../../backend/features/contractor_performance/refresh.py) | Refresh CLI |
| [backend/features/contractor_performance/exporter.py](../../backend/features/contractor_performance/exporter.py) | Optional JSON snapshot (debugging only, not the source of truth) |
| [backend/features/__init__.py](../../backend/features/__init__.py), `contractor_performance/__init__.py` | Package markers |
| [supabase/migrations/20261121000200_contractor_monthly_scorecards.sql](../../supabase/migrations/20261121000200_contractor_monthly_scorecards.sql) | New tables, constraints, index, RLS |
| [backend/tests/test_contractor_performance.py](../../backend/tests/test_contractor_performance.py), [conftest.py](../../backend/tests/conftest.py) | 18 pytest tests (no database needed) |

### Existing files modified
The exact diff is in [modified_existing_files.patch](modified_existing_files.patch). `openapi.json` is left out because it is generated.

| File | Change |
|---|---|
| `backend/api.py` | +3 lines: import the feature router, pass it the shared engine, and `include_router` |
| `supabase/load_source.sql` | Adds the 2 new tables to the `truncate` list. **This is required**: they reference `contractors`, so without it the reload fails. |
| `backend/openapi.json` | Regenerated with `STRICT_MODELS=1`. The 3 new paths and their schemas are added; existing paths and schemas are unchanged. |
| `postman/backend.postman_collection.json` | 5 new requests under "View 3", making 33 requests and 83 assertions in total |
| `backend/README.md` | Endpoint table rows and a "Monthly contractor scorecards" section |
| `view3/README.md` | Refresh step for the new tables; updated test counts |
| `view3/requirements.txt` | Adds `pytest` and `httpx` (for tests only) |

## Database
**`contractor_monthly_scorecards`** has one row per `(contractor_id, month, methodology_version)`, which is the primary key.
- Foreign keys point to `contractors` and to `contractor_scorecard_runs` (with cascade on delete).
- `month` is stored as the first day of the month; the API returns it as `YYYY-MM`.
- Typed columns cover jobs, billed INR, and for SLA, reopens, speed and cost: the known, missing and value counts plus each rank.
- JSONB columns: `rank_eligibility`, `rank_cohort_sizes`, `workload_mix`, `context`, `data_quality`.
- `evidence_work_order_ids` is a `text[]`.
- CHECK constraints make every denominator add up to `completed_jobs`.
- An index on `(methodology_version, month)` serves the monthly list.

**`contractor_scorecard_runs`** has one row per methodology version, holding its parameters, source row counts and run-level data quality.

**RLS** is enabled on both tables with **no anon or authenticated policy**. Only the backend, connecting with `DATABASE_URL`, can read or write them. This is deliberate: the frontend goes through FastAPI.

**Rollback:** `drop table if exists contractor_monthly_scorecards, contractor_scorecard_runs;` drops processed output only; re-run the refresh to rebuild.

## Setup (once per environment)
```bash
# repo root, after the existing migrations
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/20261121000200_contractor_monthly_scorecards.sql
# after load_source.sql (which now truncates these tables)
cd backend && python -m features.contractor_performance.refresh
```
- The refresh is **CLI-only**; the public API has no write route.
- It is idempotent. In one transaction it upserts the run row, deletes stale rows for that version, and upserts all rows.
- GET requests only read the stored rows.
- To debug without a database: `python -m features.contractor_performance.refresh --csv-dir ../data --dry-run --export /tmp/cp.json`

## API (for the frontend team)
All routes are `GET` and live under the `View 3` tag in Swagger (`/docs`).

| Route | Returns |
|---|---|
| `/api/v3/contractor-performance/monthly?from=YYYY-MM&to=YYYY-MM&sort_by=speed_rank&min_jobs=0&methodology_version=v1` | `{methodology_version, sort_by, run, months: [{month, contractors: [...]}]}` |
| `/api/v3/contractor-performance/contractors/{contractor_id}?from=&to=` | One contractor's monthly series (404 if the contractor is unknown; empty `months` if there are no jobs in range) |
| `/api/v3/contractor-performance/methodology` | Metric definitions, directions, tie rule, eligibility, limitations |

- `sort_by` can be `speed_rank`, `sla_rank`, `durability_rank`, `cost_rank`, `completed_jobs` or `contractor_id`. Null ranks sort last, then by `contractor_id`.
- `min_jobs` **only hides rows**; ranks stay as stored.
- Errors:
  - 422 for a bad month format, `from` > `to`, or an unknown version or sort.
  - 404 if the refresh has never been run.
  - 503 if the database is unavailable.

Each contractor-month row contains:
- `speed`, `sla`, `durability` and `cost_alignment`, each with its counts, `rate` or value, `rank` (nullable) and `cohort_size`
- `rank_eligibility[dimension].reason`, which explains any null rank (e.g. `"sample 3 < min 5"`)
- `workload_mix`, `context`, `data_quality` and `evidence_work_order_ids`

Amounts are INR numbers; format them as Lakhs or Crores in the UI.

## Methodology `v1`
| Dimension | Metric | Better |
|---|---|---|
| Speed | Median of (earliest linked complaint → `completed_at` hours) ÷ (the same month's city median for the same `repair_method`). Raw median hours, the peer cohort median, a per-method breakdown and an assigned→completed **proxy** (never ranked) are shown alongside. | lower |
| SLA | `sla_met` true / known | higher |
| Durability | `reopened_within_30d` true / known | lower |
| Cost alignment | Median absolute(cost − benchmark) / benchmark. The benchmark is `area_sqm × rate` for per-sqm methods and `rate` for per-job methods. Jobs more than 30% over are counted; jobs more than 30% under are only reported, so cheapness isn't rewarded. | lower |

- **Month:** a job belongs to the calendar month of `completed_at`. Jobs without a completion date get no month row and are counted in `run.data_quality`.
- **Eligibility** is checked per dimension: a dimension is ranked only if its known sample is ≥ 5.
- **Ties:** values are rounded to 6 decimals, then equal values share the best rank (1, 2, 2, 4).
- **Null outcomes** count as `missing`, never as a success or a failure.
- **No fan-out:** every context table is aggregated to its own grain (date, ward or road) before it is joined once per job.
- **Ward check:** if a work order's ward differs from `roads.ward_code`, it is listed in `data_quality` rather than silently resolved.
- **Context is descriptive only, never evidence of fault.** It covers:
  - regional rain (the daily max across Santacruz and Colaba over the work window)
  - city-level big-tide days
  - jobs in flood-hotspot wards
  - job-weighted traffic
  - same-month accidents on the roads the contractor serviced
  - jobs on ambulance-entry roads

  Each block reports its coverage and is `null` if its source table is missing.
- Changing any parameter means adding a new version in `config.py`, so old rankings stay reproducible.

## Verification done
- `cd backend && pytest tests -q`: **18 passed**. The tests cover month assignment, no double-counting, denominators, speed normalization, per-dimension eligibility, ties, cost tolerance, ward mismatch, missing context, idempotency, the upsert SQL, routes and validation.
- Real CSVs (dry run): 40 contractor-month rows, 2,499 jobs, ₹13.43 Cr billed, matching the CSV totals exactly.
- A temporary local Postgres (since deleted):
  - the migration applied twice cleanly;
  - the refresh ran twice and the row count stayed at 40;
  - the CSV and database paths gave identical output;
  - all 3 routes returned correct responses under `STRICT_MODELS=1`;
  - `api.py` imports with the router registered.
- **Not yet done:** running against the team's Supabase project (no credentials were available) and running the Postman collection (the CLI is not installed).

## Known data notes and limitations
- The dataset is synthetic, and all contractors are fictional.
- October 2025 has only 36 jobs, so several contractors are unranked that month (by design).
- 45 work orders have no linked complaint, so they are excluded from speed (reported under `speed_missing_reasons`).
- Rain is regional and tides are city-level; flood-hotspot exposure is ward-level, not distance-based.
- Ranks describe recorded outcomes. Use the neutral wording "Needs Explanation", never an accusation.
