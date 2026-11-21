-- Audit engine outputs (written by pipeline/build.py via supabase/load_audit.sql) and one read
-- view per frontend screen. Column order of the three tables matches exports/*.csv.

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

create table contractor_scorecard (
  contractor_id                 text primary key references contractors,
  jobs_count                    integer not null,
  total_billed_inr              bigint not null,
  reopen_rate_30d               numeric not null,
  expected_reopen_rate_30d      numeric not null,  -- given work type, flood-prone ward, rain day
  reopen_observed_to_expected   numeric,           -- 1.0 = as expected for conditions
  sla_met_rate                  numeric not null,
  risk_adjusted_score           numeric not null,  -- % fixes expected to survive 30d, context-adjusted
  score_low                     numeric not null,  -- 95% band
  score_high                    numeric not null,
  small_sample                  boolean not null,
  tier1_flags_count             integer not null,
  flags_count                   integer not null,
  recoverable_inr               bigint not null,
  avg_rain_mm_on_completion_day numeric not null,
  flood_prone_share             numeric not null,
  avg_peak_vehicles             integer not null
);

create table road_priority (
  road_id                      text primary key references roads,
  priority_score               numeric not null check (priority_score between 0 and 100),
  estimated_repair_cost_inr    bigint not null,
  cost_to_bmc_inr              bigint not null,  -- 0 when under DLP
  priority_per_lakh            numeric,          -- null for bucket A
  bucket                       text not null check (bucket in ('A_DLP_OWED', 'B_INVEST')),
  reason_codes                 text[] not null,
  nearest_hotspot_id           text references flood_hotspots,
  nearest_hotspot_m            integer,
  ambulance_weight             integer not null,
  road_condition_accident_harm integer not null,
  reopened_jobs                integer not null,
  peak_hour_vehicles           integer,
  evidence_row_ids             text[] not null,
  bucket_rank                  integer not null,
  unique (bucket, bucket_rank)
);

-- ── View 1: City & Ward Audit Overview ───────────────────────────────────────
create view city_kpis with (security_invoker = true) as
select sum(budget_inr)          as total_budget_inr,
       sum(spend_inr)           as total_spend_inr,
       sum(recoverable_dlp_inr) as recoverable_dlp_inr,
       sum(flagged_bills_count) as flagged_bills_count,
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
       coalesce(q.flagged_bills, 0)     as flagged_bills_count,
       p.priority_score, p.reason_codes
from roads r
left join (select road_id, sum(cost_inr) total_billed_inr, count(*) work_orders_count
             from work_orders group by road_id) b using (road_id)
left join (select road_id, sum(rupees_at_stake) rupees_at_stake, count(*) flagged_bills
             from flagged_queue group by road_id) q using (road_id)
left join road_priority p using (road_id);

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

-- ── View 3A: Context-Adjusted Contractor Scorecard ───────────────────────────
create view contractor_overview with (security_invoker = true) as
select s.*, c.contractor_name, c.empanelled_since, c.active_wards
from contractor_scorecard s join contractors c using (contractor_id);

-- ── View 3B: Next-Rupee Planner ──────────────────────────────────────────────
-- Slider: show bucket B rows where cumulative_cost_to_bmc_inr <= remaining budget.
create view next_rupee with (security_invoker = true) as
select p.*, r.road_name, r.ward_code, r.under_dlp,
       sum(p.cost_to_bmc_inr) over (partition by p.bucket order by p.bucket_rank) as cumulative_cost_to_bmc_inr
from road_priority p join roads r using (road_id);

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
alter table ward_audit enable row level security;
alter table contractor_scorecard enable row level security;
alter table road_priority enable row level security;
create policy "public read" on ward_audit for select to anon, authenticated using (true);
create policy "public read" on contractor_scorecard for select to anon, authenticated using (true);
create policy "public read" on road_priority for select to anon, authenticated using (true);
