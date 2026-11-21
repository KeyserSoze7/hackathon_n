# Frontend decisions (context for the next agent)

Read this before changing anything in `frontend/`. It records what was decided, why, and what not to undo. `summary.md` in the same folder describes what exists and how to run it.

## The project in one paragraph

Hackathon build (Claude Impact Lab Mumbai, 21 Nov 2026), "Follow the Rupee: Mumbai monsoon roads". Synthetic BMC data in `../data/*.csv`. The product, **MARG·LEDGER**, is a pre-payment audit gate and public rupee receipt. It connects citizen complaints to repair work orders, flags bills that need explanation (warranty/DLP, rate card, overlaps, rain-day work), scores contractors fairly, and recommends where the next rupee goes. Judging weights: audit accuracy 25, fair accountability 20, budget recommendation 20, connecting the trail 15, usability 10, demo 10.

## Hard rules (from the team, keep them)

1. **Code computes every number; Claude never does arithmetic.** The backend computes. The frontend only formats, plus trivial sums for display.
2. **Never invent data.** If the API does not serve something, show the `Pending` component ("Data coming in"). Do not fall back to sample or hard-coded figures.
3. **Neutral language.** "Needs explanation", "Billed under warranty", "Recoverable under DLP". Never "fraud" or "corrupt". Contractor verdicts are "better / worse / in line with expected", never grades.
4. **The 20 UI rules** (from the user, apply to every component): delete filler badges; drop redundant labels; no random italics; mono only for IDs, timestamps and citations; one design system; show the actual product; enlarge the main feature; group with spacing, not boxes; specific headlines; one emphasised CTA per screen; one accent colour; consistent icons (lucide, 1.5 stroke); no embellishments (no gradients, no shadows); inner radius = outer radius − padding; strong text contrast; `text-wrap: balance` on headlines; align by eye; tabular numbers; real loading states; animate only useful feedback.
5. **Indian number format.** Lakh and crore (`₹60.3L`, `₹13.43 Cr`), via `lib/format.ts`.

## Decisions and why

| Decision | Why | Do not |
|---|---|---|
| React + Vite + Tailwind v4 + lucide-react, TypeScript strict | Fast to build, small bundle, the team's planned stack | Add a UI kit or a heavy map library (Leaflet/Mapbox): the ward map is a hand-rolled SVG from `public/wards.geojson` |
| Visual direction: "Daylight Highway" (concrete `#F3F4F6`, white cards, ink `#111317`, highway yellow `#F5B700` as the only accent, highway green `#0F5C43`, black/yellow kerb stripe) | The user chose it from a pasted HTML prototype ("I like the design") after rejecting a first "Civic Paper" look and a second Indian-palette look | Reintroduce the cobalt or saffron palettes |
| Five screens with hash routing: `#start`, `#receipt?road=RD0220`, `#city`, `#contractors`, `#nextrupee` | Deep links work, back/forward works, no router dependency | Rename hashes without updating links in the HTML prototype and docs |
| Header: logo, green ward pill (opens ward list), EN/हिन्दी/मराठी switch, then a 5-item nav (icon + label; on phones 5 equal columns with short labels) | The user said the original nav "is very bad"; this is the rebuilt version | Put the nav in a horizontal scroller that hides tabs |
| Data comes only from the live backend (`src/data/api.ts`), base URL `VITE_API_BASE`, default `http://10.10.38.50:8000` | The user said: use the API; anything missing is a "Data coming in" placeholder | Import JSON from `scripts/` output or `public/data/` into the React app |
| Maintenance alerts were dropped for V1 | Not in the dataset; the user decided to drop them | Re-add an alert queue |
| Ward map colour = `dlp_leakage_rate` | `warranty_enforcement_rate` is 0 for every ward (every warranty bill was paid), so it carries no signal; the API docs also say to colour by leakage | Colour by enforcement rate |
| Headline uses the backend's ₹60.3L recoverable, not the ₹2.62 Cr our early sample computed | The backend applies a stricter DLP test; the early figure counted every job on a currently-warranted road | Show ₹2.62 Cr anywhere |
| Next-rupee planning is per ward (slider in lakhs, default = backend `recommended_budget_inr`, max = 4× that) | The API only solves per ward (`/api/v3/allocate`) | Build a city-wide slider until the backend adds `ward_code=ALL` |
| Brand assets vectorised one-to-one: `public/brand/marg-logo.svg` (full card), `marg-mark.svg` (emblem, transparent), `load_animation.webm` (VP9, all 240 frames, verified ≥ 48 dB PSNR per frame against the MP4) | The user asked for universal vector logo and a one-to-one WebM | Edit the SVG paths by hand: regenerate with `scripts/vectorize_logo.py` |
| Boot splash plays the animation once per session; closes when data is ready and the logo has formed (≈4.6 s), or after a 6.1 s safety timeout, or on Skip. Reduced motion shows the still SVG | Branding without holding the app hostage on slow 4G or blocked autoplay | Use the 10 s animation for per-screen loading; screens use skeletons |
| Right of reply posts to the backend; citizen "Still broken? Report it" posts to `/api/citizen-reports` | Both endpoints exist; replies are now on the record | Fake a local-only save |

## Later decisions (final polish)

| Decision | Why | Do not |
|---|---|---|
| Header is one row: emblem only (no "MARG·LEDGER" text), ward pill, language toggle (EN / हिं / मरा). | The user asked to remove the English wordmark and move the toggle up. The emblem carries the name. | Re-add the wordmark text |
| Phones (< 640 px): navigation is a fixed bottom bar with 5 equal items; the top nav row is hidden. From 640 px up the nav sits under the header. | Thumb reach on mobile. | Put the nav back at the top on phones |
| Cards, not lists or tables, everywhere (flagged bills, contractors, flags, timeline, wards). | Lists were too cluttered on mobile. | Reintroduce `<table>` or divided lists |
| The report is a four-step workflow in `components/ReportFlow.tsx` (What, Photo, Where, Review) ending in a live tracker; opened from the lookup result and the road receipt; deep link `#receipt?road=RD0220&report=1`. | The user wanted a full workflow, not one click. | Collapse it back to a single button |
| Report details (issue type, landmark, GPS) are packed into the report `text` field; the photo is chosen and previewed but NOT uploaded. | `POST /api/citizen-reports` accepts only text-level fields and no upload endpoint exists yet. | Pretend the photo was sent |
| All dialogs render through a portal to `<body>` and lock page scroll. | A fade-in ancestor made `position: fixed` relative to the page, so the dialog appeared off-screen under a dim overlay. | Render a `Modal` inside an animated container without the portal |

## Data facts worth knowing

- Real ID formats: roads `RD0220`, work orders `WO25-00007`, complaints `BMC25-000020`, contractors `CT01`–`CT08`, wards `K/W` (with a slash; encode it in URLs).
- Demo road: **RD0220, Kurla Andheri Road (ward L)**: 35 repair jobs on one warranty segment, 89 complaints.
- The dataset has **no DLP end date**, no maintenance records, no payment-hold status, no QR codes.
- Contractor names carry " (synthetic)"; `cleanName()` strips it for display.
- `/api/lookup` returns 404 on no match; the UI treats that as "No road matched".
- `POST /api/citizen-reports` returns `id` (not `report_id`), `status`, `flag_id` and `tracker: [{step, done}]` with steps `reported`, `matched_to_contract`, `payment_held`, `contractor_notified`. Test reports titled "FRONTEND TEST" (ids 6 to 9) were created while verifying; they can be deleted.
- Hosting: the API is plain http on a LAN address. An https page (for example Vercel) cannot call it (mixed content). Serve from the laptop (`npm run dev -- --host`) or expose the API over https and set `VITE_API_BASE`.

## Open items (see summary.md for the endpoint spec)

- Waiting on backend: road list/search, localities list, 1.5 km livability, defect-notice drafting (Claude), citizen-query (Claude), city totals for failed repairs, segment number and length on roads, report form with photo upload.
- Not verified by hand: the two POSTs (reply, citizen report) were never called during development because they write data; the report response's id field is assumed to be `report_id` or `id`.
- Phone layout checked only approximately (headless browser minimum width ≈ 492 px).
- Hindi and Marathi: only nav labels translate so far.

## Files that are not part of the React app

- `public/marg-ledger.html` + `public/data/*.json`: the earlier single-file HTML prototype with sample data (generated by `scripts/make_sample.py`). Kept for reference; the React app does not use them.
- `../docs/marg_ledger_flow_and_comparison.md`: comparison of that prototype with the two planning docs. Its numbers are from sample data and are out of date.
