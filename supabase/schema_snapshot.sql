-- =============================================================================================
-- Follow the Rupee: full database schema (REFERENCE SNAPSHOT, do not run this file)
--
-- Dumped from Supabase (Postgres 17) with:
--   pg_dump "$DATABASE_URL" --schema-only --schema=public --no-owner --no-privileges --restrict-key=schemadump
-- Contains: 30 tables, 16 views, 29 RLS policies, constraints and indexes, as they exist after
--   supabase/migrations/*.sql  (source tables, flags, user writes, engine outputs, v3_*, read views, RLS)
--   scorecard_planner/run_pipeline.py    (runtime feature views v_*, security_invoker + read-only)
--
-- To build a database, run the migrations + loaders in order (see backend/README.md and scorecard_planner/README.md):
--   supabase/migrations/20261121000000_schema.sql
--   supabase/migrations/20261121000100_audit_views.sql
--   supabase/migrations/20261121000200_revoke_truncate.sql
--   supabase/migrations/20261121000300_v3_model_meta.sql
--   supabase/migrations/20261121000400_city_kpis_extra.sql
--   supabase/migrations/20261121000500_frontend_contract.sql
--   supabase/migrations/20261121000600_report_form.sql
--   supabase/migrations/20261121000700_contractor_monthly_scorecards.sql
--   supabase/load_source_data.sql, supabase/load_audit_outputs.sql, then python -m scorecard_planner.run_pipeline
-- Regenerate this snapshot after any schema change (same pg_dump command, prepend this header).
-- =============================================================================================

--
-- PostgreSQL database dump
--
-- PostgreSQL database dump
--

\restrict schemadump

-- Dumped from database version 17.12
-- Dumped by pg_dump version 18.7 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA public;


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS 'standard public schema';


--
-- Name: approx_m(double precision, double precision, double precision, double precision); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.approx_m(lat1 double precision, lon1 double precision, lat2 double precision, lon2 double precision) RETURNS double precision
    LANGUAGE sql IMMUTABLE
    AS $$
  select sqrt(power((lat2 - lat1) * 110540, 2) + power((lon2 - lon1) * 111320 * cos(radians((lat1 + lat2) / 2)), 2))
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: accidents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.accidents (
    accident_id text NOT NULL,
    occurred_at timestamp without time zone NOT NULL,
    ward_code text NOT NULL,
    road_id text NOT NULL,
    lat double precision,
    lon double precision,
    vehicle_type text,
    severity text,
    probable_cause text
);


--
-- Name: citizen_report_contacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.citizen_report_contacts (
    report_id bigint NOT NULL,
    contact_phone text NOT NULL,
    CONSTRAINT citizen_report_contacts_contact_phone_check CHECK ((contact_phone ~ '^\+?[0-9 -]{6,20}$'::text))
);


--
-- Name: citizen_report_photos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.citizen_report_photos (
    report_id bigint NOT NULL,
    photo_id text NOT NULL,
    "position" smallint NOT NULL,
    CONSTRAINT citizen_report_photos_position_check CHECK ((("position" >= 1) AND ("position" <= 3)))
);


--
-- Name: citizen_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.citizen_reports (
    id bigint NOT NULL,
    kind text NOT NULL,
    input_mode text DEFAULT 'text'::text NOT NULL,
    text text,
    language text,
    photo_url text,
    matched_locality text,
    road_id text,
    work_order_id text,
    flag_id text,
    status text DEFAULT 'reported'::text NOT NULL,
    status_updated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    issue_type text,
    location_lat double precision,
    location_lon double precision,
    location_accuracy_m numeric,
    location_source text,
    landmark text,
    duplicate_of bigint,
    linked_work_order_id text,
    CONSTRAINT citizen_reports_input_mode_check CHECK ((input_mode = ANY (ARRAY['text'::text, 'voice'::text, 'photo'::text, 'qr'::text]))),
    CONSTRAINT citizen_reports_issue_type_check CHECK ((issue_type = ANY (ARRAY['pothole'::text, 'waterlogging'::text, 'open_manhole'::text, 'broken_paver'::text, 'cave_in'::text, 'choked_drain'::text, 'other'::text]))),
    CONSTRAINT citizen_reports_kind_check CHECK ((kind = ANY (ARRAY['still_broken'::text, 'verified_fixed'::text, 'new_issue'::text]))),
    CONSTRAINT citizen_reports_landmark_check CHECK ((char_length(landmark) <= 200)),
    CONSTRAINT citizen_reports_language_check CHECK ((language = ANY (ARRAY['en'::text, 'hi'::text, 'mr'::text]))),
    CONSTRAINT citizen_reports_location_accuracy_m_check CHECK ((location_accuracy_m >= (0)::numeric)),
    CONSTRAINT citizen_reports_location_lat_check CHECK (((location_lat >= ('-90'::integer)::double precision) AND (location_lat <= (90)::double precision))),
    CONSTRAINT citizen_reports_location_lon_check CHECK (((location_lon >= ('-180'::integer)::double precision) AND (location_lon <= (180)::double precision))),
    CONSTRAINT citizen_reports_location_source_check CHECK ((location_source = ANY (ARRAY['gps'::text, 'map_pin'::text, 'exif'::text, 'landmark'::text, 'manual'::text]))),
    CONSTRAINT citizen_reports_photo_url_check CHECK ((char_length(photo_url) <= 1000)),
    CONSTRAINT citizen_reports_status_check CHECK ((status = ANY (ARRAY['reported'::text, 'matched_to_contract'::text, 'payment_held'::text, 'contractor_notified'::text]))),
    CONSTRAINT citizen_reports_text_check CHECK ((char_length(text) <= 4000))
);


--
-- Name: citizen_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.citizen_reports ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.citizen_reports_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: complaints; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.complaints (
    complaint_id text NOT NULL,
    received_at timestamp without time zone NOT NULL,
    channel text,
    category_reported text,
    description text,
    language text,
    locality_text text,
    ward_code text,
    lat double precision,
    lon double precision,
    gps_accuracy_m numeric,
    photo_url text,
    photo_description text,
    complainant_id text,
    upvotes integer,
    status text,
    resolved_at timestamp without time zone,
    resolved_ward_code text
);


--
-- Name: contractors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contractors (
    contractor_id text NOT NULL,
    contractor_name text NOT NULL,
    empanelled_since integer,
    active_wards text
);


--
-- Name: flag_replies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.flag_replies (
    id bigint NOT NULL,
    flag_id text NOT NULL,
    author_role text NOT NULL,
    author_name text,
    body text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT flag_replies_author_name_check CHECK ((char_length(author_name) <= 120)),
    CONSTRAINT flag_replies_author_role_check CHECK ((author_role = ANY (ARRAY['ward_engineer'::text, 'contractor'::text, 'other'::text]))),
    CONSTRAINT flag_replies_body_check CHECK (((char_length(body) >= 1) AND (char_length(body) <= 4000)))
);


--
-- Name: flags; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.flags (
    flag_id text NOT NULL,
    tier smallint NOT NULL,
    detector text NOT NULL,
    status_label text NOT NULL,
    ward_code text NOT NULL,
    road_id text NOT NULL,
    work_order_id text NOT NULL,
    contractor_id text NOT NULL,
    rupees_at_stake bigint NOT NULL,
    evidence_row_ids text[] NOT NULL,
    rule_text text NOT NULL,
    CONSTRAINT flags_rupees_at_stake_check CHECK ((rupees_at_stake > 0)),
    CONSTRAINT flags_status_label_check CHECK ((status_label = ANY (ARRAY['Needs Explanation'::text, 'Recoverable under DLP'::text]))),
    CONSTRAINT flags_tier_check CHECK (((tier >= 1) AND (tier <= 3)))
);


--
-- Name: roads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roads (
    road_id text NOT NULL,
    road_name text NOT NULL,
    segment_no integer,
    ward_code text NOT NULL,
    road_type text,
    surface text,
    lanes integer,
    length_m numeric,
    start_lat double precision,
    start_lon double precision,
    end_lat double precision,
    end_lon double precision,
    last_resurfaced date,
    under_dlp boolean NOT NULL,
    bus_route boolean
);


--
-- Name: work_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.work_orders (
    work_order_id text NOT NULL,
    linked_complaint_ids text,
    ward_code text NOT NULL,
    road_id text NOT NULL,
    work_type text,
    repair_method text NOT NULL,
    contractor_id text NOT NULL,
    contractor_name_raw text,
    assigned_at timestamp without time zone,
    work_started_at timestamp without time zone,
    completed_at timestamp without time zone,
    area_sqm numeric,
    cost_inr numeric NOT NULL,
    sla_hours integer,
    sla_met boolean,
    reopened_within_30d boolean,
    engineer_remark text,
    CONSTRAINT work_orders_check CHECK (((work_started_at >= assigned_at) AND (completed_at >= work_started_at)))
);


--
-- Name: flagged_queue; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.flagged_queue WITH (security_invoker='true') AS
 SELECT f.work_order_id,
    wo.road_id,
    r.road_name,
    wo.ward_code,
    wo.contractor_id,
    c.contractor_name,
    wo.repair_method,
    wo.cost_inr,
    wo.completed_at,
    min(f.tier) AS top_tier,
    max(f.rupees_at_stake) AS rupees_at_stake,
        CASE
            WHEN bool_or((f.detector = 'DLP_PAID_TWICE'::text)) THEN 'Recoverable under DLP'::text
            ELSE 'Needs Explanation'::text
        END AS status_label,
    array_agg(f.flag_id ORDER BY f.tier, f.flag_id) AS flag_ids,
    array_agg(DISTINCT f.detector) AS detectors,
    count(rep.id) AS replies_count
   FROM ((((public.flags f
     JOIN public.work_orders wo USING (work_order_id))
     JOIN public.roads r ON ((r.road_id = wo.road_id)))
     JOIN public.contractors c ON ((c.contractor_id = wo.contractor_id)))
     LEFT JOIN public.flag_replies rep ON ((rep.flag_id = f.flag_id)))
  GROUP BY f.work_order_id, wo.road_id, r.road_name, wo.ward_code, wo.contractor_id, c.contractor_name, wo.repair_method, wo.cost_inr, wo.completed_at;


--
-- Name: ward_audit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ward_audit (
    ward_code text NOT NULL,
    budget_inr bigint NOT NULL,
    spend_inr bigint NOT NULL,
    recoverable_dlp_inr bigint NOT NULL,
    flagged_bills_count integer NOT NULL,
    warranty_enforcement_rate numeric,
    dlp_eligible_jobs integer NOT NULL,
    dlp_leakage_rate numeric NOT NULL,
    physical_risk_score numeric NOT NULL,
    complaints_per_lakh numeric NOT NULL,
    under_reported_flag boolean NOT NULL,
    flood_hotspots_count integer NOT NULL,
    accidents_count integer NOT NULL
);


--
-- Name: city_kpis; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.city_kpis WITH (security_invoker='true') AS
 SELECT (sum(budget_inr))::bigint AS total_budget_inr,
    (sum(spend_inr))::bigint AS total_spend_inr,
    (sum(recoverable_dlp_inr))::bigint AS recoverable_dlp_inr,
    sum(flagged_bills_count) AS flagged_bills_count,
    ( SELECT jsonb_object_agg(d.detector, d.n) AS jsonb_object_agg
           FROM ( SELECT flags.detector,
                    count(*) AS n
                   FROM public.flags
                  GROUP BY flags.detector) d) AS flags_by_detector,
    ( SELECT (COALESCE(sum(flagged_queue.rupees_at_stake), (0)::numeric))::bigint AS "coalesce"
           FROM public.flagged_queue) AS rupees_at_stake_total,
    (count(*) FILTER (WHERE (spend_inr > budget_inr)))::integer AS wards_over_budget,
    COALESCE(array_agg(ward_code ORDER BY ward_code) FILTER (WHERE under_reported_flag), '{}'::text[]) AS under_reported_wards,
    (( SELECT count(*) AS count
           FROM public.work_orders))::integer AS work_orders_count,
    (( SELECT count(*) AS count
           FROM public.complaints))::integer AS complaints_count,
    (( SELECT count(*) AS count
           FROM public.work_orders
          WHERE work_orders.reopened_within_30d))::integer AS reopened_within_30d_count,
    ( SELECT round(avg(
                CASE
                    WHEN work_orders.sla_met THEN 1.0
                    ELSE 0.0
                END), 4) AS round
           FROM public.work_orders) AS sla_met_rate,
    ( SELECT (COALESCE(sum(wo.cost_inr), (0)::numeric))::bigint AS "coalesce"
           FROM (public.work_orders wo
             JOIN public.roads r USING (road_id))
          WHERE r.under_dlp) AS dlp_road_spend_inr,
    (('Only road-surface repairs (cold mix, hot mix, mastic asphalt, paver blocks) billed on roads still under the '::text || 'original contractor''s Defect Liability Period count as recoverable; drainage, pumping, manhole and utility '::text) || 'work on those roads is not a surface defect, so the warranty does not cover it.'::text) AS recoverable_dlp_rule
   FROM public.ward_audit;


--
-- Name: complaint_work_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.complaint_work_orders (
    complaint_id text NOT NULL,
    work_order_id text NOT NULL
);


--
-- Name: contractor_monthly_scorecards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contractor_monthly_scorecards (
    contractor_id text NOT NULL,
    month date NOT NULL,
    methodology_version text NOT NULL,
    computed_at timestamp with time zone NOT NULL,
    completed_jobs integer NOT NULL,
    total_billed_inr numeric NOT NULL,
    sla_known integer NOT NULL,
    sla_met integer NOT NULL,
    sla_missing integer NOT NULL,
    sla_rate numeric,
    sla_rank smallint,
    reopen_known integer NOT NULL,
    reopened integer NOT NULL,
    reopen_missing integer NOT NULL,
    reopen_rate numeric,
    durability_rank smallint,
    speed_sample integer NOT NULL,
    speed_missing integer NOT NULL,
    speed_raw_sample integer NOT NULL,
    speed_median_hours numeric,
    speed_cohort_median_hours numeric,
    speed_relative_index numeric,
    speed_rank smallint,
    assigned_to_completed_median_hours numeric,
    cost_sample integer NOT NULL,
    cost_missing integer NOT NULL,
    cost_median_abs_pct_dev numeric,
    cost_over_tolerance_count integer NOT NULL,
    cost_over_tolerance_share numeric,
    cost_under_tolerance_count integer NOT NULL,
    cost_rank smallint,
    rank_eligibility jsonb NOT NULL,
    rank_cohort_sizes jsonb NOT NULL,
    workload_mix jsonb NOT NULL,
    context jsonb NOT NULL,
    data_quality jsonb NOT NULL,
    evidence_work_order_ids text[] NOT NULL,
    CONSTRAINT contractor_monthly_scorecards_check CHECK (((sla_met >= 0) AND (sla_met <= sla_known))),
    CONSTRAINT contractor_monthly_scorecards_check1 CHECK (((reopened >= 0) AND (reopened <= reopen_known))),
    CONSTRAINT contractor_monthly_scorecards_check2 CHECK (((sla_known + sla_missing) = completed_jobs)),
    CONSTRAINT contractor_monthly_scorecards_check3 CHECK (((reopen_known + reopen_missing) = completed_jobs)),
    CONSTRAINT contractor_monthly_scorecards_check4 CHECK (((speed_sample + speed_missing) = completed_jobs)),
    CONSTRAINT contractor_monthly_scorecards_check5 CHECK (((cost_sample + cost_missing) = completed_jobs)),
    CONSTRAINT contractor_monthly_scorecards_check6 CHECK ((cardinality(evidence_work_order_ids) = completed_jobs)),
    CONSTRAINT contractor_monthly_scorecards_completed_jobs_check CHECK ((completed_jobs > 0)),
    CONSTRAINT contractor_monthly_scorecards_cost_median_abs_pct_dev_check CHECK ((cost_median_abs_pct_dev >= (0)::numeric)),
    CONSTRAINT contractor_monthly_scorecards_cost_missing_check CHECK ((cost_missing >= 0)),
    CONSTRAINT contractor_monthly_scorecards_cost_over_tolerance_count_check CHECK ((cost_over_tolerance_count >= 0)),
    CONSTRAINT contractor_monthly_scorecards_cost_over_tolerance_share_check CHECK (((cost_over_tolerance_share >= (0)::numeric) AND (cost_over_tolerance_share <= (1)::numeric))),
    CONSTRAINT contractor_monthly_scorecards_cost_rank_check CHECK ((cost_rank >= 1)),
    CONSTRAINT contractor_monthly_scorecards_cost_sample_check CHECK ((cost_sample >= 0)),
    CONSTRAINT contractor_monthly_scorecards_cost_under_tolerance_count_check CHECK ((cost_under_tolerance_count >= 0)),
    CONSTRAINT contractor_monthly_scorecards_durability_rank_check CHECK ((durability_rank >= 1)),
    CONSTRAINT contractor_monthly_scorecards_month_check CHECK ((month = (date_trunc('month'::text, (month)::timestamp with time zone))::date)),
    CONSTRAINT contractor_monthly_scorecards_reopen_known_check CHECK ((reopen_known >= 0)),
    CONSTRAINT contractor_monthly_scorecards_reopen_missing_check CHECK ((reopen_missing >= 0)),
    CONSTRAINT contractor_monthly_scorecards_reopen_rate_check CHECK (((reopen_rate >= (0)::numeric) AND (reopen_rate <= (1)::numeric))),
    CONSTRAINT contractor_monthly_scorecards_sla_known_check CHECK ((sla_known >= 0)),
    CONSTRAINT contractor_monthly_scorecards_sla_missing_check CHECK ((sla_missing >= 0)),
    CONSTRAINT contractor_monthly_scorecards_sla_rank_check CHECK ((sla_rank >= 1)),
    CONSTRAINT contractor_monthly_scorecards_sla_rate_check CHECK (((sla_rate >= (0)::numeric) AND (sla_rate <= (1)::numeric))),
    CONSTRAINT contractor_monthly_scorecards_speed_missing_check CHECK ((speed_missing >= 0)),
    CONSTRAINT contractor_monthly_scorecards_speed_rank_check CHECK ((speed_rank >= 1)),
    CONSTRAINT contractor_monthly_scorecards_speed_raw_sample_check CHECK ((speed_raw_sample >= 0)),
    CONSTRAINT contractor_monthly_scorecards_speed_relative_index_check CHECK ((speed_relative_index >= (0)::numeric)),
    CONSTRAINT contractor_monthly_scorecards_speed_sample_check CHECK ((speed_sample >= 0))
);


--
-- Name: contractor_scorecard_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contractor_scorecard_runs (
    methodology_version text NOT NULL,
    computed_at timestamp with time zone NOT NULL,
    params jsonb NOT NULL,
    source_counts jsonb NOT NULL,
    data_quality jsonb NOT NULL
);


--
-- Name: facilities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.facilities (
    facility_id text NOT NULL,
    type text NOT NULL,
    name text NOT NULL,
    ward_code text NOT NULL,
    lat double precision,
    lon double precision,
    beds_or_students integer,
    emergency_services boolean,
    ambulance_entry_road text
);


--
-- Name: flag_replies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.flag_replies ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.flag_replies_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: flood_hotspots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.flood_hotspots (
    hotspot_id text NOT NULL,
    name text NOT NULL,
    ward_code text NOT NULL,
    lat double precision,
    lon double precision,
    flood_threshold_mm_per_day numeric,
    tide_sensitive boolean,
    avg_water_depth_cm numeric,
    avg_recession_hours numeric,
    pumping_station_nearby boolean,
    years_flagged_last_5 integer
);


--
-- Name: issue_sla; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.issue_sla WITH (security_invoker='true') AS
 SELECT issue_type,
    work_type,
    ( SELECT percentile_disc((0.5)::double precision) WITHIN GROUP (ORDER BY w.sla_hours) AS percentile_disc
           FROM public.work_orders w
          WHERE (w.work_type = i.work_type)) AS sla_hours
   FROM ( VALUES ('pothole'::text,'Pothole'::text), ('waterlogging'::text,'Waterlogging'::text), ('open_manhole'::text,'Open or broken manhole'::text), ('broken_paver'::text,'Broken paver blocks'::text), ('cave_in'::text,'Road cave-in'::text), ('choked_drain'::text,'Choked drain / nullah overflow'::text), ('other'::text,NULL::text)) i(issue_type, work_type);


--
-- Name: localities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.localities (
    locality text NOT NULL,
    ward_code text NOT NULL,
    lat double precision,
    lon double precision,
    aliases text
);


--
-- Name: locality_aliases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.locality_aliases (
    alias text NOT NULL,
    locality text NOT NULL
);


--
-- Name: locality_list; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.locality_list WITH (security_invoker='true') AS
 SELECT locality,
    ward_code,
    lat,
    lon,
    COALESCE(ARRAY( SELECT TRIM(BOTH FROM a.a) AS btrim
           FROM unnest(string_to_array(l.aliases, ';'::text)) a(a)
          WHERE (TRIM(BOTH FROM a.a) <> ''::text)), '{}'::text[]) AS aliases
   FROM public.localities l;


--
-- Name: locality_livability; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.locality_livability WITH (security_invoker='true') AS
 WITH near_roads AS (
         SELECT l_1.locality,
            r.road_id,
            public.approx_m(l_1.lat, l_1.lon, ((r.start_lat + r.end_lat) / (2)::double precision), ((r.start_lon + r.end_lon) / (2)::double precision)) AS m
           FROM (public.localities l_1
             CROSS JOIN public.roads r)
        )
 SELECT l.locality,
    l.ward_code,
    l.lat,
    l.lon,
    1500 AS radius_m,
    (( SELECT count(*) AS count
           FROM public.flood_hotspots h
          WHERE (public.approx_m(l.lat, l.lon, h.lat, h.lon) <= (1500)::double precision)))::integer AS flood_hotspots_1500m,
    (( SELECT count(*) AS count
           FROM (public.work_orders wo
             JOIN near_roads n USING (road_id))
          WHERE ((n.locality = l.locality) AND (n.m <= (1500)::double precision))))::integer AS jobs_1500m,
    ( SELECT round(avg(
                CASE
                    WHEN wo.reopened_within_30d THEN 1.0
                    ELSE 0.0
                END), 4) AS round
           FROM (public.work_orders wo
             JOIN near_roads n USING (road_id))
          WHERE ((n.locality = l.locality) AND (n.m <= (1500)::double precision))) AS failure_rate_30d_1500m,
    (( SELECT count(DISTINCT f.ambulance_entry_road) AS count
           FROM (public.facilities f
             JOIN near_roads n ON ((n.road_id = f.ambulance_entry_road)))
          WHERE ((n.locality = l.locality) AND (n.m <= (1500)::double precision) AND (f.type = 'Hospital'::text))))::integer AS hospital_access_roads_1500m,
    wa.dlp_leakage_rate AS ward_dlp_leakage_rate,
    COALESCE(( SELECT array_agg(n.road_id ORDER BY n.m) AS array_agg
           FROM near_roads n
          WHERE ((n.locality = l.locality) AND (n.m <= (1500)::double precision))), '{}'::text[]) AS nearby_road_ids
   FROM (public.localities l
     LEFT JOIN public.ward_audit wa USING (ward_code));


--
-- Name: locality_nearest_road; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.locality_nearest_road WITH (security_invoker='true') AS
 SELECT l.locality,
    l.ward_code,
    nr.road_id,
    nr.road_name,
    nr.under_dlp,
    nr.approx_m
   FROM (public.localities l
     CROSS JOIN LATERAL ( SELECT r.road_id,
            r.road_name,
            r.under_dlp,
            (round(sqrt((power(((((r.start_lat + r.end_lat) / (2)::double precision) - l.lat) * (110540)::double precision), (2)::double precision) + power(((((r.start_lon + r.end_lon) / (2)::double precision) - l.lon) * (105200)::double precision), (2)::double precision)))))::integer AS approx_m
           FROM public.roads r
          WHERE (r.ward_code = l.ward_code)
          ORDER BY ((round(sqrt((power(((((r.start_lat + r.end_lat) / (2)::double precision) - l.lat) * (110540)::double precision), (2)::double precision) + power(((((r.start_lon + r.end_lon) / (2)::double precision) - l.lon) * (105200)::double precision), (2)::double precision)))))::integer)
         LIMIT 1) nr);


--
-- Name: photos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.photos (
    photo_id text NOT NULL,
    storage text NOT NULL,
    content_type text NOT NULL,
    original_content_type text NOT NULL,
    size_bytes integer NOT NULL,
    width integer,
    height integer,
    taken_at timestamp without time zone,
    exif_lat double precision,
    exif_lon double precision,
    storage_path text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT photos_content_type_check CHECK ((content_type = ANY (ARRAY['image/jpeg'::text, 'image/png'::text, 'image/webp'::text]))),
    CONSTRAINT photos_original_content_type_check CHECK ((original_content_type = ANY (ARRAY['image/jpeg'::text, 'image/png'::text, 'image/webp'::text, 'image/heic'::text]))),
    CONSTRAINT photos_size_bytes_check CHECK (((size_bytes >= 1) AND (size_bytes <= 8388608))),
    CONSTRAINT photos_storage_check CHECK ((storage = ANY (ARRAY['supabase'::text, 'local'::text])))
);


--
-- Name: rainfall_daily; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rainfall_daily (
    date date NOT NULL,
    station text NOT NULL,
    rainfall_mm numeric NOT NULL,
    imd_category text,
    imd_alert text
);


--
-- Name: rain_by_day; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.rain_by_day WITH (security_invoker='true') AS
 SELECT date,
    max(rainfall_mm) AS max_rainfall_mm
   FROM public.rainfall_daily
  GROUP BY date;


--
-- Name: rate_card; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rate_card (
    repair_method text NOT NULL,
    unit text NOT NULL,
    standard_rate_inr numeric NOT NULL,
    CONSTRAINT rate_card_unit_check CHECK ((unit = ANY (ARRAY['per sqm'::text, 'per job'::text])))
);


--
-- Name: road_audit; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.road_audit WITH (security_invoker='true') AS
 SELECT r.road_id,
    r.road_name,
    r.ward_code,
    r.road_type,
    r.surface,
    r.under_dlp,
    r.last_resurfaced,
    COALESCE(b.total_billed_inr, (0)::numeric) AS total_billed_inr,
    COALESCE(b.work_orders_count, (0)::bigint) AS work_orders_count,
    COALESCE(q.rupees_at_stake, (0)::numeric) AS rupees_at_stake,
    COALESCE(q.flagged_bills, (0)::bigint) AS flagged_bills_count,
    r.segment_no,
    r.length_m,
        CASE
            WHEN r.under_dlp THEN 36
            ELSE NULL::integer
        END AS dlp_months,
        CASE
            WHEN r.under_dlp THEN ((r.last_resurfaced + '3 years'::interval))::date
            ELSE NULL::date
        END AS dlp_expires_on
   FROM ((public.roads r
     LEFT JOIN ( SELECT work_orders.road_id,
            sum(work_orders.cost_inr) AS total_billed_inr,
            count(*) AS work_orders_count
           FROM public.work_orders
          GROUP BY work_orders.road_id) b USING (road_id))
     LEFT JOIN ( SELECT flagged_queue.road_id,
            sum(flagged_queue.rupees_at_stake) AS rupees_at_stake,
            count(*) AS flagged_bills
           FROM public.flagged_queue
          GROUP BY flagged_queue.road_id) q USING (road_id));


--
-- Name: road_timeline; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.road_timeline WITH (security_invoker='true') AS
 SELECT wo.road_id,
    c.received_at AS event_at,
    'complaint'::text AS event_type,
    c.complaint_id AS ref_id,
    jsonb_build_object('work_order_id', wo.work_order_id, 'channel', c.channel, 'status', c.status, 'language', c.language, 'description', c.description) AS detail
   FROM ((public.complaint_work_orders cw
     JOIN public.complaints c USING (complaint_id))
     JOIN public.work_orders wo USING (work_order_id))
UNION ALL
 SELECT wo.road_id,
    wo.assigned_at AS event_at,
    'work_order_assigned'::text AS event_type,
    wo.work_order_id AS ref_id,
    jsonb_build_object('contractor_id', wo.contractor_id, 'repair_method', wo.repair_method, 'cost_inr', wo.cost_inr) AS detail
   FROM public.work_orders wo
UNION ALL
 SELECT wo.road_id,
    wo.completed_at AS event_at,
    'work_order_completed'::text AS event_type,
    wo.work_order_id AS ref_id,
    jsonb_build_object('contractor_id', wo.contractor_id, 'sla_met', wo.sla_met, 'reopened_within_30d', wo.reopened_within_30d, 'rain_mm_on_completion_day', COALESCE(rd.max_rainfall_mm, (0)::numeric), 'engineer_remark', wo.engineer_remark) AS detail
   FROM (public.work_orders wo
     LEFT JOIN public.rain_by_day rd ON ((rd.date = (wo.completed_at)::date)))
UNION ALL
 SELECT a.road_id,
    a.occurred_at AS event_at,
    'accident'::text AS event_type,
    a.accident_id AS ref_id,
    jsonb_build_object('severity', a.severity, 'probable_cause', a.probable_cause, 'vehicle_type', a.vehicle_type) AS detail
   FROM public.accidents a
UNION ALL
 SELECT cr.road_id,
    (cr.created_at)::timestamp without time zone AS event_at,
    'citizen_report'::text AS event_type,
    (cr.id)::text AS ref_id,
    jsonb_build_object('kind', cr.kind, 'status', cr.status, 'work_order_id', cr.work_order_id) AS detail
   FROM public.citizen_reports cr
  WHERE (cr.road_id IS NOT NULL);


--
-- Name: social_posts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.social_posts (
    post_id text NOT NULL,
    posted_at timestamp without time zone,
    source text,
    author_handle text,
    text text,
    has_media boolean,
    likes_or_forwards integer
);


--
-- Name: tides; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tides (
    date date NOT NULL,
    high_tide_time time without time zone NOT NULL,
    height_m numeric,
    big_tide_flag boolean
);


--
-- Name: traffic; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.traffic (
    road_id text NOT NULL,
    peak_hour_vehicles integer,
    avg_peak_speed_kmph numeric,
    congestion_index_0_10 numeric,
    bus_routes_count integer,
    two_wheeler_share_pct numeric
);


--
-- Name: v3_contractor_scorecard; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.v3_contractor_scorecard (
    contractor_id text NOT NULL,
    contractor_name text NOT NULL,
    jobs_count integer NOT NULL,
    total_billed_inr bigint NOT NULL,
    reopen_rate_30d numeric NOT NULL,
    expected_reopen_rate_30d numeric NOT NULL,
    sla_met_rate numeric NOT NULL,
    expected_sla_met_rate numeric NOT NULL,
    durability_index numeric NOT NULL,
    durability_verdict text NOT NULL,
    durability_ratio_obs_over_exp numeric,
    durability_ratio_ci90 jsonb,
    speed_index numeric NOT NULL,
    speed_verdict text NOT NULL,
    risk_adjusted_score numeric NOT NULL,
    cost_vs_rate_median numeric,
    jobs_over_130pct_rate integer,
    method_mix_top3 jsonb,
    context jsonb,
    drivers jsonb,
    evidence_reopened_wo_ids jsonb,
    explanation text,
    CONSTRAINT v3_contractor_scorecard_durability_index_check CHECK (((durability_index >= (0)::numeric) AND (durability_index <= (100)::numeric))),
    CONSTRAINT v3_contractor_scorecard_speed_index_check CHECK (((speed_index >= (0)::numeric) AND (speed_index <= (100)::numeric)))
);


--
-- Name: v3_job_expected_risk; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.v3_job_expected_risk (
    work_order_id text NOT NULL,
    contractor_id text NOT NULL,
    p_reopen_expected numeric NOT NULL,
    p_sla_miss_expected numeric NOT NULL
);


--
-- Name: v3_model_meta; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.v3_model_meta (
    id smallint DEFAULT 1 NOT NULL,
    meta jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT v3_model_meta_id_check CHECK ((id = 1))
);


--
-- Name: v3_next_rupee; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.v3_next_rupee (
    item_id text NOT NULL,
    road_id text NOT NULL,
    road_name text,
    ward_code text NOT NULL,
    issue text NOT NULL,
    under_dlp boolean NOT NULL,
    bucket text NOT NULL,
    funded boolean NOT NULL,
    recommended_method text,
    method_reopen_rate numeric,
    estimated_repair_cost_inr bigint,
    cost_to_bmc_inr bigint,
    harm_avoided numeric,
    harm_per_lakh numeric,
    priority_score numeric,
    reason_codes jsonb NOT NULL,
    inputs jsonb,
    evidence_wo_ids jsonb,
    explanation text,
    CONSTRAINT v3_next_rupee_bucket_check CHECK ((bucket = ANY (ARRAY['A_OWED_BY_CONTRACTOR_DLP'::text, 'B_NEXT_RUPEE'::text])))
);


--
-- Name: v3_ward_allocation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.v3_ward_allocation (
    ward_code text NOT NULL,
    ward_name text,
    budget_2025_inr bigint NOT NULL,
    spend_2025_inr bigint NOT NULL,
    remaining_2025_inr bigint NOT NULL,
    recommended_budget_inr bigint NOT NULL,
    equity_floor_inr bigint NOT NULL,
    harm_avoided numeric NOT NULL,
    harm_avoided_per_next_lakh numeric NOT NULL,
    dlp_items_owed_by_contractor integer NOT NULL,
    dlp_value_owed_inr bigint NOT NULL
);


--
-- Name: v_road_geo; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_road_geo WITH (security_invoker='true') AS
 WITH mid AS (
         SELECT r.road_id,
            r.road_name,
            r.segment_no,
            r.ward_code,
            r.road_type,
            r.surface,
            r.lanes,
            r.length_m,
            r.start_lat,
            r.start_lon,
            r.end_lat,
            r.end_lon,
            r.last_resurfaced,
            r.under_dlp,
            r.bus_route,
            ((r.start_lat + r.end_lat) / (2.0)::double precision) AS mid_lat,
            ((r.start_lon + r.end_lon) / (2.0)::double precision) AS mid_lon
           FROM public.roads r
        )
 SELECT m.road_id,
    m.ward_code,
    m.road_type,
    m.surface,
    m.lanes,
    m.length_m,
    m.last_resurfaced,
    m.under_dlp,
    m.bus_route,
    m.mid_lat,
    m.mid_lon,
    min(((111320.0)::double precision * sqrt((power((h.lat - m.mid_lat), (2)::double precision) + power(((h.lon - m.mid_lon) * cos(radians(m.mid_lat))), (2)::double precision))))) AS hotspot_dist_m
   FROM (mid m
     CROSS JOIN public.flood_hotspots h)
  GROUP BY m.road_id, m.ward_code, m.road_type, m.surface, m.lanes, m.length_m, m.last_resurfaced, m.under_dlp, m.bus_route, m.mid_lat, m.mid_lon;


--
-- Name: v_complaint_road; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_complaint_road WITH (security_invoker='true') AS
 WITH pts AS (
         SELECT c.complaint_id,
            c.received_at,
            c.status,
            c.upvotes,
            COALESCE(c.ward_code, l.ward_code) AS ward_code,
            COALESCE(c.lat, l.lat) AS lat,
            COALESCE(c.lon, l.lon) AS lon
           FROM (public.complaints c
             LEFT JOIN public.localities l ON ((lower(TRIM(BOTH FROM l.locality)) = lower(TRIM(BOTH FROM c.locality_text)))))
        ), ranked AS (
         SELECT p.complaint_id,
            p.received_at,
            p.status,
            p.upvotes,
            g.road_id,
            row_number() OVER (PARTITION BY p.complaint_id ORDER BY (power((g.mid_lat - p.lat), (2)::double precision) + power(((g.mid_lon - p.lon) * (0.945)::double precision), (2)::double precision))) AS rn
           FROM (pts p
             JOIN public.v_road_geo g ON ((g.ward_code = p.ward_code)))
          WHERE (p.lat IS NOT NULL)
        )
 SELECT complaint_id,
    received_at,
    status,
    upvotes,
    road_id
   FROM ranked
  WHERE (rn = 1);


--
-- Name: v_road_activity; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_road_activity WITH (security_invoker='true') AS
 WITH wo AS (
         SELECT work_orders.road_id,
                CASE
                    WHEN ((work_orders.completed_at)::date < '2025-08-01'::date) THEN 1
                    ELSE 2
                END AS win,
            work_orders.cost_inr,
                CASE
                    WHEN (work_orders.reopened_within_30d = true) THEN 1
                    ELSE 0
                END AS reopen,
                CASE
                    WHEN (work_orders.work_type = ANY (ARRAY['Pothole'::text, 'Road cave-in'::text, 'Broken paver blocks'::text])) THEN 1
                    ELSE 0
                END AS surface_job
           FROM public.work_orders
        ), cp AS (
         SELECT v_complaint_road.road_id,
                CASE
                    WHEN ((v_complaint_road.received_at)::date < '2025-08-01'::date) THEN 1
                    ELSE 2
                END AS win,
            v_complaint_road.upvotes,
                CASE
                    WHEN (v_complaint_road.status = ANY (ARRAY['Open'::text, 'In Progress'::text])) THEN 1
                    ELSE 0
                END AS still_open
           FROM public.v_complaint_road
        ), ac AS (
         SELECT accidents.road_id,
                CASE
                    WHEN ((accidents.occurred_at)::date < '2025-08-01'::date) THEN 1
                    ELSE 2
                END AS win,
                CASE
                    WHEN (accidents.probable_cause = ANY (ARRAY['Pothole'::text, 'Waterlogged road'::text, 'Uneven road / open chamber'::text])) THEN 1
                    ELSE 0
                END AS road_caused,
                CASE accidents.severity
                    WHEN 'Fatal'::text THEN 10
                    WHEN 'Grievous'::text THEN 3
                    ELSE 1
                END AS sev_w
           FROM public.accidents
        )
 SELECT road_id,
    ( SELECT count(*) AS count
           FROM wo
          WHERE ((wo.road_id = r.road_id) AND (wo.win = 1))) AS w1_jobs,
    ( SELECT COALESCE(sum(wo.reopen), (0)::bigint) AS "coalesce"
           FROM wo
          WHERE ((wo.road_id = r.road_id) AND (wo.win = 1))) AS w1_reopens,
    ( SELECT COALESCE(sum(wo.cost_inr), (0)::numeric) AS "coalesce"
           FROM wo
          WHERE ((wo.road_id = r.road_id) AND (wo.win = 1))) AS w1_cost,
    ( SELECT count(*) AS count
           FROM cp
          WHERE ((cp.road_id = r.road_id) AND (cp.win = 1))) AS w1_complaints,
    ( SELECT COALESCE(sum(cp.upvotes), (0)::bigint) AS "coalesce"
           FROM cp
          WHERE ((cp.road_id = r.road_id) AND (cp.win = 1))) AS w1_upvotes,
    ( SELECT count(*) AS count
           FROM wo
          WHERE ((wo.road_id = r.road_id) AND (wo.win = 2))) AS w2_jobs,
    ( SELECT COALESCE(sum(wo.reopen), (0)::bigint) AS "coalesce"
           FROM wo
          WHERE ((wo.road_id = r.road_id) AND (wo.win = 2))) AS w2_reopens,
    ( SELECT count(*) AS count
           FROM wo
          WHERE (wo.road_id = r.road_id)) AS all_jobs,
    ( SELECT COALESCE(sum(wo.reopen), (0)::bigint) AS "coalesce"
           FROM wo
          WHERE (wo.road_id = r.road_id)) AS all_reopens,
    ( SELECT COALESCE(sum(wo.cost_inr), (0)::numeric) AS "coalesce"
           FROM wo
          WHERE (wo.road_id = r.road_id)) AS all_cost,
    ( SELECT COALESCE(sum(wo.surface_job), (0)::bigint) AS "coalesce"
           FROM wo
          WHERE (wo.road_id = r.road_id)) AS all_surface_jobs,
    ( SELECT count(*) AS count
           FROM cp
          WHERE (cp.road_id = r.road_id)) AS all_complaints,
    ( SELECT COALESCE(sum(cp.upvotes), (0)::bigint) AS "coalesce"
           FROM cp
          WHERE (cp.road_id = r.road_id)) AS all_upvotes,
    ( SELECT COALESCE(sum(cp.still_open), (0)::bigint) AS "coalesce"
           FROM cp
          WHERE (cp.road_id = r.road_id)) AS open_complaints,
    ( SELECT COALESCE(sum((ac.road_caused * ac.sev_w)), (0)::bigint) AS "coalesce"
           FROM ac
          WHERE (ac.road_id = r.road_id)) AS road_accident_harm,
    ( SELECT COALESCE(sum((ac.road_caused * ac.sev_w)), (0)::bigint) AS "coalesce"
           FROM ac
          WHERE ((ac.road_id = r.road_id) AND (ac.win = 1))) AS w1_road_accident_harm
   FROM public.roads r;


--
-- Name: wards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wards (
    ward_code text NOT NULL,
    ward_name text NOT NULL,
    zone text,
    assistant_commissioner_office text,
    centroid_lat double precision,
    centroid_lon double precision,
    approx_area_km2 numeric,
    population_est integer,
    low_lying_index numeric,
    engineering_crews integer,
    localities text,
    monsoon_repair_budget_inr_2025 bigint NOT NULL,
    CONSTRAINT wards_low_lying_index_check CHECK (((low_lying_index >= (0)::numeric) AND (low_lying_index <= (1)::numeric)))
);


--
-- Name: v_road_static; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_road_static WITH (security_invoker='true') AS
 SELECT g.road_id,
    g.ward_code,
    g.road_type,
    g.surface,
    g.lanes,
    g.length_m,
    g.under_dlp,
    g.bus_route,
    g.hotspot_dist_m,
    ((('2025-10-15'::date - g.last_resurfaced))::numeric / 365.25) AS road_age_years,
    w.low_lying_index,
    tr.peak_hour_vehicles,
    tr.congestion_index_0_10,
    tr.bus_routes_count,
    tr.two_wheeler_share_pct,
    COALESCE(f.hospitals_emergency, (0)::bigint) AS hospitals_emergency,
    COALESCE(f.hospital_beds, (0)::bigint) AS hospital_beds,
    COALESCE(f.schools, (0)::bigint) AS schools,
    COALESCE(f.students, (0)::bigint) AS students
   FROM (((public.v_road_geo g
     JOIN public.wards w USING (ward_code))
     LEFT JOIN public.traffic tr USING (road_id))
     LEFT JOIN ( SELECT facilities.ambulance_entry_road AS road_id,
            sum(
                CASE
                    WHEN ((facilities.type = 'Hospital'::text) AND (facilities.emergency_services = true)) THEN 1
                    ELSE 0
                END) AS hospitals_emergency,
            sum(
                CASE
                    WHEN (facilities.type = 'Hospital'::text) THEN facilities.beds_or_students
                    ELSE 0
                END) AS hospital_beds,
            sum(
                CASE
                    WHEN (facilities.type = 'School'::text) THEN 1
                    ELSE 0
                END) AS schools,
            sum(
                CASE
                    WHEN (facilities.type = 'School'::text) THEN facilities.beds_or_students
                    ELSE 0
                END) AS students
           FROM public.facilities
          GROUP BY facilities.ambulance_entry_road) f USING (road_id));


--
-- Name: v_ward_station; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_ward_station WITH (security_invoker='true') AS
 SELECT ward_code,
        CASE
            WHEN (ward_code = ANY (ARRAY['A'::text, 'B'::text, 'C'::text, 'D'::text, 'E'::text, 'F/S'::text, 'F/N'::text, 'G/S'::text, 'G/N'::text])) THEN 'Colaba'::text
            ELSE 'Santacruz'::text
        END AS station
   FROM public.wards;


--
-- Name: v_wo_context; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_wo_context WITH (security_invoker='true') AS
 WITH base AS (
         SELECT wo.work_order_id,
            wo.linked_complaint_ids,
            wo.ward_code,
            wo.road_id,
            wo.work_type,
            wo.repair_method,
            wo.contractor_id,
            wo.contractor_name_raw,
            wo.assigned_at,
            wo.work_started_at,
            wo.completed_at,
            wo.area_sqm,
            wo.cost_inr,
            wo.sla_hours,
            wo.sla_met,
            wo.reopened_within_30d,
            wo.engineer_remark,
            (wo.completed_at)::date AS done_date,
            s.station
           FROM (public.work_orders wo
             JOIN public.v_ward_station s USING (ward_code))
        ), rain AS (
         SELECT b_1.work_order_id,
            sum(rf.rainfall_mm) AS rain_next7_mm,
            sum(
                CASE
                    WHEN (rf.imd_category = ANY (ARRAY['Heavy'::text, 'Very heavy'::text, 'Extremely heavy'::text])) THEN 1
                    ELSE 0
                END) AS heavy_days_next7
           FROM (base b_1
             JOIN public.rainfall_daily rf ON (((rf.station = b_1.station) AND (rf.date > b_1.done_date) AND (rf.date <= (b_1.done_date + 7)))))
          GROUP BY b_1.work_order_id
        ), rain_before AS (
         SELECT b_1.work_order_id,
            sum(rf.rainfall_mm) AS rain_during_mm
           FROM (base b_1
             JOIN public.rainfall_daily rf ON (((rf.station = b_1.station) AND (rf.date >= (b_1.work_started_at)::date) AND (rf.date <= b_1.done_date))))
          GROUP BY b_1.work_order_id
        ), tide AS (
         SELECT b_1.work_order_id,
            sum(
                CASE
                    WHEN (t_1.big_tide_flag = true) THEN 1
                    ELSE 0
                END) AS big_tides_next7
           FROM (base b_1
             JOIN public.tides t_1 ON (((t_1.date > b_1.done_date) AND (t_1.date <= (b_1.done_date + 7)))))
          GROUP BY b_1.work_order_id
        )
 SELECT b.work_order_id,
    b.contractor_id,
    ct.contractor_name,
    b.ward_code,
    b.road_id,
    b.work_type,
    b.repair_method,
    b.area_sqm,
    b.cost_inr,
    b.sla_hours,
    b.sla_met,
    b.reopened_within_30d,
    b.done_date,
    EXTRACT(month FROM b.done_date) AS month,
    w.low_lying_index,
    g.road_type,
    g.surface,
    g.lanes,
    g.under_dlp,
    g.bus_route,
    g.hotspot_dist_m,
    (((b.done_date - g.last_resurfaced))::numeric / 365.25) AS road_age_years,
    tr.peak_hour_vehicles,
    tr.congestion_index_0_10,
    tr.two_wheeler_share_pct,
    COALESCE(r.rain_next7_mm, (0)::numeric) AS rain_next7_mm,
    COALESCE(r.heavy_days_next7, (0)::bigint) AS heavy_days_next7,
    COALESCE(rb.rain_during_mm, (0)::numeric) AS rain_during_mm,
    COALESCE(t.big_tides_next7, (0)::bigint) AS big_tides_next7,
    (b.cost_inr / (rc.standard_rate_inr *
        CASE
            WHEN (rc.unit = 'per sqm'::text) THEN b.area_sqm
            ELSE (1)::numeric
        END)) AS cost_vs_rate
   FROM ((((((((base b
     JOIN public.contractors ct ON ((ct.contractor_id = b.contractor_id)))
     JOIN public.wards w USING (ward_code))
     JOIN public.v_road_geo g USING (road_id))
     LEFT JOIN public.traffic tr USING (road_id))
     LEFT JOIN public.rate_card rc USING (repair_method))
     LEFT JOIN rain r ON ((r.work_order_id = b.work_order_id)))
     LEFT JOIN rain_before rb ON ((rb.work_order_id = b.work_order_id)))
     LEFT JOIN tide t ON ((t.work_order_id = b.work_order_id)));


--
-- Name: ward_overview; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.ward_overview WITH (security_invoker='true') AS
 SELECT a.ward_code,
    a.budget_inr,
    a.spend_inr,
    a.recoverable_dlp_inr,
    a.flagged_bills_count,
    a.warranty_enforcement_rate,
    a.dlp_eligible_jobs,
    a.dlp_leakage_rate,
    a.physical_risk_score,
    a.complaints_per_lakh,
    a.under_reported_flag,
    a.flood_hotspots_count,
    a.accidents_count,
    w.ward_name,
    w.zone,
    w.centroid_lat,
    w.centroid_lon
   FROM (public.ward_audit a
     JOIN public.wards w USING (ward_code));


--
-- Name: accidents accidents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accidents
    ADD CONSTRAINT accidents_pkey PRIMARY KEY (accident_id);


--
-- Name: citizen_report_contacts citizen_report_contacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citizen_report_contacts
    ADD CONSTRAINT citizen_report_contacts_pkey PRIMARY KEY (report_id);


--
-- Name: citizen_report_photos citizen_report_photos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citizen_report_photos
    ADD CONSTRAINT citizen_report_photos_pkey PRIMARY KEY (report_id, photo_id);


--
-- Name: citizen_reports citizen_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citizen_reports
    ADD CONSTRAINT citizen_reports_pkey PRIMARY KEY (id);


--
-- Name: complaint_work_orders complaint_work_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.complaint_work_orders
    ADD CONSTRAINT complaint_work_orders_pkey PRIMARY KEY (complaint_id, work_order_id);


--
-- Name: complaints complaints_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT complaints_pkey PRIMARY KEY (complaint_id);


--
-- Name: contractor_monthly_scorecards contractor_monthly_scorecards_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contractor_monthly_scorecards
    ADD CONSTRAINT contractor_monthly_scorecards_pkey PRIMARY KEY (contractor_id, month, methodology_version);


--
-- Name: contractor_scorecard_runs contractor_scorecard_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contractor_scorecard_runs
    ADD CONSTRAINT contractor_scorecard_runs_pkey PRIMARY KEY (methodology_version);


--
-- Name: contractors contractors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contractors
    ADD CONSTRAINT contractors_pkey PRIMARY KEY (contractor_id);


--
-- Name: facilities facilities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facilities
    ADD CONSTRAINT facilities_pkey PRIMARY KEY (facility_id);


--
-- Name: flag_replies flag_replies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.flag_replies
    ADD CONSTRAINT flag_replies_pkey PRIMARY KEY (id);


--
-- Name: flags flags_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.flags
    ADD CONSTRAINT flags_pkey PRIMARY KEY (flag_id);


--
-- Name: flood_hotspots flood_hotspots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.flood_hotspots
    ADD CONSTRAINT flood_hotspots_pkey PRIMARY KEY (hotspot_id);


--
-- Name: localities localities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.localities
    ADD CONSTRAINT localities_pkey PRIMARY KEY (locality);


--
-- Name: locality_aliases locality_aliases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.locality_aliases
    ADD CONSTRAINT locality_aliases_pkey PRIMARY KEY (alias);


--
-- Name: photos photos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.photos
    ADD CONSTRAINT photos_pkey PRIMARY KEY (photo_id);


--
-- Name: rainfall_daily rainfall_daily_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rainfall_daily
    ADD CONSTRAINT rainfall_daily_pkey PRIMARY KEY (date, station);


--
-- Name: rate_card rate_card_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rate_card
    ADD CONSTRAINT rate_card_pkey PRIMARY KEY (repair_method);


--
-- Name: roads roads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roads
    ADD CONSTRAINT roads_pkey PRIMARY KEY (road_id);


--
-- Name: social_posts social_posts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.social_posts
    ADD CONSTRAINT social_posts_pkey PRIMARY KEY (post_id);


--
-- Name: tides tides_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tides
    ADD CONSTRAINT tides_pkey PRIMARY KEY (date, high_tide_time);


--
-- Name: traffic traffic_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traffic
    ADD CONSTRAINT traffic_pkey PRIMARY KEY (road_id);


--
-- Name: v3_contractor_scorecard v3_contractor_scorecard_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.v3_contractor_scorecard
    ADD CONSTRAINT v3_contractor_scorecard_pkey PRIMARY KEY (contractor_id);


--
-- Name: v3_job_expected_risk v3_job_expected_risk_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.v3_job_expected_risk
    ADD CONSTRAINT v3_job_expected_risk_pkey PRIMARY KEY (work_order_id);


--
-- Name: v3_model_meta v3_model_meta_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.v3_model_meta
    ADD CONSTRAINT v3_model_meta_pkey PRIMARY KEY (id);


--
-- Name: v3_next_rupee v3_next_rupee_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.v3_next_rupee
    ADD CONSTRAINT v3_next_rupee_pkey PRIMARY KEY (item_id);


--
-- Name: v3_ward_allocation v3_ward_allocation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.v3_ward_allocation
    ADD CONSTRAINT v3_ward_allocation_pkey PRIMARY KEY (ward_code);


--
-- Name: ward_audit ward_audit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ward_audit
    ADD CONSTRAINT ward_audit_pkey PRIMARY KEY (ward_code);


--
-- Name: wards wards_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wards
    ADD CONSTRAINT wards_pkey PRIMARY KEY (ward_code);


--
-- Name: work_orders work_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_orders
    ADD CONSTRAINT work_orders_pkey PRIMARY KEY (work_order_id);


--
-- Name: contractor_monthly_scorecards_version_month_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX contractor_monthly_scorecards_version_month_idx ON public.contractor_monthly_scorecards USING btree (methodology_version, month);


--
-- Name: accidents accidents_road_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accidents
    ADD CONSTRAINT accidents_road_id_fkey FOREIGN KEY (road_id) REFERENCES public.roads(road_id);


--
-- Name: accidents accidents_ward_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accidents
    ADD CONSTRAINT accidents_ward_code_fkey FOREIGN KEY (ward_code) REFERENCES public.wards(ward_code);


--
-- Name: citizen_report_contacts citizen_report_contacts_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citizen_report_contacts
    ADD CONSTRAINT citizen_report_contacts_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.citizen_reports(id);


--
-- Name: citizen_report_photos citizen_report_photos_photo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citizen_report_photos
    ADD CONSTRAINT citizen_report_photos_photo_id_fkey FOREIGN KEY (photo_id) REFERENCES public.photos(photo_id);


--
-- Name: citizen_report_photos citizen_report_photos_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citizen_report_photos
    ADD CONSTRAINT citizen_report_photos_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.citizen_reports(id);


--
-- Name: citizen_reports citizen_reports_duplicate_of_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citizen_reports
    ADD CONSTRAINT citizen_reports_duplicate_of_fkey FOREIGN KEY (duplicate_of) REFERENCES public.citizen_reports(id);


--
-- Name: citizen_reports citizen_reports_flag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citizen_reports
    ADD CONSTRAINT citizen_reports_flag_id_fkey FOREIGN KEY (flag_id) REFERENCES public.flags(flag_id);


--
-- Name: citizen_reports citizen_reports_linked_work_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citizen_reports
    ADD CONSTRAINT citizen_reports_linked_work_order_id_fkey FOREIGN KEY (linked_work_order_id) REFERENCES public.work_orders(work_order_id);


--
-- Name: citizen_reports citizen_reports_matched_locality_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citizen_reports
    ADD CONSTRAINT citizen_reports_matched_locality_fkey FOREIGN KEY (matched_locality) REFERENCES public.localities(locality);


--
-- Name: citizen_reports citizen_reports_road_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citizen_reports
    ADD CONSTRAINT citizen_reports_road_id_fkey FOREIGN KEY (road_id) REFERENCES public.roads(road_id);


--
-- Name: citizen_reports citizen_reports_work_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.citizen_reports
    ADD CONSTRAINT citizen_reports_work_order_id_fkey FOREIGN KEY (work_order_id) REFERENCES public.work_orders(work_order_id);


--
-- Name: complaint_work_orders complaint_work_orders_complaint_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.complaint_work_orders
    ADD CONSTRAINT complaint_work_orders_complaint_id_fkey FOREIGN KEY (complaint_id) REFERENCES public.complaints(complaint_id);


--
-- Name: complaint_work_orders complaint_work_orders_work_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.complaint_work_orders
    ADD CONSTRAINT complaint_work_orders_work_order_id_fkey FOREIGN KEY (work_order_id) REFERENCES public.work_orders(work_order_id);


--
-- Name: complaints complaints_resolved_ward_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT complaints_resolved_ward_code_fkey FOREIGN KEY (resolved_ward_code) REFERENCES public.wards(ward_code);


--
-- Name: complaints complaints_ward_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.complaints
    ADD CONSTRAINT complaints_ward_code_fkey FOREIGN KEY (ward_code) REFERENCES public.wards(ward_code);


--
-- Name: contractor_monthly_scorecards contractor_monthly_scorecards_contractor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contractor_monthly_scorecards
    ADD CONSTRAINT contractor_monthly_scorecards_contractor_id_fkey FOREIGN KEY (contractor_id) REFERENCES public.contractors(contractor_id);


--
-- Name: contractor_monthly_scorecards contractor_monthly_scorecards_methodology_version_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contractor_monthly_scorecards
    ADD CONSTRAINT contractor_monthly_scorecards_methodology_version_fkey FOREIGN KEY (methodology_version) REFERENCES public.contractor_scorecard_runs(methodology_version) ON DELETE CASCADE;


--
-- Name: facilities facilities_ambulance_entry_road_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facilities
    ADD CONSTRAINT facilities_ambulance_entry_road_fkey FOREIGN KEY (ambulance_entry_road) REFERENCES public.roads(road_id);


--
-- Name: facilities facilities_ward_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.facilities
    ADD CONSTRAINT facilities_ward_code_fkey FOREIGN KEY (ward_code) REFERENCES public.wards(ward_code);


--
-- Name: flag_replies flag_replies_flag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.flag_replies
    ADD CONSTRAINT flag_replies_flag_id_fkey FOREIGN KEY (flag_id) REFERENCES public.flags(flag_id);


--
-- Name: flags flags_contractor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.flags
    ADD CONSTRAINT flags_contractor_id_fkey FOREIGN KEY (contractor_id) REFERENCES public.contractors(contractor_id);


--
-- Name: flags flags_road_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.flags
    ADD CONSTRAINT flags_road_id_fkey FOREIGN KEY (road_id) REFERENCES public.roads(road_id);


--
-- Name: flags flags_ward_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.flags
    ADD CONSTRAINT flags_ward_code_fkey FOREIGN KEY (ward_code) REFERENCES public.wards(ward_code);


--
-- Name: flags flags_work_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.flags
    ADD CONSTRAINT flags_work_order_id_fkey FOREIGN KEY (work_order_id) REFERENCES public.work_orders(work_order_id);


--
-- Name: flood_hotspots flood_hotspots_ward_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.flood_hotspots
    ADD CONSTRAINT flood_hotspots_ward_code_fkey FOREIGN KEY (ward_code) REFERENCES public.wards(ward_code);


--
-- Name: localities localities_ward_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.localities
    ADD CONSTRAINT localities_ward_code_fkey FOREIGN KEY (ward_code) REFERENCES public.wards(ward_code);


--
-- Name: locality_aliases locality_aliases_locality_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.locality_aliases
    ADD CONSTRAINT locality_aliases_locality_fkey FOREIGN KEY (locality) REFERENCES public.localities(locality);


--
-- Name: roads roads_ward_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roads
    ADD CONSTRAINT roads_ward_code_fkey FOREIGN KEY (ward_code) REFERENCES public.wards(ward_code);


--
-- Name: traffic traffic_road_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.traffic
    ADD CONSTRAINT traffic_road_id_fkey FOREIGN KEY (road_id) REFERENCES public.roads(road_id);


--
-- Name: v3_contractor_scorecard v3_contractor_scorecard_contractor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.v3_contractor_scorecard
    ADD CONSTRAINT v3_contractor_scorecard_contractor_id_fkey FOREIGN KEY (contractor_id) REFERENCES public.contractors(contractor_id);


--
-- Name: v3_job_expected_risk v3_job_expected_risk_contractor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.v3_job_expected_risk
    ADD CONSTRAINT v3_job_expected_risk_contractor_id_fkey FOREIGN KEY (contractor_id) REFERENCES public.contractors(contractor_id);


--
-- Name: v3_job_expected_risk v3_job_expected_risk_work_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.v3_job_expected_risk
    ADD CONSTRAINT v3_job_expected_risk_work_order_id_fkey FOREIGN KEY (work_order_id) REFERENCES public.work_orders(work_order_id);


--
-- Name: v3_next_rupee v3_next_rupee_road_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.v3_next_rupee
    ADD CONSTRAINT v3_next_rupee_road_id_fkey FOREIGN KEY (road_id) REFERENCES public.roads(road_id);


--
-- Name: v3_next_rupee v3_next_rupee_ward_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.v3_next_rupee
    ADD CONSTRAINT v3_next_rupee_ward_code_fkey FOREIGN KEY (ward_code) REFERENCES public.wards(ward_code);


--
-- Name: v3_ward_allocation v3_ward_allocation_ward_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.v3_ward_allocation
    ADD CONSTRAINT v3_ward_allocation_ward_code_fkey FOREIGN KEY (ward_code) REFERENCES public.wards(ward_code);


--
-- Name: ward_audit ward_audit_ward_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ward_audit
    ADD CONSTRAINT ward_audit_ward_code_fkey FOREIGN KEY (ward_code) REFERENCES public.wards(ward_code);


--
-- Name: work_orders work_orders_contractor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_orders
    ADD CONSTRAINT work_orders_contractor_id_fkey FOREIGN KEY (contractor_id) REFERENCES public.contractors(contractor_id);


--
-- Name: work_orders work_orders_repair_method_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_orders
    ADD CONSTRAINT work_orders_repair_method_fkey FOREIGN KEY (repair_method) REFERENCES public.rate_card(repair_method);


--
-- Name: work_orders work_orders_road_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_orders
    ADD CONSTRAINT work_orders_road_id_fkey FOREIGN KEY (road_id) REFERENCES public.roads(road_id);


--
-- Name: work_orders work_orders_ward_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.work_orders
    ADD CONSTRAINT work_orders_ward_code_fkey FOREIGN KEY (ward_code) REFERENCES public.wards(ward_code);


--
-- Name: accidents; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.accidents ENABLE ROW LEVEL SECURITY;

--
-- Name: citizen_reports anon insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "anon insert" ON public.citizen_reports FOR INSERT TO authenticated, anon WITH CHECK ((status = 'reported'::text));


--
-- Name: flag_replies anon insert; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "anon insert" ON public.flag_replies FOR INSERT TO authenticated, anon WITH CHECK (true);


--
-- Name: citizen_report_contacts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.citizen_report_contacts ENABLE ROW LEVEL SECURITY;

--
-- Name: citizen_report_photos; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.citizen_report_photos ENABLE ROW LEVEL SECURITY;

--
-- Name: citizen_reports; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.citizen_reports ENABLE ROW LEVEL SECURITY;

--
-- Name: complaint_work_orders; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.complaint_work_orders ENABLE ROW LEVEL SECURITY;

--
-- Name: complaints; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.complaints ENABLE ROW LEVEL SECURITY;

--
-- Name: contractor_monthly_scorecards; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.contractor_monthly_scorecards ENABLE ROW LEVEL SECURITY;

--
-- Name: contractor_scorecard_runs; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.contractor_scorecard_runs ENABLE ROW LEVEL SECURITY;

--
-- Name: contractors; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.contractors ENABLE ROW LEVEL SECURITY;

--
-- Name: facilities; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.facilities ENABLE ROW LEVEL SECURITY;

--
-- Name: flag_replies; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.flag_replies ENABLE ROW LEVEL SECURITY;

--
-- Name: flags; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.flags ENABLE ROW LEVEL SECURITY;

--
-- Name: flood_hotspots; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.flood_hotspots ENABLE ROW LEVEL SECURITY;

--
-- Name: localities; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.localities ENABLE ROW LEVEL SECURITY;

--
-- Name: locality_aliases; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.locality_aliases ENABLE ROW LEVEL SECURITY;

--
-- Name: photos; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.photos ENABLE ROW LEVEL SECURITY;

--
-- Name: accidents public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.accidents FOR SELECT TO authenticated, anon USING (true);


--
-- Name: citizen_report_photos public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.citizen_report_photos FOR SELECT TO authenticated, anon USING (true);


--
-- Name: citizen_reports public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.citizen_reports FOR SELECT TO authenticated, anon USING (true);


--
-- Name: complaint_work_orders public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.complaint_work_orders FOR SELECT TO authenticated, anon USING (true);


--
-- Name: complaints public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.complaints FOR SELECT TO authenticated, anon USING (true);


--
-- Name: contractors public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.contractors FOR SELECT TO authenticated, anon USING (true);


--
-- Name: facilities public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.facilities FOR SELECT TO authenticated, anon USING (true);


--
-- Name: flag_replies public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.flag_replies FOR SELECT TO authenticated, anon USING (true);


--
-- Name: flags public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.flags FOR SELECT TO authenticated, anon USING (true);


--
-- Name: flood_hotspots public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.flood_hotspots FOR SELECT TO authenticated, anon USING (true);


--
-- Name: localities public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.localities FOR SELECT TO authenticated, anon USING (true);


--
-- Name: locality_aliases public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.locality_aliases FOR SELECT TO authenticated, anon USING (true);


--
-- Name: photos public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.photos FOR SELECT TO authenticated, anon USING (true);


--
-- Name: rainfall_daily public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.rainfall_daily FOR SELECT TO authenticated, anon USING (true);


--
-- Name: rate_card public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.rate_card FOR SELECT TO authenticated, anon USING (true);


--
-- Name: roads public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.roads FOR SELECT TO authenticated, anon USING (true);


--
-- Name: social_posts public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.social_posts FOR SELECT TO authenticated, anon USING (true);


--
-- Name: tides public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.tides FOR SELECT TO authenticated, anon USING (true);


--
-- Name: traffic public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.traffic FOR SELECT TO authenticated, anon USING (true);


--
-- Name: v3_contractor_scorecard public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.v3_contractor_scorecard FOR SELECT TO authenticated, anon USING (true);


--
-- Name: v3_job_expected_risk public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.v3_job_expected_risk FOR SELECT TO authenticated, anon USING (true);


--
-- Name: v3_model_meta public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.v3_model_meta FOR SELECT TO authenticated, anon USING (true);


--
-- Name: v3_next_rupee public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.v3_next_rupee FOR SELECT TO authenticated, anon USING (true);


--
-- Name: v3_ward_allocation public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.v3_ward_allocation FOR SELECT TO authenticated, anon USING (true);


--
-- Name: ward_audit public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.ward_audit FOR SELECT TO authenticated, anon USING (true);


--
-- Name: wards public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.wards FOR SELECT TO authenticated, anon USING (true);


--
-- Name: work_orders public read; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "public read" ON public.work_orders FOR SELECT TO authenticated, anon USING (true);


--
-- Name: rainfall_daily; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.rainfall_daily ENABLE ROW LEVEL SECURITY;

--
-- Name: rate_card; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.rate_card ENABLE ROW LEVEL SECURITY;

--
-- Name: roads; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.roads ENABLE ROW LEVEL SECURITY;

--
-- Name: social_posts; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.social_posts ENABLE ROW LEVEL SECURITY;

--
-- Name: tides; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.tides ENABLE ROW LEVEL SECURITY;

--
-- Name: traffic; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.traffic ENABLE ROW LEVEL SECURITY;

--
-- Name: v3_contractor_scorecard; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.v3_contractor_scorecard ENABLE ROW LEVEL SECURITY;

--
-- Name: v3_job_expected_risk; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.v3_job_expected_risk ENABLE ROW LEVEL SECURITY;

--
-- Name: v3_model_meta; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.v3_model_meta ENABLE ROW LEVEL SECURITY;

--
-- Name: v3_next_rupee; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.v3_next_rupee ENABLE ROW LEVEL SECURITY;

--
-- Name: v3_ward_allocation; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.v3_ward_allocation ENABLE ROW LEVEL SECURITY;

--
-- Name: ward_audit; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.ward_audit ENABLE ROW LEVEL SECURITY;

--
-- Name: wards; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.wards ENABLE ROW LEVEL SECURITY;

--
-- Name: work_orders; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.work_orders ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--

\unrestrict schemadump

