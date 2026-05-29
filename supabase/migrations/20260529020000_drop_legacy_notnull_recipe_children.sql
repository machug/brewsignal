-- tilt_ui-nyn: drop NOT NULL on legacy recipe-child columns that the current
-- model no longer sets.
--
-- These columns were renamed in the model (amount_kg -> amount_grams,
-- use -> timing, step_order -> step_number) but the old NOT NULL columns still
-- linger in the Supabase schema. Cloud Sync POSTs the new fields and omits the
-- legacy ones, so every INSERT into these tables failed the NOT NULL check —
-- silently (the child POSTs ignored the response), which is why synced recipes
-- arrived on the cloud with no hop schedule.
--
-- Dropping NOT NULL lets new-schema inserts succeed. The columns are left in
-- place (data, if any, is preserved) but no longer block writes.

ALTER TABLE "public"."recipe_hops"               ALTER COLUMN "amount_kg"  DROP NOT NULL;
ALTER TABLE "public"."recipe_hops"               ALTER COLUMN "use"        DROP NOT NULL;
ALTER TABLE "public"."recipe_mash_steps"         ALTER COLUMN "step_order" DROP NOT NULL;
ALTER TABLE "public"."recipe_fermentation_steps" ALTER COLUMN "step_order" DROP NOT NULL;
ALTER TABLE "public"."recipe_water_adjustments"  ALTER COLUMN "name"       DROP NOT NULL;
