-- Audit engine outputs and one read view per frontend screen.
--   ward_audit           <- pipeline/build.py via supabase/load_audit.sql (column order = exports/ward_audit.csv)
--   v3_* (View 3)        <- view3/view3_pipeline.py (truncate + insert; columns = its output dict keys)

-- ── Engine output tables ─────────────────────────────────────────────────────
create table ward_audit (
  ward_code                 text primary key references wards,
  budget_inr                bigint not null,
  spend_inr                 bigint not null,
  recoverable_dlp_inr       bigint not null,
  flagged_bills_count       integer not null,
  warranty_enforcement_rate numeric,  -- null when ward has no DLP-eligible jobs
  dlp_eligible_jobs         integer not null,
  dlp_leakage_rate          numeric not null,  -- recoverable / spend; colour the map by this
  physical_risk_score       numeric not null,
  complaints_per_lakh       numeric not null,
  under_reported_flag       boolean not null,
  flood_hotspots_count      integer not null,
  accidents_count           integer not null
);

-- View 3A: context-adjusted contractor scorecard (XGBoost expected risk; 50 = as expected).
create table v3_contractor_scorecard (
  contractor_id                  text primary key references contractors,
  contractor_name                text not null,
  jobs_count                     integer not null,
  total_billed_inr               bigint not null,
  reopen_rate_30d                numeric not null,
  expected_reopen_rate_30d       numeric not null,
  sla_met_rate                   numeric not null,
  expected_sla_met_rate          numeric not null,
  durability_index               numeric not null check (durability_index between 0 and 100),
  durability_verdict             text not null,
  durability_ratio_obs_over_exp  numeric,
  durability_ratio_ci90          jsonb,
  speed_index                    numeric not null check (speed_index between 0 and 100),
  speed_verdict                  text not null,
  risk_adjusted_score            numeric not null,  -- 60% durability + 40% speed
  cost_vs_rate_median            numeric,
  jobs_over_130pct_rate          integer,
  method_mix_top3                jsonb,
  context                        jsonb,
  drivers                        jsonb,  -- SHAP: why their jobs were harder/easier than average
  evidence_reopened_wo_ids       jsonb,
  explanation                    text
);

create table v3_job_expected_risk (
  work_order_id       text primary key references work_orders,
  contractor_id       text not null references contractors,
  p_reopen_expected   numeric not null,
  p_sla_miss_expected numeric not null
);

-- View 3B: one item per (road x issue). Bucket A = DLP surface defect, Rs 0 to BMC.
create table v3_next_rupee (
  item_id                   text primary key,  -- <road_id>|<issue>
  road_id                   text not null references roads,
  road_name                 text,
  ward_code                 text not null references wards,
  issue                     text not null,
  under_dlp                 boolean not null,
  bucket                    text not null check (bucket in ('A_OWED_BY_CONTRACTOR_DLP', 'B_NEXT_RUPEE')),
  funded                    boolean not null,
  recommended_method        text,
  method_reopen_rate        numeric,
  estimated_repair_cost_inr bigint,
  cost_to_bmc_inr           bigint,
  harm_avoided              numeric,
  harm_per_lakh             numeric,
  priority_score            numeric,
  reason_codes              jsonb not null,
  inputs                    jsonb,
  evidence_wo_ids           jsonb,
  explanation               text
);

create table v3_ward_allocation (
  ward_code                    text primary key references wards,
  ward_name                    text,
  budget_2025_inr              bigint not null,
  spend_2025_inr               bigint not null,
  remaining_2025_inr           bigint not null,
  recommended_budget_inr       bigint not null,
  equity_floor_inr             bigint not null,
  harm_avoided                 numeric not null,
  harm_avoided_per_next_lakh   numeric not null,
  dlp_items_owed_by_contractor integer not null,
  dlp_value_owed_inr           bigint not null  -- future surface fixes owed (rate card); not ward_audit.recoverable_dlp_inr
);

-- ── View 1: City & Ward Audit Overview ───────────────────────────────────────
create view city_kpis with (security_invoker = true) as
select sum(budget_inr)::bigint          as total_budget_inr,
       sum(spend_inr)::bigint           as total_spend_inr,
       sum(recoverable_dlp_inr)::bigint as recoverable_dlp_inr,
       sum(flagged_bills_count)::bigint as flagged_bills_count,
       (select jsonb_object_agg(detector, n)
          from (select detector, count(*) n from flags group by detector) d) as flags_by_detector
from ward_audit;

create view ward_overview with (security_invoker = true) as
select a.*, w.ward_name, w.zone, w.centroid_lat, w.centroid_lon
from ward_audit a join wards w using (ward_code);

-- One row per flagged bill; rupees not double-counted when a bill has several flags.
create view flagged_queue with (security_invoker = true) as
select f.work_order_id, wo.road_id, r.road_name, wo.ward_code, wo.contractor_id, c.contractor_name,
       wo.repair_method, wo.cost_inr, wo.completed_at,
       min(f.tier)            as top_tier,
       max(f.rupees_at_stake) as rupees_at_stake,
       case when bool_or(f.detector = 'DLP_PAID_TWICE') then 'Recoverable under DLP'
            else 'Needs Explanation' end as status_label,
       array_agg(f.flag_id order by f.tier, f.flag_id) as flag_ids,
       array_agg(distinct f.detector) as detectors,
       count(rep.id)          as replies_count
from flags f
join work_orders wo using (work_order_id)
join roads r on r.road_id = wo.road_id
join contractors c on c.contractor_id = wo.contractor_id
left join flag_replies rep on rep.flag_id = f.flag_id
group by f.work_order_id, wo.road_id, r.road_name, wo.ward_code, wo.contractor_id, c.contractor_name,
         wo.repair_method, wo.cost_inr, wo.completed_at;

-- ── View 2: Road Story / Rupee Receipt ───────────────────────────────────────
create view road_audit with (security_invoker = true) as
select r.road_id, r.road_name, r.ward_code, r.road_type, r.surface, r.under_dlp, r.last_resurfaced,
       coalesce(b.total_billed_inr, 0)  as total_billed_inr,
       coalesce(b.work_orders_count, 0) as work_orders_count,
       coalesce(q.rupees_at_stake, 0)   as rupees_at_stake,
       coalesce(q.flagged_bills, 0)     as flagged_bills_count
from roads r
left join (select road_id, sum(cost_inr) total_billed_inr, count(*) work_orders_count
             from work_orders group by road_id) b using (road_id)
left join (select road_id, sum(rupees_at_stake) rupees_at_stake, count(*) flagged_bills
             from flagged_queue group by road_id) q using (road_id);

-- Chronological trail per road: complaint -> work order -> reopen -> accident -> citizen report.
create view road_timeline with (security_invoker = true) as
select wo.road_id, c.received_at as event_at, 'complaint' as event_type, c.complaint_id as ref_id,
       jsonb_build_object('work_order_id', wo.work_order_id, 'channel', c.channel, 'status', c.status,
                          'language', c.language, 'description', c.description) as detail
from complaint_work_orders cw
join complaints c using (complaint_id)
join work_orders wo using (work_order_id)
union all
select wo.road_id, wo.assigned_at, 'work_order_assigned', wo.work_order_id,
       jsonb_build_object('contractor_id', wo.contractor_id, 'repair_method', wo.repair_method,
                          'cost_inr', wo.cost_inr)
from work_orders wo
union all
select wo.road_id, wo.completed_at, 'work_order_completed', wo.work_order_id,
       jsonb_build_object('contractor_id', wo.contractor_id, 'sla_met', wo.sla_met,
                          'reopened_within_30d', wo.reopened_within_30d,
                          'rain_mm_on_completion_day', coalesce(rd.max_rainfall_mm, 0),
                          'engineer_remark', wo.engineer_remark)
from work_orders wo
left join rain_by_day rd on rd.date = wo.completed_at::date
union all
select a.road_id, a.occurred_at, 'accident', a.accident_id,
       jsonb_build_object('severity', a.severity, 'probable_cause', a.probable_cause,
                          'vehicle_type', a.vehicle_type)
from accidents a
union all
select cr.road_id, cr.created_at::timestamp, 'citizen_report', cr.id::text,
       jsonb_build_object('kind', cr.kind, 'status', cr.status, 'work_order_id', cr.work_order_id)
from citizen_reports cr
where cr.road_id is not null;

-- ── View 3: read v3_contractor_scorecard / v3_next_rupee / v3_ward_allocation directly
--    (queries in view3/sql/02_view3_api.sql; live budget slider = POST /api/v3/allocate).

-- ── View 4: Citizen lookup ───────────────────────────────────────────────────
-- Landmark text -> locality_aliases -> locality -> nearest road segment in the same ward.
create view locality_nearest_road with (security_invoker = true) as
select l.locality, l.ward_code, nr.road_id, nr.road_name, nr.under_dlp, nr.approx_m
from localities l
cross join lateral (
  select r.road_id, r.road_name, r.under_dlp,
         round(sqrt(power(((r.start_lat + r.end_lat) / 2 - l.lat) * 110540, 2) +
                    power(((r.start_lon + r.end_lon) / 2 - l.lon) * 105200, 2)))::int as approx_m
  from roads r
  where r.ward_code = l.ward_code
  order by approx_m
  limit 1
) nr;

-- ── RLS: public read on engine outputs (views inherit via security_invoker) ──
do $$
declare t text;
begin
  foreach t in array array['ward_audit','v3_contractor_scorecard','v3_job_expected_risk','v3_next_rupee','v3_ward_allocation'] loop
    execute format('alter table %I enable row level security', t);
    execute format('create policy "public read" on %I for select to anon, authenticated using (true)', t);
  end loop;
end $$;
