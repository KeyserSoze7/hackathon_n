-- Contractor accountability platform: core schema.
-- Source tables mirror data/*.csv (synthetic Mumbai monsoon dataset). Timestamps are IST, stored naive.
-- Y/N columns are boolean (Postgres accepts 'Y'/'N' on input).

-- ── Reference ────────────────────────────────────────────────────────────────
create table wards (
  ward_code                      text primary key,
  ward_name                      text not null,
  zone                           text,
  assistant_commissioner_office  text,
  centroid_lat                   double precision,
  centroid_lon                   double precision,
  approx_area_km2                numeric,
  population_est                 integer,
  low_lying_index                numeric check (low_lying_index between 0 and 1),
  engineering_crews              integer,
  localities                     text,  -- raw "; " list, normalized in localities table
  monsoon_repair_budget_inr_2025 bigint not null
);

create table localities (
  locality  text primary key,
  ward_code text not null references wards,
  lat       double precision,
  lon       double precision,
  aliases   text  -- raw "; " list, normalized in locality_aliases
);

-- Derived from localities.aliases at load time. Lowercased for matching.
create table locality_aliases (
  alias    text primary key,
  locality text not null references localities
);

create table contractors (
  contractor_id    text primary key,
  contractor_name  text not null,
  empanelled_since integer,
  active_wards     text
);

create table rate_card (
  repair_method     text primary key,
  unit              text not null check (unit in ('per sqm', 'per job')),
  standard_rate_inr numeric not null
);

create table roads (
  road_id         text primary key,
  road_name       text not null,
  segment_no      integer,
  ward_code       text not null references wards,
  road_type       text,
  surface         text,
  lanes           integer,
  length_m        numeric,
  start_lat       double precision,
  start_lon       double precision,
  end_lat         double precision,
  end_lon         double precision,
  last_resurfaced date,
  under_dlp       boolean not null,
  bus_route       boolean
);

create table traffic (
  road_id               text primary key references roads,
  peak_hour_vehicles    integer,
  avg_peak_speed_kmph   numeric,
  congestion_index_0_10 numeric,
  bus_routes_count      integer,
  two_wheeler_share_pct numeric
);

create table flood_hotspots (
  hotspot_id                 text primary key,
  name                       text not null,
  ward_code                  text not null references wards,
  lat                        double precision,
  lon                        double precision,
  flood_threshold_mm_per_day numeric,
  tide_sensitive             boolean,
  avg_water_depth_cm         numeric,
  avg_recession_hours        numeric,
  pumping_station_nearby     boolean,
  years_flagged_last_5       integer
);

create table facilities (
  facility_id          text primary key,
  type                 text not null,
  name                 text not null,
  ward_code            text not null references wards,
  lat                  double precision,
  lon                  double precision,
  beds_or_students     integer,
  emergency_services   boolean,
  ambulance_entry_road text references roads (road_id)
);

create table accidents (
  accident_id    text primary key,
  occurred_at    timestamp not null,
  ward_code      text not null references wards,
  road_id        text not null references roads,
  lat            double precision,
  lon            double precision,
  vehicle_type   text,
  severity       text,
  probable_cause text
);

create table rainfall_daily (
  date         date,
  station      text,
  rainfall_mm  numeric not null,
  imd_category text,
  imd_alert    text,
  primary key (date, station)
);

create table tides (
  date           date,
  high_tide_time time,
  height_m       numeric,
  big_tide_flag  boolean,
  primary key (date, high_tide_time)
);

-- ── Complaints & work ────────────────────────────────────────────────────────
create table complaints (
  complaint_id       text primary key,
  received_at        timestamp not null,
  channel            text,
  category_reported  text,
  description        text,
  language           text,
  locality_text      text,
  ward_code          text references wards,  -- as reported; null for ~7%
  lat                double precision,
  lon                double precision,
  gps_accuracy_m     numeric,
  photo_url          text,
  photo_description  text,
  complainant_id     text,
  upvotes            integer,
  status             text,
  resolved_at        timestamp,
  resolved_ward_code text references wards   -- ward_code, else matched via locality_aliases at load
);

create table work_orders (
  work_order_id        text primary key,
  linked_complaint_ids text,  -- raw "|" list, normalized in complaint_work_orders
  ward_code            text not null references wards,
  road_id              text not null references roads,
  work_type            text,
  repair_method        text not null references rate_card,
  contractor_id        text not null references contractors,
  contractor_name_raw  text,  -- do not use; canonical name is contractors.contractor_name
  assigned_at          timestamp,
  work_started_at      timestamp,
  completed_at         timestamp,
  area_sqm             numeric,
  cost_inr             numeric not null,
  sla_hours            integer,
  sla_met              boolean,
  reopened_within_30d  boolean,
  engineer_remark      text,
  check (work_started_at >= assigned_at and completed_at >= work_started_at)
);

create table complaint_work_orders (
  complaint_id  text references complaints,
  work_order_id text references work_orders,
  primary key (complaint_id, work_order_id)
);

create table social_posts (
  post_id           text primary key,
  posted_at         timestamp,
  source            text,
  author_handle     text,
  text              text,
  has_media         boolean,
  likes_or_forwards integer
);

-- ── Audit output (written by pipeline/build_summary.py) ──────────────────────
create table flags (
  flag_id          text primary key,  -- stable: <DETECTOR>:<work_order_id>
  tier             smallint not null check (tier between 1 and 3),
  detector         text not null,
  status_label     text not null check (status_label in ('Needs Explanation', 'Recoverable under DLP')),
  ward_code        text not null references wards,
  road_id          text not null references roads,
  work_order_id    text not null references work_orders,
  contractor_id    text not null references contractors,
  rupees_at_stake  bigint not null check (rupees_at_stake > 0),
  evidence_row_ids text[] not null,
  rule_text        text not null
);

-- ── User writes (zero-login) ─────────────────────────────────────────────────
create table flag_replies (
  id           bigint generated always as identity primary key,
  flag_id      text not null references flags,
  author_role  text not null check (author_role in ('ward_engineer', 'contractor', 'other')),
  author_name  text check (char_length(author_name) <= 120),
  body         text not null check (char_length(body) between 1 and 4000),
  created_at   timestamptz not null default now()
);

-- View 4 citizen lookup/report + View 2 two-key verification. Tracker status is advanced by the
-- backend (service role); anonymous inserts can only start at 'reported'.
create table citizen_reports (
  id                bigint generated always as identity primary key,
  kind              text not null check (kind in ('still_broken', 'verified_fixed', 'new_issue')),
  input_mode        text not null default 'text' check (input_mode in ('text', 'voice', 'photo', 'qr')),
  text              text check (char_length(text) <= 4000),  -- typed text or voice transcript
  language          text check (language in ('en', 'hi', 'mr')),
  photo_url         text check (char_length(photo_url) <= 1000),
  matched_locality  text references localities,
  road_id           text references roads,
  work_order_id     text references work_orders,
  flag_id           text references flags,
  status            text not null default 'reported'
                    check (status in ('reported', 'matched_to_contract', 'payment_held', 'contractor_notified')),
  status_updated_at timestamptz not null default now(),
  created_at        timestamptz not null default now()
);

-- Daily grain for rain joins (prevents station fan-out).
create view rain_by_day with (security_invoker = true) as
  select date, max(rainfall_mm) as max_rainfall_mm from rainfall_daily group by date;

-- ── Row level security ───────────────────────────────────────────────────────
-- Public ledger: anyone can read everything. Only replies/reports accept anonymous inserts;
-- no anonymous update/delete anywhere. Pipeline loads with the service role (bypasses RLS).
do $$
declare t text;
begin
  foreach t in array array[
    'wards','localities','locality_aliases','contractors','rate_card','roads','traffic',
    'flood_hotspots','facilities','accidents','rainfall_daily','tides','complaints',
    'work_orders','complaint_work_orders','social_posts','flags','flag_replies','citizen_reports'
  ] loop
    execute format('alter table %I enable row level security', t);
    execute format('create policy "public read" on %I for select to anon, authenticated using (true)', t);
  end loop;
end $$;

create policy "anon insert" on flag_replies for insert to anon, authenticated with check (true);
create policy "anon insert" on citizen_reports for insert to anon, authenticated with check (status = 'reported');
