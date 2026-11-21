-- Frontend contract additions (View 1 KPIs, View 2 warranty fields, View 4 localities + livability).
-- Views only gain columns at the end (create or replace keeps existing clients working). No table changes.

-- Approximate metres between two lat/lon points (equirectangular; fine at city scale).
create or replace function approx_m(lat1 double precision, lon1 double precision,
                                    lat2 double precision, lon2 double precision)
returns double precision language sql immutable as $$
  select sqrt(power((lat2 - lat1) * 110540, 2) + power((lon2 - lon1) * 111320 * cos(radians((lat1 + lat2) / 2)), 2))
$$;

-- ── View 1: KPI strip extras (failed-repairs tile, SLA, DLP explanation) ─────
create or replace view city_kpis with (security_invoker = true) as
select sum(budget_inr)::bigint          as total_budget_inr,
       sum(spend_inr)::bigint           as total_spend_inr,
       sum(recoverable_dlp_inr)::bigint as recoverable_dlp_inr,
       sum(flagged_bills_count)::bigint as flagged_bills_count,
       (select jsonb_object_agg(detector, n)
          from (select detector, count(*) n from flags group by detector) d) as flags_by_detector,
       (select coalesce(sum(rupees_at_stake), 0)::bigint from flagged_queue) as rupees_at_stake_total,
       count(*) filter (where spend_inr > budget_inr)::int                as wards_over_budget,
       coalesce(array_agg(ward_code order by ward_code) filter (where under_reported_flag), '{}') as under_reported_wards,
       (select count(*) from work_orders)::int                                  as work_orders_count,
       (select count(*) from complaints)::int                                   as complaints_count,
       (select count(*) from work_orders where reopened_within_30d)::int        as reopened_within_30d_count,
       (select round(avg(case when sla_met then 1.0 else 0.0 end), 4) from work_orders) as sla_met_rate,
       -- everything BMC paid on roads under DLP; recoverable_dlp_inr is the surface-repair part of this
       (select coalesce(sum(wo.cost_inr), 0)::bigint
          from work_orders wo join roads r using (road_id) where r.under_dlp)   as dlp_road_spend_inr,
       'Only road-surface repairs (cold mix, hot mix, mastic asphalt, paver blocks) billed on roads still under the '
       || 'original contractor''s Defect Liability Period count as recoverable; drainage, pumping, manhole and utility '
       || 'work on those roads is not a surface defect, so the warranty does not cover it.'::text as recoverable_dlp_rule
from ward_audit;

-- ── View 2: warranty fields on the road header ───────────────────────────────
-- The dataset gives under_dlp but no expiry. A 36-month DLP is assumed: every DLP road was resurfaced
-- 5-33 months before Oct 2025, so 36 months is consistent with all of them. dlp_expires_on is an estimate.
create or replace view road_audit with (security_invoker = true) as
select r.road_id, r.road_name, r.ward_code, r.road_type, r.surface, r.under_dlp, r.last_resurfaced,
       coalesce(b.total_billed_inr, 0)  as total_billed_inr,
       coalesce(b.work_orders_count, 0) as work_orders_count,
       coalesce(q.rupees_at_stake, 0)   as rupees_at_stake,
       coalesce(q.flagged_bills, 0)     as flagged_bills_count,
       r.segment_no,
       r.length_m,
       case when r.under_dlp then 36 end                                          as dlp_months,
       case when r.under_dlp then (r.last_resurfaced + interval '36 months')::date end as dlp_expires_on
from roads r
left join (select road_id, sum(cost_inr) total_billed_inr, count(*) work_orders_count
             from work_orders group by road_id) b using (road_id)
left join (select road_id, sum(rupees_at_stake) rupees_at_stake, count(*) flagged_bills
             from flagged_queue group by road_id) q using (road_id);

-- ── View 4: localities with aliases as an array ──────────────────────────────
create or replace view locality_list with (security_invoker = true) as
select l.locality, l.ward_code, l.lat, l.lon,
       coalesce(array(select trim(a) from unnest(string_to_array(l.aliases, ';')) a where trim(a) <> ''), '{}') as aliases
from localities l;

-- ── View 4: "Moving here" livability within 1.5 km of each locality ──────────
create or replace view locality_livability with (security_invoker = true) as
with near_roads as (
  select l.locality, r.road_id,
         approx_m(l.lat, l.lon, (r.start_lat + r.end_lat) / 2, (r.start_lon + r.end_lon) / 2) as m
  from localities l cross join roads r
)
select l.locality, l.ward_code, l.lat, l.lon,
       1500 as radius_m,
       (select count(*) from flood_hotspots h where approx_m(l.lat, l.lon, h.lat, h.lon) <= 1500)::int
         as flood_hotspots_1500m,
       (select count(*) from work_orders wo join near_roads n using (road_id)
         where n.locality = l.locality and n.m <= 1500)::int as jobs_1500m,
       (select round(avg(case when wo.reopened_within_30d then 1.0 else 0.0 end), 4)
          from work_orders wo join near_roads n using (road_id)
         where n.locality = l.locality and n.m <= 1500) as failure_rate_30d_1500m,
       (select count(distinct f.ambulance_entry_road) from facilities f
          join near_roads n on n.road_id = f.ambulance_entry_road
         where n.locality = l.locality and n.m <= 1500 and f.type = 'Hospital')::int as hospital_access_roads_1500m,
       wa.dlp_leakage_rate as ward_dlp_leakage_rate,
       coalesce((select array_agg(n.road_id order by n.m) from near_roads n
                  where n.locality = l.locality and n.m <= 1500), '{}') as nearby_road_ids
from localities l
left join ward_audit wa using (ward_code);
