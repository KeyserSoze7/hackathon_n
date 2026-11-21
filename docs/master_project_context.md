# {{PROJECT_NAME}} — Master Project Context (Agent & Team Reference)

> **Purpose:** Single source of truth for developers, policy/pitch leads, and AI coding agents building **{{PROJECT_NAME}}** for the Mumbai Civic Budget & Accountability Impact Lab.  
> **Placeholders:** Replace any `{{VARIABLE}}` once the team locks final names, URLs, and owners.

---

## 1. Product Positioning & Differentiator

**{{PROJECT_NAME}}** is a **Pre-Payment Audit Gate & Public Rupee Ledger** for Mumbai's monsoon road repairs.

- **What everyone else builds:** A passive pothole heatmap, raw z-score outlier list, unadjusted "name-and-shame" ward leaderboard, and a free-form chatbot over CSVs.
- **What {{PROJECT_NAME}} builds instead:**
  1. **Pre-Payment Gate ("Paid Twice" Ledger):** Joins work orders to road DLP (Defect Liability Period) status to flag money owed free by contractors *before* bills are cleared.
  2. **Deterministic Physics & Rate Checks:** Catches rate-card inflation, duplicate/overlapping work orders, rain-day asphalt work, and paper closures using pure code.
  3. **Context-Adjusted Fairness:** Scores contractors after adjusting for ward rainfall, flood hotspots, and traffic—so nobody is penalized just for working in a flood-prone ward.
  4. **Silence-Adjusted Next-Rupee Planner:** Ranks next-rupee spending by physical risk (flooding, traffic, accidents, hospital/school ambulance access) and flags under-reported wards. Roads under DLP cost BMC **₹0**, freeing budget for other stretches.
  5. **Zero-App Citizen Accessibility:** Vernacular (`EN | हिन्दी | मराठी`), voice-first citizen lookup and verification with no login wall.

### The Golden Architecture Rule
**Code computes every number. Claude NEVER does arithmetic.**  
All joins, rupee totals, anomaly flags, and rankings are computed deterministically in Python/DuckDB. Claude sits strictly downstream to:
1. Explain pre-computed flag records in plain English/Hindi/Marathi with explicit row ID citations.
2. Draft formal **DLP Defect Notices** and **RTI Applications** citing exact contract/work-order IDs.
3. Parse messy vernacular citizen complaints/queries and match them to `localities.csv` / `roads.csv`.

---

## 2. Judging Criteria Alignment

| Criterion | Weight | How {{PROJECT_NAME}} Wins It |
| :--- | :---: | :--- |
| **Audit Accuracy** | 25% | Tier 1–3 deterministic detectors (DLP violations, rate-card overbilling, duplicate claims, rain-day work) with `rupees_at_stake` and `evidence_row_ids[]`. |
| **Fair Accountability** | 20% | Risk-adjusted contractor scorecard (rainfall, flood, traffic context). Flags read **"Needs Explanation"** (never "Fraud") with a Right-of-Reply field. |
| **Budget Smarts** | 20% | Next-Rupee Planner with budget slider, reason codes (`FLOOD_SPOT`, `AMBULANCE_ROUTE`, `UNDER_REPORTED_WARD`), and ₹0 DLP reallocation bucket. |
| **Connects the Trail** | 15% | Full normalized trail: `complaints.csv` ↔ `complaint_work_orders` ↔ `work_orders.csv` ↔ `roads.csv` ↔ `contractors.csv`. |
| **Usable + Demo** | 20% | Mobile-first UPI-style Road Receipt, `EN | हिन्दी | मराठी` toggle, voice-first citizen drawer, and 1-click Notice Generator. |

---

## 3. Official Dataset Schema (`Claude-Impact-Labs-data-2`)

### Core Tables & Keys
| File | Primary Key | Foreign Keys / Joins | Notes |
| :--- | :--- | :--- | :--- |
| `wards.csv` | `ward_code` | — | Contains `monsoon_repair_budget_inr_2025` |
| `localities.csv` | `locality` | `ward_code` → `wards` | Contains `lat`, `lon`, semicolon-separated `aliases` |
| `roads.csv` | `road_id` | `ward_code` → `wards` | Contains `road_name`, `under_dlp` |
| `traffic.csv` | `road_id` | `road_id` → `roads` | 291 rows (`peak_hour_vehicles`, `avg_peak_speed_kmph`) |
| `complaints.csv` | `complaint_id` | `ward_code` (nullable) | 6,501 rows; `locality_text`, `received_at`, `status` |
| `work_orders.csv` | `work_order_id` | `ward_code`, `road_id`, `contractor_id`, `repair_method` | 2,499 rows; `cost_inr`, `completed_at`, `reopened_within_30d`, `sla_met`, `linked_complaint_ids` |
| `contractors.csv` | `contractor_id` | — | Canonical `contractor_name` |
| `rate_card.csv` | `repair_method` | — | `unit`, `standard_rate_inr` |
| `flood_hotspots.csv` | `hotspot_id` | `ward_code` → `wards` | `flood_threshold_mm_per_day` |
| `facilities.csv` | `facility_id` | `ward_code` → `wards`; `ambulance_entry_road` → `roads` | 160 rows (hospitals & schools) |
| `accidents.csv` | `accident_id` | `ward_code`, `road_id` | 420 rows (`occurred_at`) |
| `rainfall_daily.csv` | (`date`, `station`) | Joins to `tides.csv` on `date` | No explicit ward key; aggregate by date |
| `tides.csv` | (`date`, `high_tide_time`) | Joins to `rainfall_daily.csv` on `date` | Two rows per date; aggregate by date |
| `social_posts.csv` | `post_id` | None (text-only) | Infer road/locality via text matching with confidence score |
| `wards.geojson` / `roads.geojson` | `ward_code` / `road_id` | Spatial companions | Synthetic road geometries & approximate ward polygons |

### Mandatory Data Hygiene Rules (For All Agents & Scripts)
1. **Explode Junction Table:** Split `work_orders.linked_complaint_ids` on `|` to create `complaint_work_orders(complaint_id, work_order_id)` (4,948 of 6,501 complaints link to work orders).
2. **Do Not Double-Count Sample:** `complaints_sample_200.csv` is a strict subset of `complaints.csv`. Never union them.
3. **Clean Null Wards & Localities:** 457 complaints have null `ward_code`, and 37 locality strings don't match `localities.csv` exactly. Normalize case/spelling against `localities.aliases` and retain unmatched rows for review.
4. **Canonical Contractor Names:** Always join on `contractor_id` and read names from `contractors.csv` (not the repeated column in `work_orders.csv`).
5. **Prevent Date Fan-Out:** Aggregate `rainfall_daily.csv` and `tides.csv` to daily grain before joining to work orders or complaints.

---

## 4. Deterministic Audit Detectors & Flag Schema

Every flag generated by the backend MUST follow this schema so Claude and the frontend can render verifiable citations:
~~~json
{
  "flag_id": "FLG-001",
  "tier": 1,
  "detector": "DLP_PAID_TWICE | RATE_INFLATION | OVERLAPPING_WORK_ORDER | RAIN_DAY_WORK | PAPER_CLOSURE",
  "status_label": "Needs Explanation",
  "ward_code": "string",
  "road_id": "string",
  "contractor_id": "string",
  "rupees_at_stake": 0,
  "evidence_row_ids": ["WO-...", "CMP-...", "R-..."],
  "rule_text": "Plain deterministic rule that triggered this flag",
  "right_of_reply": ""
}
~~~

- **Tier 1 (Contractual / Physical Impossibilities):** Paid work order on a road where `under_dlp == true`; overlapping/duplicate work orders on the same `road_id` & date window; impossible dates.
- **Tier 2 (Strong Implausibilities):** Unit cost significantly above `rate_card.standard_rate_inr`; asphalt work logged on heavy-rain days (`rainfall_daily.csv`); closed complaints with rapid repeat complaints (`reopened_within_30d`) or no linked work order.
- **Tier 3 (Statistical Leads — Never Accusations):** Approval-limit bill splitting; contractor ward concentration; fast-failure outliers after risk adjustment.

---

## 5. Tech Stack, Ownership & Placeholders

- **Project Name:** `{{PROJECT_NAME}}`
- **Frontend:** `{{FRONTEND_FRAMEWORK}}` — Owner: `{{FRONTEND_OWNER}}`
- **Backend / Data Engine:** `{{BACKEND_STACK}}` (Python + DuckDB/Pandas + FastAPI) — Owner: `{{BACKEND_OWNER}}`
- **AI / Policy / Pitch:** `{{POLICY_OWNER}}`
- **Claude Model:** `{{CLAUDE_MODEL}}`
- **API Base URL:** `{{API_BASE_URL}}`
- **Static Data Export Path:** `{{DATA_PATH}}` (exports: `summary.json`, `roads_audit.json`, `contractors.json`, `next_rupee.json`)
- **Hero Demo Road ID:** `{{DEMO_ROAD_ID}}` *(pick the clearest Tier 1 DLP case from the dataset)*

---

## 6. Guardrails for AI Agents Working in This Repo

1. **Never fabricate numbers in prompts or UI copy.** All ₹ figures must come from `{{DATA_PATH}}/*.json` or verified DuckDB queries.
2. **Preserve neutral civic framing.** Use *"Needs Explanation"*, *"Recoverable under DLP"*, and *"Context-Adjusted"*. Never output *"Fraud"* or *"Corrupt"*.
3. **Format currency for India.** Display Lakhs (`₹42.0L`) and Crores (`₹1.80 Cr`).
4. **Keep citizen UI accessible.** Mobile-first, zero login, support `EN | हिन्दी | मराठी` copy keys.
5. **Document limitations transparently.** Synthetic dataset, inferred text matches carry confidence scores, Tier 3 flags are auditor leads only.