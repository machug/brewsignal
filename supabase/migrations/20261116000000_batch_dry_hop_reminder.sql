-- tilt_ui-n1w7: dry hop reminder. NOT applied automatically to hosted.
ALTER TABLE "public"."batches" ADD COLUMN IF NOT EXISTS "dry_hop_trigger_sg" double precision;
ALTER TABLE "public"."batches" ADD COLUMN IF NOT EXISTS "dry_hop_done_at" timestamp with time zone;
