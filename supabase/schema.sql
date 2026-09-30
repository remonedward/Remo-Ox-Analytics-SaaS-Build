-- ============================================================
-- REMO_OX Analytics — Production Supabase Schema
-- All tables have Row Level Security (RLS) enabled.
-- Standard user operations are isolated via auth.uid().
-- Admin operations bypass RLS using the service_role key.
-- ============================================================

-- ---- Extensions ----
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 1. plans
-- ============================================================
CREATE TABLE IF NOT EXISTS plans (
    id                   TEXT PRIMARY KEY,            -- 'trial', 'basic', 'pro'
    name                 TEXT NOT NULL,
    monthly_ai_messages  INTEGER NOT NULL DEFAULT 20,
    max_datasets         INTEGER NOT NULL DEFAULT 1,
    max_file_mb          INTEGER NOT NULL DEFAULT 5,
    monthly_pdf_exports  INTEGER NOT NULL DEFAULT 3,
    is_default           BOOLEAN NOT NULL DEFAULT FALSE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed plans (idempotent)
INSERT INTO plans (id, name, monthly_ai_messages, max_datasets, max_file_mb, monthly_pdf_exports, is_default)
VALUES
    ('trial', 'Trial',   20,   1,  5,  3,  TRUE),
    ('basic', 'Basic',   200,  5,  20, 20, FALSE),
    ('pro',   'Pro',     1000, 20, 50, 100,FALSE)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    monthly_ai_messages = EXCLUDED.monthly_ai_messages,
    max_datasets = EXCLUDED.max_datasets,
    max_file_mb = EXCLUDED.max_file_mb,
    monthly_pdf_exports = EXCLUDED.monthly_pdf_exports;

-- ============================================================
-- 2. profiles (mirrors auth.users; created via trigger on signup)
-- ============================================================
CREATE TABLE IF NOT EXISTS profiles (
    id              UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email           TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user'
                        CHECK (role IN ('user', 'admin')),
    plan_id         TEXT NOT NULL DEFAULT 'trial' REFERENCES plans(id),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    language        TEXT NOT NULL DEFAULT 'ar' CHECK (language IN ('ar', 'en')),
    consent_ai_at   TIMESTAMPTZ,                  -- NULL = not yet consented
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
    INSERT INTO public.profiles (id, email, role, plan_id, language)
    VALUES (
        NEW.id,
        NEW.email,
        'user',
        'trial',
        'ar'
    )
    ON CONFLICT (id) DO NOTHING;
    RETURN NEW;
EXCEPTION
    WHEN OTHERS THEN
        RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- ============================================================
-- 3. datasets
-- ============================================================
CREATE TABLE IF NOT EXISTS datasets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    original_name   TEXT NOT NULL,
    display_name    TEXT,                         -- user-editable rename
    storage_path    TEXT NOT NULL,                -- bucket path: {user_id}/{dataset_id}/{filename}
    file_size_bytes BIGINT,
    sheet_names     JSONB NOT NULL DEFAULT '[]',  -- list of sheet names
    row_counts      JSONB NOT NULL DEFAULT '{}',  -- {sheet: count}
    mapping         JSONB NOT NULL DEFAULT '{}',  -- {role: column_name}
    quality         JSONB NOT NULL DEFAULT '{}',  -- QualityReport snapshot
    dayfirst        BOOLEAN NOT NULL DEFAULT FALSE,
    business_type   TEXT NOT NULL DEFAULT 'products',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ                   -- NULL = never (or now() + interval)
);

CREATE INDEX IF NOT EXISTS idx_datasets_user_id ON datasets(user_id);
CREATE INDEX IF NOT EXISTS idx_datasets_expires_at ON datasets(expires_at)
    WHERE expires_at IS NOT NULL;

-- ============================================================
-- 4. conversations (one active conversation per user + dataset)
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    dataset_id  UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, dataset_id)
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_dataset
    ON conversations(user_id, dataset_id);

-- ============================================================
-- 5. messages
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id  UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role             TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content          TEXT NOT NULL,
    tool_trace       JSONB,                        -- compact tool calls + computed results
    tokens_in        INTEGER,
    tokens_out       INTEGER,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conv_id ON messages(conversation_id);

-- ============================================================
-- 6. usage_events (metering and quota enforcement)
-- ============================================================
CREATE TABLE IF NOT EXISTS usage_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('ai_message', 'pdf_export', 'report_run')),
    tokens_in   INTEGER DEFAULT 0,
    tokens_out  INTEGER DEFAULT 0,
    cost_usd    NUMERIC(12,8) DEFAULT 0,
    model       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_usage_user_kind_created
    ON usage_events(user_id, kind, created_at);

-- ============================================================
-- 7. exports (download history for PDFs and chart PNGs)
-- ============================================================
CREATE TABLE IF NOT EXISTS exports (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    dataset_id    UUID REFERENCES datasets(id) ON DELETE SET NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('pdf', 'chart_png')),
    storage_path  TEXT NOT NULL,
    file_name     TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_exports_user_id ON exports(user_id);

-- ============================================================
-- 8. app_errors (admin-facing error log; no sensitive data)
-- ============================================================
CREATE TABLE IF NOT EXISTS app_errors (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    location    TEXT,                             -- e.g. "analytics/engine.py:120"
    message     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_errors_created ON app_errors(created_at DESC);

-- ============================================================
-- ROW LEVEL SECURITY (RLS) POLICIES
-- ============================================================

-- plans: authenticated users can read plans
ALTER TABLE plans ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS plans_read ON plans;
CREATE POLICY plans_read ON plans
    FOR SELECT USING (auth.role() = 'authenticated');

-- profiles: users can view and update only their own profile
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS profiles_self ON profiles;
CREATE POLICY profiles_self ON profiles
    FOR ALL USING (id = auth.uid());

-- datasets: users own their datasets
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS datasets_owner ON datasets;
CREATE POLICY datasets_owner ON datasets
    FOR ALL USING (user_id = auth.uid());

-- conversations: users own their conversations
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS conversations_owner ON conversations;
CREATE POLICY conversations_owner ON conversations
    FOR ALL USING (user_id = auth.uid());

-- messages: users read and write messages in their own conversations
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS messages_owner ON messages;
CREATE POLICY messages_owner ON messages
    FOR ALL USING (
        conversation_id IN (
            SELECT id FROM conversations WHERE user_id = auth.uid()
        )
    );

-- usage_events: users can inspect their own usage
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS usage_events_owner ON usage_events;
CREATE POLICY usage_events_owner ON usage_events
    FOR ALL USING (user_id = auth.uid());

-- exports: users own their generated exports
ALTER TABLE exports ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS exports_owner ON exports;
CREATE POLICY exports_owner ON exports
    FOR ALL USING (user_id = auth.uid());

-- app_errors: users can INSERT error records, but cannot SELECT
ALTER TABLE app_errors ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS app_errors_no_user_read ON app_errors;
CREATE POLICY app_errors_no_user_read ON app_errors
    FOR SELECT USING (FALSE);          -- Only service_role can select
DROP POLICY IF EXISTS app_errors_insert ON app_errors;
CREATE POLICY app_errors_insert ON app_errors
    FOR INSERT WITH CHECK (TRUE);      -- Authenticated or anon can log an error

-- ============================================================
-- STORAGE BUCKETS AND STORAGE POLICIES
-- Path convention: {user_id}/{dataset_id}/{filename}
-- ============================================================

INSERT INTO storage.buckets (id, name, public)
VALUES
    ('datasets', 'datasets', false),
    ('exports', 'exports', false)
ON CONFLICT (id) DO NOTHING;

-- datasets bucket RLS
DROP POLICY IF EXISTS "datasets_owner_select" ON storage.objects;
CREATE POLICY "datasets_owner_select" ON storage.objects FOR SELECT
    USING (bucket_id = 'datasets' AND (storage.foldername(name))[1] = auth.uid()::TEXT);

DROP POLICY IF EXISTS "datasets_owner_insert" ON storage.objects;
CREATE POLICY "datasets_owner_insert" ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'datasets' AND (storage.foldername(name))[1] = auth.uid()::TEXT);

DROP POLICY IF EXISTS "datasets_owner_delete" ON storage.objects;
CREATE POLICY "datasets_owner_delete" ON storage.objects FOR DELETE
    USING (bucket_id = 'datasets' AND (storage.foldername(name))[1] = auth.uid()::TEXT);

-- exports bucket RLS
DROP POLICY IF EXISTS "exports_owner_select" ON storage.objects;
CREATE POLICY "exports_owner_select" ON storage.objects FOR SELECT
    USING (bucket_id = 'exports' AND (storage.foldername(name))[1] = auth.uid()::TEXT);

DROP POLICY IF EXISTS "exports_owner_insert" ON storage.objects;
CREATE POLICY "exports_owner_insert" ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'exports' AND (storage.foldername(name))[1] = auth.uid()::TEXT);

DROP POLICY IF EXISTS "exports_owner_delete" ON storage.objects;
CREATE POLICY "exports_owner_delete" ON storage.objects FOR DELETE
    USING (bucket_id = 'exports' AND (storage.foldername(name))[1] = auth.uid()::TEXT);
