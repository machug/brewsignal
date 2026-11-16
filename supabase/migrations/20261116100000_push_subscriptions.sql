-- tilt_ui-91a: browser Web Push subscriptions. NOT applied automatically to hosted.
CREATE TABLE IF NOT EXISTS "public"."push_subscriptions" (
    "id" serial PRIMARY KEY,
    "endpoint" text NOT NULL UNIQUE,
    "p256dh" text NOT NULL,
    "auth" text NOT NULL,
    "user_agent" text,
    "created_at" timestamp with time zone
);
ALTER TABLE "public"."push_subscriptions" ENABLE ROW LEVEL SECURITY;
