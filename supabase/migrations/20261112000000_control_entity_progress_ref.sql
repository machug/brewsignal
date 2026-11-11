-- tilt_ui-xrq5.4: cooler "no progress" reference, persisted so a restart does not reset it.
-- NOT applied automatically to hosted.
ALTER TABLE "public"."control_entity_state" ADD COLUMN IF NOT EXISTS "progress_ref_temp" double precision;
ALTER TABLE "public"."control_entity_state" ADD COLUMN IF NOT EXISTS "progress_ref_at" timestamp with time zone;
ALTER TABLE "public"."control_entity_state" ADD COLUMN IF NOT EXISTS "progress_ref_source" character varying(100);
