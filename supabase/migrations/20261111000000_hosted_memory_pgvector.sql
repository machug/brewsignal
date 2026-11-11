-- tilt_ui-or48: durable, per-user assistant memory on the hosted deployment.
--
-- mem0 (pgvector store) keeps memories in two tables in public: "mem0" (memories) and
-- "mem0_entities" (entity index, also holds memory text fragments). Both have the same shape,
-- created by mem0 itself (create_col): id uuid, vector vector(1536), payload jsonb.
-- There is NO user_id column: mem0 stores it inside the payload as payload->>'user_id'
-- (the Supabase auth user id as text). The backend (direct Postgres, table owner, bypasses RLS)
-- always filters on it; the RLS policies below are a second lock for anyone using the Data API.
--
-- Created here up front so RLS is in place before the first memory is written.
-- Index names match what mem0 would create, so its CREATE ... IF NOT EXISTS is a no-op.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS "public"."mem0" (
    "id" uuid PRIMARY KEY,
    "vector" vector(1536),
    "payload" jsonb
);
CREATE TABLE IF NOT EXISTS "public"."mem0_entities" (
    "id" uuid PRIMARY KEY,
    "vector" vector(1536),
    "payload" jsonb
);

CREATE INDEX IF NOT EXISTS "mem0_hnsw_idx" ON "public"."mem0" USING hnsw ("vector" vector_cosine_ops);
CREATE INDEX IF NOT EXISTS "mem0_text_lemmatized_idx" ON "public"."mem0"
    USING gin (to_tsvector('simple', "payload"->>'text_lemmatized'));
CREATE INDEX IF NOT EXISTS "mem0_entities_hnsw_idx" ON "public"."mem0_entities" USING hnsw ("vector" vector_cosine_ops);
CREATE INDEX IF NOT EXISTS "mem0_entities_text_lemmatized_idx" ON "public"."mem0_entities"
    USING gin (to_tsvector('simple', "payload"->>'text_lemmatized'));
-- per-user lookups (list / delete all) filter on this expression
CREATE INDEX IF NOT EXISTS "mem0_user_id_idx" ON "public"."mem0" (("payload"->>'user_id'));
CREATE INDEX IF NOT EXISTS "mem0_entities_user_id_idx" ON "public"."mem0_entities" (("payload"->>'user_id'));

-- Row Level Security: a signed-in user can read and delete only their own rows.
-- No INSERT/UPDATE for API roles; only the backend writes.
ALTER TABLE "public"."mem0" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."mem0_entities" ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON "public"."mem0", "public"."mem0_entities" FROM "anon", "authenticated";
GRANT SELECT, DELETE ON "public"."mem0", "public"."mem0_entities" TO "authenticated";

DROP POLICY IF EXISTS "mem0_owner_policy" ON "public"."mem0";
CREATE POLICY "mem0_owner_policy" ON "public"."mem0"
    FOR ALL TO "authenticated"
    USING (("payload"->>'user_id') = ("auth"."uid"())::text)
    WITH CHECK (("payload"->>'user_id') = ("auth"."uid"())::text);

DROP POLICY IF EXISTS "mem0_entities_owner_policy" ON "public"."mem0_entities";
CREATE POLICY "mem0_entities_owner_policy" ON "public"."mem0_entities"
    FOR ALL TO "authenticated"
    USING (("payload"->>'user_id') = ("auth"."uid"())::text)
    WITH CHECK (("payload"->>'user_id') = ("auth"."uid"())::text);

-- Account deletion: the backend has no delete-account path (accounts are removed in Supabase
-- Auth), so remove a user's memories when their auth.users row is deleted.
CREATE OR REPLACE FUNCTION "public"."delete_user_memories"() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = ''
AS $$
BEGIN
    DELETE FROM public.mem0 WHERE payload->>'user_id' = OLD.id::text;
    DELETE FROM public.mem0_entities WHERE payload->>'user_id' = OLD.id::text;
    RETURN OLD;
END;
$$;
REVOKE ALL ON FUNCTION "public"."delete_user_memories"() FROM PUBLIC, "anon", "authenticated";

DROP TRIGGER IF EXISTS "delete_user_memories_on_user_delete" ON "auth"."users";
CREATE TRIGGER "delete_user_memories_on_user_delete"
    AFTER DELETE ON "auth"."users"
    FOR EACH ROW EXECUTE FUNCTION "public"."delete_user_memories"();

-- One-time: the old hosted index was a /tmp folder wiped on every deploy, yet learnings were
-- marked as indexed. Clear the marks so the startup backfill re-adds every learning into the
-- durable store. Guarded so re-running after memories exist does not duplicate them.
UPDATE "public"."brewing_learnings" SET "mem0_memory_id" = NULL
WHERE "mem0_memory_id" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "public"."mem0");
