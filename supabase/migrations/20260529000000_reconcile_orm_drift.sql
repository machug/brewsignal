-- tilt_ui-xf8: reconcile Postgres schema with ORM models.
-- Supabase migrations were applied by hand and drifted ~1 month behind the
-- models, so full-model SELECTs failed with UndefinedColumnError. These are
-- the additive columns missing from prod at 2026-05-29. All idempotent.
-- The app also self-heals this at boot via _reconcile_postgres_columns()
-- (backend/database.py); this file is the auditable record + parity copy.

ALTER TABLE "public"."equipment" ADD COLUMN IF NOT EXISTS "user_id" VARCHAR(36);
ALTER TABLE "public"."gateways" ADD COLUMN IF NOT EXISTS "token_hash" VARCHAR(64);
ALTER TABLE "public"."gateways" ADD COLUMN IF NOT EXISTS "claimed_at" TIMESTAMP WITH TIME ZONE;
ALTER TABLE "public"."hop_inventory" ADD COLUMN IF NOT EXISTS "user_id" VARCHAR(36);
ALTER TABLE "public"."recipes" ADD COLUMN IF NOT EXISTS "target_og" FLOAT;
ALTER TABLE "public"."recipes" ADD COLUMN IF NOT EXISTS "target_fg" FLOAT;
ALTER TABLE "public"."recipes" ADD COLUMN IF NOT EXISTS "target_abv" FLOAT;
ALTER TABLE "public"."recipes" ADD COLUMN IF NOT EXISTS "target_ibu" FLOAT;
ALTER TABLE "public"."recipes" ADD COLUMN IF NOT EXISTS "target_srm" FLOAT;
ALTER TABLE "public"."recipe_cultures" ADD COLUMN IF NOT EXISTS "amount" FLOAT;
ALTER TABLE "public"."recipe_cultures" ADD COLUMN IF NOT EXISTS "amount_unit" VARCHAR(10);
ALTER TABLE "public"."recipe_cultures" ADD COLUMN IF NOT EXISTS "timing" JSON;
ALTER TABLE "public"."recipe_cultures" ADD COLUMN IF NOT EXISTS "format_extensions" JSON;
ALTER TABLE "public"."recipe_fermentables" ADD COLUMN IF NOT EXISTS "grain_group" VARCHAR(50);
ALTER TABLE "public"."recipe_fermentables" ADD COLUMN IF NOT EXISTS "percentage" FLOAT;
ALTER TABLE "public"."recipe_fermentables" ADD COLUMN IF NOT EXISTS "color_srm" FLOAT;
ALTER TABLE "public"."recipe_fermentables" ADD COLUMN IF NOT EXISTS "timing" JSON;
ALTER TABLE "public"."recipe_fermentables" ADD COLUMN IF NOT EXISTS "format_extensions" JSON;
ALTER TABLE "public"."recipe_fermentation_steps" ADD COLUMN IF NOT EXISTS "step_number" INTEGER;
ALTER TABLE "public"."recipe_fermentation_steps" ADD COLUMN IF NOT EXISTS "type" VARCHAR(20);
ALTER TABLE "public"."recipe_fermentation_steps" ADD COLUMN IF NOT EXISTS "temp_c" FLOAT;
ALTER TABLE "public"."recipe_fermentation_steps" ADD COLUMN IF NOT EXISTS "time_days" INTEGER;
ALTER TABLE "public"."recipe_fermentation_steps" ADD COLUMN IF NOT EXISTS "format_extensions" JSON;
ALTER TABLE "public"."recipe_hops" ADD COLUMN IF NOT EXISTS "alpha_acid_percent" FLOAT;
ALTER TABLE "public"."recipe_hops" ADD COLUMN IF NOT EXISTS "beta_acid_percent" FLOAT;
ALTER TABLE "public"."recipe_hops" ADD COLUMN IF NOT EXISTS "amount_grams" FLOAT;
ALTER TABLE "public"."recipe_hops" ADD COLUMN IF NOT EXISTS "amount_ml" FLOAT;
ALTER TABLE "public"."recipe_hops" ADD COLUMN IF NOT EXISTS "is_extract" BOOLEAN DEFAULT false;
ALTER TABLE "public"."recipe_hops" ADD COLUMN IF NOT EXISTS "timing" JSON;
ALTER TABLE "public"."recipe_hops" ADD COLUMN IF NOT EXISTS "format_extensions" JSON;
ALTER TABLE "public"."recipe_mash_steps" ADD COLUMN IF NOT EXISTS "step_number" INTEGER;
ALTER TABLE "public"."recipe_mash_steps" ADD COLUMN IF NOT EXISTS "temp_c" FLOAT;
ALTER TABLE "public"."recipe_mash_steps" ADD COLUMN IF NOT EXISTS "time_minutes" INTEGER;
ALTER TABLE "public"."recipe_mash_steps" ADD COLUMN IF NOT EXISTS "infusion_amount_liters" FLOAT;
ALTER TABLE "public"."recipe_mash_steps" ADD COLUMN IF NOT EXISTS "infusion_temp_c" FLOAT;
ALTER TABLE "public"."recipe_mash_steps" ADD COLUMN IF NOT EXISTS "ramp_time_minutes" INTEGER;
ALTER TABLE "public"."recipe_mash_steps" ADD COLUMN IF NOT EXISTS "format_extensions" JSON;
ALTER TABLE "public"."recipe_miscs" ADD COLUMN IF NOT EXISTS "amount_unit" VARCHAR(10);
ALTER TABLE "public"."recipe_miscs" ADD COLUMN IF NOT EXISTS "timing" JSON;
ALTER TABLE "public"."recipe_miscs" ADD COLUMN IF NOT EXISTS "format_extensions" JSON;
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "stage" VARCHAR(20);
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "volume_liters" FLOAT;
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "calcium_sulfate_g" FLOAT;
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "calcium_chloride_g" FLOAT;
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "magnesium_sulfate_g" FLOAT;
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "sodium_bicarbonate_g" FLOAT;
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "calcium_carbonate_g" FLOAT;
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "calcium_hydroxide_g" FLOAT;
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "magnesium_chloride_g" FLOAT;
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "sodium_chloride_g" FLOAT;
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "acid_type" VARCHAR(20);
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "acid_ml" FLOAT;
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "acid_concentration_percent" FLOAT;
ALTER TABLE "public"."recipe_water_adjustments" ADD COLUMN IF NOT EXISTS "format_extensions" JSON;
ALTER TABLE "public"."recipe_water_profiles" ADD COLUMN IF NOT EXISTS "profile_type" VARCHAR(20);
ALTER TABLE "public"."recipe_water_profiles" ADD COLUMN IF NOT EXISTS "alkalinity" FLOAT;
ALTER TABLE "public"."recipe_water_profiles" ADD COLUMN IF NOT EXISTS "format_extensions" JSON;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "user_id" VARCHAR(36);
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "days_since_packaging" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "serving_temp_c" FLOAT;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "glassware" VARCHAR(50);
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "total_score" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "to_style" BOOLEAN;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "style_deviation_notes" TEXT;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "ai_suggestions" TEXT;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "interview_transcript" JSON;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "scoring_version" INTEGER DEFAULT 1;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "aroma_malt" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "aroma_hops" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "aroma_fermentation" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "aroma_other" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "appearance_color" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "appearance_clarity" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "appearance_head" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "flavor_malt" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "flavor_hops" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "flavor_bitterness" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "flavor_fermentation" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "flavor_balance" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "flavor_finish" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "mouthfeel_body" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "mouthfeel_carbonation" INTEGER;
ALTER TABLE "public"."tasting_notes" ADD COLUMN IF NOT EXISTS "mouthfeel_warmth" INTEGER;
ALTER TABLE "public"."yeast_inventory" ADD COLUMN IF NOT EXISTS "user_id" VARCHAR(36);

-- Seed target_* from canonical columns so existing recipes keep their
-- brewer-declared values (mirrors 20260425124000_recipe_target_stats.sql).
UPDATE "public"."recipes" SET
    "target_og" = COALESCE("target_og", "og"),
    "target_fg" = COALESCE("target_fg", "fg"),
    "target_abv" = COALESCE("target_abv", "abv"),
    "target_ibu" = COALESCE("target_ibu", "ibu"),
    "target_srm" = COALESCE("target_srm", "color_srm");
