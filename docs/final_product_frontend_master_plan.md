# {{PROJECT_NAME}} — Final Product, Frontend & Agent Master Plan

> **Event:** Mumbai Civic Budget & Accountability Impact Lab (Nov 21, 2026)  
> **Status:** Final Planning Lock (Structure & Stack Ready; Replace `{{PLACEHOLDERS}}` as locked)  
> **Audience:** Frontend, Backend/Data, Policy/Pitch Leads, and AI Coding Agents

---

## 1. Product Positioning & The Golden Rule

**{{PROJECT_NAME}}** is a **Pre-Payment Audit Gate & Public Rupee Ledger** for Mumbai's monsoon road repairs.

- **Why we beat 99% of hackathon demos:** Most teams will build a passive pothole heatmap, a raw outlier list, a "name-and-shame" leaderboard (which BMC rejects), and a hallucination-prone chatbot.
- **What we build instead:**
  1. **Pre-Payment Gate ("Paid Twice" Ledger):** Catches fresh repair bills on roads still under active DLP (Defect Liability Period) warranty *before* money leaves the treasury.
  2. **Audit Shield for Officers:** Frames flags as **"Needs Explanation"** (never "Fraud") with a Right-of-Reply—protecting signing engineers from personal liability and CAG audit objections.
  3. **Proactive Maintenance Alerts:** Tracks scheduled contractor maintenance obligations and logs `Alert Sent → Replied / No Reply → Escalated` as indisputable accountability proof.
  4. **Consumer Pull ("Move-In Check"):** Gives citizens a reason to use the app *before* filing a complaint by checking a neighborhood's monsoon livability, flood history, and contractor track record before renting/buying/relocating.
  5. **Zero-App, Voice-First Accessibility:** Built for Mumbai's real networks, low-end Android phones, outdoor sunlight, and Marathi/Hindi/English commuters.

### The Golden Architecture Rule
**Deterministic code computes every number. Claude NEVER does arithmetic.**  
Python/DuckDB computes all joins, rupee totals, flags, and scores. Claude sits strictly downstream to:
1. Explain pre-computed flag records in plain `EN / हिन्दी / मराठी` with clickable row ID citations.
2. Draft formal **DLP Defect Notices** and **RTI Applications**.
3. Parse messy vernacular citizen voice/text queries and match them to `localities.csv` / `roads.csv`.

---

## 2. Judging Criteria Alignment

| Criterion | Weight | How {{PROJECT_NAME}} Wins |
| :--- | :---: | :--- |
| **Audit Accuracy** | 25% | Tier 1–3 deterministic detectors (DLP paid-twice, rate-card overbilling, duplicate/overlapping work orders, rain-day asphalt work) with `rupees_at_stake` and `evidence_row_ids[]`. |
| **Fair Accountability** | 20% | Context-adjusted contractor scoring (rainfall, flood hotspots, traffic) + documented **Maintenance Alert** heads-up log + **Right-of-Reply** field. |
| **Budget Smarts** | 20% | Next-Rupee Planner with budget slider, reason codes (`FLOOD_SPOT`, `AMBULANCE_ROUTE`, `UNDER_REPORTED_WARD`), and a **₹0 Cost to BMC (Owed under DLP)** bucket. |
| **Connects the Trail** | 15% | End-to-end normalized trail: `complaints.csv` ↔ `work_orders.csv` ↔ `roads.csv` (`under_dlp`) ↔ `contractors.csv` ↔ `accidents.csv`. |
| **Usable + Demo** | 20% | Tactile UPI-style Road Receipt, 10-second vernacular audio readout, voice-first citizen lookup, **Move-In Check** radius tool, and 1-click Notice Generator. |

---

## 3. India-First Frontend Stack (Low-End Devices & Spotty 4G)

- **Core Framework:** **React + Vite + Tailwind CSS** — fast hackathon iteration, tiny gzipped bundle (<100 KB).
- **Maps (No Heavy WebGL):** **Leaflet** or lightweight **D3/SVG GeoJSON** for `wards.geojson` and `roads.geojson` (avoids Mapbox GL crashes on budget Android GPUs).
- **Typography:** `Inter` (with `font-variant-numeric: tabular-nums` enforced globally) + `Noto Sans Devanagari` for Marathi/Hindi. `JetBrains Mono` / `ui-monospace` strictly for IDs (`WO-1042`, `road_id`), timestamps, and evidence row citations.
- **Icons:** `lucide-react` (single consistent `1.5px` stroke weight everywhere).
- **Voice & Audio Accessibility:** Native Web Speech API (`SpeechRecognition` for Marathi/Hindi/English voice input + `speechSynthesis` for 10-second "Station Announcement" audio summaries) with instant text fallback.
- **Network Resilience:** Cache all static JSON exports in `localStorage` on first load so the live demo never dies if venue Wi-Fi drops. Include real skeleton/loading states for the 2 live Claude endpoints.

---

## 4. The 20 Non-Negotiable UI & Accessibility Rules

Every screen and component MUST follow these rules:
1. **Delete filler badges** — no decorative pills or vanity tags.
2. **Drop redundant labels** — let context and hierarchy speak.
3. **Unitalicize random words** — keep typography crisp and straight.
4. **Mono only where needed** — strictly IDs, timestamps, and row citations.
5. **Use a design system** — locked spacing, type scale, and radius tokens.
6. **Show the actual product** — lead with real data and actions, not marketing fluff.
7. **Enlarge the main feature** — make the hero ₹ figure, voice button, or map unmistakable.
8. **Group with spacing** — use whitespace instead of excessive borders and boxes.
9. **Make headlines specific** — exact road names, ward codes, and rupee totals.
10. **Emphasize the CTA** — one unmistakable primary action per screen.
11. **Add an accent colour** — one deliberate signal accent reserved for CTAs and active states.
12. **Keep icons consistent** — uniform `1.5px` stroke from `lucide-react`.
13. **Remove embellishments** — zero gradients, drop-shadow bloat, or decorative noise.
14. **Inner radius = outer − padding** — strict nested corner geometry.
15. **Improve text contrast** — sunlight-safe WCAG AAA/AA contrast + geometric status patterns (never rely on red/green alone).
16. **Wrap headlines properly** — use `text-wrap: balance`.
17. **Align by eye, not pixels** — optical alignment on icons, buttons, and numerals.
18. **Use tabular nums** — `tabular-nums` on every ₹ figure, percentage, date, and count.
19. **Add loading states** — real skeletons for Claude notice generation and locality lookups.
20. **Animate useful feedback** — functional micro-transitions only (e.g., alert flipping to `No Reply`, budget slider recalculating, payment hold stamp).

### Design System Options (Lock One Before Coding)
- **Form Factor:**
  - *Option A (Recommended):* **Dual-Mode** — Mobile-first frame (`max-w-[430px]`) for Citizen Hub & Road Receipt + Desktop Split-Pane (`1280px`) for Officer Audit Desk.
  - *Option B:* **Unified Responsive Shell** — single fluid layout across mobile and desktop.
- **Visual Polarity:**
  - *Polarity A (Recommended for Sunlight/Citizens):* **High-Contrast Civic Paper (Light)** — Canvas `#F7F7F5`, Surface `#FFFFFF`, Ink `#111111`, Secondary `#52525B`, Accent `#D94E1F` (Signal Vermilion) or `#0052CC` (Cobalt).
  - *Polarity B (Great for Dark Projectors/Officers):* **Forensic Telemetry (Dark)** — Canvas `#0D0E11`, Surface `#16181D`, Text `#F4F4F5`, Secondary `#A1A1AA`, Accent `#F59E0B` (Amber).

---

## 5. Complete 5-Screen Architecture & Structural Variations

### Sync Map (From Earlier 4-View Plan → Final 5-Screen Plan)
- **View 1 → Screen 1:** City Pulse & Audit Gate *(same + Maintenance Alert ticker)*
- **View 2 → Screen 2:** Road Receipt *(same + Maintenance Alert step in timeline)*
- **View 3 (Tab A) → Screen 3:** Maintenance Alert & Contractor Ledger *(promoted from tab + automated alert escalation queue)*
- **View 3 (Tab B) → Screen 4:** Next-Rupee Planner *(100% identical, now its own screen)*
- **View 4 → Screen 5:** Citizen Hub *(same base + 2-mode toggle: "Check My Street" & "Moving Here?")*

---

### Screen 1: City Pulse & Audit Gate (Officer / Judge Entry)
- **Top 3-Metric Rupee Strip (`tabular-nums`):** Total Spend vs. Budget | Recoverable ₹ (Active DLP) | Overdue Maintenance Alerts (`No Reply`).
- **Interactive Ward Map (`wards.geojson`):** Colored by **Warranty Enforcement Rate**; flags **Under-Reported Wards**.
- **Top Flagged Queue:** 5 highest-rupee roads needing explanation (click any row → Screen 2).

---

### Screen 2: Road Receipt / The Proof Trail (Officer & Citizen)
*Choose one layout variation:*

- **Variation 2A — Vertical UPI Ledger (Mobile-First):**
  - Sticky header: Road Name + Ward/Road ID (mono) + **10-sec Audio Readout (`🔊`)**.
  - Enlarged hero ₹ Total Spent + Geometric Warranty Status Block (`UNDER WARRANTY`).
  - Vertical Proof Trail (grouped by spacing): `Complaint (CMP-ID)` → `Work Order (WO-ID, ₹, Contractor)` → `Maintenance Alert (Sent / No Reply 72h)` → `Audit Flag (Needs Explanation + Evidence Row IDs)`.
  - High-contrast Accent CTA: **Draft Defect Notice (EN / मराठी)**.
- **Variation 2B — Split-Pane Forensic Desk (Desktop):**
  - Left pane: Road Identity, Hero ₹ Spent & ₹ Recoverable, Warranty Block, Contractor Context, Primary CTA.
  - Right pane: Chronological Proof Trail, Maintenance Alert Log, Flag Card with clickable row IDs + **Right-of-Reply** input.
- **Variation 2C — Compact 2G Accordion (Ultra-Low Bandwidth):**
  - Single-row summary header + collapsible sections (`Billing Trail`, `Maintenance Alerts`, `Linked Complaints`) + sticky CTA.

---

### Screen 3: Maintenance Alert & Contractor Ledger (Officer)
- **60/40 Split Layout:**
  - **Left (Fair Contractor Matrix):** 30-Day Reopen Rate, SLA Met Rate, and Risk-Adjusted Score displayed *directly beside* Ward Rainfall, Flood Hotspots, and Traffic context (zero blame without context).
  - **Right (Automated Maintenance Alert Queue):** Tracks scheduled DLP/pre-monsoon maintenance loops: `Scheduled → Alert Sent → Replied / No Reply (Overdue) → Escalated to Payment Hold`.

---

### Screen 4: Next-Rupee Planner (Officer)
- **Top Interactive Budget Scrubber:** Adjust remaining ward budget in ₹ Lakhs/Crores.
- **Dual-Bucket Output:**
  - **Bucket A (`₹0 Cost to BMC` — Contractor Owes under DLP):** High-risk roads still under warranty, visually showing how much budget is freed up.
  - **Bucket B (`Ranked High-Risk Roads`):** Sorted by harm avoided per rupee with explicit reason codes (`FLOOD_SPOT`, `AMBULANCE_ROUTE`, `HIGH_TRAFFIC`, `ACCIDENT_PRONE`, `UNDER_REPORTED_WARD`).

---

### Screen 5: Citizen Hub — Voice Lookup + Move-In Check (Everyday Citizen)
*Choose one layout variation:*

- **Variation 5A — Thumb-Dock + Dual Mode Switcher (Recommended):**
  - Top segmented switch: **`[ Check My Street ]`** | **`[ Moving Here? ]`**.
  - Enlarged Hero Card:
    - *Mode A (Check My Street):* Instant Road Receipt + 1-tap `Still Broken / Reopen` + Swiggy-style live tracker.
    - *Mode B (Moving Here? / Relocation Check):* 1.5 km radius **Monsoon Livability Card** showing nearby flood hotspots, past road failure rate, ambulance/hospital entry road reliability, and zone contractor track record.
  - **10-sec Audio Summary (`🔊 Listen in EN / हिं / म`)**.
  - **Bottom 25% "Local Train" Thumb Dock:** `[ EN | हिं | म ]` | `( 🎙️ VOICE )` | `[ 📍 Pin / QR ]`.
- **Variation 5B — Map-First Radius Scanner:** 55% viewport interactive 1.5 km radius map + 45% draggable bottom sheet for Move-In Livability stats.
- **Variation 5C — Zero-Read Voice Canvas:** Enlarged centered mic trigger + single locality search bar; cards slide up only after input.

---

## 6. Official Dataset Schema & Hygiene Rules (`Claude-Impact-Labs-data-2`)

- **Core Tables:** `wards.csv` (`ward_code`, `monsoon_repair_budget_inr_2025`), `roads.csv` (`road_id`, `under_dlp`), `work_orders.csv` (2,499 rows: `work_order_id`, `cost_inr`, `completed_at`, `reopened_within_30d`, `sla_met`, `linked_complaint_ids`), `complaints.csv` (6,501 rows), `contractors.csv` (`contractor_id`), `rate_card.csv` (`repair_method`, `standard_rate_inr`).
- **Context & Risk Tables:** `localities.csv` (`locality`, `lat`, `lon`, `aliases`), `traffic.csv` (`road_id`), `flood_hotspots.csv` (`ward_code`), `facilities.csv` (`ambulance_entry_road` → `road_id`), `accidents.csv` (`road_id`), `rainfall_daily.csv` (`date`, `station`), `tides.csv` (`date`, `high_tide_time`), `social_posts.csv` (text-only).
- **Spatial Files:** `wards.geojson` (`ward_code`), `roads.geojson` (`road_id`).

### Mandatory Data Hygiene Rules
1. **Explode Junction Table:** Split `work_orders.linked_complaint_ids` on `|` into `complaint_work_orders(complaint_id, work_order_id)` (4,948 of 6,501 complaints link to work orders).
2. **Never Double-Count Sample:** `complaints_sample_200.csv` is a strict subset of `complaints.csv`.
3. **Normalize Null Wards & Localities:** 457 complaints have null `ward_code`; 37 locality strings need case/alias normalization against `localities.csv`.
4. **Canonical Contractor Names:** Always join on `contractor_id` and pull names from `contractors.csv`.
5. **Prevent Date Fan-Out:** Aggregate `rainfall_daily.csv` and `tides.csv` to daily grain before joining.

---

## 7. Frontend ↔ Backend Handoff Contract

> **Hackathon Speed Rule:** Backend exports **5 static JSON files** to `{{DATA_PATH}}` and exposes only **2 live Claude endpoints**. Frontend caches static JSON in `localStorage`.

### A. Static JSON Exports
1. **`{{DATA_PATH}}/summary.json`** *(Screen 1)*: City totals (`total_budget_inr`, `total_spend_inr`, `recoverable_dlp_inr`, `overdue_alerts_count`) + `wards[]` (`ward_code`, `budget_inr`, `spend_inr`, `recoverable_dlp_inr`, `warranty_enforcement_rate`, `under_reported_flag`).
2. **`{{DATA_PATH}}/roads_audit.json`** *(Screen 2)*: Per-road `road_id`, `road_name`, `ward_code`, `under_dlp`, `work_orders[]`, `linked_complaints[]`, `flags[]` (`flag_id`, `tier`, `detector`, `status_label: "Needs Explanation"`, `rupees_at_stake`, `evidence_row_ids[]`, `rule_text`, `right_of_reply`), and **`maintenance_alerts[]`** (`alert_id`, `alert_date`, `due_date`, `status: "sent" | "replied" | "no_reply" | "escalated"`).
3. **`{{DATA_PATH}}/contractors.json`** *(Screen 3)*: Per-contractor `contractor_id`, `contractor_name`, `jobs_count`, `reopen_rate_30d`, `sla_met_rate`, `risk_adjusted_score`, `unanswered_alerts_count`, `context` (`avg_ward_rainfall_mm`, `flood_prone_share`, `avg_peak_vehicles`).
4. **`{{DATA_PATH}}/next_rupee.json`** *(Screen 4)*: Ranked roads with `road_id`, `ward_code`, `under_dlp`, `priority_score`, `estimated_repair_cost_inr`, `cost_to_bmc_inr` (`0` if DLP), and `reason_codes[]`.
5. **`{{DATA_PATH}}/localities_livability.json`** *(Screen 5 — Move-In Check; optional backend export or computed client-side)*: Keyed by `locality` (`lat`, `lon`, `ward_code`, `nearby_flood_hotspots_count`, `road_failure_rate_30d`, `ambulance_route_status`, `avg_contractor_score`, `nearby_road_ids[]`).

### B. Live Claude Endpoints (`{{API_BASE_URL}}`)
- **`POST /api/draft-notice`**
  - In: `{ "flag_id": "string", "language": "en|hi|mr", "doc_type": "defect_notice|rti" }`
  - Out: `{ "title": "string", "body": "string", "cited_row_ids": ["string"] }`
- **`POST /api/citizen-query`**
  - In: `{ "text": "string", "language": "en|hi|mr", "mode": "street_check|move_in" }`
  - Out: `{ "matched_locality": "string", "matched_road_id": "string", "plain_language_reply": "string", "warranty_status": "string" }`

---

## 8. Placeholders & Build Checklist

- **Project Name:** `{{PROJECT_NAME}}`
- **Frontend Owner:** `{{FRONTEND_OWNER}}` | **Backend Owner:** `{{BACKEND_OWNER}}` | **Policy/Pitch Owner:** `{{POLICY_OWNER}}`
- **Claude Model:** `{{CLAUDE_MODEL}}` | **API Base URL:** `{{API_BASE_URL}}` | **Hero Demo Road ID:** `{{DEMO_ROAD_ID}}`

### Execution Milestones
- [ ] **Lock Polarity & Variations** (Recommended: Dual-Mode + Light Civic Paper + Var 2A + Var 5A).
- [ ] **Scaffold App + Design Tokens** (`tabular-nums`, `inner = outer - padding`, `EN | हिं | म` switcher, mock JSON).
- [ ] **Build Screens 2 & 5 First** (Road Receipt + Citizen Hub / Move-In Check — highest visual & demo differentiation).
- [ ] **Build Screens 1, 3 & 4** (City Map + Maintenance Alert / Fair Contractor Ledger + Next-Rupee Budget Slider).
- [ ] **Swap Real JSON + Wire 2 Live Claude Endpoints** + cache in `localStorage`.
- [ ] **Rehearse 3-Minute Demo** (Open with 1 real road story → show ignored maintenance alert → draft notice → show fair context → close with freed ₹ budget & Move-In Check).