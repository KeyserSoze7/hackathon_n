-- Zero-login frontend: anyone may READ the View 3 results, nobody may write through the public API.
-- Tables created by pandas in the public schema start with RLS off, which lets the anon key write to them.
-- Run by the pipeline after every refresh (tables are recreated, so policies are re-applied).
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['v3_contractor_scorecard','v3_next_rupee','v3_ward_allocation','v3_job_expected_risk']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS public_read ON %I', t);
    EXECUTE format('CREATE POLICY public_read ON %I FOR SELECT USING (true)', t);
  END LOOP;
  -- Raw source tables: lock them (no policy = no access via anon key). The pipeline uses the DB password, which bypasses RLS.
  FOREACH t IN ARRAY ARRAY['work_orders','wards','roads','rate_card','rainfall_daily','tides','traffic',
                           'accidents','facilities','flood_hotspots','complaints','localities','contractors']
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
  END LOOP;
END $$;
