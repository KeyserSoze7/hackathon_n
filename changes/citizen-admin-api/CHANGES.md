# Change log: citizen accounts + admin / ward-officer dashboard APIs

**Branches:**
- `feat/citizen-admin-api`: the feature, based on `main` @ `0aea2c1`.
- `merge/citizen-admin-api`: the feature merged into the latest `main` (`6dacbc5`), plus the frontend-compatibility
  layer described below. This is the branch to review and merge.
**Scope:** backend only (FastAPI + Supabase). No UI. This is the backend for the frontend's citizen "my reports" flow
and the officer dashboard.
**Frontend guide:** [docs/api_reference.md](../../docs/api_reference.md), in the sections *Citizen accounts*, *Report
lifecycle* and *Admin & ward-officer dashboard*. The exact shapes are in Swagger (`/docs`) and `backend/openapi.json`.

## What this adds
- **Citizen accounts, with no login wall.** `POST /api/citizens` returns a bearer token, which the app stores and sends
  on citizen calls. With it, the citizen can use:
  - `GET /api/me`: profile and stats, with rupees computed on the server
  - `GET /api/me/reports`: their reports, each with its history
  - `POST /api/citizen-reports/{id}/confirm`: confirm a fix holds, or reopen the report
- **Officer dashboard**:
  - access requests (an admin approves them)
  - email + password login
  - a summary of tiles
  - a paged report queue and a full triage detail view
  - `PATCH` to change status, with validated transitions
  - a contractor notice record
  - flags awaiting reply
- **Report lifecycle**: `reported → matched_to_contract → payment_held (DLP surface only) → contractor_notified →
  resolved → confirmed_fixed | reopened`. A report can also become `rejected` or `duplicate`. Every change is written
  to a history (`events[]`).
- The earlier "still pending" items (`/api/roads?q=`, `/api/localities`, `/api/livability`, `draft-notice`,
  `citizen-query`, `uploads/photo`) **already existed on main**. Nothing was rebuilt.

## Frontend compatibility (`merge/citizen-admin-api`)
The frontend on `pratham` (`f572cf9`) already has a client for these APIs. Where its calls differed from the first
version of the backend, the backend now matches the frontend:

| Frontend expects | Backend now |
|---|---|
| One email + password sign-in: `POST /api/auth/signup`, `POST /api/auth/login` → `{token, role: citizen\|ward_officer\|admin, ward_codes, name, email}` | **Added** in `routes/accounts.py`. Login checks officer/admin accounts first, then citizen accounts. `citizens` gains `email` and `password_hash`, and `citizen_sessions` holds one token per device. `POST /api/citizens` (anonymous) and `POST /api/admin/login` still work |
| The same session token sent on every call | An officer token on a citizen call (e.g. filing a report) is treated as **anonymous**, not 401 |
| `GET /api/admin/reports` returns an array | **Array.** Paging is in the `X-Total-Count`, `X-Page` and `X-Page-Size` headers, exposed through CORS. `GET /api/admin/flags` follows the same pattern |
| `events[].status` and `events[].by_role` | **Added** alongside `to_status` and `actor` |
| `GET /api/wards/{ward}/money-trail` | **Built** in `routes/city_overview.py`: budget vs spend, by contractor and by repair method, and 30-day failures. One row per job, and a summary sentence computed from the numbers |

Merging: `merge/citizen-admin-api` merges into `main` with no conflicts. A trial merge of `pratham` shows 3 frontend
conflicts (`api.ts`, `types.ts`, `Start.tsx`). Those conflicts exist **between `pratham` and `main` with or without this
branch**; this work touches no frontend file.

## ⚠ Behaviour changes for the frontend
| Before | Now | What to do |
|---|---|---|
| A new DLP pothole report was auto-set to `payment_held` | A new report stops at `matched_to_contract`. `payment_hold_eligible: true` tells officers they may set the hold | Show `payment_hold_eligible` as "eligible for payment hold" instead of assuming it is held |
| The tracker had 4 steps and `done\|current\|pending` | It has 6 steps (adds `resolved` and `confirmed_fixed`), plus the step statuses `skipped` and `stopped` | Render the 2 extra steps, and grey out `skipped`/`stopped` |
| `POST /api/flags/{id}/replies` was anonymous | It needs an officer or admin token for the flag's ward: **401** without a token, **403** outside the officer's wards | `pratham`'s client already sends the officer token. The older RoadReceipt on `main` shows an error until `pratham` is merged |
| The report `status` enum had 4 values | It has 9 (see the lifecycle) | Update `TrackerStatus` in `frontend/src/data/types.ts` |

## Files
### New
| File | Purpose |
|---|---|
| [supabase/migrations/20261121000800_citizen_accounts_admin.sql](../../supabase/migrations/20261121000800_citizen_accounts_admin.sql) | Tables `citizens`, `admin_users`, `admin_sessions`, `admin_access_requests`, `citizen_report_events`, `contractor_notices`. Adds `citizen_reports.citizen_id/rejection_reason/repair_due_at/resolved_at`, the 9-status check and `flag_replies.admin_id`. Drops the anon insert policy on `flag_replies`. Safe to re-run; the rollback is in the header |
| [backend/auth.py](../../backend/auth.py) | Tokens (`cit_…` / `adm_…`, only the sha256 is stored), scrypt passwords, FastAPI dependencies for citizen, admin and ward scope |
| [backend/report_lifecycle.py](../../backend/report_lifecycle.py) | Statuses, the transition table, citizen confirmation, `sla_due_at` and tracker steps. Pure functions |
| [backend/routes/citizen_accounts.py](../../backend/routes/citizen_accounts.py) | `POST /api/citizens`, `GET /api/me`, `GET /api/me/reports`, `POST /api/citizen-reports/{id}/confirm` |
| [backend/routes/admin.py](../../backend/routes/admin.py) | All `/api/admin/*` routes |
| [backend/routes/accounts.py](../../backend/routes/accounts.py) | `POST /api/auth/signup`, `POST /api/auth/login` (unified sign-in) |
| [backend/admin_cli.py](../../backend/admin_cli.py) | `python -m backend.admin_cli create-admin`: bootstraps the first admin |
| [backend/tests/test_citizen_admin.py](../../backend/tests/test_citizen_admin.py) | 28 unit tests for auth primitives, transitions, confirmation, SLA and tracker |

### Changed
| File | Change |
|---|---|
| `backend/routes/citizen.py` | Report insert stores `citizen_id` (optional token), stops at `matched_to_contract` and writes a `created` event. `build_report` adds `events`, `sla_due_at`, `repair_due_at`, `resolved_at`, `rejection_reason` and `payment_hold_eligible`. Shared helpers added: `add_event`, `report_events`, `check_photo_ids`, `hold_eligible` |
| `backend/routes/road_story.py` | Right-of-Reply needs an officer token scoped to the flag's ward. `author_name` defaults to the account; `admin_id` is stored |
| `backend/database.py` | `invalid()` (the shared 422 helper) moved here; `parse_ts()` added; `rows()` returns uuid columns as strings |
| `backend/schemas.py` | `ReportStatus` (9 values; `TrackerStatus` kept as an alias), `TrackerStep`, `ReportEvent`, the new `CitizenReport` fields, `AUTH`/`CONFLICT` responses, and the citizen and admin models |
| `backend/main.py` | Registers the two routers, adds the "Admin" tag and updates the API description |
| `backend/response_examples.json` | Real captured examples for the new POST responses. `CitizenReport` was refreshed; tokens and passwords are redacted |
| `backend/openapi.json` | Regenerated: 15 new paths, 27 new schemas. Existing paths are unchanged, apart from the 3 above |
| `supabase/load_source_data.sql` | Truncate list now includes `citizen_report_events` and `contractor_notices`. Accounts survive a reload |
| `backend/routes/city_overview.py` | `GET /api/wards/{ward}/money-trail` |
| `postman/backend.postman_collection.json` | Adds 9 citizen requests to View 4, 3 money-trail requests to View 1, a new Admin folder (35 requests) and a new Accounts folder (11 requests). Existing reply and DLP-report tests are updated to the new behaviour, and the endpoint count is now 47 |
| `docs/api_reference.md`, `backend/README.md`, `.env.example` | Docs, setup steps and `ADMIN_SESSION_HOURS` |

## Database and RLS
- All new tables are **private**: RLS is on, there is no policy, and everything is revoked from `anon` and
  `authenticated`. This is the same pattern as `citizen_report_contacts`. Only FastAPI (using `DATABASE_URL`) can
  read or write them.
- `citizen_reports` keeps its existing public read, as decided. That means `citizen_id` (a random uuid, with no name
  or phone) can be read with the public key and used to group one person's reports. If this becomes a concern,
  revoke public read on that table in a later migration; the API doesn't depend on it.
- There are no foreign keys from accounts to source tables (the ward code is validated in the API), so
  `load_source_data.sql` never wipes accounts.

## Setup (once per environment)
```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/20261121000800_citizen_accounts_admin.sql
python -m backend.admin_cli create-admin --email <ops email> --name "Ops Admin"     # prompts for a password
```

## Verification done
- `pytest backend/tests -q`: 46 passed (28 new and 18 existing), on both branches.
- On a throwaway Postgres in `/tmp` (deleted afterwards), with stand-in `anon`/`authenticated` roles:
  - All migrations `0000`–`0800` applied in order, and `0800` re-ran cleanly.
  - `load_source_data.sql` and `load_audit_outputs.sql` loaded, followed by the View 3 pipeline and the scorecard refresh.
  - The anon role is denied `SELECT` on all 6 private tables.
  - The anon insert policy on `flag_replies` is gone; `citizen_reports` keeps its policies.
- **Postman (newman) against `uvicorn backend.main:app` with `STRICT_MODELS=1`, on `merge/citizen-admin-api`: 122 requests, 290 assertions, 0 failures.**
- The updated `0800` also re-applies cleanly over a database that already ran the first version of `0800`.
- A separate end-to-end script passed 92/92 checks. It covered:
  - citizen stats, including a bill counted only once
  - ward scoping, with 403s
  - illegal transitions, with 422s
  - duplicate chains
  - the notice going to the flagged bill's contractor
  - a full resolve → reopen → confirm cycle
  - no officer identity appearing in the history

## Not done / follow-ups
- **`supabase/schema_snapshot.sql` is not regenerated.** It's a `pg_dump` from Supabase (Postgres 17); a local
  Postgres 15 dump would rewrite the whole file. After applying `0800` on Supabase, run the command in its header.
- Nothing is applied to the team's Supabase project yet, because no credentials were available here.
- `notify-contractor` **records** a notice; it doesn't send email, SMS or letters.
- Phone numbers (`citizens.phone`, report contact phones) are stored for later SMS. No endpoint returns them.
- There is no login rate limiting yet. Add it at the proxy level, or as a small table, before a public deployment.
