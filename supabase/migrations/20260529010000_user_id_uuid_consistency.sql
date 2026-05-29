-- tilt_ui-unt: make every recipes/inventory user_id column native uuid.
--
-- The ORM now models user_id as uuid on Postgres (String(36) on SQLite) so it
-- emits `WHERE user_id = $1::uuid`. Six tables were already uuid; seven were
-- varchar (added ad hoc / by the column-drift reconcile) and would reject a
-- uuid bind. All seven are empty, so the USING cast is a no-op on data.
--
-- uuid is also what Supabase's auth.users and the per-table RLS policies use,
-- so this keeps user_id type-compatible with auth.uid().

ALTER TABLE "public"."equipment"          ALTER COLUMN "user_id" TYPE uuid USING "user_id"::uuid;
ALTER TABLE "public"."gateways"           ALTER COLUMN "user_id" TYPE uuid USING "user_id"::uuid;
ALTER TABLE "public"."hop_inventory"      ALTER COLUMN "user_id" TYPE uuid USING "user_id"::uuid;
ALTER TABLE "public"."yeast_inventory"    ALTER COLUMN "user_id" TYPE uuid USING "user_id"::uuid;
ALTER TABLE "public"."tasting_notes"      ALTER COLUMN "user_id" TYPE uuid USING "user_id"::uuid;
ALTER TABLE "public"."batch_reflections"  ALTER COLUMN "user_id" TYPE uuid USING "user_id"::uuid;
ALTER TABLE "public"."brewing_learnings"  ALTER COLUMN "user_id" TYPE uuid USING "user_id"::uuid;
