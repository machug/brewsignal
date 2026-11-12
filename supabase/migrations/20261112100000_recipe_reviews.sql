-- tilt_ui-de6v: saved AI recipe reviews (score history).
-- NOT applied automatically to hosted.
CREATE TABLE IF NOT EXISTS "public"."recipe_reviews" (
    "id" serial PRIMARY KEY,
    "recipe_id" integer NOT NULL REFERENCES "public"."recipes"("id") ON DELETE CASCADE,
    "user_id" uuid,
    "review" text NOT NULL,
    "score" double precision,
    "stats_score" double precision,
    "compliance" json,
    "style_name" character varying(200),
    "model" character varying(200),
    "fingerprint" character varying(64) NOT NULL,
    "created_at" timestamp with time zone
);
CREATE INDEX IF NOT EXISTS "ix_recipe_reviews_recipe_id" ON "public"."recipe_reviews" ("recipe_id");
CREATE INDEX IF NOT EXISTS "ix_recipe_reviews_user_id" ON "public"."recipe_reviews" ("user_id");
ALTER TABLE "public"."recipe_reviews" ENABLE ROW LEVEL SECURITY;
