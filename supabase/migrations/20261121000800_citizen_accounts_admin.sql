-- Citizen accounts (anonymous, token-based) + admin / ward-officer dashboard.
-- New tables are private (RLS on, NO policy, revoked from anon/authenticated), like citizen_report_contacts:
-- only the backend (DATABASE_URL role) reads or writes them. citizen_reports keeps its existing public read.
-- Safe to re-run. Apply after 20261121000700:
--   psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/20261121000800_citizen_accounts_admin.sql
-- Rollback (drops accounts, sessions, access requests, events and notices; restores the 4-status check):
--   alter table flag_replies drop column if exists admin_id;
--   alter table citizen_reports drop column if exists citizen_id, drop column if exists rejection_reason,
--     drop column if exists repair_due_at, drop column if exists resolved_at;
--   drop table if exists contractor_notices, citizen_report_events, admin_sessions, admin_access_requests,
--     admin_users, citizens;
--   (then re-add citizen_reports_status_check with the 4 original statuses and the flag_replies "anon insert" policy)

-- ── Citizens: anonymous accounts. The API returns the bearer token once; only its sha256 is stored. ────
create table if not exists citizens (
  citizen_id   uuid primary key default gen_random_uuid(),
  display_name text not null check (char_length(display_name) between 1 and 60),
  token_hash   text not null unique,                                   -- sha256 hex of the bearer token
  phone        text check (phone ~ '^\+?[0-9 -]{6,20}$'),              -- optional, for SMS later; never returned
  joined_at    timestamptz not null default now(),
  last_seen_at timestamptz
);

-- ── Admin / ward-officer accounts. Created by the CLI (first admin) or by approving an access request. ──
create table if not exists admin_users (
  admin_id      uuid primary key default gen_random_uuid(),
  email         text not null unique check (email = lower(email) and email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  name          text not null check (char_length(name) between 1 and 120),
  designation   text check (char_length(designation) <= 120),
  role          text not null check (role in ('ward_officer', 'admin')),
  ward_codes    text[] not null default '{}',   -- ward_officer: wards they may act on; admin: ignored (all wards)
  password_hash text not null,                  -- scrypt$n$r$p$salt$hash (backend/auth.py)
  active        boolean not null default true,
  created_at    timestamptz not null default now()
);

create table if not exists admin_sessions (
  token_hash text primary key,                  -- sha256 hex of the bearer token
  admin_id   uuid not null references admin_users on delete cascade,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);
create index if not exists admin_sessions_admin_idx on admin_sessions (admin_id);

-- ward_code is validated by the API (no FK to wards, so a source-data reload never touches accounts).
create table if not exists admin_access_requests (
  request_id    bigint generated always as identity primary key,
  name          text not null check (char_length(name) between 1 and 120),
  email         text not null check (email = lower(email) and email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  designation   text not null check (char_length(designation) between 1 and 120),
  ward_code     text not null,
  reason        text not null check (char_length(reason) between 1 and 2000),
  status        text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  created_at    timestamptz not null default now(),
  decided_at    timestamptz,
  decided_by    uuid references admin_users,
  decision_note text check (char_length(decision_note) <= 2000),
  admin_id      uuid references admin_users     -- the account created on approval
);
create unique index if not exists admin_access_requests_one_pending
  on admin_access_requests (email) where status = 'pending';

-- ── Citizen reports: owner, lifecycle fields, full status set ───────────────
alter table citizen_reports
  add column if not exists citizen_id       uuid references citizens,
  add column if not exists rejection_reason text check (char_length(rejection_reason) <= 500),
  add column if not exists repair_due_at    timestamptz,
  add column if not exists resolved_at      timestamptz;

alter table citizen_reports drop constraint if exists citizen_reports_status_check;
alter table citizen_reports add constraint citizen_reports_status_check check (status in (
  'reported', 'matched_to_contract', 'payment_held', 'contractor_notified',
  'resolved', 'confirmed_fixed', 'reopened', 'rejected', 'duplicate'));

create index if not exists citizen_reports_citizen_idx on citizen_reports (citizen_id);
create index if not exists citizen_reports_status_idx on citizen_reports (status);
create index if not exists citizen_reports_road_issue_idx on citizen_reports (road_id, issue_type, created_at);

-- Report history: every create / status change / note / citizen confirmation / contractor notice.
create table if not exists citizen_report_events (
  id          bigint generated always as identity primary key,
  report_id   bigint not null references citizen_reports (id),
  at          timestamptz not null default now(),
  actor_type  text not null check (actor_type in ('citizen', 'admin', 'system')),
  admin_id    uuid references admin_users,
  event_type  text not null check (event_type in
                ('created', 'status_change', 'note', 'confirm', 'duplicate', 'contractor_notified')),
  from_status text,
  to_status   text,
  note        text check (char_length(note) <= 2000),
  photo_ids   text[] not null default '{}',
  meta        jsonb not null default '{}'
);
create index if not exists citizen_report_events_report_idx on citizen_report_events (report_id, at, id);

-- Contractor notices recorded by ward officers (the API records them; it does not send email/SMS/letters).
create table if not exists contractor_notices (
  id            bigint generated always as identity primary key,
  report_id     bigint not null references citizen_reports (id),
  flag_id       text references flags,
  work_order_id text references work_orders,
  contractor_id text references contractors,
  channel       text not null check (channel in ('email', 'sms', 'letter')),
  message       text not null check (char_length(message) between 1 and 20000),
  generated_by  text not null check (generated_by in ('claude', 'template', 'officer')),
  sent_by       uuid not null references admin_users,
  created_at    timestamptz not null default now()
);
create index if not exists contractor_notices_report_idx on contractor_notices (report_id);

-- ── Right-of-Reply is now authenticated (officers/admins through the API) ───
alter table flag_replies add column if not exists admin_id uuid references admin_users;
drop policy if exists "anon insert" on flag_replies;

-- ── Private: RLS on, no policy, no grants for the public keys ───────────────
do $$
declare t text;
begin
  foreach t in array array['citizens', 'admin_users', 'admin_sessions', 'admin_access_requests',
                           'citizen_report_events', 'contractor_notices'] loop
    execute format('alter table %I enable row level security', t);
    execute format('revoke all on %I from anon, authenticated', t);
  end loop;
end $$;
