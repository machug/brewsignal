-- Backfill zero-min boil hops as whirlpool/flameout additions.
-- Mirrors backend/migrations/backfill_zero_min_boil_to_whirlpool.py for
-- the cloud schema. Pre-2.13.0 imports of Brewfather Whirlpool hops
-- landed as use=add_to_boil with duration.value=0; the new stand-time
-- IBU model needs add_to_whirlpool to credit them. Heuristic: only
-- retag rows with EXPLICIT duration of 0 — missing duration is
-- ambiguous (legacy First Wort additions imply the recipe boil time).

-- 1. recipe_hops.timing
-- The cloud schema may use the legacy scalar `use` / `time_min` columns
-- OR a newer `timing` jsonb column depending on schema state. Update
-- whichever exists. Wrap in DO blocks so a deployment with neither
-- column (fresh install with no hops) still succeeds.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'recipe_hops'
          AND column_name = 'timing'
    ) THEN
        UPDATE "public"."recipe_hops"
        SET "timing" = jsonb_set("timing"::jsonb, '{use}', '"add_to_whirlpool"')
        WHERE "timing" IS NOT NULL
          AND lower(coalesce("timing"::jsonb->>'use', '')) IN ('add_to_boil', 'boil')
          AND (
            -- missing or null duration: treat as zero
            NOT ("timing"::jsonb ? 'duration')
            OR jsonb_typeof("timing"::jsonb->'duration') = 'null'
            -- duration as object: {value: 0, ...} or no value key
            OR (jsonb_typeof("timing"::jsonb->'duration') = 'object'
                AND (
                    NOT ("timing"::jsonb->'duration' ? 'value')
                    OR ("timing"::jsonb->'duration'->>'value')::numeric = 0
                ))
            -- duration as scalar: 0
            OR (jsonb_typeof("timing"::jsonb->'duration') = 'number'
                AND ("timing"::jsonb->>'duration')::numeric = 0)
          );
    END IF;
END $$;

-- Legacy scalar shape: use + time_min columns. Same explicit-zero gate.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'recipe_hops'
          AND column_name = 'time_min'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'recipe_hops'
          AND column_name = 'use'
    ) THEN
        UPDATE "public"."recipe_hops"
        SET "use" = 'add_to_whirlpool'
        WHERE lower(coalesce("use", '')) IN ('add_to_boil', 'boil')
          AND ("time_min" IS NULL OR "time_min" = 0);
    END IF;
END $$;

-- 2. recipes.format_extensions.hops[*].use
-- Postgres jsonb path mutation requires walking the array. Build a new
-- hops array with the offending entries' use rewritten, then write it
-- back. A subquery+jsonb_agg approach is simplest and readable.
UPDATE "public"."recipes" r
SET "format_extensions" = jsonb_set(
    "format_extensions"::jsonb,
    '{hops}',
    (
        SELECT jsonb_agg(
            CASE
                WHEN lower(coalesce(hop->>'use', '')) IN ('add_to_boil', 'boil')
                     AND (
                         NOT (hop ? 'boil_time_minutes')
                         OR jsonb_typeof(hop->'boil_time_minutes') = 'null'
                         OR (hop->>'boil_time_minutes')::numeric = 0
                     )
                THEN jsonb_set(hop, '{use}', '"add_to_whirlpool"')
                ELSE hop
            END
            ORDER BY ord
        )
        FROM jsonb_array_elements(r."format_extensions"::jsonb->'hops')
            WITH ORDINALITY AS arr(hop, ord)
    )
)
WHERE "format_extensions" IS NOT NULL
  AND jsonb_typeof("format_extensions"::jsonb->'hops') = 'array'
  AND EXISTS (
      SELECT 1
      FROM jsonb_array_elements(r."format_extensions"::jsonb->'hops') AS hop
      WHERE lower(coalesce(hop->>'use', '')) IN ('add_to_boil', 'boil')
        AND (
            NOT (hop ? 'boil_time_minutes')
            OR jsonb_typeof(hop->'boil_time_minutes') = 'null'
            OR (hop->>'boil_time_minutes')::numeric = 0
        )
  );
