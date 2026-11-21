-- Load audit engine output (exports/*.csv). Safe anytime: never touches user-written tables.
-- Run from repo root after `python3 pipeline/build.py`:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/load_audit.sql
begin;

-- Flags: upsert so replies/reports keep pointing at the same stable flag_id.
create temp table flags_new (like flags) on commit drop;
\copy flags_new from 'exports/flags.csv' csv header

insert into flags select * from flags_new
on conflict (flag_id) do update set
  tier = excluded.tier, detector = excluded.detector, status_label = excluded.status_label,
  ward_code = excluded.ward_code, road_id = excluded.road_id, work_order_id = excluded.work_order_id,
  contractor_id = excluded.contractor_id, rupees_at_stake = excluded.rupees_at_stake,
  evidence_row_ids = excluded.evidence_row_ids, rule_text = excluded.rule_text;

-- Drop flags no longer produced, unless a user already replied/reported against them.
delete from flags f
where not exists (select 1 from flags_new n where n.flag_id = f.flag_id)
  and not exists (select 1 from flag_replies r where r.flag_id = f.flag_id)
  and not exists (select 1 from citizen_reports c where c.flag_id = f.flag_id);

-- Derived tables: nothing references them, full replace.
truncate ward_audit, contractor_scorecard, road_priority;
\copy ward_audit from 'exports/ward_audit.csv' csv header
\copy contractor_scorecard from 'exports/contractor_scorecard.csv' csv header
\copy road_priority from 'exports/road_priority.csv' csv header

commit;

select 'flags' t, count(*) from flags union all
select 'ward_audit', count(*) from ward_audit union all
select 'contractor_scorecard', count(*) from contractor_scorecard union all
select 'road_priority', count(*) from road_priority;
