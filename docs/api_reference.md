# API reference (frontend)

Source of truth: Swagger UI at `<base>/docs` and the spec `backend/openapi.json` (every response is typed and
the POSTs carry real example responses). This page is the quick map. Backend code: `backend/README.md`.

## Conventions

- **Base URL**: the host running `uvicorn backend.main:app` (on the venue LAN: `http://10.10.38.50:8000`).
- **Ward codes**: responses always use `K/W`. Inputs accept `K/W`, `K-W` or `k_w`. `ALL` = city-wide where noted.
- **Timestamps**: ISO 8601 in IST with offset, e.g. `2025-06-22T02:59:00+05:30`. Dates: `YYYY-MM-DD`.
- **Money**: whole rupees (integers, INR). Format for display on the client (₹42.5L, ₹1.80 Cr).
- **Errors**: `404 {detail: "unknown ..."}`; `422 {detail: [{loc, msg, type}]}` (same shape for every 422);
  uploads also `413` (too large) and `415` (not a supported image).
- **Auth**: no login wall for citizens. Public reads stay anonymous. Signed-in calls send
  `Authorization: Bearer <token>`:
  - citizen token (`cit_…`) from `POST /api/citizens`: keep it on the device, it is shown once and never expires;
  - officer/admin token (`adm_…`) from `POST /api/admin/login`: expires after `ADMIN_SESSION_HOURS` (default 12).
  `401` = missing/invalid/expired token, `403` = signed in but wrong role or ward, `409` = conflicts with the
  report's current state. All are `{detail: "..."}`.
- **Labels**: flags read *Needs Explanation* or *Recoverable under DLP*. Never "fraud".
- **Claude endpoints** (`draft-notice`, `citizen-query`) take ~7-19 s and never fail because of Claude: on a slow
  or failed call they return a filled template (`generated_by: "template"`). Show a loading state.

## Demo-critical (items 1-5)

### 1. Photo upload: `POST /api/uploads/photo`
Multipart field `file`: JPEG, PNG, WebP or HEIC, max 8 MB.
Response 201: `{photo_id, photo_url, width, height, taken_at, exif_lat, exif_lon}`.
EXIF (time, GPS) is read into the response, then stripped from the stored image. HEIC is stored as JPEG.
Photos are stored in Supabase Storage (public bucket `report-photos`); `photo_url` loads directly in an `<img>`.
`GET /api/uploads/photo/{photo_id}` serves (or redirects to) the image.

### 2. Report form: `POST /api/citizen-reports`
Request (all optional except what you have). Send the citizen token, if the app has one, to save the report to
"my reports"; without it the report is anonymous (and cannot be confirmed later):
```json
{
  "issue_type": "pothole | waterlogging | open_manhole | broken_paver | cave_in | choked_drain | other",
  "photo_ids": ["<up to 3 from /api/uploads/photo>"],
  "location": {"lat": 19.0058, "lon": 72.8425, "accuracy_m": 12, "source": "gps | map_pin | exif | landmark | manual"},
  "landmark": "opposite KEM Hospital gate",
  "road_id": "RD0048", "flag_id": "DLP_PAID_TWICE:WO25-01947", "work_order_id": null,
  "kind": "still_broken | verified_fixed | new_issue",
  "contact_phone": "+91 98200 00000",
  "input_mode": "text | voice | photo | qr", "language": "en | hi | mr", "text": "free text / voice transcript"
}
```
- Road: `road_id`, else the nearest road within 500 m of `location`, else `landmark`/`text` lookup.
- `kind` defaults to `still_broken` when a matching work order exists, else `new_issue`.
- `contact_phone` is stored privately and is never returned (not even with the Supabase public key).

Response 201 (and `GET /api/citizen-reports/{id}`, same shape):
`{report_id, kind, issue_type, status, road{road_id, road_name, ward_code, under_dlp}, duplicate_of,
linked_work_order_id, responsible{party, name, ward_office, basis}, sla_hours, photos[{photo_id, photo_url, width,
height}], tracker[{step, label, status: done|current|pending|skipped|stopped, at}], flag_id, landmark, location,
input_mode, language, text, matched_locality, created_at, events[{at, event_type, actor, from_status, to_status, note,
photo_ids[]}], sla_due_at, repair_due_at, resolved_at, rejection_reason, payment_hold_eligible}`
- A new report **stops at `matched_to_contract`** (or `reported` if no road matched). Payment is no longer auto-held:
  `payment_hold_eligible: true` (surface defect on a road under DLP) tells the officer they may set `payment_held`.
  The DLP flag is still auto-linked (`flag_id`). Full lifecycle: see *Report lifecycle* below.
- `tracker` has 6 steps: reported, matched_to_contract, payment_held, contractor_notified, resolved, confirmed_fixed.
  `skipped` = payment hold not applicable; `stopped` = report was rejected or marked duplicate.
- `events[]` is the history (oldest first). `actor` is `citizen`, `ward_office` or `system`, never an officer's name.
- `sla_due_at` = the officer's `repair_due_at` if set, else `created_at + sla_hours` (null without an issue type).
- `responsible.party`: `contractor_under_dlp` (DLP surface defect, contractor fixes at no cost to BMC) or `bmc_ward`.
- `duplicate_of`: earlier report for the same road + issue in the last 7 days.
- `sla_hours`: typical SLA for the issue type (median of matching work orders).

### 3. Road search: `GET /api/roads?q=&ward=&limit=&offset=`
`[{road_id, road_name, segment_no, ward_code, under_dlp, total_billed_inr, rupees_at_stake, flagged_bills_count}]`.
`q` matches road name or road id. `limit` 1-500 (default 50).

### 4. Defect notice / RTI (Claude): `POST /api/draft-notice`
Request `{flag_id | road_id, language: en|hi|mr, doc_type: defect_notice|rti}` (one of flag_id / road_id).
Response `{title, body, cited_row_ids[], flag_id, road_id, language, doc_type, generated_by: claude|template}`.
`cited_row_ids` come from the flag's evidence, never from the model.

### 5. City totals: `GET /api/city`
KPI strip plus `work_orders_count`, `complaints_count`, `reopened_within_30d_count` (failed repairs), `sla_met_rate`,
`dlp_road_spend_inr` (all spend on DLP roads) and `recoverable_dlp_rule` (one sentence: why `recoverable_dlp_inr`
is smaller than `dlp_road_spend_inr`).

## After the demo (items 6-12)

| # | Endpoint | Returns |
|---|---|---|
| 6 | `GET /api/roads/{road_id}/reports?limit=20` | `[{report_id, kind, issue_type, created_at, status, photo_url}]`, newest first |
| 7 | `GET /api/localities?ward=` | `[{locality, ward_code, lat, lon, aliases[]}]` |
| 8 | `GET /api/livability?locality=` | `{flood_hotspots_1500m, failure_rate_30d_1500m, jobs_1500m, hospital_access_roads_1500m, ward_dlp_leakage_rate, nearby_road_ids[]}` (+ locality, ward_code, lat, lon, radius_m) |
| 9 | `GET /api/lookup?q=&language=` | match + `matched_locality` + `candidates[]`: nearest 3 roads with `road_distance_m` and `latest_work_order{work_order_id, contractor_id, contractor_name, cost_inr, completed_at, sla_met, reopened_within_30d}` |
| 10 | `POST /api/citizen-query` `{text, language, mode: street_check|move_in}` | `{matched_locality, matched_road_id, plain_language_reply, warranty_status, generated_by, lookup, livability}`; no match is still 200 |
| 11 | `GET /api/roads/{road_id}` | road header incl. `segment_no`, `length_m`, `dlp_months`, `dlp_expires_on`, `dlp_rule`; each work order has `under_dlp_at_billing` |
| 12 | `GET /api/v3/next-rupee/{ward or ALL}`, `POST /api/v3/allocate {ward_code: ward or ALL, budget_inr}`, `GET /api/v3/budget-range/{ward or ALL}` | city-wide planner; slider `{min_inr, max_inr, default_inr, step_inr}` |

Note on item 11: the dataset says whether a road is under DLP but has no expiry. A 36-month DLP is assumed
(every DLP road was resurfaced 5-33 months before Oct 2025); `dlp_expires_on` is an estimate.

## Monthly contractor scorecards (View 3)

Four separate monthly ranks per contractor (speed, SLA, durability, rate-card cost alignment), raw recorded outcomes,
no composite score. Complements the season-level, context-adjusted `GET /api/v3/contractors`.

| Endpoint | Returns |
|---|---|
| `GET /api/v3/contractor-performance/monthly?from=2025-06&to=2025-09&sort_by=speed_rank&min_jobs=0` | one block per month; each contractor-month has the four ranks (null with a reason when its sample is too small), denominators, context and evidence work-order IDs |
| `GET /api/v3/contractor-performance/contractors/{contractor_id}?from=&to=` | one contractor's monthly series (404 if unknown) |
| `GET /api/v3/contractor-performance/methodology` | metric definitions, ranking and tie rules, eligibility, limitations |

Data is computed by `python -m backend.features.contractor_performance.refresh` (rerun after each data load).

## Citizen accounts (View 4)

| Endpoint | Auth | Returns |
|---|---|---|
| `POST /api/citizens` `{display_name?, phone?}` | none | 201 `{citizen_id, token, display_name}`. Token shown once. `phone` (optional, for SMS later) is stored privately, never returned. Default name `Citizen XXXX` |
| `GET /api/me` | citizen | `{citizen_id, display_name, joined_at, stats{reports, roads, open, resolved, confirmed_fixed, rupees_flagged_inr, rupees_held_inr}}` |
| `GET /api/me/reports?status=` | citizen | newest first: `[{id, kind, issue_type, road{road_id, road_name, ward_code, under_dlp}, status, created_at, photo_url, flag{flag_id, rupees_at_stake}, events[]}]`. `status` = one status, or `open` / `closed` |
| `POST /api/citizen-reports/{id}/confirm` `{fixed, note?, photo_ids?}` | citizen (report owner) | the full report. `fixed: true` resolved → confirmed_fixed; `fixed: false` resolved/confirmed_fixed → reopened. Other statuses 409; someone else's report 403 |
| `GET /api/citizen-reports/{id}` | none | now also `events[]`, `sla_due_at`, `rejection_reason` (see item 2) |

Stats, computed on the server:
- `roads`: distinct roads reported on.
- `open`: reports not in a closed status.
- `resolved`: resolved + confirmed_fixed.
- `rupees_flagged_inr`: sum of `rupees_at_stake` on the flagged bills matched to this citizen's reports. Each bill is
  counted once, even when several reports or flags point at it.
- `rupees_held_inr`: the same sum, for reports currently in `payment_held`.

## Report lifecycle

```
reported ──► matched_to_contract ──► payment_held (DLP surface defect only) ──► contractor_notified
                     │                                                    ▲          │
                     └────────────────────────────────────────────────────┘          ▼
                                     resolved (officer) ──► confirmed_fixed (citizen confirms)
                                         └──► reopened (citizen: still broken) ──► back to contractor_notified / resolved
rejected (needs rejection_reason) and duplicate (needs duplicate_of) can be set from any open status.
```

| From | Officer may set (`PATCH /api/admin/reports/{id}`) |
|---|---|
| reported | matched_to_contract, rejected, duplicate |
| matched_to_contract | payment_held\*, contractor_notified, resolved, rejected, duplicate |
| payment_held | contractor_notified, resolved, rejected, duplicate |
| contractor_notified | resolved, rejected, duplicate |
| reopened | payment_held\*, contractor_notified, resolved, rejected, duplicate |
| resolved | reopened |
| confirmed_fixed, rejected, duplicate | (final) |

\* only when `payment_hold_eligible`. Only the citizen moves `resolved` to `confirmed_fixed`.
`open` = reported, matched_to_contract, payment_held, contractor_notified, reopened.

## Admin & ward-officer dashboard

Roles:
- `admin`: every ward; approves access requests.
- `ward_officer`: only the wards in their `ward_codes`.

A report belongs to its matched road's ward, else to its matched locality's ward. Reports with neither are visible
to admins only. The first admin is created on the server with `python -m backend.admin_cli create-admin` (see
`backend/README.md`).

| # | Endpoint | Auth | Returns |
|---|---|---|---|
| 8 | `POST /api/admin/access-requests` `{name, email, designation, ward_code, reason}` | none | 201 `{request_id, status: "pending"}`. 409 if a request for that email is pending or it already has an account; 422 unknown ward |
| 9 | `GET /api/admin/access-requests?status=` | admin | `[{request_id, name, email, designation, ward_code, reason, status, created_at, decided_at, decision_note, admin_id}]`, pending first |
| 9 | `POST /api/admin/access-requests/{id}/approve` | admin | `{request_id, status: "approved", email, admin_id, temporary_password}`: creates the ward officer for that ward. **The password is shown once**; pass it to the officer |
| 9 | `POST /api/admin/access-requests/{id}/reject` `{reason}` | admin | `{request_id, status: "rejected", email, admin_id: null, temporary_password: null}` |
| 10 | `POST /api/admin/login` `{email, password}` | none | `{token, role: ward_officer\|admin, ward_codes[], expires_at}` (admin: `ward_codes` = `[]` = every ward). Wrong credentials 401 |
| 10 | `GET /api/admin/me` · `POST /api/admin/logout` (204) | officer | `{admin_id, email, name, designation, role, ward_codes, session_expires_at}` |
| 11 | `GET /api/admin/summary?ward=` | officer | `{ward_codes, reports_by_status{<all 9 statuses>}, new_today, overdue_sla, median_hours_to_resolve, rupees_held_inr, flags_awaiting_reply}` |
| 12 | `GET /api/admin/reports?ward=&status=&kind=&issue_type=&q=&sort=newest\|oldest\|sla_due&page=&page_size=` | officer | `{items[{id, created_at, age_hours, sla_due_at, status, kind, issue_type, road, flag, photo_url, citizen}], page, page_size, total}`. `citizen` is the pseudonym (or "Anonymous"), never a phone. `q` matches report id, road name, landmark, text. `page_size` ≤ 100 |
| 13 | `GET /api/admin/reports/{id}` | officer | the full report (item 2) plus `citizen`, `confirm_photos[]`, `flags[]` (report's flag first, then the road's flags, each with `replies_count`), `work_orders[]` (linked one first), `duplicate_candidates[{id, created_at, status, issue_type, road_id, distance_m, reason}]`, `notices[]`, `allowed_next[]` |
| 14 | `PATCH /api/admin/reports/{id}` `{status?, note?, duplicate_of?, rejection_reason?, repair_due_at?}` | officer | same as item 13. Illegal transition → 422 listing the allowed ones. `rejected` needs `rejection_reason`; `duplicate` needs `duplicate_of` (a chain is followed to the original). Every change writes an event |
| 15 | `POST /api/admin/reports/{id}/notify-contractor` `{channel: email\|sms\|letter, message?, language?}` | officer | 201 `{id, report_id, channel, flag_id, work_order_id, contractor_id, contractor_name, message, generated_by: claude\|template\|officer, sent_by, created_at, delivery: "recorded"}` |
| 16 | `GET /api/admin/flags?ward=&awaiting_reply=true&page=&page_size=` | officer | `{items[{flag_id, tier, detector, status_label, ward_code, road_id, road_name, work_order_id, contractor_id, contractor_name, rupees_at_stake, rule_text, replies_count, last_reply_at}], page, page_size, total}`, highest stakes first |
| 16 | `POST /api/flags/{flag_id}/replies` `{author_role, author_name?, body}` | officer (flag's ward) | **now authenticated** (401 without a token, 403 outside your wards). `author_name` defaults to the officer's name. Use `author_role: contractor` to log a reply the contractor gave the ward office |

Summary tile definitions:
- `new_today`: reports created today (IST).
- `overdue_sla`: open reports past `sla_due_at`.
- `median_hours_to_resolve`: from creation to the first time a report was resolved.
- `rupees_held_inr`: bills of reports in `payment_held`, each bill counted once.
- `flags_awaiting_reply`: flags in scope with no reply yet.

`notify-contractor`:
- **Records** the notice; it does not send email, SMS or letters.
- The notice concerns the report's flagged bill and goes to that bill's contractor. Without a flag, it goes to the
  contractor of the linked work order, else the road's latest surface-repair contractor.
- With no `message`, the text is drafted like `POST /api/draft-notice` (Claude, with the template as fallback).
- It moves the report to `contractor_notified` when that transition is allowed. Closed reports return 409.

### Still pending?
The earlier "still pending" list is built. `GET /api/roads?q=` (item 3), `/api/localities`, `/api/livability`,
`POST /api/draft-notice` (item 4), `POST /api/citizen-query` and `POST /api/uploads/photo` (item 1) all exist.

### Privacy notes
- Citizen tokens, phone numbers, officer accounts, sessions, access requests, report history and contractor notices
  live in private tables. RLS is on with no policy, so the Supabase public key cannot read them; only FastAPI can.
- `citizen_reports` keeps its existing public read. Its new `citizen_id` (a random uuid, no name or phone) can
  therefore be read with the public key, which lets someone group one person's reports. The API never needs this
  column exposed. If that matters, revoke public read on `citizen_reports` in a later migration.

## Everything else

`GET /api/health`, `GET /api/wards` (`?ward=` / `X-Ward-Code` for one), `GET /api/wards/map` (GeoJSON),
`GET /api/flagged-queue`, `GET /api/roads/{id}/timeline`, `GET /api/flags/{id}`,
`GET /api/v3/contractors`, `GET /api/v3/wards`, `GET /api/v3/summary`. See Swagger for shapes.
