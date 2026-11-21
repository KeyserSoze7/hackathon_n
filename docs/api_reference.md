# API reference (frontend)

Source of truth: Swagger UI at `<base>/docs` and the spec `backend/openapi.json` (every response is typed and
the POSTs carry real example responses). This page is the quick map. Backend code: `backend/README.md`.

## Conventions

- **Base URL**: the host running `uvicorn backend.main:app` (on the venue LAN: `http://10.10.38.50:8000`). No login.
- **Ward codes**: responses always use `K/W`. Inputs accept `K/W`, `K-W` or `k_w`. `ALL` = city-wide where noted.
- **Timestamps**: ISO 8601 in IST with offset, e.g. `2025-06-22T02:59:00+05:30`. Dates: `YYYY-MM-DD`.
- **Money**: whole rupees (integers, INR). Format for display on the client (₹42.5L, ₹1.80 Cr).
- **Errors**: `404 {detail: "unknown ..."}`; `422 {detail: [{loc, msg, type}]}` (same shape for every 422);
  uploads also `413` (too large) and `415` (not a supported image).
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
Request (all optional except what you have):
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
height}], tracker[{step, label, status: done|current|pending, at}], flag_id, landmark, location, input_mode,
language, text, matched_locality, created_at}`
- `status` / tracker steps: `reported` → `matched_to_contract` → `payment_held` → `contractor_notified`.
  Payment is auto-held for a surface defect (pothole, broken paver) on a road under DLP.
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

## Everything else

`GET /api/health`, `GET /api/wards` (`?ward=` / `X-Ward-Code` for one), `GET /api/wards/map` (GeoJSON),
`GET /api/flagged-queue`, `GET /api/roads/{id}/timeline`, `GET /api/flags/{id}`, `POST /api/flags/{id}/replies`,
`GET /api/v3/contractors`, `GET /api/v3/wards`, `GET /api/v3/summary`. See Swagger for shapes.
