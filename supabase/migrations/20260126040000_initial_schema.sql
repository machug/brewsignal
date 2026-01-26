


SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;


CREATE SCHEMA IF NOT EXISTS "public";


ALTER SCHEMA "public" OWNER TO "pg_database_owner";


COMMENT ON SCHEMA "public" IS 'standard public schema';


SET default_tablespace = '';

SET default_table_access_method = "heap";


CREATE TABLE IF NOT EXISTS "public"."ag_ui_messages" (
    "id" "text" NOT NULL,
    "thread_id" "text" NOT NULL,
    "role" "text" NOT NULL,
    "content" "text",
    "tool_calls" "jsonb",
    "tool_call_id" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."ag_ui_messages" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ag_ui_threads" (
    "id" "text" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "title" "text",
    "title_locked" boolean DEFAULT false,
    "batch_id" integer,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."ag_ui_threads" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."ambient_readings" (
    "id" integer NOT NULL,
    "user_id" "uuid" NOT NULL,
    "timestamp" timestamp with time zone DEFAULT "now"(),
    "temperature" real,
    "humidity" real,
    "entity_id" "text"
);


ALTER TABLE "public"."ambient_readings" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."ambient_readings_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."ambient_readings_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."ambient_readings_id_seq" OWNED BY "public"."ambient_readings"."id";



CREATE TABLE IF NOT EXISTS "public"."batches" (
    "id" integer NOT NULL,
    "user_id" "uuid" NOT NULL,
    "recipe_id" integer,
    "device_id" "text",
    "yeast_strain_id" integer,
    "batch_number" integer,
    "name" "text",
    "status" "text" DEFAULT 'planning'::"text",
    "brew_date" timestamp with time zone,
    "start_time" timestamp with time zone,
    "end_time" timestamp with time zone,
    "brewing_started_at" timestamp with time zone,
    "fermenting_started_at" timestamp with time zone,
    "conditioning_started_at" timestamp with time zone,
    "completed_at" timestamp with time zone,
    "measured_og" real,
    "measured_fg" real,
    "measured_abv" real,
    "measured_attenuation" real,
    "actual_mash_temp" real,
    "actual_mash_ph" real,
    "strike_water_volume" real,
    "pre_boil_gravity" real,
    "pre_boil_volume" real,
    "post_boil_volume" real,
    "actual_efficiency" real,
    "brew_day_notes" "text",
    "packaged_at" timestamp with time zone,
    "packaging_type" "text",
    "packaging_volume" real,
    "carbonation_method" "text",
    "priming_sugar_type" "text",
    "priming_sugar_amount" real,
    "packaging_notes" "text",
    "heater_entity_id" "text",
    "cooler_entity_id" "text",
    "temp_target" real,
    "temp_hysteresis" real,
    "notes" "text",
    "deleted_at" timestamp with time zone,
    "readings_paused" boolean DEFAULT false,
    "timer_phase" "text",
    "timer_started_at" timestamp with time zone,
    "timer_duration_seconds" integer,
    "timer_paused_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."batches" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."batches_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."batches_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."batches_id_seq" OWNED BY "public"."batches"."id";



CREATE TABLE IF NOT EXISTS "public"."calibration_points" (
    "id" integer NOT NULL,
    "device_id" "text" NOT NULL,
    "type" "text" NOT NULL,
    "raw_value" real NOT NULL,
    "actual_value" real NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."calibration_points" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."calibration_points_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."calibration_points_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."calibration_points_id_seq" OWNED BY "public"."calibration_points"."id";



CREATE TABLE IF NOT EXISTS "public"."chamber_readings" (
    "id" integer NOT NULL,
    "user_id" "uuid" NOT NULL,
    "timestamp" timestamp with time zone DEFAULT "now"(),
    "temperature" real,
    "humidity" real,
    "entity_id" "text"
);


ALTER TABLE "public"."chamber_readings" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."chamber_readings_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."chamber_readings_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."chamber_readings_id_seq" OWNED BY "public"."chamber_readings"."id";



CREATE TABLE IF NOT EXISTS "public"."config" (
    "key" "text" NOT NULL,
    "value" "text"
);


ALTER TABLE "public"."config" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."control_events" (
    "id" integer NOT NULL,
    "timestamp" timestamp with time zone DEFAULT "now"(),
    "device_id" "text",
    "batch_id" integer,
    "action" "text",
    "wort_temp" real,
    "ambient_temp" real,
    "target_temp" real
);


ALTER TABLE "public"."control_events" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."control_events_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."control_events_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."control_events_id_seq" OWNED BY "public"."control_events"."id";



CREATE TABLE IF NOT EXISTS "public"."devices" (
    "id" "text" NOT NULL,
    "user_id" "uuid" NOT NULL,
    "device_type" "text" DEFAULT 'tilt'::"text" NOT NULL,
    "name" "text" NOT NULL,
    "display_name" "text",
    "beer_name" "text",
    "original_gravity" real,
    "native_gravity_unit" "text" DEFAULT 'sg'::"text",
    "native_temp_unit" "text" DEFAULT 'c'::"text",
    "calibration_type" "text" DEFAULT 'none'::"text",
    "calibration_data" "text",
    "auth_token" "text",
    "last_seen" timestamp with time zone,
    "battery_voltage" real,
    "firmware_version" "text",
    "color" "text",
    "mac" "text",
    "paired" boolean DEFAULT false,
    "paired_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."devices" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."fermentables" (
    "id" integer NOT NULL,
    "name" "text" NOT NULL,
    "type" "text",
    "origin" "text",
    "maltster" "text",
    "color_srm" real,
    "potential_sg" real,
    "max_in_batch_percent" real,
    "diastatic_power" real,
    "flavor_profile" "text",
    "substitutes" "text",
    "description" "text",
    "source" "text" DEFAULT 'custom'::"text",
    "is_custom" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."fermentables" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."fermentables_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."fermentables_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."fermentables_id_seq" OWNED BY "public"."fermentables"."id";



CREATE TABLE IF NOT EXISTS "public"."fermentation_alerts" (
    "id" integer NOT NULL,
    "batch_id" integer NOT NULL,
    "device_id" "text",
    "alert_type" "text" NOT NULL,
    "severity" "text" DEFAULT 'warning'::"text",
    "message" "text" NOT NULL,
    "context" "text",
    "trigger_reading_id" integer,
    "first_detected_at" timestamp with time zone DEFAULT "now"(),
    "last_seen_at" timestamp with time zone DEFAULT "now"(),
    "cleared_at" timestamp with time zone
);


ALTER TABLE "public"."fermentation_alerts" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."fermentation_alerts_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."fermentation_alerts_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."fermentation_alerts_id_seq" OWNED BY "public"."fermentation_alerts"."id";



CREATE TABLE IF NOT EXISTS "public"."hop_varieties" (
    "id" integer NOT NULL,
    "name" "text" NOT NULL,
    "origin" "text",
    "alpha_acid_low" real,
    "alpha_acid_high" real,
    "beta_acid_low" real,
    "beta_acid_high" real,
    "purpose" "text",
    "aroma_profile" "text",
    "substitutes" "text",
    "description" "text",
    "source" "text" DEFAULT 'custom'::"text",
    "is_custom" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."hop_varieties" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."hop_varieties_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."hop_varieties_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."hop_varieties_id_seq" OWNED BY "public"."hop_varieties"."id";



CREATE TABLE IF NOT EXISTS "public"."readings" (
    "id" integer NOT NULL,
    "device_id" "text",
    "batch_id" integer,
    "device_type" "text" DEFAULT 'tilt'::"text",
    "timestamp" timestamp with time zone DEFAULT "now"(),
    "sg_raw" real,
    "sg_calibrated" real,
    "temp_raw" real,
    "temp_calibrated" real,
    "rssi" integer,
    "battery_voltage" real,
    "battery_percent" integer,
    "angle" real,
    "source_protocol" "text" DEFAULT 'ble'::"text",
    "status" "text" DEFAULT 'valid'::"text",
    "is_pre_filtered" boolean DEFAULT false,
    "sg_filtered" real,
    "temp_filtered" real,
    "confidence" real,
    "sg_rate" real,
    "temp_rate" real,
    "is_anomaly" boolean DEFAULT false,
    "anomaly_score" real,
    "anomaly_reasons" "text"
);


ALTER TABLE "public"."readings" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."readings_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."readings_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."readings_id_seq" OWNED BY "public"."readings"."id";



CREATE TABLE IF NOT EXISTS "public"."recipe_cultures" (
    "id" integer NOT NULL,
    "recipe_id" integer NOT NULL,
    "name" "text" NOT NULL,
    "producer" "text",
    "product_id" "text",
    "type" "text",
    "form" "text",
    "attenuation_min_percent" real,
    "attenuation_max_percent" real,
    "temp_min_c" real,
    "temp_max_c" real,
    "flocculation" "text",
    "amount_l" real,
    "amount_kg" real,
    "cell_count_billions" real,
    "pitch_rate" real,
    "notes" "text",
    "timing_use" "text",
    "timing_time_days" real,
    "timing_duration_days" real,
    "timing_step_index" integer
);


ALTER TABLE "public"."recipe_cultures" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."recipe_cultures_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."recipe_cultures_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."recipe_cultures_id_seq" OWNED BY "public"."recipe_cultures"."id";



CREATE TABLE IF NOT EXISTS "public"."recipe_fermentables" (
    "id" integer NOT NULL,
    "recipe_id" integer NOT NULL,
    "name" "text" NOT NULL,
    "type" "text",
    "amount_kg" real,
    "yield_percent" real,
    "color_lovibond" real,
    "origin" "text",
    "supplier" "text",
    "notes" "text",
    "add_after_boil" boolean DEFAULT false,
    "coarse_fine_diff" real,
    "moisture" real,
    "diastatic_power" real,
    "protein" real,
    "max_in_batch" real,
    "recommend_mash" boolean,
    "timing_use" "text",
    "timing_time_minutes" real,
    "timing_duration_minutes" real,
    "timing_step_index" integer
);


ALTER TABLE "public"."recipe_fermentables" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."recipe_fermentables_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."recipe_fermentables_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."recipe_fermentables_id_seq" OWNED BY "public"."recipe_fermentables"."id";



CREATE TABLE IF NOT EXISTS "public"."recipe_fermentation_steps" (
    "id" integer NOT NULL,
    "recipe_id" integer NOT NULL,
    "step_order" integer NOT NULL,
    "name" "text",
    "step_temp_c" real,
    "step_time_days" real,
    "free_rise" boolean DEFAULT false,
    "notes" "text"
);


ALTER TABLE "public"."recipe_fermentation_steps" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."recipe_fermentation_steps_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."recipe_fermentation_steps_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."recipe_fermentation_steps_id_seq" OWNED BY "public"."recipe_fermentation_steps"."id";



CREATE TABLE IF NOT EXISTS "public"."recipe_hops" (
    "id" integer NOT NULL,
    "recipe_id" integer NOT NULL,
    "name" "text" NOT NULL,
    "alpha_percent" real,
    "amount_kg" real NOT NULL,
    "use" "text" NOT NULL,
    "time_min" real,
    "form" "text",
    "type" "text",
    "origin" "text",
    "substitutes" "text",
    "beta_percent" real,
    "hsi" real,
    "humulene" real,
    "caryophyllene" real,
    "cohumulone" real,
    "myrcene" real,
    "notes" "text",
    "timing_use" "text",
    "timing_time_minutes" real,
    "timing_duration_minutes" real,
    "timing_step_index" integer
);


ALTER TABLE "public"."recipe_hops" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."recipe_hops_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."recipe_hops_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."recipe_hops_id_seq" OWNED BY "public"."recipe_hops"."id";



CREATE TABLE IF NOT EXISTS "public"."recipe_mash_steps" (
    "id" integer NOT NULL,
    "recipe_id" integer NOT NULL,
    "step_order" integer NOT NULL,
    "name" "text" NOT NULL,
    "type" "text",
    "step_temp_c" real,
    "step_time_min" real,
    "ramp_time_min" real,
    "infuse_amount_l" real,
    "decoction_amount_l" real,
    "notes" "text"
);


ALTER TABLE "public"."recipe_mash_steps" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."recipe_mash_steps_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."recipe_mash_steps_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."recipe_mash_steps_id_seq" OWNED BY "public"."recipe_mash_steps"."id";



CREATE TABLE IF NOT EXISTS "public"."recipe_miscs" (
    "id" integer NOT NULL,
    "recipe_id" integer NOT NULL,
    "name" "text" NOT NULL,
    "type" "text" NOT NULL,
    "use" "text" NOT NULL,
    "time_min" real,
    "amount_kg" real,
    "amount_is_weight" boolean DEFAULT true,
    "use_for" "text",
    "notes" "text",
    "timing_use" "text",
    "timing_time_minutes" real,
    "timing_duration_minutes" real,
    "timing_step_index" integer
);


ALTER TABLE "public"."recipe_miscs" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."recipe_miscs_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."recipe_miscs_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."recipe_miscs_id_seq" OWNED BY "public"."recipe_miscs"."id";



CREATE TABLE IF NOT EXISTS "public"."recipe_water_adjustments" (
    "id" integer NOT NULL,
    "recipe_id" integer NOT NULL,
    "name" "text" NOT NULL,
    "type" "text",
    "amount_g" real,
    "notes" "text"
);


ALTER TABLE "public"."recipe_water_adjustments" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."recipe_water_adjustments_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."recipe_water_adjustments_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."recipe_water_adjustments_id_seq" OWNED BY "public"."recipe_water_adjustments"."id";



CREATE TABLE IF NOT EXISTS "public"."recipe_water_profiles" (
    "id" integer NOT NULL,
    "recipe_id" integer NOT NULL,
    "name" "text" NOT NULL,
    "calcium_ppm" real,
    "magnesium_ppm" real,
    "sodium_ppm" real,
    "chloride_ppm" real,
    "sulfate_ppm" real,
    "bicarbonate_ppm" real,
    "ph" real,
    "notes" "text"
);


ALTER TABLE "public"."recipe_water_profiles" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."recipe_water_profiles_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."recipe_water_profiles_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."recipe_water_profiles_id_seq" OWNED BY "public"."recipe_water_profiles"."id";



CREATE TABLE IF NOT EXISTS "public"."recipes" (
    "id" integer NOT NULL,
    "user_id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "type" "text",
    "author" "text",
    "batch_size_liters" real,
    "boil_time_minutes" integer,
    "efficiency_percent" real,
    "og" real,
    "fg" real,
    "abv" real,
    "ibu" real,
    "color_srm" real,
    "carbonation_vols" real,
    "style_id" "text",
    "beerjson_version" "text" DEFAULT '1.0'::"text",
    "format_extensions" "jsonb",
    "yeast_name" "text",
    "yeast_lab" "text",
    "yeast_product_id" "text",
    "yeast_temp_min" real,
    "yeast_temp_max" real,
    "yeast_attenuation" real,
    "brewer" "text",
    "asst_brewer" "text",
    "boil_size_l" real,
    "primary_age_days" integer,
    "primary_temp_c" real,
    "secondary_age_days" integer,
    "secondary_temp_c" real,
    "tertiary_age_days" integer,
    "tertiary_temp_c" real,
    "age_days" integer,
    "age_temp_c" real,
    "forced_carbonation" boolean,
    "priming_sugar_name" "text",
    "priming_sugar_amount_kg" real,
    "taste_notes" "text",
    "taste_rating" real,
    "date" "text",
    "notes" "text",
    "beerxml_content" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."recipes" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."recipes_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."recipes_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."recipes_id_seq" OWNED BY "public"."recipes"."id";



CREATE TABLE IF NOT EXISTS "public"."styles" (
    "id" "text" NOT NULL,
    "guide" "text" NOT NULL,
    "category_number" "text" NOT NULL,
    "style_letter" "text",
    "name" "text" NOT NULL,
    "category" "text" NOT NULL,
    "type" "text",
    "og_min" real,
    "og_max" real,
    "fg_min" real,
    "fg_max" real,
    "ibu_min" real,
    "ibu_max" real,
    "srm_min" real,
    "srm_max" real,
    "abv_min" real,
    "abv_max" real,
    "description" "text",
    "comments" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."styles" OWNER TO "postgres";


CREATE TABLE IF NOT EXISTS "public"."tasting_notes" (
    "id" integer NOT NULL,
    "batch_id" integer NOT NULL,
    "tasted_at" timestamp with time zone DEFAULT "now"(),
    "appearance_score" integer,
    "appearance_notes" "text",
    "aroma_score" integer,
    "aroma_notes" "text",
    "flavor_score" integer,
    "flavor_notes" "text",
    "mouthfeel_score" integer,
    "mouthfeel_notes" "text",
    "overall_score" integer,
    "overall_notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."tasting_notes" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."tasting_notes_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."tasting_notes_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."tasting_notes_id_seq" OWNED BY "public"."tasting_notes"."id";



CREATE TABLE IF NOT EXISTS "public"."yeast_strains" (
    "id" integer NOT NULL,
    "name" "text" NOT NULL,
    "producer" "text",
    "product_id" "text",
    "type" "text",
    "form" "text",
    "attenuation_low" real,
    "attenuation_high" real,
    "temp_low" real,
    "temp_high" real,
    "alcohol_tolerance" "text",
    "flocculation" "text",
    "description" "text",
    "source" "text" DEFAULT 'custom'::"text",
    "is_custom" boolean DEFAULT false,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "updated_at" timestamp with time zone DEFAULT "now"()
);


ALTER TABLE "public"."yeast_strains" OWNER TO "postgres";


CREATE SEQUENCE IF NOT EXISTS "public"."yeast_strains_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE "public"."yeast_strains_id_seq" OWNER TO "postgres";


ALTER SEQUENCE "public"."yeast_strains_id_seq" OWNED BY "public"."yeast_strains"."id";



ALTER TABLE ONLY "public"."ambient_readings" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."ambient_readings_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."batches" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."batches_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."calibration_points" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."calibration_points_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."chamber_readings" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."chamber_readings_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."control_events" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."control_events_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."fermentables" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."fermentables_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."fermentation_alerts" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."fermentation_alerts_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."hop_varieties" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."hop_varieties_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."readings" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."readings_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."recipe_cultures" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."recipe_cultures_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."recipe_fermentables" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."recipe_fermentables_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."recipe_fermentation_steps" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."recipe_fermentation_steps_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."recipe_hops" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."recipe_hops_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."recipe_mash_steps" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."recipe_mash_steps_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."recipe_miscs" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."recipe_miscs_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."recipe_water_adjustments" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."recipe_water_adjustments_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."recipe_water_profiles" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."recipe_water_profiles_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."recipes" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."recipes_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."tasting_notes" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."tasting_notes_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."yeast_strains" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."yeast_strains_id_seq"'::"regclass");



ALTER TABLE ONLY "public"."ag_ui_messages"
    ADD CONSTRAINT "ag_ui_messages_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."ag_ui_threads"
    ADD CONSTRAINT "ag_ui_threads_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."ambient_readings"
    ADD CONSTRAINT "ambient_readings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."batches"
    ADD CONSTRAINT "batches_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."calibration_points"
    ADD CONSTRAINT "calibration_points_device_id_type_raw_value_key" UNIQUE ("device_id", "type", "raw_value");



ALTER TABLE ONLY "public"."calibration_points"
    ADD CONSTRAINT "calibration_points_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."chamber_readings"
    ADD CONSTRAINT "chamber_readings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."config"
    ADD CONSTRAINT "config_pkey" PRIMARY KEY ("key");



ALTER TABLE ONLY "public"."control_events"
    ADD CONSTRAINT "control_events_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."devices"
    ADD CONSTRAINT "devices_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."fermentables"
    ADD CONSTRAINT "fermentables_name_key" UNIQUE ("name");



ALTER TABLE ONLY "public"."fermentables"
    ADD CONSTRAINT "fermentables_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."fermentation_alerts"
    ADD CONSTRAINT "fermentation_alerts_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."hop_varieties"
    ADD CONSTRAINT "hop_varieties_name_key" UNIQUE ("name");



ALTER TABLE ONLY "public"."hop_varieties"
    ADD CONSTRAINT "hop_varieties_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."readings"
    ADD CONSTRAINT "readings_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."recipe_cultures"
    ADD CONSTRAINT "recipe_cultures_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."recipe_fermentables"
    ADD CONSTRAINT "recipe_fermentables_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."recipe_fermentation_steps"
    ADD CONSTRAINT "recipe_fermentation_steps_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."recipe_hops"
    ADD CONSTRAINT "recipe_hops_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."recipe_mash_steps"
    ADD CONSTRAINT "recipe_mash_steps_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."recipe_miscs"
    ADD CONSTRAINT "recipe_miscs_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."recipe_water_adjustments"
    ADD CONSTRAINT "recipe_water_adjustments_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."recipe_water_profiles"
    ADD CONSTRAINT "recipe_water_profiles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."recipes"
    ADD CONSTRAINT "recipes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."styles"
    ADD CONSTRAINT "styles_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."tasting_notes"
    ADD CONSTRAINT "tasting_notes_pkey" PRIMARY KEY ("id");



ALTER TABLE ONLY "public"."yeast_strains"
    ADD CONSTRAINT "yeast_strains_pkey" PRIMARY KEY ("id");



CREATE INDEX "idx_ag_ui_messages_created_at" ON "public"."ag_ui_messages" USING "btree" ("created_at");



CREATE INDEX "idx_ag_ui_messages_thread_id" ON "public"."ag_ui_messages" USING "btree" ("thread_id");



CREATE INDEX "idx_ag_ui_threads_batch_id" ON "public"."ag_ui_threads" USING "btree" ("batch_id");



CREATE INDEX "idx_ag_ui_threads_user_id" ON "public"."ag_ui_threads" USING "btree" ("user_id");



CREATE INDEX "idx_ambient_readings_timestamp" ON "public"."ambient_readings" USING "btree" ("timestamp");



CREATE INDEX "idx_ambient_readings_user_id" ON "public"."ambient_readings" USING "btree" ("user_id");



CREATE INDEX "idx_batches_deleted_at" ON "public"."batches" USING "btree" ("deleted_at");



CREATE INDEX "idx_batches_device_id" ON "public"."batches" USING "btree" ("device_id");



CREATE INDEX "idx_batches_recipe_id" ON "public"."batches" USING "btree" ("recipe_id");



CREATE INDEX "idx_batches_status" ON "public"."batches" USING "btree" ("status");



CREATE INDEX "idx_batches_user_id" ON "public"."batches" USING "btree" ("user_id");



CREATE INDEX "idx_calibration_points_device_id" ON "public"."calibration_points" USING "btree" ("device_id");



CREATE INDEX "idx_chamber_readings_timestamp" ON "public"."chamber_readings" USING "btree" ("timestamp");



CREATE INDEX "idx_chamber_readings_user_id" ON "public"."chamber_readings" USING "btree" ("user_id");



CREATE INDEX "idx_control_events_batch_timestamp" ON "public"."control_events" USING "btree" ("batch_id", "timestamp");



CREATE INDEX "idx_control_events_timestamp" ON "public"."control_events" USING "btree" ("timestamp");



CREATE INDEX "idx_devices_paired" ON "public"."devices" USING "btree" ("paired");



CREATE INDEX "idx_devices_user_id" ON "public"."devices" USING "btree" ("user_id");



CREATE INDEX "idx_fermentables_name" ON "public"."fermentables" USING "btree" ("name");



CREATE INDEX "idx_fermentables_origin" ON "public"."fermentables" USING "btree" ("origin");



CREATE INDEX "idx_fermentables_type" ON "public"."fermentables" USING "btree" ("type");



CREATE INDEX "idx_fermentation_alerts_batch" ON "public"."fermentation_alerts" USING "btree" ("batch_id");



CREATE INDEX "idx_fermentation_alerts_batch_active" ON "public"."fermentation_alerts" USING "btree" ("batch_id", "cleared_at");



CREATE INDEX "idx_fermentation_alerts_type_batch" ON "public"."fermentation_alerts" USING "btree" ("alert_type", "batch_id");



CREATE UNIQUE INDEX "idx_fermenting_device_unique" ON "public"."batches" USING "btree" ("device_id") WHERE (("status" = 'fermenting'::"text") AND ("device_id" IS NOT NULL));



CREATE UNIQUE INDEX "idx_fermenting_heater_unique" ON "public"."batches" USING "btree" ("heater_entity_id") WHERE (("status" = 'fermenting'::"text") AND ("heater_entity_id" IS NOT NULL));



CREATE INDEX "idx_hop_varieties_name" ON "public"."hop_varieties" USING "btree" ("name");



CREATE INDEX "idx_hop_varieties_origin" ON "public"."hop_varieties" USING "btree" ("origin");



CREATE INDEX "idx_hop_varieties_purpose" ON "public"."hop_varieties" USING "btree" ("purpose");



CREATE INDEX "idx_readings_batch_id" ON "public"."readings" USING "btree" ("batch_id");



CREATE INDEX "idx_readings_batch_timestamp" ON "public"."readings" USING "btree" ("batch_id", "timestamp");



CREATE INDEX "idx_readings_device_id" ON "public"."readings" USING "btree" ("device_id");



CREATE INDEX "idx_readings_device_timestamp" ON "public"."readings" USING "btree" ("device_id", "timestamp");



CREATE INDEX "idx_readings_timestamp" ON "public"."readings" USING "btree" ("timestamp");



CREATE INDEX "idx_recipe_cultures_recipe" ON "public"."recipe_cultures" USING "btree" ("recipe_id");



CREATE INDEX "idx_recipe_fermentables_recipe" ON "public"."recipe_fermentables" USING "btree" ("recipe_id");



CREATE INDEX "idx_recipe_fermentation_steps_recipe" ON "public"."recipe_fermentation_steps" USING "btree" ("recipe_id");



CREATE INDEX "idx_recipe_hops_recipe" ON "public"."recipe_hops" USING "btree" ("recipe_id");



CREATE INDEX "idx_recipe_hops_use" ON "public"."recipe_hops" USING "btree" ("use");



CREATE INDEX "idx_recipe_mash_steps_recipe" ON "public"."recipe_mash_steps" USING "btree" ("recipe_id");



CREATE INDEX "idx_recipe_miscs_recipe" ON "public"."recipe_miscs" USING "btree" ("recipe_id");



CREATE INDEX "idx_recipe_water_adjustments_recipe" ON "public"."recipe_water_adjustments" USING "btree" ("recipe_id");



CREATE INDEX "idx_recipe_water_profiles_recipe" ON "public"."recipe_water_profiles" USING "btree" ("recipe_id");



CREATE INDEX "idx_recipes_style_id" ON "public"."recipes" USING "btree" ("style_id");



CREATE INDEX "idx_recipes_user_id" ON "public"."recipes" USING "btree" ("user_id");



CREATE INDEX "idx_tasting_notes_batch" ON "public"."tasting_notes" USING "btree" ("batch_id");



CREATE INDEX "idx_yeast_strains_producer_product" ON "public"."yeast_strains" USING "btree" ("producer", "product_id");



CREATE INDEX "idx_yeast_strains_type" ON "public"."yeast_strains" USING "btree" ("type");



ALTER TABLE ONLY "public"."ag_ui_messages"
    ADD CONSTRAINT "ag_ui_messages_thread_id_fkey" FOREIGN KEY ("thread_id") REFERENCES "public"."ag_ui_threads"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."ag_ui_threads"
    ADD CONSTRAINT "ag_ui_threads_batch_id_fkey" FOREIGN KEY ("batch_id") REFERENCES "public"."batches"("id");



ALTER TABLE ONLY "public"."ag_ui_threads"
    ADD CONSTRAINT "ag_ui_threads_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."ambient_readings"
    ADD CONSTRAINT "ambient_readings_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."batches"
    ADD CONSTRAINT "batches_device_id_fkey" FOREIGN KEY ("device_id") REFERENCES "public"."devices"("id");



ALTER TABLE ONLY "public"."batches"
    ADD CONSTRAINT "batches_recipe_id_fkey" FOREIGN KEY ("recipe_id") REFERENCES "public"."recipes"("id");



ALTER TABLE ONLY "public"."batches"
    ADD CONSTRAINT "batches_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."batches"
    ADD CONSTRAINT "batches_yeast_strain_id_fkey" FOREIGN KEY ("yeast_strain_id") REFERENCES "public"."yeast_strains"("id");



ALTER TABLE ONLY "public"."calibration_points"
    ADD CONSTRAINT "calibration_points_device_id_fkey" FOREIGN KEY ("device_id") REFERENCES "public"."devices"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."chamber_readings"
    ADD CONSTRAINT "chamber_readings_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."control_events"
    ADD CONSTRAINT "control_events_batch_id_fkey" FOREIGN KEY ("batch_id") REFERENCES "public"."batches"("id");



ALTER TABLE ONLY "public"."control_events"
    ADD CONSTRAINT "control_events_device_id_fkey" FOREIGN KEY ("device_id") REFERENCES "public"."devices"("id");



ALTER TABLE ONLY "public"."devices"
    ADD CONSTRAINT "devices_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."fermentation_alerts"
    ADD CONSTRAINT "fermentation_alerts_batch_id_fkey" FOREIGN KEY ("batch_id") REFERENCES "public"."batches"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."fermentation_alerts"
    ADD CONSTRAINT "fermentation_alerts_device_id_fkey" FOREIGN KEY ("device_id") REFERENCES "public"."devices"("id");



ALTER TABLE ONLY "public"."fermentation_alerts"
    ADD CONSTRAINT "fermentation_alerts_trigger_reading_id_fkey" FOREIGN KEY ("trigger_reading_id") REFERENCES "public"."readings"("id");



ALTER TABLE ONLY "public"."readings"
    ADD CONSTRAINT "readings_batch_id_fkey" FOREIGN KEY ("batch_id") REFERENCES "public"."batches"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."readings"
    ADD CONSTRAINT "readings_device_id_fkey" FOREIGN KEY ("device_id") REFERENCES "public"."devices"("id");



ALTER TABLE ONLY "public"."recipe_cultures"
    ADD CONSTRAINT "recipe_cultures_recipe_id_fkey" FOREIGN KEY ("recipe_id") REFERENCES "public"."recipes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."recipe_fermentables"
    ADD CONSTRAINT "recipe_fermentables_recipe_id_fkey" FOREIGN KEY ("recipe_id") REFERENCES "public"."recipes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."recipe_fermentation_steps"
    ADD CONSTRAINT "recipe_fermentation_steps_recipe_id_fkey" FOREIGN KEY ("recipe_id") REFERENCES "public"."recipes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."recipe_hops"
    ADD CONSTRAINT "recipe_hops_recipe_id_fkey" FOREIGN KEY ("recipe_id") REFERENCES "public"."recipes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."recipe_mash_steps"
    ADD CONSTRAINT "recipe_mash_steps_recipe_id_fkey" FOREIGN KEY ("recipe_id") REFERENCES "public"."recipes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."recipe_miscs"
    ADD CONSTRAINT "recipe_miscs_recipe_id_fkey" FOREIGN KEY ("recipe_id") REFERENCES "public"."recipes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."recipe_water_adjustments"
    ADD CONSTRAINT "recipe_water_adjustments_recipe_id_fkey" FOREIGN KEY ("recipe_id") REFERENCES "public"."recipes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."recipe_water_profiles"
    ADD CONSTRAINT "recipe_water_profiles_recipe_id_fkey" FOREIGN KEY ("recipe_id") REFERENCES "public"."recipes"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."recipes"
    ADD CONSTRAINT "recipes_style_id_fkey" FOREIGN KEY ("style_id") REFERENCES "public"."styles"("id");



ALTER TABLE ONLY "public"."recipes"
    ADD CONSTRAINT "recipes_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;



ALTER TABLE ONLY "public"."tasting_notes"
    ADD CONSTRAINT "tasting_notes_batch_id_fkey" FOREIGN KEY ("batch_id") REFERENCES "public"."batches"("id") ON DELETE CASCADE;



ALTER TABLE "public"."ag_ui_messages" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "ag_ui_messages_user_policy" ON "public"."ag_ui_messages" USING (("thread_id" IN ( SELECT "ag_ui_threads"."id"
   FROM "public"."ag_ui_threads"
  WHERE ("ag_ui_threads"."user_id" = "auth"."uid"()))));



ALTER TABLE "public"."ag_ui_threads" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "ag_ui_threads_user_policy" ON "public"."ag_ui_threads" USING (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."ambient_readings" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "ambient_readings_user_policy" ON "public"."ambient_readings" USING (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."batches" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "batches_user_policy" ON "public"."batches" USING (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."calibration_points" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "calibration_points_user_policy" ON "public"."calibration_points" USING (("device_id" IN ( SELECT "devices"."id"
   FROM "public"."devices"
  WHERE ("devices"."user_id" = "auth"."uid"()))));



ALTER TABLE "public"."chamber_readings" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "chamber_readings_user_policy" ON "public"."chamber_readings" USING (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."config" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "config_service_policy" ON "public"."config" USING (false);



ALTER TABLE "public"."control_events" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "control_events_user_policy" ON "public"."control_events" USING ((("batch_id" IN ( SELECT "batches"."id"
   FROM "public"."batches"
  WHERE ("batches"."user_id" = "auth"."uid"()))) OR ("device_id" IN ( SELECT "devices"."id"
   FROM "public"."devices"
  WHERE ("devices"."user_id" = "auth"."uid"())))));



ALTER TABLE "public"."devices" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "devices_user_policy" ON "public"."devices" USING (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."fermentables" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "fermentables_read_policy" ON "public"."fermentables" FOR SELECT USING (true);



ALTER TABLE "public"."fermentation_alerts" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "fermentation_alerts_user_policy" ON "public"."fermentation_alerts" USING (("batch_id" IN ( SELECT "batches"."id"
   FROM "public"."batches"
  WHERE ("batches"."user_id" = "auth"."uid"()))));



ALTER TABLE "public"."hop_varieties" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "hop_varieties_read_policy" ON "public"."hop_varieties" FOR SELECT USING (true);



ALTER TABLE "public"."readings" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "readings_user_policy" ON "public"."readings" USING ((("batch_id" IN ( SELECT "batches"."id"
   FROM "public"."batches"
  WHERE ("batches"."user_id" = "auth"."uid"()))) OR ("device_id" IN ( SELECT "devices"."id"
   FROM "public"."devices"
  WHERE ("devices"."user_id" = "auth"."uid"())))));



ALTER TABLE "public"."recipe_cultures" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "recipe_cultures_user_policy" ON "public"."recipe_cultures" USING (("recipe_id" IN ( SELECT "recipes"."id"
   FROM "public"."recipes"
  WHERE ("recipes"."user_id" = "auth"."uid"()))));



ALTER TABLE "public"."recipe_fermentables" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "recipe_fermentables_user_policy" ON "public"."recipe_fermentables" USING (("recipe_id" IN ( SELECT "recipes"."id"
   FROM "public"."recipes"
  WHERE ("recipes"."user_id" = "auth"."uid"()))));



ALTER TABLE "public"."recipe_fermentation_steps" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "recipe_fermentation_steps_user_policy" ON "public"."recipe_fermentation_steps" USING (("recipe_id" IN ( SELECT "recipes"."id"
   FROM "public"."recipes"
  WHERE ("recipes"."user_id" = "auth"."uid"()))));



ALTER TABLE "public"."recipe_hops" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "recipe_hops_user_policy" ON "public"."recipe_hops" USING (("recipe_id" IN ( SELECT "recipes"."id"
   FROM "public"."recipes"
  WHERE ("recipes"."user_id" = "auth"."uid"()))));



ALTER TABLE "public"."recipe_mash_steps" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "recipe_mash_steps_user_policy" ON "public"."recipe_mash_steps" USING (("recipe_id" IN ( SELECT "recipes"."id"
   FROM "public"."recipes"
  WHERE ("recipes"."user_id" = "auth"."uid"()))));



ALTER TABLE "public"."recipe_miscs" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "recipe_miscs_user_policy" ON "public"."recipe_miscs" USING (("recipe_id" IN ( SELECT "recipes"."id"
   FROM "public"."recipes"
  WHERE ("recipes"."user_id" = "auth"."uid"()))));



ALTER TABLE "public"."recipe_water_adjustments" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "recipe_water_adjustments_user_policy" ON "public"."recipe_water_adjustments" USING (("recipe_id" IN ( SELECT "recipes"."id"
   FROM "public"."recipes"
  WHERE ("recipes"."user_id" = "auth"."uid"()))));



ALTER TABLE "public"."recipe_water_profiles" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "recipe_water_profiles_user_policy" ON "public"."recipe_water_profiles" USING (("recipe_id" IN ( SELECT "recipes"."id"
   FROM "public"."recipes"
  WHERE ("recipes"."user_id" = "auth"."uid"()))));



ALTER TABLE "public"."recipes" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "recipes_user_policy" ON "public"."recipes" USING (("auth"."uid"() = "user_id"));



ALTER TABLE "public"."styles" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "styles_read_policy" ON "public"."styles" FOR SELECT USING (true);



ALTER TABLE "public"."tasting_notes" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "tasting_notes_user_policy" ON "public"."tasting_notes" USING (("batch_id" IN ( SELECT "batches"."id"
   FROM "public"."batches"
  WHERE ("batches"."user_id" = "auth"."uid"()))));



ALTER TABLE "public"."yeast_strains" ENABLE ROW LEVEL SECURITY;


CREATE POLICY "yeast_strains_read_policy" ON "public"."yeast_strains" FOR SELECT USING (true);



GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";



GRANT ALL ON TABLE "public"."ag_ui_messages" TO "anon";
GRANT ALL ON TABLE "public"."ag_ui_messages" TO "authenticated";
GRANT ALL ON TABLE "public"."ag_ui_messages" TO "service_role";



GRANT ALL ON TABLE "public"."ag_ui_threads" TO "anon";
GRANT ALL ON TABLE "public"."ag_ui_threads" TO "authenticated";
GRANT ALL ON TABLE "public"."ag_ui_threads" TO "service_role";



GRANT ALL ON TABLE "public"."ambient_readings" TO "anon";
GRANT ALL ON TABLE "public"."ambient_readings" TO "authenticated";
GRANT ALL ON TABLE "public"."ambient_readings" TO "service_role";



GRANT ALL ON SEQUENCE "public"."ambient_readings_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."ambient_readings_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."ambient_readings_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."batches" TO "anon";
GRANT ALL ON TABLE "public"."batches" TO "authenticated";
GRANT ALL ON TABLE "public"."batches" TO "service_role";



GRANT ALL ON SEQUENCE "public"."batches_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."batches_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."batches_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."calibration_points" TO "anon";
GRANT ALL ON TABLE "public"."calibration_points" TO "authenticated";
GRANT ALL ON TABLE "public"."calibration_points" TO "service_role";



GRANT ALL ON SEQUENCE "public"."calibration_points_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."calibration_points_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."calibration_points_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."chamber_readings" TO "anon";
GRANT ALL ON TABLE "public"."chamber_readings" TO "authenticated";
GRANT ALL ON TABLE "public"."chamber_readings" TO "service_role";



GRANT ALL ON SEQUENCE "public"."chamber_readings_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."chamber_readings_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."chamber_readings_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."config" TO "anon";
GRANT ALL ON TABLE "public"."config" TO "authenticated";
GRANT ALL ON TABLE "public"."config" TO "service_role";



GRANT ALL ON TABLE "public"."control_events" TO "anon";
GRANT ALL ON TABLE "public"."control_events" TO "authenticated";
GRANT ALL ON TABLE "public"."control_events" TO "service_role";



GRANT ALL ON SEQUENCE "public"."control_events_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."control_events_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."control_events_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."devices" TO "anon";
GRANT ALL ON TABLE "public"."devices" TO "authenticated";
GRANT ALL ON TABLE "public"."devices" TO "service_role";



GRANT ALL ON TABLE "public"."fermentables" TO "anon";
GRANT ALL ON TABLE "public"."fermentables" TO "authenticated";
GRANT ALL ON TABLE "public"."fermentables" TO "service_role";



GRANT ALL ON SEQUENCE "public"."fermentables_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."fermentables_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."fermentables_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."fermentation_alerts" TO "anon";
GRANT ALL ON TABLE "public"."fermentation_alerts" TO "authenticated";
GRANT ALL ON TABLE "public"."fermentation_alerts" TO "service_role";



GRANT ALL ON SEQUENCE "public"."fermentation_alerts_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."fermentation_alerts_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."fermentation_alerts_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."hop_varieties" TO "anon";
GRANT ALL ON TABLE "public"."hop_varieties" TO "authenticated";
GRANT ALL ON TABLE "public"."hop_varieties" TO "service_role";



GRANT ALL ON SEQUENCE "public"."hop_varieties_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."hop_varieties_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."hop_varieties_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."readings" TO "anon";
GRANT ALL ON TABLE "public"."readings" TO "authenticated";
GRANT ALL ON TABLE "public"."readings" TO "service_role";



GRANT ALL ON SEQUENCE "public"."readings_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."readings_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."readings_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."recipe_cultures" TO "anon";
GRANT ALL ON TABLE "public"."recipe_cultures" TO "authenticated";
GRANT ALL ON TABLE "public"."recipe_cultures" TO "service_role";



GRANT ALL ON SEQUENCE "public"."recipe_cultures_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."recipe_cultures_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."recipe_cultures_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."recipe_fermentables" TO "anon";
GRANT ALL ON TABLE "public"."recipe_fermentables" TO "authenticated";
GRANT ALL ON TABLE "public"."recipe_fermentables" TO "service_role";



GRANT ALL ON SEQUENCE "public"."recipe_fermentables_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."recipe_fermentables_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."recipe_fermentables_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."recipe_fermentation_steps" TO "anon";
GRANT ALL ON TABLE "public"."recipe_fermentation_steps" TO "authenticated";
GRANT ALL ON TABLE "public"."recipe_fermentation_steps" TO "service_role";



GRANT ALL ON SEQUENCE "public"."recipe_fermentation_steps_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."recipe_fermentation_steps_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."recipe_fermentation_steps_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."recipe_hops" TO "anon";
GRANT ALL ON TABLE "public"."recipe_hops" TO "authenticated";
GRANT ALL ON TABLE "public"."recipe_hops" TO "service_role";



GRANT ALL ON SEQUENCE "public"."recipe_hops_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."recipe_hops_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."recipe_hops_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."recipe_mash_steps" TO "anon";
GRANT ALL ON TABLE "public"."recipe_mash_steps" TO "authenticated";
GRANT ALL ON TABLE "public"."recipe_mash_steps" TO "service_role";



GRANT ALL ON SEQUENCE "public"."recipe_mash_steps_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."recipe_mash_steps_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."recipe_mash_steps_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."recipe_miscs" TO "anon";
GRANT ALL ON TABLE "public"."recipe_miscs" TO "authenticated";
GRANT ALL ON TABLE "public"."recipe_miscs" TO "service_role";



GRANT ALL ON SEQUENCE "public"."recipe_miscs_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."recipe_miscs_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."recipe_miscs_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."recipe_water_adjustments" TO "anon";
GRANT ALL ON TABLE "public"."recipe_water_adjustments" TO "authenticated";
GRANT ALL ON TABLE "public"."recipe_water_adjustments" TO "service_role";



GRANT ALL ON SEQUENCE "public"."recipe_water_adjustments_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."recipe_water_adjustments_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."recipe_water_adjustments_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."recipe_water_profiles" TO "anon";
GRANT ALL ON TABLE "public"."recipe_water_profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."recipe_water_profiles" TO "service_role";



GRANT ALL ON SEQUENCE "public"."recipe_water_profiles_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."recipe_water_profiles_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."recipe_water_profiles_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."recipes" TO "anon";
GRANT ALL ON TABLE "public"."recipes" TO "authenticated";
GRANT ALL ON TABLE "public"."recipes" TO "service_role";



GRANT ALL ON SEQUENCE "public"."recipes_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."recipes_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."recipes_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."styles" TO "anon";
GRANT ALL ON TABLE "public"."styles" TO "authenticated";
GRANT ALL ON TABLE "public"."styles" TO "service_role";



GRANT ALL ON TABLE "public"."tasting_notes" TO "anon";
GRANT ALL ON TABLE "public"."tasting_notes" TO "authenticated";
GRANT ALL ON TABLE "public"."tasting_notes" TO "service_role";



GRANT ALL ON SEQUENCE "public"."tasting_notes_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."tasting_notes_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."tasting_notes_id_seq" TO "service_role";



GRANT ALL ON TABLE "public"."yeast_strains" TO "anon";
GRANT ALL ON TABLE "public"."yeast_strains" TO "authenticated";
GRANT ALL ON TABLE "public"."yeast_strains" TO "service_role";



GRANT ALL ON SEQUENCE "public"."yeast_strains_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."yeast_strains_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."yeast_strains_id_seq" TO "service_role";



ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";






ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";







