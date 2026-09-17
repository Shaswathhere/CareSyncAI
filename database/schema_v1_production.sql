-- =============================================================================
-- CareSync AI — Production Schema v1.0.0  (FROZEN)
-- =============================================================================
-- This file is the canonical, frozen production schema for Sprint 2 MVP.
-- It represents the state of the database at the end of the development sprint.
--
-- DO NOT MODIFY THIS FILE after production deployment.
-- All future changes must be made via versioned migration files in:
--   database/migrations/
--
-- To apply this schema to a fresh Supabase project:
--   1. Open your Supabase project → SQL Editor
--   2. Paste and run this entire file
--   3. Run scripts/verify_migration.py to confirm all objects exist
--
-- Schema version : 1.0.0
-- Frozen on      : 2026-09-11
-- Tables         : 10
-- Indexes        : 20+
-- Functions/RPCs : 12
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Extensions
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;


-- -----------------------------------------------------------------------------
-- Enum Types
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'document_status') THEN
        CREATE TYPE document_status AS ENUM ('ACTIVE', 'SUPERSEDED', 'ARCHIVED');
    END IF;
END
$$;


-- =============================================================================
-- CORE KNOWLEDGE BASE TABLES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. documents
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id               UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    title            TEXT            NOT NULL,
    version          TEXT            NOT NULL DEFAULT 'v1',
    publication_date DATE,
    effective_date   DATE,
    status           document_status NOT NULL DEFAULT 'ACTIVE',
    language         TEXT            NOT NULL DEFAULT 'en',
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS documents_language_idx        ON documents (language);
CREATE INDEX IF NOT EXISTS documents_status_idx          ON documents (status);
CREATE INDEX IF NOT EXISTS documents_effective_date_idx  ON documents (effective_date DESC);


-- -----------------------------------------------------------------------------
-- 2. document_chunks
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_chunks (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT         NOT NULL,
    page_number INT         NOT NULL,
    content     TEXT        NOT NULL,
    embedding   VECTOR(384),
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Full-text search column (generated, stored)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'document_chunks' AND column_name = 'content_tsv'
    ) THEN
        ALTER TABLE document_chunks
            ADD COLUMN content_tsv TSVECTOR
                GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
    END IF;
END
$$;

-- Vector similarity index (HNSW — production tuned)
CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw_idx
    ON document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS document_chunks_document_id_idx   ON document_chunks (document_id);
CREATE INDEX IF NOT EXISTS document_chunks_content_tsv_idx   ON document_chunks USING gin (content_tsv);



-- =============================================================================
-- USER & LOCALE TABLES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 3. user_locale_preferences
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS user_locale_preferences (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        TEXT        NOT NULL UNIQUE,
    preferred_lang TEXT        NOT NULL DEFAULT 'en',
    fallback_lang  TEXT        NOT NULL DEFAULT 'en',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS user_locale_prefs_user_id_idx ON user_locale_preferences (user_id);

DROP TRIGGER IF EXISTS user_locale_prefs_updated_at ON user_locale_preferences;
CREATE TRIGGER user_locale_prefs_updated_at
    BEFORE UPDATE ON user_locale_preferences
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- =============================================================================
-- CONVERSATION TABLES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 4. chat_sessions
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_sessions (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    TEXT        NOT NULL,
    title      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_sessions_user_id_idx ON chat_sessions (user_id, updated_at DESC);

DROP TRIGGER IF EXISTS chat_sessions_updated_at ON chat_sessions;
CREATE TRIGGER chat_sessions_updated_at
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- -----------------------------------------------------------------------------
-- 5. chat_messages
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_messages (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID        NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role       TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT        NOT NULL,
    citations  JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_messages_session_id_idx ON chat_messages (session_id, created_at ASC);


-- =============================================================================
-- AUDIO TABLES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 6. audio_query_log
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audio_query_log (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           TEXT        NOT NULL,
    session_id        UUID        REFERENCES chat_sessions(id) ON DELETE SET NULL,
    audio_file_ref    TEXT,
    audio_duration_ms INT,
    transcription     TEXT,
    language          TEXT        NOT NULL DEFAULT 'en',
    transcription_ms  INT,
    status            TEXT        NOT NULL DEFAULT 'pending'
                          CHECK (status IN ('pending', 'processing', 'success', 'failed')),
    error_message     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audio_query_log_user_id_idx  ON audio_query_log (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS audio_query_log_session_id_idx ON audio_query_log (session_id) WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS audio_query_log_status_idx   ON audio_query_log (status, created_at DESC);


-- -----------------------------------------------------------------------------
-- 7. transcription_audit
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transcription_audit (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    audio_query_id   UUID        NOT NULL REFERENCES audio_query_log(id) ON DELETE CASCADE,
    stt_engine       TEXT        NOT NULL,
    raw_transcript   TEXT        NOT NULL,
    confidence_score FLOAT,
    word_timestamps  JSONB,
    engine_response  JSONB,
    post_processed   TEXT,
    reviewed_by      TEXT,
    reviewed_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS transcription_audit_audio_query_id_idx ON transcription_audit (audio_query_id);
CREATE INDEX IF NOT EXISTS transcription_audit_stt_engine_idx     ON transcription_audit (stt_engine, created_at DESC);
CREATE INDEX IF NOT EXISTS transcription_audit_unreviewed_idx     ON transcription_audit (reviewed_at) WHERE reviewed_at IS NULL;


-- =============================================================================
-- FEEDBACK & METRICS TABLES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 8. chat_feedback
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_feedback (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID        REFERENCES chat_messages(id) ON DELETE SET NULL,
    session_id UUID        REFERENCES chat_sessions(id) ON DELETE SET NULL,
    user_id    TEXT        NOT NULL,
    vote       TEXT        NOT NULL CHECK (vote IN ('upvote', 'downvote')),
    comment    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_feedback_message_id_idx ON chat_feedback (message_id) WHERE message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS chat_feedback_user_id_idx    ON chat_feedback (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS chat_feedback_vote_idx       ON chat_feedback (vote, created_at DESC);


-- -----------------------------------------------------------------------------
-- 9. system_metrics
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_metrics (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id     UUID        REFERENCES chat_sessions(id) ON DELETE SET NULL,
    message_id     UUID        REFERENCES chat_messages(id) ON DELETE SET NULL,
    user_id        TEXT        NOT NULL,
    query_text     TEXT,
    embedding_ms   FLOAT,
    retrieval_ms   FLOAT,
    rerank_ms      FLOAT,
    llm_ms         FLOAT,
    total_ms       FLOAT       NOT NULL,
    chunk_count    INT,
    model_name     TEXT,
    status         TEXT        NOT NULL DEFAULT 'success'
                       CHECK (status IN ('success', 'failed', 'timeout')),
    error_message  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS system_metrics_user_id_idx    ON system_metrics (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS system_metrics_session_id_idx ON system_metrics (session_id) WHERE session_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS system_metrics_total_ms_idx   ON system_metrics (total_ms DESC);
CREATE INDEX IF NOT EXISTS system_metrics_status_idx     ON system_metrics (status, created_at DESC);


-- -----------------------------------------------------------------------------
-- 10. query_performance_log
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS query_performance_log (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    operation    TEXT        NOT NULL,
    latency_ms   FLOAT       NOT NULL,
    result_count INT         NOT NULL DEFAULT 0,
    params       JSONB,
    success      BOOLEAN     NOT NULL DEFAULT TRUE,
    error        TEXT,
    logged_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS query_perf_log_latency_idx   ON query_performance_log (latency_ms DESC);
CREATE INDEX IF NOT EXISTS query_perf_log_operation_idx ON query_performance_log (operation, logged_at DESC);


-- =============================================================================
-- RPC FUNCTIONS
-- =============================================================================

-- Hybrid retrieval (vector + full-text + date/status filters)
CREATE OR REPLACE FUNCTION match_document_chunks(
    query_embedding  VECTOR(384),
    match_count      INT             DEFAULT 5,
    filter_status    document_status DEFAULT 'ACTIVE',
    keyword          TEXT            DEFAULT NULL,
    date_from        DATE            DEFAULT NULL,
    date_to          DATE            DEFAULT NULL
)
RETURNS TABLE (
    chunk_id UUID, document_id UUID, title TEXT, version TEXT,
    effective_date DATE, status document_status, chunk_index INT,
    page_number INT, content TEXT, metadata JSONB,
    vector_similarity FLOAT, text_rank FLOAT, combined_score FLOAT
)
LANGUAGE plpgsql STABLE AS $$
DECLARE tsq TSQUERY;
BEGIN
    IF keyword IS NOT NULL AND trim(keyword) <> '' THEN
        tsq := plainto_tsquery('english', keyword);
    ELSE tsq := NULL; END IF;
    RETURN QUERY
    SELECT dc.id, dc.document_id, d.title, d.version, d.effective_date, d.status,
           dc.chunk_index, dc.page_number, dc.content, dc.metadata,
           (1-(dc.embedding<=>query_embedding))::FLOAT,
           CASE WHEN tsq IS NOT NULL THEN ts_rank(dc.content_tsv,tsq)::FLOAT ELSE 0.0::FLOAT END,
           (1-(dc.embedding<=>query_embedding)+CASE WHEN tsq IS NOT NULL THEN ts_rank(dc.content_tsv,tsq) ELSE 0.0 END)::FLOAT
    FROM document_chunks dc JOIN documents d ON d.id=dc.document_id
    WHERE d.status=filter_status
      AND (tsq IS NULL OR dc.content_tsv@@tsq)
      AND (date_from IS NULL OR d.effective_date>=date_from)
      AND (date_to IS NULL OR d.effective_date<=date_to)
    ORDER BY 13 DESC LIMIT match_count;
END; $$;

-- Bulk chunk fetch by document IDs
CREATE OR REPLACE FUNCTION bulk_fetch_chunks_by_documents(doc_ids UUID[])
RETURNS TABLE (chunk_id UUID, document_id UUID, title TEXT, version TEXT,
    effective_date DATE, status document_status, chunk_index INT,
    page_number INT, content TEXT, metadata JSONB, created_at TIMESTAMPTZ)
LANGUAGE sql STABLE AS $$
    SELECT dc.id,dc.document_id,d.title,d.version,d.effective_date,d.status,
           dc.chunk_index,dc.page_number,dc.content,dc.metadata,dc.created_at
    FROM document_chunks dc JOIN documents d ON d.id=dc.document_id
    WHERE dc.document_id=ANY(doc_ids) ORDER BY dc.document_id,dc.chunk_index; $$;

-- Feedback logging RPC
CREATE OR REPLACE FUNCTION log_chat_feedback(
    p_user_id TEXT, p_vote TEXT,
    p_message_id UUID DEFAULT NULL, p_session_id UUID DEFAULT NULL, p_comment TEXT DEFAULT NULL)
RETURNS SETOF chat_feedback LANGUAGE plpgsql AS $$
BEGIN
    IF p_vote NOT IN ('upvote','downvote') THEN
        RAISE EXCEPTION 'Invalid vote: %', p_vote; END IF;
    RETURN QUERY INSERT INTO chat_feedback(user_id,vote,message_id,session_id,comment)
    VALUES(p_user_id,p_vote,p_message_id,p_session_id,p_comment) RETURNING *;
END; $$;

-- Feedback summary RPC
CREATE OR REPLACE FUNCTION get_feedback_summary(p_message_id UUID)
RETURNS TABLE(message_id UUID, upvotes BIGINT, downvotes BIGINT, total BIGINT)
LANGUAGE sql STABLE AS $$
    SELECT p_message_id,
           COUNT(*) FILTER(WHERE vote='upvote'),
           COUNT(*) FILTER(WHERE vote='downvote'),
           COUNT(*) FROM chat_feedback WHERE message_id=p_message_id; $$;

-- System metrics logging RPC
CREATE OR REPLACE FUNCTION log_system_metrics(
    p_user_id TEXT, p_total_ms FLOAT,
    p_session_id UUID DEFAULT NULL, p_message_id UUID DEFAULT NULL,
    p_query_text TEXT DEFAULT NULL, p_embedding_ms FLOAT DEFAULT NULL,
    p_retrieval_ms FLOAT DEFAULT NULL, p_rerank_ms FLOAT DEFAULT NULL,
    p_llm_ms FLOAT DEFAULT NULL, p_chunk_count INT DEFAULT NULL,
    p_model_name TEXT DEFAULT NULL, p_status TEXT DEFAULT 'success',
    p_error_message TEXT DEFAULT NULL)
RETURNS SETOF system_metrics LANGUAGE plpgsql AS $$
BEGIN
    IF p_status NOT IN ('success','failed','timeout') THEN
        RAISE EXCEPTION 'Invalid status: %', p_status; END IF;
    RETURN QUERY INSERT INTO system_metrics(
        user_id,total_ms,session_id,message_id,query_text,embedding_ms,
        retrieval_ms,rerank_ms,llm_ms,chunk_count,model_name,status,error_message)
    VALUES(p_user_id,p_total_ms,p_session_id,p_message_id,p_query_text,p_embedding_ms,
           p_retrieval_ms,p_rerank_ms,p_llm_ms,p_chunk_count,p_model_name,p_status,p_error_message)
    RETURNING *;
END; $$;

-- Latency summary RPC
CREATE OR REPLACE FUNCTION get_latency_summary(since_ts TIMESTAMPTZ DEFAULT (now()-INTERVAL '24 hours'))
RETURNS TABLE(avg_total_ms FLOAT, p95_total_ms FLOAT, max_total_ms FLOAT,
    avg_embedding_ms FLOAT, avg_retrieval_ms FLOAT, avg_llm_ms FLOAT,
    total_queries BIGINT, failed_queries BIGINT)
LANGUAGE sql STABLE AS $$
    SELECT AVG(total_ms)::FLOAT,
           PERCENTILE_CONT(0.95) WITHIN GROUP(ORDER BY total_ms)::FLOAT,
           MAX(total_ms)::FLOAT, AVG(embedding_ms)::FLOAT,
           AVG(retrieval_ms)::FLOAT, AVG(llm_ms)::FLOAT,
           COUNT(*), COUNT(*) FILTER(WHERE status!='success')
    FROM system_metrics WHERE created_at>=since_ts; $$;

-- Analytics RPCs
CREATE OR REPLACE FUNCTION get_daily_active_users(since_ts TIMESTAMPTZ DEFAULT (now()-INTERVAL '30 days'))
RETURNS TABLE(day DATE, active_users BIGINT) LANGUAGE sql STABLE AS $$
    SELECT DATE(cm.created_at AT TIME ZONE 'UTC'), COUNT(DISTINCT cs.user_id)
    FROM chat_messages cm JOIN chat_sessions cs ON cs.id=cm.session_id
    WHERE cm.created_at>=since_ts AND cm.role='user'
    GROUP BY 1 ORDER BY 1; $$;

CREATE OR REPLACE FUNCTION get_total_queries_over_time(
    since_ts TIMESTAMPTZ DEFAULT (now()-INTERVAL '30 days'), bucket_size TEXT DEFAULT 'day')
RETURNS TABLE(bucket TIMESTAMPTZ, total_queries BIGINT) LANGUAGE plpgsql STABLE AS $$
BEGIN
    IF bucket_size NOT IN ('hour','day','week') THEN
        RAISE EXCEPTION 'Invalid bucket_size: %', bucket_size; END IF;
    RETURN QUERY SELECT DATE_TRUNC(bucket_size,cm.created_at), COUNT(*)
    FROM chat_messages cm WHERE cm.created_at>=since_ts AND cm.role='user'
    GROUP BY 1 ORDER BY 1;
END; $$;

CREATE OR REPLACE FUNCTION get_top_queried_topics(
    since_ts TIMESTAMPTZ DEFAULT (now()-INTERVAL '30 days'), top_n INT DEFAULT 20)
RETURNS TABLE(term TEXT, frequency BIGINT) LANGUAGE sql STABLE AS $$
    SELECT word, COUNT(*) FROM (
        SELECT unnest(tsvector_to_array(to_tsvector('english',cm.content))) AS word
        FROM chat_messages cm
        WHERE cm.created_at>=since_ts AND cm.role='user' AND LENGTH(cm.content)>0
    ) l WHERE LENGTH(word)>3
    GROUP BY word ORDER BY COUNT(*) DESC LIMIT top_n; $$;

CREATE OR REPLACE FUNCTION get_feedback_satisfaction_rate(since_ts TIMESTAMPTZ DEFAULT (now()-INTERVAL '30 days'))
RETURNS TABLE(upvotes BIGINT, downvotes BIGINT, total_votes BIGINT, satisfaction_rate FLOAT)
LANGUAGE sql STABLE AS $$
    SELECT COUNT(*) FILTER(WHERE vote='upvote'),
           COUNT(*) FILTER(WHERE vote='downvote'), COUNT(*),
           CASE WHEN COUNT(*)=0 THEN NULL
                ELSE ROUND(COUNT(*) FILTER(WHERE vote='upvote')::NUMERIC/COUNT(*)::NUMERIC*100,2)::FLOAT
           END FROM chat_feedback WHERE created_at>=since_ts; $$;

CREATE OR REPLACE FUNCTION get_system_health_metrics(since_ts TIMESTAMPTZ DEFAULT (now()-INTERVAL '24 hours'))
RETURNS TABLE(total_queries BIGINT, success_count BIGINT, failed_count BIGINT,
    timeout_count BIGINT, fallback_count BIGINT,
    error_rate_pct FLOAT, timeout_rate_pct FLOAT,
    avg_total_ms FLOAT, p95_total_ms FLOAT, max_total_ms FLOAT,
    avg_embedding_ms FLOAT, avg_retrieval_ms FLOAT, avg_llm_ms FLOAT)
LANGUAGE sql STABLE AS $$
    SELECT COUNT(*), COUNT(*) FILTER(WHERE status='success'),
           COUNT(*) FILTER(WHERE status='failed'),
           COUNT(*) FILTER(WHERE status='timeout'),
           COUNT(*) FILTER(WHERE status!='success' OR (error_message IS NOT NULL AND lower(error_message) LIKE '%fallback%')),
           CASE WHEN COUNT(*)=0 THEN 0 ELSE ROUND(COUNT(*) FILTER(WHERE status='failed')::NUMERIC/COUNT(*)::NUMERIC*100,2)::FLOAT END,
           CASE WHEN COUNT(*)=0 THEN 0 ELSE ROUND(COUNT(*) FILTER(WHERE status='timeout')::NUMERIC/COUNT(*)::NUMERIC*100,2)::FLOAT END,
           AVG(total_ms)::FLOAT,
           PERCENTILE_CONT(0.95) WITHIN GROUP(ORDER BY total_ms)::FLOAT,
           MAX(total_ms)::FLOAT, AVG(embedding_ms)::FLOAT,
           AVG(retrieval_ms)::FLOAT, AVG(llm_ms)::FLOAT
    FROM system_metrics WHERE created_at>=since_ts; $$;


-- =============================================================================
-- SCHEMA VERSION MARKER
-- =============================================================================
-- Insert a version record into query_performance_log to mark this deployment.
INSERT INTO query_performance_log (operation, latency_ms, result_count, params)
VALUES (
    'schema_migration',
    0,
    0,
    '{"version": "1.0.0", "tables": 10, "frozen_at": "2026-09-11", "sprint": "Sprint 2 MVP"}'::jsonb
)
ON CONFLICT DO NOTHING;
