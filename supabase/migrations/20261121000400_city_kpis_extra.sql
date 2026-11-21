-- View 1 KPI strip: add headline numbers the frontend needs without doing arithmetic in the UI.
-- Appends columns to city_kpis (existing columns unchanged, so current clients keep working).
--   rupees_at_stake_total  every flagged bill's rupees at stake, each bill counted once (flagged_queue grain)
--   wards_over_budget      wards whose 2025 spend exceeded their monsoon budget
--   under_reported_wards   wards with high physical risk but few complaints (ward_audit.under_reported_flag)
create or replace view city_kpis with (security_invoker = true) as
select sum(budget_inr)::bigint          as total_budget_inr,
       sum(spend_inr)::bigint           as total_spend_inr,
       sum(recoverable_dlp_inr)::bigint as recoverable_dlp_inr,
       sum(flagged_bills_count)::bigint as flagged_bills_count,
       (select jsonb_object_agg(detector, n)
          from (select detector, count(*) n from flags group by detector) d) as flags_by_detector,
       (select coalesce(sum(rupees_at_stake), 0)::bigint from flagged_queue) as rupees_at_stake_total,
       count(*) filter (where spend_inr > budget_inr)::int                as wards_over_budget,
       coalesce(array_agg(ward_code order by ward_code) filter (where under_reported_flag), '{}') as under_reported_wards
from ward_audit;
