-- Load data/*.csv into the source tables. Rerunnable until users start writing;
-- refuses once flag_replies/citizen_reports have rows (truncate would cascade into them).
-- Run from repo root, then supabase/load_audit_outputs.sql:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/load_source_data.sql
begin;

do $$ begin
  if exists (select 1 from flag_replies) or exists (select 1 from citizen_reports) then
    raise exception 'user data present in flag_replies/citizen_reports; refusing to truncate source tables';
  end if;
end $$;

truncate wards, localities, locality_aliases, contractors, rate_card, roads, traffic, flood_hotspots,
  facilities, accidents, rainfall_daily, tides, complaints, work_orders, complaint_work_orders,
  social_posts, flags, flag_replies, citizen_reports, ward_audit,
  v3_contractor_scorecard, v3_job_expected_risk, v3_next_rupee, v3_ward_allocation, v3_model_meta;

\copy wards from 'data/wards.csv' csv header
\copy localities from 'data/localities.csv' csv header
\copy contractors from 'data/contractors.csv' csv header
\copy rate_card from 'data/rate_card.csv' csv header
\copy roads from 'data/roads.csv' csv header
\copy traffic from 'data/traffic.csv' csv header
\copy flood_hotspots from 'data/flood_hotspots.csv' csv header
\copy facilities from 'data/facilities.csv' csv header
\copy accidents from 'data/accidents.csv' csv header
\copy rainfall_daily from 'data/rainfall_daily.csv' csv header
\copy tides from 'data/tides.csv' csv header
\copy complaints (complaint_id, received_at, channel, category_reported, description, language, locality_text, ward_code, lat, lon, gps_accuracy_m, photo_url, photo_description, complainant_id, upvotes, status, resolved_at) from 'data/complaints.csv' csv header
\copy work_orders from 'data/work_orders.csv' csv header
\copy social_posts from 'data/social_posts.csv' csv header

-- Junction: explode "|" list.
insert into complaint_work_orders
select distinct trim(c), work_order_id
from work_orders, unnest(string_to_array(linked_complaint_ids, '|')) c
where trim(c) <> '';

-- Alias lookup: canonical name + each "; " alias, lowercased. First locality wins on collision.
insert into locality_aliases
select distinct on (alias) alias, locality from (
  select lower(trim(locality)) alias, locality from localities
  union all
  select lower(trim(a)), locality from localities, unnest(string_to_array(aliases, ';')) a
) x where alias <> '' order by alias, locality;

update complaints c set resolved_ward_code = coalesce(c.ward_code, l.ward_code)
from complaints c2
left join locality_aliases a on a.alias = lower(trim(c2.locality_text))
left join localities l on l.locality = a.locality
where c2.complaint_id = c.complaint_id;

commit;

select 'work_orders' t, count(*) from work_orders union all
select 'complaints', count(*) from complaints union all
select 'complaint_work_orders', count(*) from complaint_work_orders union all
select 'complaints_unresolved_ward', count(*) from complaints where resolved_ward_code is null;
