-- Queries the frontend / FastAPI can run directly on Supabase after the pipeline has
-- written v3_contractor_scorecard, v3_next_rupee and v3_job_expected_risk.

-- 3A. Scorecard list (fair score first; raw numbers shown next to expected ones).
SELECT contractor_id, contractor_name, jobs_count, total_billed_inr,
       reopen_rate_30d, expected_reopen_rate_30d, durability_index, durability_verdict,
       sla_met_rate, expected_sla_met_rate, speed_index, risk_adjusted_score,
       cost_vs_rate_median, jobs_over_130pct_rate, context, drivers, explanation
FROM v3_contractor_scorecard
ORDER BY risk_adjusted_score DESC;

-- 3B. Ward card: where the next rupee does most good (sorted by marginal harm avoided per lakh).
SELECT ward_code, ward_name, budget_2025_inr, spend_2025_inr, remaining_2025_inr,
       recommended_budget_inr, harm_avoided, harm_avoided_per_next_lakh,
       dlp_items_owed_by_contractor, dlp_value_owed_inr
FROM v3_ward_allocation ORDER BY harm_avoided_per_next_lakh DESC;

-- 3B. Items for one ward at the default scenario. Bucket A (DLP, Rs 0) first, then funded, then unfunded.
-- The live slider calls allocator.allocate_ward() instead of SQL, since it re-solves exactly.
SELECT bucket, funded, item_id, road_name, issue, recommended_method, cost_to_bmc_inr,
       harm_avoided, harm_per_lakh, priority_score, reason_codes, explanation
FROM v3_next_rupee WHERE ward_code = :ward
ORDER BY bucket, funded DESC, priority_score DESC;

-- Evidence drill-down: every job of one contractor with its expected failure probability.
SELECT w.work_order_id, w.road_id, w.ward_code, w.repair_method, w.cost_inr,
       w.reopened_within_30d, j.p_reopen_expected
FROM work_orders w JOIN v3_job_expected_risk j USING (work_order_id)
WHERE w.contractor_id = :contractor_id
ORDER BY (w.reopened_within_30d = 'Y') DESC, j.p_reopen_expected ASC;  -- failures on "easy" jobs first
