-- Monthly contractor scorecards (processed output, written by the refresh CLI:
--   python -m backend.features.contractor_performance.refresh, from the repo root).
-- Grain: one contractor x calendar month of work_orders.completed_at x methodology_version.
-- Four separate dimension ranks (speed, sla, durability, cost); no composite score is stored.
--
-- Safe to re-run (if not exists / drop policy if exists). Apply after the earlier migrations (renumbered from 0200, which collided with revoke_truncate):
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/20261121000700_contractor_monthly_scorecards.sql
-- Rollback (drops processed output only; source tables untouched; re-run refresh to rebuild):
--   drop table if exists contractor_monthly_scorecards, contractor_scorecard_runs;
-- Change the schema with a new migration file rather than editing this one once applied.

-- One row per methodology version: parameters + source counts + run-level data quality, for reproducibility.
create table if not exists contractor_scorecard_runs (
  methodology_version text primary key,
  computed_at         timestamptz not null,
  params              jsonb not null,   -- cost_tolerance, min_sample, min_cohort, rank_decimals
  source_counts       jsonb not null,
  data_quality        jsonb not null    -- jobs without completed_at, ward mismatches, missing context tables
);

create table if not exists contractor_monthly_scorecards (
  contractor_id        text not null references contractors (contractor_id),
  month                date not null check (month = date_trunc('month', month)::date),  -- first day of month
  methodology_version  text not null references contractor_scorecard_runs (methodology_version) on delete cascade,
  computed_at          timestamptz not null,

  -- workload (descriptive)
  completed_jobs       integer not null check (completed_jobs > 0),
  total_billed_inr     numeric not null,

  -- SLA: work_orders.sla_met as recorded. rate = met / known. higher is better.
  sla_known            integer not null check (sla_known >= 0),
  sla_met              integer not null check (sla_met between 0 and sla_known),
  sla_missing          integer not null check (sla_missing >= 0),
  sla_rate             numeric check (sla_rate between 0 and 1),
  sla_rank             smallint check (sla_rank >= 1),

  -- Durability: work_orders.reopened_within_30d as recorded. rate = reopened / known. lower is better.
  reopen_known         integer not null check (reopen_known >= 0),
  reopened             integer not null check (reopened between 0 and reopen_known),
  reopen_missing       integer not null check (reopen_missing >= 0),
  reopen_rate          numeric check (reopen_rate between 0 and 1),
  durability_rank      smallint check (durability_rank >= 1),

  -- Speed: earliest linked complaint -> completed_at, hours. Ranked on speed_relative_index
  -- (median of job hours / same-month same-repair_method city median). lower is faster.
  speed_sample                       integer not null check (speed_sample >= 0),  -- normalized (ranked) sample
  speed_missing                      integer not null check (speed_missing >= 0),
  speed_raw_sample                   integer not null check (speed_raw_sample >= 0),
  speed_median_hours                 numeric,  -- raw, unnormalized
  speed_cohort_median_hours          numeric,  -- peer value for this contractor's method mix
  speed_relative_index               numeric check (speed_relative_index >= 0),
  speed_rank                         smallint check (speed_rank >= 1),
  assigned_to_completed_median_hours numeric,  -- proxy only, never ranked

  -- Cost alignment: median |cost - benchmark| / benchmark. lower is closer to the rate card.
  cost_sample                 integer not null check (cost_sample >= 0),
  cost_missing                integer not null check (cost_missing >= 0),
  cost_median_abs_pct_dev     numeric check (cost_median_abs_pct_dev >= 0),
  cost_over_tolerance_count   integer not null check (cost_over_tolerance_count >= 0),
  cost_over_tolerance_share   numeric check (cost_over_tolerance_share between 0 and 1),
  cost_under_tolerance_count  integer not null check (cost_under_tolerance_count >= 0),  -- descriptive
  cost_rank                   smallint check (cost_rank >= 1),

  rank_eligibility        jsonb not null,  -- {dimension: {eligible, sample, min_sample, reason}}
  rank_cohort_sizes       jsonb not null,  -- {dimension: contractors eligible that month}
  workload_mix            jsonb not null,  -- repair_methods, work_types, wards, speed_by_repair_method
  context                 jsonb not null,  -- rainfall, tides, flood_hotspots, traffic, accidents, facility_access (descriptive)
  data_quality            jsonb not null,  -- missing reasons, ward mismatches
  evidence_work_order_ids text[] not null,

  primary key (contractor_id, month, methodology_version),
  check (sla_known + sla_missing = completed_jobs),
  check (reopen_known + reopen_missing = completed_jobs),
  check (speed_sample + speed_missing = completed_jobs),
  check (cost_sample + cost_missing = completed_jobs),
  check (cardinality(evidence_work_order_ids) = completed_jobs)
);

-- Monthly list reads (version + month range); the PK already serves the per-contractor series.
create index if not exists contractor_monthly_scorecards_version_month_idx
  on contractor_monthly_scorecards (methodology_version, month);

-- Backend-only: RLS on with no anon/authenticated policy. The React app reads through FastAPI;
-- the backend connects with DATABASE_URL (table owner / service role), which bypasses RLS.
alter table contractor_scorecard_runs enable row level security;
alter table contractor_monthly_scorecards enable row level security;
drop policy if exists "public read" on contractor_scorecard_runs;
drop policy if exists "public read" on contractor_monthly_scorecards;
