# {{PROJECT_NAME}} — Frontend User Flow & Backend Handoff Plan

> **Owner:** {{FRONTEND_OWNER}}  
> **Stack:** {{FRONTEND_FRAMEWORK}}  
> **Goal:** Build a zero-login, mobile-first **Pre-Payment Audit Gate + Citizen Rupee Receipt** that directly hits all 5 judging criteria and gives the backend team a clean, frictionless data contract.

---

## 1. Core UX & Trust Principles

1. **UPI-Receipt Simplicity:** Citizens should read a road's budget and warranty status as effortlessly as a UPI payment receipt—clear Indian currency formatting (`₹42.5L`, `₹1.80 Cr`), bold status pills, and zero government-portal clutter.
2. **Neutral, Official-Friendly Tone (Adoption Layer):**
   - Never label a flag as *"Fraud"* or *"Corrupt"*. Always label it **"Needs Explanation"** or **"Recoverable under DLP"**.
   - Every flagged bill includes a **Right-of-Reply** field for the Ward Engineer / Contractor.
   - Frame the internal view as an **Audit Shield** that protects signing engineers from personal liability.
3. **Verifiable Evidence Receipts:** Code computes every number; Claude only writes the explanation. Every metric or flag displays clickable **Evidence Row IDs** (e.g., `WO-1042`, `CMP-4821`) so judges can verify zero hallucination.
4. **Vernacular & Zero-Friction Accessibility:**
   - **No login walls.**
   - Live language toggle: **`EN` | `हिन्दी` | `मराठी`**.
   - **Voice-first** citizen input (Marathi/Hindi/Hinglish/English) + photo upload / QR scan entry.

---

## 2. End-to-End User Flow (4 Views)

### View 1: City & Ward Audit Overview
*Maps to: **Audit Accuracy (25%)***

- **Top KPI Strip (3 Hero Numbers):**
  1. **Total Monsoon Spend vs. Budget** (`work_orders.cost_inr` vs. `wards.monsoon_repair_budget_inr_2025`)
  2. **Recoverable ₹ (Paid Twice / Active DLP)** — headline money-back figure
  3. **Bills Needing Explanation** — count of Tier 1 & Tier 2 flags
- **Interactive Ward Map (`wards.geojson`):**
  - Colored by **Warranty Enforcement Rate** (not raw complaint counts).
  - Badges highlighting **Under-Reported Wards** (high physical risk, low complaint volume).
- **Flagged Queue Table:** Top work orders ranked by `rupees_at_stake`.
- **User Action:** Clicking any ward or flagged road transitions to **View 2 (The Road Story)**.

---

### View 2: The Road Story / "Rupee Receipt"
*Maps to: **Connects the Trail (15%)** + **Audit Accuracy (25%)***

- **Header Card (`road_id`):**
  - Road name, ward, surface type, total ₹ billed.
  - Bold **Warranty Pill:** `🟢 UNDER WARRANTY (DLP Active)` or `⚪ OUT OF WARRANTY`.
  - **Audit Alert Banner (if flagged):** Plain-language 3-line Claude summary + exact `rupees_at_stake` + clickable `evidence_row_ids[]`.
- **Connected Trail Timeline (Vertical):**
  - Stitches `complaints.csv` → `work_orders.csv` → `roads.csv` (`under_dlp`) → `accidents.csv` in chronological order.
  - Clearly highlights repeat complaints within 30 days (`reopened_within_30d`) and rain-day work (`rainfall_daily.csv`).
- **Two-Key Verification & Right-of-Reply Box:**
  - Shows Contractor Claim (`completed_at`) vs. Citizen Verification status.
  - Includes a **Right-of-Reply** text box for the ward officer/contractor to log a justification (e.g., utility trenching).
- **1-Click Action Button:**
  - **"Draft Defect Notice / RTI (EN | मराठी)"** → Calls `POST /api/draft-notice`, opens a clean modal with copy/PDF export and cited row IDs.

---

### View 3: Fair Accountability & Next-Rupee Planner
*Maps to: **Fair Accountability (20%)** + **Budget Smarts (20%)***

Split into two clean sub-tabs:

#### Tab 3A: Context-Adjusted Contractor Scorecard
- **No raw "A–F" shaming grades.**
- Displays each contractor's **30-Day Reopen Rate**, **SLA Met Rate**, and **Risk-Adjusted Survival / Half-Life Score** *side-by-side* with their **Ward Context** (rainfall volume, flood hotspots, peak traffic).
- Shows sample size / uncertainty band so a small contractor isn't unfairly penalized.

#### Tab 3B: Next-Rupee Budget Planner
- **Interactive Budget Slider:** Adjust remaining ward budget (in ₹ Lakhs / Crores).
- **Two-Bucket Output (The Demo Closer):**
  1. **Bucket A — ₹0 Cost to BMC (Owed by Contractor under DLP):** High-risk roads currently under warranty. Visually shows how much budget is *freed up* by enforcing DLP.
  2. **Bucket B — Ranked Next-Rupee Investments:** Remaining high-risk roads ranked by harm avoided per rupee, showing explicit **Reason Badges**:
     - `FLOOD_SPOT` (`flood_hotspots.csv`)
     - `AMBULANCE_ROUTE` (`facilities.csv` → `ambulance_entry_road`)
     - `HIGH_TRAFFIC` (`traffic.csv`)
     - `ACCIDENT_PRONE` (`accidents.csv`)
     - `UNDER_REPORTED_WARD` (Silence-adjusted need)

---

### View 4: Citizen Accessibility Layer (Zero-App Lookup & Report)
*Maps to: **Usable + Demo (20%)***

- **Entry:** Simulated QR-scan banner + WhatsApp-style chat / lookup drawer.
- **Input:** Single tactile **Mic Button** (voice note in Marathi/Hindi/Hinglish/English) + text input + optional photo attachment.
- **Flow:**
  1. Citizen asks: *"Andheri subway ke bahar wapas khadda ho gaya, paisa kahan gaya?"*
  2. Calls `POST /api/citizen-query` → resolves landmark via `localities.csv` aliases.
  3. Returns a mobile-friendly **Road Receipt Card** in the user's selected language: road owner, warranty status, linked work order status, and a 1-tap **"Still Broken / Reopen"** or **"Draft RTI"** button.
  4. **Live Accountability Tracker (Swiggy-style):** `Reported → Matched to Contract → Payment Auto-Held (DLP) → Contractor Notified`.

---

## 3. Frontend ↔ Backend Handoff Contract

> **Hackathon Speed Rule:** Pre-compute all analytics into **4 static JSON files** in `{{DATA_PATH}}` so the frontend never blocks on backend server setup. Only **2 live API endpoints** need to call Claude.

### A. Static JSON Exports (Generated by Python / DuckDB Pipeline)

#### 1. `{{DATA_PATH}}/summary.json` (Powers View 1)
~~~json
{
  "city_totals": {
    "total_budget_inr": 0,
    "total_spend_inr": 0,
    "recoverable_dlp_inr": 0,
    "flagged_bills_count": 0
  },
  "wards": [
    {
      "ward_code": "K-W",
      "ward_name": "K-West",
      "budget_inr": 0,
      "spend_inr": 0,
      "recoverable_dlp_inr": 0,
      "warranty_enforcement_rate": 0.42,
      "under_reported_flag": false,
      "flood_hotspots_count": 5
    }
  ]
}
~~~

#### 2. `{{DATA_PATH}}/roads_audit.json` (Powers View 2)
~~~json
[
  {
    "road_id": "R-1042",
    "road_name": "S.V. Road Stretch",
    "ward_code": "K-W",
    "under_dlp": true,
    "dlp_expiry": "2028-10-01",
    "total_billed_inr": 24000000,
    "work_orders": [
      {
        "work_order_id": "WO-8819",
        "contractor_id": "C-12",
        "contractor_name": "{{CONTRACTOR_NAME}}",
        "repair_method": "Mastic Asphalt",
        "cost_inr": 4200000,
        "completed_at": "2025-07-14",
        "sla_met": false,
        "reopened_within_30d": true,
        "linked_complaint_ids": ["CMP-101", "CMP-102"]
      }
    ],
    "flags": [
      {
        "flag_id": "FLG-001",
        "tier": 1,
        "detector": "DLP_PAID_TWICE",
        "status_label": "Needs Explanation",
        "rupees_at_stake": 4200000,
        "rule_text": "Paid repair billed on road segment with under_dlp = true.",
        "evidence_row_ids": ["WO-8819", "R-1042", "CMP-101"]
      }
    ]
  }
]
~~~

#### 3. `{{DATA_PATH}}/contractors.json` (Powers View 3A)
~~~json
[
  {
    "contractor_id": "C-12",
    "contractor_name": "{{CONTRACTOR_NAME}}",
    "jobs_count": 28,
    "total_billed_inr": 85000000,
    "reopen_rate_30d": 0.24,
    "sla_met_rate": 0.71,
    "risk_adjusted_score": 62.5,
    "tier1_flags_count": 3,
    "recoverable_inr": 4200000,
    "context": {
      "avg_ward_rainfall_mm": 118.4,
      "flood_prone_share": 0.65,
      "avg_peak_vehicles": 3400
    }
  }
]
~~~

#### 4. `{{DATA_PATH}}/next_rupee.json` (Powers View 3B)
~~~json
[
  {
    "road_id": "R-1042",
    "road_name": "S.V. Road Stretch",
    "ward_code": "K-W",
    "under_dlp": true,
    "priority_score": 94.2,
    "estimated_repair_cost_inr": 4500000,
    "cost_to_bmc_inr": 0,
    "reason_codes": ["FLOOD_SPOT", "AMBULANCE_ROUTE", "HIGH_TRAFFIC", "REPEAT_FAILURE"]
  }
]
~~~

---

### B. Live Claude Endpoints (FastAPI / Backend)

1. **`POST {{API_BASE_URL}}/api/draft-notice`**
   - **Request:** `{ "flag_id": "FLG-001", "language": "en|hi|mr", "doc_type": "defect_notice|rti" }`
   - **Response:** `{ "title": "string", "body": "string", "cited_row_ids": ["WO-8819", "R-1042"] }`
2. **`POST {{API_BASE_URL}}/api/citizen-query`**
   - **Request:** `{ "text": "string", "language": "en|hi|mr" }`
   - **Response:** `{ "matched_locality": "string", "matched_road_id": "R-1042", "plain_language_reply": "string", "warranty_status": "UNDER_DLP|OUT_OF_DLP" }`

---

## 4. Frontend Build Checklist

- [ ] **Hour 1:** Scaffold app shell + language switcher (`EN | हिन्दी | मराठी`) + load mock JSON matching the 4 schemas above.
- [ ] **Hour 2:** Build **View 2 (Road Receipt + Timeline + Evidence Badges)** and **View 4 (Citizen Voice/Chat Drawer)**.
- [ ] **Hour 3:** Build **View 1 (KPIs + Ward Map)** and **View 3 (Fair Scorecard + Next-Rupee Budget Slider)**.
- [ ] **Hour 4:** Swap mock JSON with real backend exports from `Claude-Impact-Labs-data-2` + wire the 2 live Claude endpoints.
- [ ] **Hour 5:** Lock demo road story (`{{DEMO_ROAD_ID}}`) and rehearse 3-minute live walkthrough.