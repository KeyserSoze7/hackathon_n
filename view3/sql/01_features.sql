-- View 3 feature layer. Runs unchanged on Supabase (Postgres) and on DuckDB locally.
-- Assumes the CSVs are loaded as tables with the same names and column names
-- (work_orders, wards, roads, rate_card, rainfall_daily, tides, traffic,
--  accidents, facilities, flood_hotspots, complaints, localities, contractors).
-- On Supabase these come from supabase/migrations (Y/N stored as boolean; comparisons to 'Y' still work in SQL).

-- Ward -> rain gauge. Island city wards use Colaba, suburbs use Santacruz.
CREATE OR REPLACE VIEW v_ward_station AS
SELECT ward_code,
       CASE WHEN ward_code IN ('A','B','C','D','E','F/S','F/N','G/S','G/N')
            THEN 'Colaba' ELSE 'Santacruz' END AS station
FROM wards;

-- Road midpoints + distance to nearest flood hotspot (metres, equirectangular).
CREATE OR REPLACE VIEW v_road_geo AS
WITH mid AS (
  SELECT r.*, (start_lat + end_lat) / 2.0 AS mid_lat, (start_lon + end_lon) / 2.0 AS mid_lon
  FROM roads r
)
SELECT m.road_id, m.ward_code, m.road_type, m.surface, m.lanes, m.length_m,
       m.last_resurfaced, m.under_dlp, m.bus_route, m.mid_lat, m.mid_lon,
       MIN(111320.0 * SQRT(POWER(h.lat - m.mid_lat, 2)
           + POWER((h.lon - m.mid_lon) * COS(RADIANS(m.mid_lat)), 2))) AS hotspot_dist_m
FROM mid m CROSS JOIN flood_hotspots h
GROUP BY m.road_id, m.ward_code, m.road_type, m.surface, m.lanes, m.length_m,
         m.last_resurfaced, m.under_dlp, m.bus_route, m.mid_lat, m.mid_lon;

-- One row per work order with everything a contractor could NOT control.
CREATE OR REPLACE VIEW v_wo_context AS
WITH base AS (
  SELECT wo.*, CAST(wo.completed_at AS DATE) AS done_date, s.station
  FROM work_orders wo JOIN v_ward_station s USING (ward_code)
),
rain AS (
  SELECT b.work_order_id,
         SUM(rf.rainfall_mm) AS rain_next7_mm,
         SUM(CASE WHEN rf.imd_category IN ('Heavy','Very heavy','Extremely heavy') THEN 1 ELSE 0 END) AS heavy_days_next7
  FROM base b JOIN rainfall_daily rf
    ON rf.station = b.station
   AND CAST(rf.date AS DATE) >  b.done_date
   AND CAST(rf.date AS DATE) <= b.done_date + 7
  GROUP BY b.work_order_id
),
rain_before AS (
  SELECT b.work_order_id, SUM(rf.rainfall_mm) AS rain_during_mm
  FROM base b JOIN rainfall_daily rf
    ON rf.station = b.station
   AND CAST(rf.date AS DATE) >= CAST(b.work_started_at AS DATE)
   AND CAST(rf.date AS DATE) <= b.done_date
  GROUP BY b.work_order_id
),
tide AS (
  SELECT b.work_order_id,
         SUM(CASE WHEN t.big_tide_flag = 'Y' THEN 1 ELSE 0 END) AS big_tides_next7
  FROM base b JOIN tides t
    ON CAST(t.date AS DATE) > b.done_date AND CAST(t.date AS DATE) <= b.done_date + 7
  GROUP BY b.work_order_id
)
SELECT b.work_order_id, b.contractor_id, ct.contractor_name, b.ward_code, b.road_id,
       b.work_type, b.repair_method, b.area_sqm, b.cost_inr, b.sla_hours, b.sla_met,
       b.reopened_within_30d, b.done_date,
       EXTRACT(MONTH FROM b.done_date)                      AS month,
       w.low_lying_index,
       g.road_type, g.surface, g.lanes, g.under_dlp, g.bus_route, g.hotspot_dist_m,
       (b.done_date - CAST(g.last_resurfaced AS DATE)) / 365.25 AS road_age_years,
       tr.peak_hour_vehicles, tr.congestion_index_0_10, tr.two_wheeler_share_pct,
       COALESCE(r.rain_next7_mm, 0)     AS rain_next7_mm,
       COALESCE(r.heavy_days_next7, 0)  AS heavy_days_next7,
       COALESCE(rb.rain_during_mm, 0)   AS rain_during_mm,
       COALESCE(t.big_tides_next7, 0)   AS big_tides_next7,
       b.cost_inr / (rc.standard_rate_inr *
         CASE WHEN rc.unit = 'per sqm' THEN b.area_sqm ELSE 1 END) AS cost_vs_rate
FROM base b
JOIN contractors ct ON ct.contractor_id = b.contractor_id  -- canonical name (work_orders repeats it)
JOIN wards w        USING (ward_code)
JOIN v_road_geo g   USING (road_id)
LEFT JOIN traffic tr USING (road_id)
LEFT JOIN rate_card rc USING (repair_method)
LEFT JOIN rain r        ON r.work_order_id  = b.work_order_id
LEFT JOIN rain_before rb ON rb.work_order_id = b.work_order_id
LEFT JOIN tide t        ON t.work_order_id  = b.work_order_id;

-- Complaints placed on their nearest road (GPS if present, else locality centroid).
CREATE OR REPLACE VIEW v_complaint_road AS
WITH pts AS (
  SELECT c.complaint_id, c.received_at, c.status, c.upvotes,
         COALESCE(c.ward_code, l.ward_code) AS ward_code,
         COALESCE(c.lat, l.lat) AS lat, COALESCE(c.lon, l.lon) AS lon
  FROM complaints c
  LEFT JOIN localities l ON LOWER(TRIM(l.locality)) = LOWER(TRIM(c.locality_text))
),
ranked AS (
  SELECT p.complaint_id, p.received_at, p.status, p.upvotes, g.road_id,
         ROW_NUMBER() OVER (PARTITION BY p.complaint_id ORDER BY
           POWER(g.mid_lat - p.lat, 2) + POWER((g.mid_lon - p.lon) * 0.945, 2)) AS rn
  FROM pts p JOIN v_road_geo g ON g.ward_code = p.ward_code
  WHERE p.lat IS NOT NULL
)
SELECT complaint_id, received_at, status, upvotes, road_id FROM ranked WHERE rn = 1;

-- Static road attributes used by the next-rupee model.
CREATE OR REPLACE VIEW v_road_static AS
SELECT g.road_id, g.ward_code, g.road_type, g.surface, g.lanes, g.length_m,
       g.under_dlp, g.bus_route, g.hotspot_dist_m,
       (DATE '2025-10-15' - CAST(g.last_resurfaced AS DATE)) / 365.25 AS road_age_years,
       w.low_lying_index,
       tr.peak_hour_vehicles, tr.congestion_index_0_10, tr.bus_routes_count, tr.two_wheeler_share_pct,
       COALESCE(f.hospitals_emergency, 0) AS hospitals_emergency,
       COALESCE(f.hospital_beds, 0)       AS hospital_beds,
       COALESCE(f.schools, 0)             AS schools,
       COALESCE(f.students, 0)            AS students
FROM v_road_geo g
JOIN wards w USING (ward_code)
LEFT JOIN traffic tr USING (road_id)
LEFT JOIN (
  SELECT ambulance_entry_road AS road_id,
         SUM(CASE WHEN type = 'Hospital' AND emergency_services = 'Y' THEN 1 ELSE 0 END) AS hospitals_emergency,
         SUM(CASE WHEN type = 'Hospital' THEN beds_or_students ELSE 0 END) AS hospital_beds,
         SUM(CASE WHEN type = 'School' THEN 1 ELSE 0 END) AS schools,
         SUM(CASE WHEN type = 'School' THEN beds_or_students ELSE 0 END) AS students
  FROM facilities GROUP BY ambulance_entry_road
) f USING (road_id);

-- Per-road activity split into two windows so the model can forecast forward.
-- Window 1 = Jun-Jul (features), Window 2 = Aug-Oct (target). Full season used to score.
CREATE OR REPLACE VIEW v_road_activity AS
WITH wo AS (
  SELECT road_id,
         CASE WHEN CAST(completed_at AS DATE) < DATE '2025-08-01' THEN 1 ELSE 2 END AS win,
         cost_inr, CASE WHEN reopened_within_30d = 'Y' THEN 1 ELSE 0 END AS reopen,
         CASE WHEN work_type IN ('Pothole','Road cave-in','Broken paver blocks') THEN 1 ELSE 0 END AS surface_job
  FROM work_orders
),
cp AS (
  SELECT road_id,
         CASE WHEN CAST(received_at AS DATE) < DATE '2025-08-01' THEN 1 ELSE 2 END AS win,
         upvotes,
         CASE WHEN status IN ('Open','In Progress') THEN 1 ELSE 0 END AS still_open
  FROM v_complaint_road
),
ac AS (
  SELECT road_id,
         CASE WHEN CAST(occurred_at AS DATE) < DATE '2025-08-01' THEN 1 ELSE 2 END AS win,
         CASE WHEN probable_cause IN ('Pothole','Waterlogged road','Uneven road / open chamber') THEN 1 ELSE 0 END AS road_caused,
         CASE severity WHEN 'Fatal' THEN 10 WHEN 'Grievous' THEN 3 ELSE 1 END AS sev_w
  FROM accidents
)
SELECT r.road_id,
  (SELECT COUNT(*)            FROM wo WHERE wo.road_id = r.road_id AND win = 1) AS w1_jobs,
  (SELECT COALESCE(SUM(reopen),0) FROM wo WHERE wo.road_id = r.road_id AND win = 1) AS w1_reopens,
  (SELECT COALESCE(SUM(cost_inr),0) FROM wo WHERE wo.road_id = r.road_id AND win = 1) AS w1_cost,
  (SELECT COUNT(*)            FROM cp WHERE cp.road_id = r.road_id AND win = 1) AS w1_complaints,
  (SELECT COALESCE(SUM(upvotes),0) FROM cp WHERE cp.road_id = r.road_id AND win = 1) AS w1_upvotes,
  (SELECT COUNT(*)            FROM wo WHERE wo.road_id = r.road_id AND win = 2) AS w2_jobs,
  (SELECT COALESCE(SUM(reopen),0) FROM wo WHERE wo.road_id = r.road_id AND win = 2) AS w2_reopens,
  (SELECT COUNT(*)            FROM wo WHERE wo.road_id = r.road_id) AS all_jobs,
  (SELECT COALESCE(SUM(reopen),0) FROM wo WHERE wo.road_id = r.road_id) AS all_reopens,
  (SELECT COALESCE(SUM(cost_inr),0) FROM wo WHERE wo.road_id = r.road_id) AS all_cost,
  (SELECT COALESCE(SUM(surface_job),0) FROM wo WHERE wo.road_id = r.road_id) AS all_surface_jobs,
  (SELECT COUNT(*)            FROM cp WHERE cp.road_id = r.road_id) AS all_complaints,
  (SELECT COALESCE(SUM(upvotes),0) FROM cp WHERE cp.road_id = r.road_id) AS all_upvotes,
  (SELECT COALESCE(SUM(still_open),0) FROM cp WHERE cp.road_id = r.road_id) AS open_complaints,
  (SELECT COALESCE(SUM(road_caused * sev_w),0) FROM ac WHERE ac.road_id = r.road_id) AS road_accident_harm,
  (SELECT COALESCE(SUM(road_caused * sev_w),0) FROM ac WHERE ac.road_id = r.road_id AND win = 1) AS w1_road_accident_harm
FROM roads r;
