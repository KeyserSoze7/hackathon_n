# View 3 backend: fair scorecard (3A) + next-rupee planner (3B)

## Run
```bash
pip install xgboost shap duckdb "scipy>=1.9" scikit-learn pandas sqlalchemy psycopg2-binary
# local, no DB needed (DuckDB runs the same SQL on the CSVs)
python view3_pipeline.py --csv-dir ../Claude-Impact-Labs-data-2/data
# Supabase
export DATABASE_URL=postgresql://postgres:<pw>@db.<ref>.supabase.co:5432/postgres
python load_to_supabase.py --csv-dir ../Claude-Impact-Labs-data-2/data
python view3_pipeline.py      # creates SQL views, trains, writes v3_* tables back
```
Outputs: `out/contractors.json`, `out/next_rupee.json` (frontend contract plus extra fields),
`out/ward_allocation.json`, `out/allocation_summary.json`, `out/job_expected_risk.csv`, `out/view3_model_meta.json`.
`--budget 50000000` runs another city-wide scenario.

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
Roads under DLP are excluded from the budget and go to **Bucket A** (₹0 to BMC, contractor owes the fix).

**Result on this data** (same money, harm avoided):
| Budget | Optimizer | Most-complained first, cheapest patch | Highest stakes first, cheapest patch |
|---|---|---|---|
| ₹1.77 Cr (2025 money left in wards, the default) | 4,567 | 2,340 | 2,359 → **+95%** |
| ₹1.2 Cr (10% of need) | 3,549 | 1,524 | 1,625 |
| ₹6.1 Cr (50%) | 9,707 | 7,778 | 7,350 |
| ₹12.1 Cr (100%) | 13,340 | 12,867 | 12,868 |

The optimizer helps most when money is tight. At full budget only method choice differs.
Method choice falls out of the maths: hot mix on high-stakes roads, cold mix on quiet ones.
Fixing every non-warranty issue at rate card costs ₹12.1 Cr; warranty roads hold another ₹2.9 Cr owed by contractors.

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
  Swap `v_complaint_road` for their table when it's ready.
- `UNDER_REPORTED_WARD` is not computed yet: ward risk vs complaint volume would be a 10-line SQL add.
- Impact weights are judgment calls, all in `impact_table()`. Crew capacity isn't constrained (it never binds at these volumes).
