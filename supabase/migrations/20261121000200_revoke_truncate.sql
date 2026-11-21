-- Supabase's default grants give anon/authenticated TRUNCATE, REFERENCES and TRIGGER on public tables.
-- TRUNCATE ignores RLS, so remove it (and the other two, which clients never need). Writes that users
-- are allowed to make (flag_replies, citizen_reports inserts) stay governed by RLS policies.
revoke truncate, references, trigger on all tables in schema public from anon, authenticated;

-- Same for tables created later by the postgres role (pipelines, future migrations).
alter default privileges for role postgres in schema public
  revoke truncate, references, trigger on tables from anon, authenticated;
