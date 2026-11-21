# MARG·LEDGER prototype: how it is, how it compares, and the flow

Written for: the team deciding which frontend direction to build on.

## 1. What exists now

| Item | Where | Status |
|---|---|---|
| Polished single-file prototype (the "Daylight Highway" design) | `frontend/public/marg-ledger.html` (served at `/marg-ledger.html`) | Working. All numbers come from the sample JSON. |
| Sample data for the prototype | `frontend/public/data/*.json` (copied by `frontend/scripts/make_sample.py`) | Generated from `data/*.csv`. Replace with Supabase exports later. |
| React app (Vite, Tailwind, Civic Paper / Indian palette) | `frontend/src/` | Still built. Different visual direction. Not yet merged with the prototype. |

To run: start the dev server in `frontend/` (`npx vite`), then open `http://localhost:5173/marg-ledger.html#start`. To regenerate data: `python frontend/scripts/make_sample.py`.

The prototype is one HTML file with Tailwind via CDN, no build step. The data layer is four `fetch` calls at boot. Each render function reads from `D` (the loaded JSON) and does not compute figures itself, apart from formatting, percentages and the planner's budget fill.

## 2. How it is built

### Header (always visible)
- **Brand row:** the `M₹` mark and the MARG·LEDGER wordmark (links to `#start`), the ward switch pill (opens the ward list), and the EN / हिन्दी / मराठी switch.
- **Screen nav:** five real links (`#start`, `#receipt`, `#city`, `#contractors`, `#nextrupee`) with an icon and a label. The active one gets `aria-current="page"` and the yellow fill. Phone widths use short labels (Find, Receipt, City, Firms, Next ₹) in five equal columns, so no tab is hidden off-screen.
- **Kerb stripe:** a flat black-and-yellow tile pattern under the header.

### Screen 1: Find a road (`#start`)
- **Finder card:** three tabs. *Photo of signboard* and *Scan QR code* are demos that open a sample road (RD0220). *Type road or area* searches all 291 roads (first 8 shown, with the match count).
- **Your area:** ward spend against budget, billed under warranty (with its share of the ward's spend), and complaints per 100,000 residents. A 10-second audio button reads the summary aloud.
- **Moving here? (1.5 km):** four localities (Andheri West, Kurla East, Dadar West, Bhandup West). Shows flood hotspots, the share of repairs that failed within 30 days on road segments within 1.5 km, hospital access roads within 1.5 km, and the ward's warranty share.

### Screen 2: Road receipt (`#receipt`)
- **Header:** road ID, ward, surface, road name and segment, and the resurfacing date with a warranty status line.
- **Figures:** billed to BMC this monsoon, billed while under warranty, and an audio button.
- **Proof trail:** four steps. (1) first linked complaint, (2) the first flagged repair, (3) how many repairs failed within 30 days, (4) audit flags with an expandable evidence list (rule text, evidence IDs, rupees at stake), a right-of-reply field, and the draft-notice button.
- **Draft notice modal:** a skeleton for 700 ms, then a template filled from the flagged rows, in English and Marathi. The copy button copies the text and the cited row IDs.

### Screen 3: City audit (`#city`)
- **Headline:** generated from the totals, e.g. "₹13.43 Cr of monsoon repairs went out across 24 wards. ₹2.62 Cr of it was billed on roads under warranty."
- **Three figures:** spend against budget, billed on roads under warranty (with an upper-bound note), and repairs that failed within 30 days.
- **Ward grid:** all 24 wards, each showing its warranty share. Dashed outline marks flood-prone wards with few complaints. Selecting a ward filters the table and updates the header.
- **Table:** the five roads with the largest warranty bills in the selected ward (or the city), each with an Open receipt button.

### Screen 4: Contractors (`#contractors`)
- **Table:** all 8 contractors, sorted by billed amount. Columns: failure rate within 30 days (with expected rate and 95% range), SLA met (with range and median bill against the rate card), and context (flood-prone share, heavy-rain share, peak vehicles, billed under warranty).
- **Reading guide:** what "expected" means, what the range means, and a note that there are no grades.

### Screen 5: Next rupee (`#nextrupee`)
- **Budget slider:** ₹1 Cr to ₹15 Cr, default ₹7.5 Cr.
- **Bucket A (costs BMC ₹0):** warranty roads in the top-30 risk pool, with their risk reasons and the cost they would otherwise carry.
- **Bucket B (ranked to fund):** the other roads in the pool, in risk order, funded greedily until the budget runs out. Unfunded roads are dimmed and labelled "Next cycle".

### Modals and states
- **Ward switcher:** lists all 24 wards. Escape closes it.
- **Notice:** skeleton, then template, with an EN / मराठी toggle.
- **Loading:** a skeleton shows until the JSON has loaded. If the JSON is missing, a message says how to regenerate it.

## 3. Comparison with the two planning documents

Sources: `frontend_user_flow_backend_handoff_plan.md` (the 4-view plan, earlier) and `docs/final_product_frontend_master_plan.md` (the 5-screen plan, later and marked as the final lock).

| Area | Handoff plan (4 views) | Master plan (5 screens) | Prototype now | Gap or decision |
|---|---|---|---|---|
| Entry / citizen lookup | View 4: QR banner, voice input, text, photo, "Still broken / Reopen", live tracker | Screen 5: Check My Street and Moving Here, thumb dock, voice | Screen 1: three finder tabs, area card, moving-here card | Voice input, the 1-tap "Still broken" action and the live tracker are missing. The prototype's QR and photo entries are simulated. |
| City overview | View 1: 3 KPIs, ward map coloured by warranty enforcement rate, flagged queue | Screen 1: 3-metric strip, ward map, top 5 flagged roads | Screen 3: 3 figures, 24-ward tile grid, top roads table | Map is a tile grid, not the GeoJSON map. "Warranty enforcement rate" is not computable (every warranty bill is paid), so the prototype uses share of spend on warranty roads. |
| Road receipt | View 2: header, timeline, two-key check, right-of-reply, notice button | Screen 2: variations 2A/2B/2C, maintenance alert step | Screen 2: header, figures, 4-step proof trail, evidence drawer, right-of-reply, notice | Maintenance alert step removed (V1 decision). Two-key verification (contractor claim against citizen check) is not in the data, so it is not shown. |
| Contractors | View 3A: scorecard with reopen rate, SLA, survival score, ward context | Screen 3: 60/40 matrix plus maintenance alert queue | Screen 4: scorecard table with expected rate and range, plus reading guide | Alert queue removed (V1). The "survival score" is not built; the prototype shows failure rate against expected rate instead. |
| Next rupee | View 3B / Screen 4: budget slider, bucket A (₹0), bucket B with reason badges | Same, with reason codes | Screen 5: budget slider, bucket A and bucket B, reason codes | Matches. The pool is the top 30 roads by risk, a choice made in the prototype. |
| Language | EN / हिन्दी / मराठी, all copy | Same | Switch present. Only navigation labels translate. Marathi notice template present. | Hindi and Marathi copy for the other screens is still to do. |
| Voice | Mic input and spoken 10-second summary | Same | Spoken summary only (text-to-speech). No mic input. | Voice input needs the Web Speech API in the final build. |
| Live Claude endpoints | `POST /api/draft-notice`, `POST /api/citizen-query` | Same | None. Notice is a template. Lookup is local text matching. | Wire when the backend exists. |
| Static exports | 4 JSON files | 5 JSON files | 7 JSON files, names mapped below | See section 4. |
| Data fields the plans name | `dlp_expiry`, `maintenance_alerts`, payment hold status | Same | Not present | These are not in `data/`. The prototype does not show them. |

### Export name mapping

| Plan name | Prototype file | Note |
|---|---|---|
| `summary.json` | `summary.json` | Totals, ward figures and the top-10 queue. |
| `roads_audit.json` | `roads.json` | Keyed by road ID. Includes work orders, flags, complaints and accidents. |
| `contractors.json` | `contractors.json` | Adds Wilson-based 95% ranges and expected rates. |
| `next_rupee.json` | `planner.json` | Ranked roads plus method reopen rates. |
| `localities_livability.json` | `livability.json` | 1.5 km figures per locality. |
| (not in plan) | `roadlist.json` | All 291 roads, for search and the city table. |
| (not in plan) | `localities.json` | Gazetteer with aliases and the three nearest roads. |

## 4. Changes from the pasted HTML

The HTML you pasted had the right structure and look, but several things had to change.

### Removed (not in the data, or cut for V1)
- **Maintenance alerts** in all three places: the area card, the proof trail step, and the contractor queue. Dropped per your V1 decision.
- **Invented figures:** ₹142.8 Cr spend and ₹168.0 Cr budget, ₹3.84 Cr recoverable, 19 overdue alerts, the "62 / 100" zone score, the "Moderate / High risk" labels, the 8-ward rates, and the four contractor rows (CTR-007 to CTR-024).
- **Invented IDs and names:** R-1042, WO-1042, CMP-4821, R-2019, R-3104 and similar, and the names "Apex Infra Works" and "Contractor A". The real IDs are RD0220, WO25-xxxxx, BMC25-xxxxxx and CT01 to CT08.
- **Invented dates and facts:** "DLP active until Oct 2028" (the dataset has no DLP end date), "99% confidence" on a signboard match, "citations verified" on the notice, "subway stretches flood", and the claim that every BMC QR code exists.

### Replaced with data
- Every number on screen is read from `frontend/public/data/*.json`, which is computed from the CSVs.
- The ward list is the real 24 wards, using codes such as `K/W` and `M/E`, not `K-W` and `M-E`.
- The "Owed by BMC" label is now "Billed while under warranty". The old wording suggested BMC owes money. The contractor owes the repair.

### Design rules (the 20 rules)
- **Gradients removed:** the kerb is now a flat tile pattern. The hatched alert fill is gone.
- **Shadows and blur removed:** the scanner glow, the toast shadow and the modal blur.
- **Mono limited to IDs, timestamps and citations.** Labels such as "MATCHED IN ROADS.CSV" are now plain text.
- **Filler badges removed**, such as "HOME · HOSTEL · OFFICE" and "SILENCE-ADJUSTED PHYSICAL RISK RANKING".
- **Accessibility:** the screen nav uses real links with `aria-current`, the tabs use `role="tab"` with `aria-selected`, dialogs use `role="dialog"` and close on Escape, and all tap targets are at least 40 px.
- **Demo honesty:** each simulated feature is labelled as a demo on the screen (the signboard, the QR scan, the notice template).

### Navigation rebuilt
- Original: a brand row and a separate tab row, with numbered labels and a horizontal scroller that hid tabs on phones. The active state was set by rewriting class strings in JavaScript.
- Now: one `<nav>` with five links, icons, `aria-current`, and hash routes. Back and forward work, and a link can open a screen directly. Phone layout is five equal columns with short labels.

## 5. The new flow

```
                       ┌────────────────────────────┐
   header ward pill ─► │ Ward switcher (24 wards)    │─┐
                       └────────────────────────────┘ │ sets ward for
                                                      ▼ Start and City
┌──────────────────────── 1. Find a road (#start) ────────────────────────┐
│ Photo (demo)  │  QR (demo)  │  Type road / area (291 roads)             │
│ Your area: ward spend · billed under warranty · complaints per 100k     │
│ Moving here: pick locality → flood spots, failure rate, hospitals, share │
└───────────────┬───────────────────────────────────────────┬─────────────┘
                │ open a road                               │ (no road)
                ▼                                           ▼
┌──────────── 2. Road receipt (#receipt) ───────┐   ┌─── 3. City audit (#city) ───┐
│ Billed · billed under warranty · audio        │   │ Spend · warranty · failures  │
│ Proof trail: complaint → repair → failures    │   │ Ward grid (filter)           │
│   → audit flags → evidence rows + reply       │◄──│ Table: top roads → Open ───► │
│ Draft notice (EN / मराठी) → copy             │   └──────────────┬──────────────┘
└───────────────────────────────────────────────┘                  │
                ▲                                                  ▼
                │                             ┌── 4. Contractors (#contractors) ──┐
                │                             │ Failure vs expected, SLA, context  │
                │                             └───────────────────────────────────┘
                │                             ┌── 5. Next rupee (#nextrupee) ─────┐
                └──── open a road from ───────│ Budget slider → ₹0 bucket + ranked│
                      either bucket           │ roads (top-30 pool)                │
                                              └───────────────────────────────────┘
```

**What changed in the flow:**
- The citizen entry and the officer views now share one app. The first screen is a citizen lookup, and the officer screens are one click away in the same nav.
- Every road-level figure has one path: any screen → Road receipt → evidence rows. The receipt is the only place a flag is explained.
- The ward is a shared setting. Changing it in the header updates the Start screen and the City table.

## 6. What to decide next

1. **Which frontend to build on.** The React app has the Indian-palette direction, and this prototype has the Daylight Highway look you liked. The prototype runs with no build step. Porting it into React is a separate piece of work, which I have not estimated yet.
2. **Voice input** for the citizen entry, and the Hindi and Marathi copy for the other screens.
3. **Missing data.** Confirm with the organisers whether a DLP end date and the maintenance records exist. If not, the receipt keeps the "upper bound" note.
4. **Notice drafting.** The Claude endpoint is not connected. The template is a placeholder and needs an officer's review before any real use. The Marathi template needs a native-speaker check.
5. **Supabase.** When the schema lands, the prototype's JSON files are replaced by queries with the same field names, so the screens do not change.

## 7. How this was checked

- Headless Edge loaded each route. All five screens rendered their expected figures (for example ₹2.62 Cr billed under warranty, 611 failed repairs, 24.2% expected failure rate for Contractor CT02).
- The layout was checked in screenshots at desktop width. Phone layout was checked only approximately: the headless browser has a minimum width of about 492 px, so 390 px captures were cropped. Check on a real phone before the demo.
- The page was not clicked through by hand. Please click through the finder tabs, the ward switch, the budget slider and the notice modal.
