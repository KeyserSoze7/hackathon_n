-- View 3 model summary: model quality (3A) + budget curve and baseline comparison (3B) for the demo chart.
-- Single row, written by view3/view3_pipeline.py in the same transaction as the other v3_* tables.
create table v3_model_meta (
  id         smallint primary key default 1 check (id = 1),
  meta       jsonb not null,
  updated_at timestamptz not null default now()
);

alter table v3_model_meta enable row level security;
create policy "public read" on v3_model_meta for select to anon, authenticated using (true);
