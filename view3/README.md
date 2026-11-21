# View 3 backend: fair scorecard (3A) + next-rupee planner (3B)

## Run locally (no database)
From the repo root:
```bash
pip install -r view3/requirements.txt      # Python 3.12/3.13; macOS: xgboost needs libomp (`brew install libomp`)
python3 pipeline/build.py                  # audit engine first: writes exports/ward_audit.csv (UNDER_REPORTED_WARD)
python view3/view3_pipeline.py --csv-dir data   # DuckDB runs the same SQL on the CSVs
```

## Supabase / Postgres integration
The schema (tables, types, RLS) is owned by `supabase/migrations/`; this pipeline only writes rows into the `v3_*` tables.
1. **Connection string:** Supabase → Connect → *Session pooler* URI (port 5432; works on IPv4).
   URL-encode special characters in the password (`@` → `%40`). Put it in `.env` as `DATABASE_URL=...` (gitignored).
2. **Schema + data** (repo root):
   ```bash
   python3 pipeline/build.py
   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/20261121000000_schema.sql
   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/20261121000100_audit_views.sql
   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/load_source.sql
   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/load_audit.sql
   ```
3. **Build View 3 results:** `python view3/view3_pipeline.py` creates the feature views, trains, solves, and
   truncates + inserts `v3_contractor_scorecard`, `v3_next_rupee`, `v3_ward_allocation`, `v3_job_expected_risk`
   in one transaction. Y/N flags are booleans in the DB; `load()` maps them back to 'Y'/'N' for this code.
4. **Serve** (one FastAPI app for all four views, in `backend/`, see `backend/README.md`): `cd backend && uvicorn api:app --port 8000`
   - View 1: `GET /api/city`, `GET /api/wards`, `GET /api/flagged-queue?ward=K/W&tier=1&limit=20`
   - View 2: `GET /api/roads/{road_id}`, `GET /api/roads/{road_id}/timeline`, `GET /api/flags/{flag_id}`,
     `POST /api/flags/{flag_id}/replies` (Right-of-Reply)
   - View 3: `GET /api/v3/contractors`, `GET /api/v3/wards`, `GET /api/v3/next-rupee/{ward}`,
     `POST /api/v3/allocate {"ward_code":"K/W","budget_inr":500000}` → exact re-solve, about 0.01 s
   - View 4: `GET /api/lookup?q=...` (road name, locality, alias or Devanagari), `POST /api/citizen-reports`,
     `GET /api/citizen-reports/{id}` (tracker status is set by the server)
   - Tests: `postman collection run postman/backend.postman_collection.json` (23 requests, 59 assertions)
5. **Refresh** after any data change: `build.py` + `load_audit.sql`, then this pipeline. Restart the API.

## Split of work
| Layer | Where | What |
|---|---|---|
| Features | SQL (`sql/01_features.sql`) | rain/tide in the 7 days after each job, hotspot distance, road age, traffic, rate-card ratio, complaints mapped to nearest road, accident harm, hospitals/schools per road |
| Models | Python | 3A: XGBoost + SHAP (can't run inside Postgres). 3B: exact MILP budget allocation |
| Serving | SQL (`sql/02_view3_api.sql`) + `allocate_ward()` | scorecard list, ward allocation, DLP money owed, evidence drill-down; slider re-solves live |

## 3A: how "fair" works
1. XGBoost predicts each job's chance of failing within 30 days (and of missing its SLA) from context only:
   rain and big tides right after the job, ward flood-proneness, hotspot distance, work type, road type, surface, age, traffic.
   It never sees the contractor. Predictions are out-of-fold.
2. Per contractor: observed failures vs the sum of expected. Shrunk toward "as expected" with 10 pseudo-jobs,
   plus a 90% Poisson interval → verdict `better than expected` / `within the normal range` / `worse than expected`.
   Score 0-100, **50 = as expected**. `risk_adjusted_score` = 60% durability + 40% speed.
3. SHAP compares each contractor's jobs with the city average to say *why* their work was harder (the `drivers` field).

**Finding to say out loud in the demo:** weather and ward context barely predict failures in this data (AUC 0.52),
but they strongly predict SLA misses (AUC 0.78). So deadlines needed adjusting, while the gaps in durability are real:
a contractor alone predicts failure with AUC 0.65. The context-adjusted ranking held up even after controlling
for the hard conditions, which makes it stronger evidence, not weaker.

Method choice is *not* adjusted for (`ADJUST_FOR_METHOD = False`): picking cold mix in the monsoon counts against the contractor.

## 3B: next rupee as budget allocation (`allocator.py`)
No forecasting. This season's history is the demand; the model decides **what to fund and with which method**.

**Items:** one per (road segment × issue type) seen this season, 867 in total. Demand `n` = repairs needed this season, plus open complaints.
**Harm per occurrence** `H` = severity (168 / SLA hours: cave-in or open manhole = 7, pothole = 2.3, paver = 1) ×
impact (1 + flood hotspot within 800 m, emergency-hospital ambulance road, schools, traffic, BEST route, road-caused accidents, open complaints).
**Per method:** `benefit = n·H·(1 − fail rate)`, `cost = n · rate-card cost on this road · (1 + fail rate)` (pays for expected re-work).

**Exact MILP** (SciPy HiGHS, no extra solver): maximise harm avoided; at most one method per item; total cost ≤ budget;
**equity floor**: every ward gets at least 50% of its proportional share if it has the demand (`EQUITY_FLOOR`).
Surface defects (potholes, paver blocks) on roads under DLP are excluded from the budget and go to **Bucket A** (₹0 to BMC, contractor owes the fix). Drainage, manhole, waterlogging and cave-in (utility) items on those roads are not DLP liability, so they stay in Bucket B.

**Result on this data** (same money, harm avoided):
| Budget | Optimizer | Most-complained first, cheapest patch | Highest stakes first, cheapest patch |
|---|---|---|---|
| ₹1.77 Cr (2025 money left in wards, the default) | 4,708 | 2,492 | 2,294 → **+89%** vs volume-first |
| ₹1.44 Cr (10% of need) | 4,096 | 2,033 | 2,024 |
| ₹7.21 Cr (50% of need) | 11,381 | 9,100 | 8,925 |
| ₹14.43 Cr (100% of need) | 15,562 | 15,097 | 15,097 |

The optimizer helps most when money is tight. At full budget only method choice differs.
Method choice falls out of the maths: hot mix on high-stakes roads, cold mix on quiet ones.
Fixing every issue BMC pays for at rate card costs ₹14.43 Cr; DLP surface defects hold another ₹76.5L owed by contractors.

**Outputs:** `next_rupee.json` (items: bucket, funded, method, cost, harm avoided, harm per lakh, reason codes, inputs, WO ids, explanation),
`ward_allocation.json` (2025 budget / spend / remaining, recommended budget, harm avoided, **harm avoided per next ₹1 lakh** = where the next rupee does most good, DLP value owed),
`allocation_summary.json` (budget curve + baseline comparison for the demo chart).

**Slider:** call `allocator.allocate_ward(items, opts, ward, budget)` from FastAPI. It re-solves exactly in about 0.01 s.
Load `items, opts = allocator.build_items(d)` once at startup.

## Explainability contract for the Claude endpoint
Each row already carries `explanation` (a deterministic sentence), `drivers` (SHAP, feature + direction) and evidence
(work-order IDs or counts). Send exactly those to Claude with: "Rewrite for a citizen in {language}; use only these numbers; cite the IDs."

## Known gaps / easy upgrades
- Complaints without GPS are placed via exact locality match only; aliases and Devanagari are the linker team's job.
  On Supabase, `locality_aliases` (aliases + Devanagari) is available to swap into `v_complaint_road`.
- `UNDER_REPORTED_WARD` comes from the audit engine's `ward_audit.under_reported_flag` (adds 0.3 to impact and a reason code).
- `dlp_value_owed_inr` here = future surface fixes owed (rate card). The View 1 `recoverable_dlp_inr` = money BMC already paid for DLP-covered repairs. Label them differently in the UI.
- Impact weights are judgment calls, all in `impact_table()`. Crew capacity isn't constrained (it never binds at these volumes).
