# MARG·LEDGER frontend: summary

What is built, how to run it, where every number comes from, and what the backend still needs to provide. For the reasoning behind each choice, read `decision.md`.

## Run it

```bash
cd frontend
npm install          # first time only
npm run dev          # http://localhost:5173
```

The laptop must be on the same network as the backend (`http://10.10.38.50:8000`; check `/api/health`). To point elsewhere, create `frontend/.env` with `VITE_API_BASE=http://<host>:8000` and restart. Production build: `npm run build`, then `npm run preview`.

## Structure

```
frontend/
  index.html                 fonts, favicon (brand emblem)
  public/
    brand/                   marg-logo.svg, marg-mark.svg, load_animation.webm, load_animation.mp4
    wards.geojson            ward polygons for the SVG map
    marg-ledger.html, data/  old HTML prototype + sample JSON (not used by the React app)
  scripts/
    vectorize_logo.py        rebuilds the two SVGs from ../assets/main logo.jpeg
    make_sample.py           old sample-data generator (prototype only)
  src/
    App.tsx                  header, ward switcher, language switch, nav, hash routing, splash
    data/api.ts, types.ts    the only place that talks to the backend
    lib/format.ts            ₹ lakh/crore, dates, detector and reason labels
    lib/useAsync.ts          data/loading/error/reload hook
    components/ui.tsx        Skel, Id (mono evidence chip), Pending ("Data coming in"), ErrorBox, Modal, Primary
    components/WardMap.tsx   SVG ward map coloured by dlp_leakage_rate
    components/Splash.tsx    boot animation
    components/Logo.tsx      emblem + MARG·LEDGER wordmark
    screens/                 Start, RoadReceipt, City, Contractors, NextRupee
```

## Screens and their data

| Screen | Shows | Endpoints | Placeholder ("Data coming in") |
|---|---|---|---|
| Find a road `#start` | Finder (sample signboard demo, QR tab, free-text lookup), your-area ward card with 10-second spoken summary, moving-here card | `GET /api/lookup?q=`, `GET /api/wards`, `POST /api/citizen-reports` | QR codes, browse all roads, moving-here 1.5 km check |
| Road receipt `#receipt?road=` | Road header and warranty status, billed and at-stake figures, 4-step proof trail, evidence rows, right-of-reply form, full timeline, defect-notice button | `GET /api/roads/{id}`, `GET /api/roads/{id}/timeline`, `POST /api/flags/{id}/replies` | Defect notice drafting |
| City audit `#city` | Spend vs budget, ₹ billed under warranty, flagged bills by detector, ward map, ward panel, flagged-bill table | `GET /api/city`, `GET /api/wards`, `GET /api/flagged-queue?ward=&limit=` | — |
| Contractors `#contractors` | Failure and SLA rates against expected, verdicts, 90% range, context (flood, rain, tides, traffic), explanation, drivers, failed-repair evidence | `GET /api/v3/contractors` | — |
| Next rupee `#nextrupee` | Ward select, budget slider (server re-solve), ₹0 warranty bucket, funded and next-cycle items with reasons | `GET /api/v3/wards`, `GET /api/v3/next-rupee/{ward}`, `POST /api/v3/allocate` | — |

Every screen has skeleton loading and an error box with retry if the backend is unreachable.

## Current figures (from the live backend, 21 Nov 2026)

₹13.43 Cr spent of ₹14.91 Cr budget across 24 wards. ₹60.3L billed under warranty (259 bills). 496 bills need explanation: 259 under warranty, 116 heavy-rain-day work, 109 above rate card, 47 overlapping work orders.

## Mobile and report workflow

- Phones: bottom navigation, single-row header, card layouts, no horizontal overflow (verified at 390 px on all five screens).
- Report workflow (verified end to end in a 390 px browser against the live API): choose the situation and problem type, optional photo (preview only), landmark and optional GPS, review, send, then a tracker that can be refreshed.
- Hosting on Vercel: the app is a static build (`npm run build`, output `dist`, hash routing needs no rewrites). Set `VITE_API_BASE` in Vercel to an **https** address for the backend. The current `http://10.10.38.50:8000` is blocked by browsers on an https page even on the same Wi-Fi. For a same-Wi-Fi demo without Vercel, run `npm run dev -- --host` and open `http://<laptop-ip>:5173` on the phones (the "Use my location" button needs https and will fall back to the landmark field there).

## Verification done

- `tsc -b` and `vite build` pass.
- Headless Edge loaded every screen against the live API: all render real values, no error states.
- Logo SVG rendered against the JPEG: PSNR 31.2 dB, only anti-aliased edges differ. WebM: 240/240 frames, same resolution, fps and colour tags; worst frame 48.2 dB PSNR.
- Not done: clicking through by hand, the two write endpoints, a real phone.

## Requested from backend: citizen report form with photo

The "Still broken? Report it" link sends only text today. A citizen who scans or finds a road needs a proper form: what is wrong, a photo, where exactly, and a tracker afterwards. The current `POST /api/citizen-reports` takes only a `photo_url` string, and there is no way to upload a photo. Please add the following. The frontend will be built against exactly this.

### 1. `POST /api/uploads/photo`: upload one photo

Separate from the report, so a photo can upload (and retry) on a slow connection before the citizen submits.

- **Request:** `multipart/form-data` with field `file`. Accept `image/jpeg`, `image/png`, `image/webp`, `image/heic`; max 8 MB.
- **Server:** store in Supabase Storage (for example bucket `citizen-photos`). Re-encode to JPEG, max 1600 px on the long side. Remove EXIF from the stored copy (privacy), but read GPS and capture time first and return them.
- **Response 200:**
  ```json
  { "photo_id": "ph_8f2c...", "photo_url": "https://.../citizen-photos/ph_8f2c.jpg", "width": 1600, "height": 1200,
    "taken_at": "2025-07-08T09:14:00+05:30", "exif_lat": 19.0721, "exif_lon": 72.8834 }
  ```
  (`taken_at`, `exif_lat`, `exif_lon` are null when the photo has none.)
- **Errors:** 413 too large, 415 unsupported type, 422 missing file.

### 2. `POST /api/citizen-reports`: extend the existing body

Keep the current fields, and add these. All new fields optional unless marked.

```json
{
  "kind": "still_broken | verified_fixed | new_issue",            // required (exists)
  "input_mode": "text | voice | photo | qr",                       // exists
  "language": "en | hi | mr",                                       // exists
  "text": "Pothole is back near the bus stop",                     // exists
  "road_id": "RD0220",                                              // exists
  "work_order_id": "WO25-00007",                                    // exists
  "matched_locality": "Kurla West",                                 // exists
  "issue_type": "pothole | waterlogging | open_manhole | broken_paver | cave_in | choked_drain | other",
  "photo_ids": ["ph_8f2c..."],                                      // up to 3, from /api/uploads/photo
  "location": { "lat": 19.0721, "lon": 72.8834, "accuracy_m": 15, "source": "gps | photo_exif | map_pin" },
  "landmark": "Opposite Kurla depot",
  "flag_id": "DLP_PAID_TWICE:WO25-00007",                           // when reported from a road receipt flag
  "contact_phone": "+91..."                                         // optional, for SMS updates; never returned by any GET
}
```

- **Server:** validate that `photo_ids` exist and are unused, snap `location` to the nearest road if `road_id` is missing, check for an open duplicate report on the same road and issue type in the last 7 days, and set the tracker status (clients cannot).
- **Response 201:**
  ```json
  {
    "report_id": 1042,
    "status": "received",
    "road": { "road_id": "RD0220", "road_name": "Kurla Andheri Road", "ward_code": "L", "under_dlp": true },
    "duplicate_of": null,
    "linked_work_order_id": "WO25-00007",
    "responsible": "original_contractor | bmc_ward",                 // original_contractor when the road is under DLP
    "sla_hours": 48,
    "photos": [{ "photo_id": "ph_8f2c...", "photo_url": "https://..." }],
    "tracker": [
      { "step": "received", "label": "Report received", "status": "done", "at": "2026-11-21T16:02:00+05:30" },
      { "step": "matched", "label": "Matched to road and contract", "status": "done", "at": "..." },
      { "step": "notified", "label": "Contractor or ward office notified", "status": "current", "at": null },
      { "step": "resolved", "label": "Repair verified", "status": "pending", "at": null }
    ]
  }
  ```
- **Errors:** 404 unknown `road_id` or `photo_id`, 409 photo already used, 422 validation, 429 rate limit (suggest 5 reports per device per hour).

### 3. `GET /api/citizen-reports/{report_id}`

Same shape as the 201 response, with the tracker updated. Never returns `contact_phone`.

### 4. `GET /api/roads/{road_id}/reports?limit=20`

Recent citizen reports on a road (`report_id`, `kind`, `issue_type`, `created_at`, `status`, first `photo_url`), so the road receipt can show them in its timeline.

## Also still requested from backend

Road list/search (`GET /api/roads?q=&ward=&limit=`), localities list, 1.5 km livability per locality, `POST /api/draft-notice` (Claude, EN/हिं/मराठी, template fallback), `POST /api/citizen-query` (Claude), city totals for failed repairs and counts, `segment_no` and `length_m` on roads, `ward_code=ALL` for the planner. The backend has since added typed response models (commit `d6f6568`); the frontend types were written from observed responses and should be checked against them.

## Citizen "My reports" and the ward office (added 21 Nov, evening)

- **`#me` My reports** (profile icon in the header): reports sent from this device, with stat cards, report cards, a tracker per report, and "Yes, fixed" / "Still broken". Until `GET /api/me` exists, the list is the report ids saved on this device (`localStorage` key `marg-my-reports`), each loaded with `GET /api/citizen-reports/{id}`.
- **`#admin` Ward office** (link at the bottom of My reports, not in the public nav):
  - **Sign-in and access:** sign-in, a request-access form, and a preview mode.
  - **Dashboard:** KPI cards, a citizen-report inbox, and "open a report by number".
  - **Live actions:** a status stepper with allowed next steps and Notify contractor, and a "flags awaiting reply" tab with a reply form, which works today.
- **`api.ts` normalises the two report shapes** the backend returns (POST: `id`, `road_id`; GET: `report_id`, `road{}`; tracker items with `status: done|current|pending`).
- **Flow check:** `python frontend/scripts/qa_flows.py` runs 31 checks on 390 px and 1280 px (needs `npm run dev` and the API). The last run passed 31 of 31. It creates one "FRONTEND TEST" report per run.

### Still needed from the backend for these screens

Citizen identity: `POST /api/citizens` (device token), store `citizen_id` on reports, `GET /api/me`, `GET /api/me/reports`, `POST /api/citizen-reports/{id}/confirm`, and `events[]` history on a report. Insert should stop at `matched_to_contract`; officers move it on.
Ward office: `POST /api/admin/access-requests`, `GET` + approve/reject, `POST /api/admin/login` + `GET /api/admin/me`, `GET /api/admin/summary`, `GET /api/admin/reports`, `GET`/`PATCH /api/admin/reports/{id}`, `POST /api/admin/reports/{id}/notify-contractor`, `GET /api/admin/flags?awaiting_reply=true`.
Shipped by the backend but not yet wired in the frontend: `GET /api/roads` (search), `/api/localities`, `/api/livability`, `/api/roads/{id}/reports`, `POST /api/uploads/photo`, `POST /api/draft-notice`, `POST /api/citizen-query`.
