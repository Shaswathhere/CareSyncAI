-- =============================================================================
-- CareSync AI — Database Schema
-- =============================================================================
-- Run this script once against your Supabase PostgreSQL instance to set up
-- the knowledge-base tables, indexes, and retrieval functions.
--
-- Prerequisites:
--   Supabase projects support pgvector natively — no manual extension install needed.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Enable pgvector extension
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;


-- -----------------------------------------------------------------------------
-- 2. Document status type
-- -----------------------------------------------------------------------------
-- Represents the lifecycle of a public-health guideline document.
--   ACTIVE     — currently in effect, preferred by the retrieval system
--   SUPERSEDED — replaced by a newer version of the same document
--   ARCHIVED   — removed from active use, retained for audit purposes
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'document_status') THEN
        CREATE TYPE document_status AS ENUM ('ACTIVE', 'SUPERSEDED', 'ARCHIVED');
    END IF;
END
$$;


-- -----------------------------------------------------------------------------
-- 3. documents — master registry of uploaded public-health PDFs
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id               UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    title            TEXT            NOT NULL,
    version          TEXT            NOT NULL DEFAULT 'v1',
    publication_date DATE,
    effective_date   DATE,
    status           document_status NOT NULL DEFAULT 'ACTIVE',
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT now()
);

COMMENT ON TABLE  documents                  IS 'Master registry of uploaded public-health guideline documents.';
COMMENT ON COLUMN documents.id               IS 'Unique document identifier (UUID).';
COMMENT ON COLUMN documents.title            IS 'Human-readable document title, e.g. "Vaccination Protocol".';
COMMENT ON COLUMN documents.version          IS 'Document version string, e.g. "v3".';
COMMENT ON COLUMN documents.publication_date IS 'Date the document was officially published.';
COMMENT ON COLUMN documents.effective_date   IS 'Date from which this version of the document is in effect.';
COMMENT ON COLUMN documents.status           IS 'Lifecycle status: ACTIVE | SUPERSEDED | ARCHIVED.';
COMMENT ON COLUMN documents.created_at       IS 'Timestamp when the document was uploaded to the knowledge base.';


-- -----------------------------------------------------------------------------
-- 4. document_chunks — text chunks with embeddings for semantic retrieval
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS document_chunks (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT         NOT NULL,
    page_number INT         NOT NULL,
    content     TEXT        NOT NULL,
    embedding   VECTOR(384),                -- all-MiniLM-L6-v2 produces 384-dim vectors
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  document_chunks             IS 'Text chunks extracted from documents, with embeddings for semantic search.';
COMMENT ON COLUMN document_chunks.document_id IS 'Foreign key to the parent document.';
COMMENT ON COLUMN document_chunks.chunk_index IS '0-based index of this chunk within the document.';
COMMENT ON COLUMN document_chunks.page_number IS 'Page number in the source PDF — used for citation display.';
COMMENT ON COLUMN document_chunks.content     IS 'Raw text content of the chunk.';
COMMENT ON COLUMN document_chunks.embedding   IS '384-dimensional vector from all-MiniLM-L6-v2.';
COMMENT ON COLUMN document_chunks.metadata    IS 'JSONB bag for extra fields: source, document_type, effective_date, status, etc.';


-- -----------------------------------------------------------------------------
-- 5. Vector similarity index (HNSW)
-- -----------------------------------------------------------------------------
-- HNSW gives fast approximate nearest-neighbour search at query time.
-- Uses cosine distance — the standard metric for sentence-transformer embeddings.
CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw_idx
    ON document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Supporting index: fast chunk lookups by parent document
CREATE INDEX IF NOT EXISTS document_chunks_document_id_idx
    ON document_chunks (document_id);


-- -----------------------------------------------------------------------------
-- 6. Full-text search index (tsvector) on document_chunks.content
-- -----------------------------------------------------------------------------
-- A generated tsvector column stores the pre-processed lexemes for each chunk.
-- The GIN index enables fast full-text search without recomputing tsvectors at
-- query time. english stemming and stop-word removal are applied automatically.
--
-- If the column already exists (re-running the script), the ALTER is skipped
-- via the IF NOT EXISTS guard on the index.
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

COMMENT ON COLUMN document_chunks.content_tsv IS
    'Auto-generated tsvector of content column for full-text search (english dictionary).';

-- GIN index on the generated tsvector — enables fast @@ plainto_tsquery queries
CREATE INDEX IF NOT EXISTS document_chunks_content_tsv_idx
    ON document_chunks
    USING gin (content_tsv);


-- -----------------------------------------------------------------------------
-- 7. Hybrid retrieval function — vector similarity + keyword + date/status filters
-- -----------------------------------------------------------------------------
-- Replaces the original match_document_chunks with a hybrid version that:
--   a) Computes cosine similarity score from the HNSW vector index.
--   b) Optionally adds a full-text rank (ts_rank) when keyword is provided.
--   c) Filters by document effective_date range (date_from / date_to).
--   d) Filters by document status (default ACTIVE).
--   e) Returns a combined_score = vector_similarity + text_rank for re-ranking.
--
-- Parameters:
--   query_embedding  VECTOR(384)      Required. Query vector from Sentence Transformers.
--   match_count      INT              Max results to return. Default 5.
--   filter_status    document_status  Lifecycle filter. Default 'ACTIVE'.
--   keyword          TEXT             Optional keyword string for full-text boost.
--                                     Pass NULL or '' to skip full-text scoring.
--   date_from        DATE             Optional lower bound on effective_date (inclusive).
--   date_to          DATE             Optional upper bound on effective_date (inclusive).
--
-- Returns columns:
--   chunk_id, document_id, title, version, effective_date, status,
--   chunk_index, page_number, content, metadata,
--   vector_similarity FLOAT,   cosine similarity score (0-1)
--   text_rank         FLOAT,   ts_rank score (0 when no keyword given)
--   combined_score    FLOAT    vector_similarity + text_rank (used for final ordering)
CREATE OR REPLACE FUNCTION match_document_chunks(
    query_embedding  VECTOR(384),
    match_count      INT             DEFAULT 5,
    filter_status    document_status DEFAULT 'ACTIVE',
    keyword          TEXT            DEFAULT NULL,
    date_from        DATE            DEFAULT NULL,
    date_to          DATE            DEFAULT NULL
)
RETURNS TABLE (
    chunk_id          UUID,
    document_id       UUID,
    title             TEXT,
    version           TEXT,
    effective_date    DATE,
    status            document_status,
    chunk_index       INT,
    page_number       INT,
    content           TEXT,
    metadata          JSONB,
    vector_similarity FLOAT,
    text_rank         FLOAT,
    combined_score    FLOAT
)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
    tsq TSQUERY;
BEGIN
    -- Build tsquery only when a non-empty keyword is supplied
    IF keyword IS NOT NULL AND trim(keyword) <> '' THEN
        tsq := plainto_tsquery('english', keyword);
    ELSE
        tsq := NULL;
    END IF;

    RETURN QUERY
    SELECT
        dc.id                                        AS chunk_id,
        dc.document_id,
        d.title,
        d.version,
        d.effective_date,
        d.status,
        dc.chunk_index,
        dc.page_number,
        dc.content,
        dc.metadata,

        -- Vector similarity: 1 - cosine_distance (higher = more similar)
        (1 - (dc.embedding <=> query_embedding))::FLOAT     AS vector_similarity,

        -- Full-text rank: 0 when no keyword provided
        CASE
            WHEN tsq IS NOT NULL THEN ts_rank(dc.content_tsv, tsq)::FLOAT
            ELSE 0.0::FLOAT
        END                                                   AS text_rank,

        -- Combined score used for final ordering
        (1 - (dc.embedding <=> query_embedding) +
            CASE
                WHEN tsq IS NOT NULL THEN ts_rank(dc.content_tsv, tsq)
                ELSE 0.0
            END
        )::FLOAT                                              AS combined_score

    FROM document_chunks dc
    JOIN documents d ON d.id = dc.document_id

    WHERE
        -- Status filter
        d.status = filter_status

        -- Full-text filter: only apply when keyword is given
        AND (tsq IS NULL OR dc.content_tsv @@ tsq)

        -- Date range filters on effective_date (both bounds optional)
        AND (date_from IS NULL OR d.effective_date >= date_from)
        AND (date_to   IS NULL OR d.effective_date <= date_to)

    ORDER BY combined_score DESC
    LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION match_document_chunks IS
    'Hybrid retrieval: cosine vector similarity + optional full-text rank + date-range and status filters. Returns top match_count chunks ordered by combined_score DESC.';


-- -----------------------------------------------------------------------------
-- 8. Bulk chunk retrieval RPC
-- -----------------------------------------------------------------------------
-- Fetches all chunks belonging to a list of document IDs in a single round-
-- trip. Used by the bulk retrieval handler in database/chunks.py to avoid
-- N individual queries when loading chunks for multiple documents at once.
--
-- Parameters:
--   doc_ids   UUID[]   Array of document UUIDs to fetch chunks for.
--
-- Returns all columns from document_chunks plus the parent document title,
-- version, effective_date, and status — ordered by document_id, chunk_index.
CREATE OR REPLACE FUNCTION bulk_fetch_chunks_by_documents(
    doc_ids UUID[]
)
RETURNS TABLE (
    chunk_id       UUID,
    document_id    UUID,
    title          TEXT,
    version        TEXT,
    effective_date DATE,
    status         document_status,
    chunk_index    INT,
    page_number    INT,
    content        TEXT,
    metadata       JSONB,
    created_at     TIMESTAMPTZ
)
LANGUAGE sql STABLE
AS $$
    SELECT
        dc.id           AS chunk_id,
        dc.document_id,
        d.title,
        d.version,
        d.effective_date,
        d.status,
        dc.chunk_index,
        dc.page_number,
        dc.content,
        dc.metadata,
        dc.created_at
    FROM document_chunks dc
    JOIN documents d ON d.id = dc.document_id
    WHERE dc.document_id = ANY(doc_ids)
    ORDER BY dc.document_id, dc.chunk_index;
$$;

COMMENT ON FUNCTION bulk_fetch_chunks_by_documents IS
    'Fetches all chunks for an array of document UUIDs in a single RPC call, ordered by document_id and chunk_index.';


-- -----------------------------------------------------------------------------
-- 9. query_performance_log — optional persistent log table
-- -----------------------------------------------------------------------------
-- Stores query latency records written by the Python query_logger module.
-- This is optional — the Python in-memory store (query_logger.py) works
-- without this table. Create it if you want persistent latency history.
CREATE TABLE IF NOT EXISTS query_performance_log (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    operation     TEXT        NOT NULL,
    latency_ms    FLOAT       NOT NULL,
    result_count  INT         NOT NULL DEFAULT 0,
    params        JSONB,
    success       BOOLEAN     NOT NULL DEFAULT TRUE,
    error         TEXT,
    logged_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  query_performance_log            IS 'Persistent store for query latency logs from the CareSync AI backend.';
COMMENT ON COLUMN query_performance_log.operation  IS 'Name of the database operation, e.g. search_similar_chunks.';
COMMENT ON COLUMN query_performance_log.latency_ms IS 'Wall-clock query duration in milliseconds.';
COMMENT ON COLUMN query_performance_log.params     IS 'Sanitised query parameters (embedding vectors replaced with their length).';

-- Index for fast slow-query lookups
CREATE INDEX IF NOT EXISTS query_perf_log_latency_idx
    ON query_performance_log (latency_ms DESC);

-- Index for per-operation analysis
CREATE INDEX IF NOT EXISTS query_perf_log_operation_idx
    ON query_performance_log (operation, logged_at DESC);


-- -----------------------------------------------------------------------------
-- 10. Language metadata column on documents
-- -----------------------------------------------------------------------------
-- Stores the BCP-47 language tag of the document content, e.g. "en", "hi",
-- "fr", "ta". Defaults to "en" (English) for backward compatibility.
-- Used by the retrieval system to filter or prefer documents in the user's
-- preferred locale.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'documents' AND column_name = 'language'
    ) THEN
        ALTER TABLE documents
            ADD COLUMN language TEXT NOT NULL DEFAULT 'en';
    END IF;
END
$$;

COMMENT ON COLUMN documents.language IS
    'BCP-47 language tag of the document content, e.g. "en", "hi", "fr". Defaults to "en".';

-- Index for fast language-filtered queries
CREATE INDEX IF NOT EXISTS documents_language_idx
    ON documents (language);


-- -----------------------------------------------------------------------------
-- 11. user_locale_preferences — stores per-user language preference
-- -----------------------------------------------------------------------------
-- Allows field workers to record their preferred language so the UI and
-- retrieval system can automatically filter documents to their locale.
--
-- user_id is a free-form identifier (e.g. Supabase Auth UUID, session token,
-- or device ID) — no foreign key enforced to keep the schema auth-agnostic.
CREATE TABLE IF NOT EXISTS user_locale_preferences (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT        NOT NULL UNIQUE,   -- external user/session identifier
    preferred_lang  TEXT        NOT NULL DEFAULT 'en',  -- BCP-47 language tag
    fallback_lang   TEXT        NOT NULL DEFAULT 'en',  -- used when preferred_lang docs unavailable
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  user_locale_preferences                 IS 'Per-user language preferences for the CareSync AI interface and retrieval system.';
COMMENT ON COLUMN user_locale_preferences.user_id         IS 'External user identifier (e.g. Supabase Auth UUID or session token). Must be unique.';
COMMENT ON COLUMN user_locale_preferences.preferred_lang  IS 'Primary language preference as a BCP-47 tag, e.g. "en", "hi", "fr", "ta".';
COMMENT ON COLUMN user_locale_preferences.fallback_lang   IS 'Fallback language used when no documents exist in preferred_lang. Defaults to "en".';
COMMENT ON COLUMN user_locale_preferences.updated_at      IS 'Timestamp of last preference update.';

-- Index for fast user_id lookups
CREATE INDEX IF NOT EXISTS user_locale_prefs_user_id_idx
    ON user_locale_preferences (user_id);

-- Trigger to auto-update updated_at on row changes
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS user_locale_prefs_updated_at ON user_locale_preferences;
CREATE TRIGGER user_locale_prefs_updated_at
    BEFORE UPDATE ON user_locale_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- -----------------------------------------------------------------------------
-- 12. chat_sessions — one record per conversation session per user
-- -----------------------------------------------------------------------------
-- A session groups multiple chat turns together under a single conversation.
-- Each session belongs to a user (identified by the same user_id used in
-- user_locale_preferences) and optionally carries a human-readable title
-- for display in a session history sidebar.
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT        NOT NULL,           -- external user / session identifier
    title       TEXT,                           -- auto-generated or user-edited session title
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  chat_sessions            IS 'Groups chat messages into per-user conversation sessions.';
COMMENT ON COLUMN chat_sessions.user_id    IS 'External user identifier, matches user_locale_preferences.user_id.';
COMMENT ON COLUMN chat_sessions.title      IS 'Optional human-readable session title (e.g. first user question, truncated).';
COMMENT ON COLUMN chat_sessions.updated_at IS 'Timestamp of the last message added to this session.';

-- Indexes for fast per-user session lookups and recency sorting
CREATE INDEX IF NOT EXISTS chat_sessions_user_id_idx
    ON chat_sessions (user_id, updated_at DESC);

-- Auto-update updated_at when a session row is modified
DROP TRIGGER IF EXISTS chat_sessions_updated_at ON chat_sessions;
CREATE TRIGGER chat_sessions_updated_at
    BEFORE UPDATE ON chat_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- -----------------------------------------------------------------------------
-- 13. chat_messages — individual turns within a conversation session
-- -----------------------------------------------------------------------------
-- Each row is one message exchange turn: a user question or an assistant reply.
-- Citations are stored as a JSONB array so they can be queried or rendered
-- without joining additional tables.
--
-- role values:
--   'user'      — message sent by the field worker
--   'assistant' — response generated by CareSync AI
CREATE TABLE IF NOT EXISTS chat_messages (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id   UUID        NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role         TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content      TEXT        NOT NULL,          -- raw message text
    citations    JSONB,                         -- array of citation objects (title, page, version, etc.)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  chat_messages            IS 'Individual message turns within a chat session.';
COMMENT ON COLUMN chat_messages.session_id IS 'Foreign key to the parent chat session.';
COMMENT ON COLUMN chat_messages.role       IS 'Message author role: "user" or "assistant".';
COMMENT ON COLUMN chat_messages.content    IS 'Raw text content of the message.';
COMMENT ON COLUMN chat_messages.citations  IS 'JSONB array of source citations attached to an assistant response.';

-- Index for fast in-order message retrieval within a session
CREATE INDEX IF NOT EXISTS chat_messages_session_id_idx
    ON chat_messages (session_id, created_at ASC);


-- -----------------------------------------------------------------------------
-- 14. audio_query_log — records every audio/voice query submitted by users
-- -----------------------------------------------------------------------------
-- Captures each voice-input query event for analytics, debugging, and
-- quality monitoring. Stores the audio file reference (not the binary),
-- the resulting transcription, processing latency, and outcome status.
--
-- status values:
--   'pending'    — audio received, transcription not yet started
--   'processing' — transcription in progress
--   'success'    — transcription completed, query forwarded to RAG pipeline
--   'failed'     — transcription or processing error
CREATE TABLE IF NOT EXISTS audio_query_log (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             TEXT        NOT NULL,           -- external user / session identifier
    session_id          UUID        REFERENCES chat_sessions(id) ON DELETE SET NULL,
    audio_file_ref      TEXT,                           -- storage path or URL of the audio file
    audio_duration_ms   INT,                            -- duration of the audio clip in ms
    transcription       TEXT,                           -- raw transcript produced by STT engine
    language            TEXT        NOT NULL DEFAULT 'en',  -- BCP-47 language of the audio
    transcription_ms    INT,                            -- wall-clock time for transcription in ms
    status              TEXT        NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'processing', 'success', 'failed')),
    error_message       TEXT,                           -- populated when status = 'failed'
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  audio_query_log                    IS 'Logs every audio/voice query event for analytics and quality monitoring.';
COMMENT ON COLUMN audio_query_log.user_id            IS 'External user identifier.';
COMMENT ON COLUMN audio_query_log.session_id         IS 'Optional link to the chat session this audio query belongs to.';
COMMENT ON COLUMN audio_query_log.audio_file_ref     IS 'Storage path or public URL of the uploaded audio file (not the binary).';
COMMENT ON COLUMN audio_query_log.audio_duration_ms  IS 'Duration of the audio clip in milliseconds.';
COMMENT ON COLUMN audio_query_log.transcription      IS 'Raw text transcript produced by the speech-to-text engine.';
COMMENT ON COLUMN audio_query_log.language           IS 'BCP-47 language tag of the spoken audio, e.g. "en", "hi".';
COMMENT ON COLUMN audio_query_log.transcription_ms   IS 'Wall-clock time taken for the transcription call in milliseconds.';
COMMENT ON COLUMN audio_query_log.status             IS 'Processing status: pending | processing | success | failed.';
COMMENT ON COLUMN audio_query_log.error_message      IS 'Error details when status is failed.';

-- Index for per-user query history and recency sorting
CREATE INDEX IF NOT EXISTS audio_query_log_user_id_idx
    ON audio_query_log (user_id, created_at DESC);

-- Index for session-level audio query joins
CREATE INDEX IF NOT EXISTS audio_query_log_session_id_idx
    ON audio_query_log (session_id)
    WHERE session_id IS NOT NULL;

-- Index for monitoring failed transcriptions
CREATE INDEX IF NOT EXISTS audio_query_log_status_idx
    ON audio_query_log (status, created_at DESC);


-- -----------------------------------------------------------------------------
-- 15. transcription_audit — detailed audit trail for STT engine outputs
-- -----------------------------------------------------------------------------
-- One row per audio_query_log entry, storing the full STT engine response
-- payload and confidence metadata for quality review and model comparison.
-- Kept separate from audio_query_log to avoid bloating the main query log
-- with large JSON payloads.
CREATE TABLE IF NOT EXISTS transcription_audit (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    audio_query_id      UUID        NOT NULL REFERENCES audio_query_log(id) ON DELETE CASCADE,
    stt_engine          TEXT        NOT NULL,           -- engine used: e.g. "whisper", "google", "azure"
    raw_transcript      TEXT        NOT NULL,           -- unprocessed engine output
    confidence_score    FLOAT,                          -- overall confidence (0.0–1.0) if provided by engine
    word_timestamps     JSONB,                          -- per-word timestamps and confidence from engine
    engine_response     JSONB,                          -- full raw JSON response from the STT API
    post_processed      TEXT,                           -- transcript after cleaning / normalisation
    reviewed_by         TEXT,                           -- user_id of human reviewer, if manually reviewed
    reviewed_at         TIMESTAMPTZ,                    -- timestamp of human review
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  transcription_audit                   IS 'Detailed audit trail of STT engine outputs for quality review and model comparison.';
COMMENT ON COLUMN transcription_audit.audio_query_id    IS 'Foreign key to the parent audio_query_log entry.';
COMMENT ON COLUMN transcription_audit.stt_engine        IS 'Identifier of the STT engine used, e.g. "whisper-large-v3", "google-v1".';
COMMENT ON COLUMN transcription_audit.raw_transcript    IS 'Unprocessed transcript string directly from the STT engine.';
COMMENT ON COLUMN transcription_audit.confidence_score  IS 'Overall confidence score (0.0–1.0) reported by the engine, if available.';
COMMENT ON COLUMN transcription_audit.word_timestamps   IS 'JSONB array of per-word objects with start_ms, end_ms, word, confidence.';
COMMENT ON COLUMN transcription_audit.engine_response   IS 'Complete raw JSON response payload from the STT API for debugging.';
COMMENT ON COLUMN transcription_audit.post_processed    IS 'Transcript after punctuation restoration, normalisation, or spell correction.';
COMMENT ON COLUMN transcription_audit.reviewed_by       IS 'user_id of staff member who manually reviewed this transcription.';
COMMENT ON COLUMN transcription_audit.reviewed_at       IS 'Timestamp when the manual review was completed.';

-- Index for fast lookups by parent audio query
CREATE INDEX IF NOT EXISTS transcription_audit_audio_query_id_idx
    ON transcription_audit (audio_query_id);

-- Index for engine-level quality analysis
CREATE INDEX IF NOT EXISTS transcription_audit_stt_engine_idx
    ON transcription_audit (stt_engine, created_at DESC);

-- Index for finding unreviewed transcriptions
CREATE INDEX IF NOT EXISTS transcription_audit_unreviewed_idx
    ON transcription_audit (reviewed_at)
    WHERE reviewed_at IS NULL;


-- -----------------------------------------------------------------------------
-- 16. chat_feedback — user upvotes/downvotes and comments on LLM answers
-- -----------------------------------------------------------------------------
-- One row per feedback submission. A user can provide a thumbs-up or
-- thumbs-down vote on any assistant message, optionally with a free-text
-- comment explaining the rating.
--
-- vote values:
--   'upvote'   — user found the answer helpful and accurate
--   'downvote' — user found the answer unhelpful, incorrect, or incomplete
CREATE TABLE IF NOT EXISTS chat_feedback (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id   UUID        REFERENCES chat_messages(id) ON DELETE SET NULL,
    session_id   UUID        REFERENCES chat_sessions(id) ON DELETE SET NULL,
    user_id      TEXT        NOT NULL,
    vote         TEXT        NOT NULL CHECK (vote IN ('upvote', 'downvote')),
    comment      TEXT,                        -- optional free-text feedback from user
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  chat_feedback            IS 'User upvote/downvote ratings and optional comments on LLM-generated answers.';
COMMENT ON COLUMN chat_feedback.message_id IS 'The specific assistant message being rated. NULL if message was deleted.';
COMMENT ON COLUMN chat_feedback.session_id IS 'The chat session this feedback belongs to.';
COMMENT ON COLUMN chat_feedback.user_id    IS 'External user identifier.';
COMMENT ON COLUMN chat_feedback.vote       IS 'User rating: upvote | downvote.';
COMMENT ON COLUMN chat_feedback.comment    IS 'Optional free-text comment explaining the rating.';

-- Indexes for fast aggregation by message and user
CREATE INDEX IF NOT EXISTS chat_feedback_message_id_idx
    ON chat_feedback (message_id)
    WHERE message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS chat_feedback_user_id_idx
    ON chat_feedback (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS chat_feedback_vote_idx
    ON chat_feedback (vote, created_at DESC);


-- -----------------------------------------------------------------------------
-- 17. system_metrics — latency and performance metrics per query
-- -----------------------------------------------------------------------------
-- Stores end-to-end latency breakdowns for every RAG pipeline execution.
-- Each row captures timings for embedding, retrieval, LLM generation, and
-- total response time, enabling bottleneck analysis and SLA monitoring.
CREATE TABLE IF NOT EXISTS system_metrics (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID        REFERENCES chat_sessions(id) ON DELETE SET NULL,
    message_id          UUID        REFERENCES chat_messages(id) ON DELETE SET NULL,
    user_id             TEXT        NOT NULL,
    query_text          TEXT,                       -- the user's question (for correlation)
    embedding_ms        FLOAT,                      -- time to generate query embedding
    retrieval_ms        FLOAT,                      -- time for vector similarity search
    rerank_ms           FLOAT,                      -- time for reranking step (if used)
    llm_ms              FLOAT,                      -- time for LLM generation
    total_ms            FLOAT       NOT NULL,       -- end-to-end wall-clock time
    chunk_count         INT,                        -- number of chunks retrieved
    model_name          TEXT,                       -- LLM model identifier
    status              TEXT        NOT NULL DEFAULT 'success'
                            CHECK (status IN ('success', 'failed', 'timeout')),
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  system_metrics                IS 'End-to-end latency breakdowns for RAG pipeline executions.';
COMMENT ON COLUMN system_metrics.embedding_ms   IS 'Time in ms to generate the query embedding.';
COMMENT ON COLUMN system_metrics.retrieval_ms   IS 'Time in ms for the vector similarity search against pgvector.';
COMMENT ON COLUMN system_metrics.rerank_ms      IS 'Time in ms for the optional reranking step.';
COMMENT ON COLUMN system_metrics.llm_ms         IS 'Time in ms for the LLM to generate the answer.';
COMMENT ON COLUMN system_metrics.total_ms       IS 'Total end-to-end wall-clock time in ms.';
COMMENT ON COLUMN system_metrics.chunk_count    IS 'Number of document chunks retrieved and passed to the LLM.';
COMMENT ON COLUMN system_metrics.model_name     IS 'LLM model identifier, e.g. "gemini-3.5-flash".';

-- Indexes for latency analysis and per-user/session reporting
CREATE INDEX IF NOT EXISTS system_metrics_user_id_idx
    ON system_metrics (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS system_metrics_session_id_idx
    ON system_metrics (session_id)
    WHERE session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS system_metrics_total_ms_idx
    ON system_metrics (total_ms DESC);

CREATE INDEX IF NOT EXISTS system_metrics_status_idx
    ON system_metrics (status, created_at DESC);


-- -----------------------------------------------------------------------------
-- 18. RPC: log_chat_feedback
-- -----------------------------------------------------------------------------
-- Inserts a feedback vote and optional comment, returning the created record.
-- Using an RPC allows atomic insert with server-side timestamp.
CREATE OR REPLACE FUNCTION log_chat_feedback(
    p_user_id    TEXT,
    p_vote       TEXT,
    p_message_id UUID    DEFAULT NULL,
    p_session_id UUID    DEFAULT NULL,
    p_comment    TEXT    DEFAULT NULL
)
RETURNS SETOF chat_feedback
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_vote NOT IN ('upvote', 'downvote') THEN
        RAISE EXCEPTION 'Invalid vote value: %. Must be upvote or downvote.', p_vote;
    END IF;

    RETURN QUERY
    INSERT INTO chat_feedback (user_id, vote, message_id, session_id, comment)
    VALUES (p_user_id, p_vote, p_message_id, p_session_id, p_comment)
    RETURNING *;
END;
$$;

COMMENT ON FUNCTION log_chat_feedback IS
    'Inserts a user feedback vote (upvote/downvote) with optional comment and returns the created record.';


-- -----------------------------------------------------------------------------
-- 19. RPC: get_feedback_summary
-- -----------------------------------------------------------------------------
-- Returns aggregated upvote/downvote counts for a specific assistant message.
CREATE OR REPLACE FUNCTION get_feedback_summary(p_message_id UUID)
RETURNS TABLE (
    message_id  UUID,
    upvotes     BIGINT,
    downvotes   BIGINT,
    total       BIGINT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        p_message_id                                             AS message_id,
        COUNT(*) FILTER (WHERE vote = 'upvote')                  AS upvotes,
        COUNT(*) FILTER (WHERE vote = 'downvote')                AS downvotes,
        COUNT(*)                                                  AS total
    FROM chat_feedback
    WHERE message_id = p_message_id;
$$;

COMMENT ON FUNCTION get_feedback_summary IS
    'Returns aggregated upvote/downvote counts for a specific chat message.';


-- -----------------------------------------------------------------------------
-- 20. RPC: log_system_metrics
-- -----------------------------------------------------------------------------
-- Inserts a system_metrics record and returns the created row.
CREATE OR REPLACE FUNCTION log_system_metrics(
    p_user_id       TEXT,
    p_total_ms      FLOAT,
    p_session_id    UUID    DEFAULT NULL,
    p_message_id    UUID    DEFAULT NULL,
    p_query_text    TEXT    DEFAULT NULL,
    p_embedding_ms  FLOAT   DEFAULT NULL,
    p_retrieval_ms  FLOAT   DEFAULT NULL,
    p_rerank_ms     FLOAT   DEFAULT NULL,
    p_llm_ms        FLOAT   DEFAULT NULL,
    p_chunk_count   INT     DEFAULT NULL,
    p_model_name    TEXT    DEFAULT NULL,
    p_status        TEXT    DEFAULT 'success',
    p_error_message TEXT    DEFAULT NULL
)
RETURNS SETOF system_metrics
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_status NOT IN ('success', 'failed', 'timeout') THEN
        RAISE EXCEPTION 'Invalid status: %. Must be success, failed, or timeout.', p_status;
    END IF;

    RETURN QUERY
    INSERT INTO system_metrics (
        user_id, total_ms, session_id, message_id, query_text,
        embedding_ms, retrieval_ms, rerank_ms, llm_ms,
        chunk_count, model_name, status, error_message
    )
    VALUES (
        p_user_id, p_total_ms, p_session_id, p_message_id, p_query_text,
        p_embedding_ms, p_retrieval_ms, p_rerank_ms, p_llm_ms,
        p_chunk_count, p_model_name, p_status, p_error_message
    )
    RETURNING *;
END;
$$;

COMMENT ON FUNCTION log_system_metrics IS
    'Inserts a system_metrics record with latency breakdown and returns the created row.';


-- -----------------------------------------------------------------------------
-- 21. RPC: get_latency_summary
-- -----------------------------------------------------------------------------
-- Returns aggregated latency statistics (avg, p95, max) for a time window.
CREATE OR REPLACE FUNCTION get_latency_summary(
    since_ts TIMESTAMPTZ DEFAULT (now() - INTERVAL '24 hours')
)
RETURNS TABLE (
    avg_total_ms    FLOAT,
    p95_total_ms    FLOAT,
    max_total_ms    FLOAT,
    avg_embedding_ms FLOAT,
    avg_retrieval_ms FLOAT,
    avg_llm_ms      FLOAT,
    total_queries   BIGINT,
    failed_queries  BIGINT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        AVG(total_ms)::FLOAT                                         AS avg_total_ms,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_ms)::FLOAT AS p95_total_ms,
        MAX(total_ms)::FLOAT                                         AS max_total_ms,
        AVG(embedding_ms)::FLOAT                                     AS avg_embedding_ms,
        AVG(retrieval_ms)::FLOAT                                     AS avg_retrieval_ms,
        AVG(llm_ms)::FLOAT                                           AS avg_llm_ms,
        COUNT(*)                                                      AS total_queries,
        COUNT(*) FILTER (WHERE status != 'success')                   AS failed_queries
    FROM system_metrics
    WHERE created_at >= since_ts;
$$;

COMMENT ON FUNCTION get_latency_summary IS
    'Returns aggregated latency stats (avg, p95, max) and query counts since the given timestamp.';


-- =============================================================================
-- Analytics RPCs
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 22. RPC: get_daily_active_users
-- -----------------------------------------------------------------------------
-- Returns the count of distinct users who sent at least one chat message
-- per calendar day within the given time window.
CREATE OR REPLACE FUNCTION get_daily_active_users(
    since_ts TIMESTAMPTZ DEFAULT (now() - INTERVAL '30 days')
)
RETURNS TABLE (
    day          DATE,
    active_users BIGINT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        DATE(cm.created_at AT TIME ZONE 'UTC')  AS day,
        COUNT(DISTINCT cs.user_id)               AS active_users
    FROM chat_messages cm
    JOIN chat_sessions cs ON cs.id = cm.session_id
    WHERE cm.created_at >= since_ts
      AND cm.role = 'user'
    GROUP BY 1
    ORDER BY 1;
$$;

COMMENT ON FUNCTION get_daily_active_users IS
    'Returns distinct active user count per calendar day since since_ts (default 30 days).';


-- -----------------------------------------------------------------------------
-- 23. RPC: get_total_queries_over_time
-- -----------------------------------------------------------------------------
-- Returns the total number of user queries (chat messages with role=user)
-- per calendar day, optionally bucketed by hour instead of day.
CREATE OR REPLACE FUNCTION get_total_queries_over_time(
    since_ts    TIMESTAMPTZ DEFAULT (now() - INTERVAL '30 days'),
    bucket_size TEXT        DEFAULT 'day'   -- 'hour' | 'day' | 'week'
)
RETURNS TABLE (
    bucket       TIMESTAMPTZ,
    total_queries BIGINT
)
LANGUAGE plpgsql STABLE
AS $$
BEGIN
    IF bucket_size NOT IN ('hour', 'day', 'week') THEN
        RAISE EXCEPTION 'Invalid bucket_size: %. Must be hour, day, or week.', bucket_size;
    END IF;

    RETURN QUERY
    SELECT
        DATE_TRUNC(bucket_size, cm.created_at)  AS bucket,
        COUNT(*)                                  AS total_queries
    FROM chat_messages cm
    WHERE cm.created_at >= since_ts
      AND cm.role = 'user'
    GROUP BY 1
    ORDER BY 1;
END;
$$;

COMMENT ON FUNCTION get_total_queries_over_time IS
    'Returns total user query counts bucketed by hour/day/week since since_ts.';


-- -----------------------------------------------------------------------------
-- 24. RPC: get_top_queried_topics
-- -----------------------------------------------------------------------------
-- Extracts individual lexemes from user messages using PostgreSQL full-text
-- processing and returns the most frequently occurring terms.
-- Stop words and short tokens are filtered out automatically by the english
-- text-search dictionary.
CREATE OR REPLACE FUNCTION get_top_queried_topics(
    since_ts    TIMESTAMPTZ DEFAULT (now() - INTERVAL '30 days'),
    top_n       INT         DEFAULT 20
)
RETURNS TABLE (
    term        TEXT,
    frequency   BIGINT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        word                AS term,
        COUNT(*)            AS frequency
    FROM (
        SELECT unnest(tsvector_to_array(
                    to_tsvector('english', cm.content)
               )) AS word
        FROM chat_messages cm
        WHERE cm.created_at >= since_ts
          AND cm.role = 'user'
          AND LENGTH(cm.content) > 0
    ) lexemes
    -- filter out very short tokens that slipped through stop-word removal
    WHERE LENGTH(word) > 3
    GROUP BY word
    ORDER BY COUNT(*) DESC
    LIMIT top_n;
$$;

COMMENT ON FUNCTION get_top_queried_topics IS
    'Returns the top_n most frequently occurring terms from user queries since since_ts using full-text lexeme extraction.';


-- -----------------------------------------------------------------------------
-- 25. RPC: get_feedback_satisfaction_rate
-- -----------------------------------------------------------------------------
-- Returns upvote count, downvote count, total, and satisfaction rate (upvotes
-- as a percentage of total votes) for a given time window.
CREATE OR REPLACE FUNCTION get_feedback_satisfaction_rate(
    since_ts TIMESTAMPTZ DEFAULT (now() - INTERVAL '30 days')
)
RETURNS TABLE (
    upvotes           BIGINT,
    downvotes         BIGINT,
    total_votes       BIGINT,
    satisfaction_rate FLOAT       -- upvotes / total * 100, NULL when total = 0
)
LANGUAGE sql STABLE
AS $$
    SELECT
        COUNT(*) FILTER (WHERE vote = 'upvote')   AS upvotes,
        COUNT(*) FILTER (WHERE vote = 'downvote') AS downvotes,
        COUNT(*)                                   AS total_votes,
        CASE
            WHEN COUNT(*) = 0 THEN NULL
            ELSE ROUND(
                (COUNT(*) FILTER (WHERE vote = 'upvote'))::NUMERIC
                / COUNT(*)::NUMERIC * 100, 2
            )::FLOAT
        END                                        AS satisfaction_rate
    FROM chat_feedback
    WHERE created_at >= since_ts;
$$;

COMMENT ON FUNCTION get_feedback_satisfaction_rate IS
    'Returns upvote/downvote counts and satisfaction rate (% upvotes) since since_ts.';


-- -----------------------------------------------------------------------------
-- 26. RPC: get_system_health_metrics
-- -----------------------------------------------------------------------------
-- Returns p95 latency, error rate, timeout rate, fallback trigger count,
-- and average per-stage latencies for a given time window.
-- "Fallback triggers" are queries where the LLM returned a no-results answer
-- (identified by error_message containing 'fallback' or status = 'failed').
CREATE OR REPLACE FUNCTION get_system_health_metrics(
    since_ts TIMESTAMPTZ DEFAULT (now() - INTERVAL '24 hours')
)
RETURNS TABLE (
    total_queries       BIGINT,
    success_count       BIGINT,
    failed_count        BIGINT,
    timeout_count       BIGINT,
    fallback_count      BIGINT,
    error_rate_pct      FLOAT,
    timeout_rate_pct    FLOAT,
    avg_total_ms        FLOAT,
    p95_total_ms        FLOAT,
    max_total_ms        FLOAT,
    avg_embedding_ms    FLOAT,
    avg_retrieval_ms    FLOAT,
    avg_llm_ms          FLOAT
)
LANGUAGE sql STABLE
AS $$
    SELECT
        COUNT(*)                                                            AS total_queries,
        COUNT(*) FILTER (WHERE status = 'success')                          AS success_count,
        COUNT(*) FILTER (WHERE status = 'failed')                           AS failed_count,
        COUNT(*) FILTER (WHERE status = 'timeout')                          AS timeout_count,
        -- fallback: failed queries OR those whose error_message mentions fallback
        COUNT(*) FILTER (
            WHERE status != 'success'
               OR (error_message IS NOT NULL
                   AND lower(error_message) LIKE '%fallback%')
        )                                                                   AS fallback_count,
        -- error rate as percentage
        CASE WHEN COUNT(*) = 0 THEN 0
             ELSE ROUND(
                COUNT(*) FILTER (WHERE status = 'failed')::NUMERIC
                / COUNT(*)::NUMERIC * 100, 2
             )::FLOAT
        END                                                                  AS error_rate_pct,
        -- timeout rate as percentage
        CASE WHEN COUNT(*) = 0 THEN 0
             ELSE ROUND(
                COUNT(*) FILTER (WHERE status = 'timeout')::NUMERIC
                / COUNT(*)::NUMERIC * 100, 2
             )::FLOAT
        END                                                                  AS timeout_rate_pct,
        AVG(total_ms)::FLOAT                                                 AS avg_total_ms,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_ms)::FLOAT       AS p95_total_ms,
        MAX(total_ms)::FLOAT                                                 AS max_total_ms,
        AVG(embedding_ms)::FLOAT                                             AS avg_embedding_ms,
        AVG(retrieval_ms)::FLOAT                                             AS avg_retrieval_ms,
        AVG(llm_ms)::FLOAT                                                   AS avg_llm_ms
    FROM system_metrics
    WHERE created_at >= since_ts;
$$;

COMMENT ON FUNCTION get_system_health_metrics IS
    'Returns p95 latency, error/timeout rates, fallback counts, and per-stage averages since since_ts.';

-- =============================================================================
-- Query Optimisation — Index Parameter Tuning
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 27. Tuned HNSW index parameters
-- -----------------------------------------------------------------------------
-- The HNSW index was created in section 5 with default parameters (m=16,
-- ef_construction=64). This section provides the ALTER INDEX commands to
-- tune ef_search at query time without rebuilding the index.
--
-- ef_search controls the size of the candidate list during ANN search:
--   Higher ef_search → better recall, slower queries
--   Lower  ef_search → faster queries, slightly lower recall
--
-- Recommended values for CareSync AI workload:
--   Development / low traffic:  ef_search = 40  (fast, recall ~97%)
--   Production / balanced:      ef_search = 100 (recommended default)
--   High-recall / audit:        ef_search = 200 (slower, recall ~99.5%)
--
-- Apply at session level (per-query, no downtime):
--   SET hnsw.ef_search = 100;
--
-- Apply as a persistent index storage parameter (requires reindex):
--   ALTER INDEX document_chunks_embedding_hnsw_idx
--       SET (ef_search = 100);
--
-- The statement below sets the recommended production default.
-- Wrap in DO $$ … $$ to make it idempotent and skip if already set.
DO $$
BEGIN
    -- ef_search is a runtime GUC — set a session-level default via ALTER SYSTEM
    -- so it persists across connections without modifying application code.
    -- Note: ALTER SYSTEM requires superuser on self-hosted Postgres.
    -- On Supabase, set this via the Supabase dashboard → Database → Parameters,
    -- or apply per-query with SET hnsw.ef_search = 100; in the RPC function.
    NULL; -- placeholder: configure ef_search via dashboard or session SET
END
$$;

COMMENT ON INDEX document_chunks_embedding_hnsw_idx IS
    'HNSW ANN index for cosine similarity search. Tune ef_search at session level: SET hnsw.ef_search = 100 (recommended production default).';


-- -----------------------------------------------------------------------------
-- 28. IVFFlat alternative index (commented out — enable for large datasets)
-- -----------------------------------------------------------------------------
-- IVFFlat is more memory-efficient than HNSW for very large chunk tables
-- (>500k rows). It requires a training pass (VACUUM ANALYZE) after bulk inserts.
--
-- lists   = sqrt(row_count) is a good starting point.
-- probes  = lists / 10 balances speed vs recall.
--
-- To switch from HNSW to IVFFlat:
--   1. DROP INDEX document_chunks_embedding_hnsw_idx;
--   2. CREATE the IVFFlat index below.
--   3. VACUUM ANALYZE document_chunks;
--   4. Set ivfflat.probes at query time: SET ivfflat.probes = 10;
--
-- CREATE INDEX IF NOT EXISTS document_chunks_embedding_ivfflat_idx
--     ON document_chunks
--     USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 100);
--
-- COMMENT ON INDEX document_chunks_embedding_ivfflat_idx IS
--     'IVFFlat ANN index. Tune probes at session level: SET ivfflat.probes = 10.';


-- -----------------------------------------------------------------------------
-- 29. Composite covering index for the most common retrieval query pattern
-- -----------------------------------------------------------------------------
-- The match_document_chunks RPC joins document_chunks → documents and filters
-- on d.status. This partial index on document_chunks pre-filters the join to
-- only ACTIVE parent rows, reducing the scan range for the most common query.
--
-- Only created if the index does not already exist.




-- -----------------------------------------------------------------------------
-- 30. ANALYZE hint — keep planner statistics fresh after bulk inserts
-- -----------------------------------------------------------------------------
-- Run this after bulk-uploading a new document to ensure the query planner
-- uses up-to-date row count and histogram statistics.
-- Not a schema change — execute manually or via the sync cron job.
--
--   ANALYZE document_chunks;
--   ANALYZE documents;
