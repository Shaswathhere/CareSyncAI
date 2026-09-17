"""
scripts/verify_migration.py
---------------------------
Migration verification script for CareSync AI.

Connects to the configured Supabase project and verifies that every table,
index, function, and enum defined in the production schema (v1.0.0) exists
and is structurally correct.

Exit codes:
    0 — all checks passed
    1 — one or more checks failed

Usage:
    python scripts/verify_migration.py
    python scripts/verify_migration.py --json        # machine-readable output

Environment:
    Requires SUPABASE_URL and SUPABASE_KEY in .env or environment.
    Uses the psycopg2 direct PostgreSQL connection (not the REST API) so it
    can query pg_catalog directly.
    Set DATABASE_URL in .env to the direct Postgres connection string from
    your Supabase project → Settings → Database → Connection string (URI).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s verify_migration — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("verify_migration")


# =============================================================================
# Expected schema objects — production v1.0.0
# =============================================================================

EXPECTED_TABLES = [
    "documents",
    "document_chunks",
    "query_performance_log",
    "user_locale_preferences",
    "chat_sessions",
    "chat_messages",
    "audio_query_log",
    "transcription_audit",
    "chat_feedback",
    "system_metrics",
]

EXPECTED_COLUMNS = {
    "documents": [
        "id", "title", "version", "publication_date",
        "effective_date", "status", "language", "created_at",
    ],
    "document_chunks": [
        "id", "document_id", "chunk_index", "page_number",
        "content", "embedding", "metadata", "created_at",
    ],
    "chat_sessions":   ["id", "user_id", "title", "created_at", "updated_at"],
    "chat_messages":   ["id", "session_id", "role", "content", "citations", "created_at"],
    "chat_feedback":   ["id", "message_id", "session_id", "user_id", "vote", "comment", "created_at"],
    "system_metrics":  [
        "id", "session_id", "message_id", "user_id", "query_text",
        "embedding_ms", "retrieval_ms", "rerank_ms", "llm_ms", "total_ms",
        "chunk_count", "model_name", "status", "error_message", "created_at",
    ],
    "audio_query_log": [
        "id", "user_id", "session_id", "audio_file_ref", "audio_duration_ms",
        "transcription", "language", "transcription_ms", "status", "error_message", "created_at",
    ],
    "transcription_audit": [
        "id", "audio_query_id", "stt_engine", "raw_transcript",
        "confidence_score", "word_timestamps", "engine_response",
        "post_processed", "reviewed_by", "reviewed_at", "created_at",
    ],
    "user_locale_preferences": [
        "id", "user_id", "preferred_lang", "fallback_lang", "created_at", "updated_at",
    ],
    "query_performance_log": [
        "id", "operation", "latency_ms", "result_count", "params", "success", "error", "logged_at",
    ],
}

EXPECTED_INDEXES = [
    "document_chunks_embedding_hnsw_idx",
    "document_chunks_document_id_idx",
    "document_chunks_content_tsv_idx",
    "documents_language_idx",
    "user_locale_prefs_user_id_idx",
    "chat_sessions_user_id_idx",
    "chat_messages_session_id_idx",
    "audio_query_log_user_id_idx",
    "audio_query_log_status_idx",
    "transcription_audit_audio_query_id_idx",
    "chat_feedback_message_id_idx",
    "chat_feedback_user_id_idx",
    "system_metrics_user_id_idx",
    "system_metrics_total_ms_idx",
    "query_perf_log_latency_idx",
]

EXPECTED_FUNCTIONS = [
    "match_document_chunks",
    "bulk_fetch_chunks_by_documents",
    "log_chat_feedback",
    "get_feedback_summary",
    "log_system_metrics",
    "get_latency_summary",
    "get_daily_active_users",
    "get_total_queries_over_time",
    "get_top_queried_topics",
    "get_feedback_satisfaction_rate",
    "get_system_health_metrics",
    "update_updated_at_column",
]

EXPECTED_ENUMS = ["document_status"]
EXPECTED_EXTENSIONS = ["vector"]


# =============================================================================
# Verification runner
# =============================================================================

class MigrationVerifier:
    def __init__(self, conn) -> None:
        self.conn    = conn
        self.passed  = 0
        self.failed  = 0
        self.details: list[dict] = []

    def _check(self, name: str, passed: bool, detail: str = "") -> None:
        status = "PASS" if passed else "FAIL"
        if passed:
            self.passed += 1
            log.info("  ✓ %s", name)
        else:
            self.failed += 1
            log.error("  ✗ %s  %s", name, detail)
        self.details.append({"check": name, "status": status, "detail": detail})

    def _query_one(self, sql: str, params=()) -> tuple | None:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def _query_all(self, sql: str, params=()) -> list[tuple]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    # ------------------------------------------------------------------
    def verify_extensions(self) -> None:
        log.info("── Extensions")
        for ext in EXPECTED_EXTENSIONS:
            row = self._query_one(
                "SELECT extname FROM pg_extension WHERE extname = %s", (ext,)
            )
            self._check(f"extension:{ext}", row is not None)

    def verify_enums(self) -> None:
        log.info("── Enum types")
        for enum in EXPECTED_ENUMS:
            row = self._query_one(
                "SELECT typname FROM pg_type WHERE typname = %s AND typtype = 'e'", (enum,)
            )
            self._check(f"enum:{enum}", row is not None)

    def verify_tables(self) -> None:
        log.info("── Tables")
        existing = {
            r[0] for r in self._query_all(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
        }
        for table in EXPECTED_TABLES:
            self._check(f"table:{table}", table in existing)

    def verify_columns(self) -> None:
        log.info("── Columns")
        for table, cols in EXPECTED_COLUMNS.items():
            existing_cols = {
                r[0] for r in self._query_all(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=%s",
                    (table,),
                )
            }
            for col in cols:
                self._check(f"column:{table}.{col}", col in existing_cols)

    def verify_indexes(self) -> None:
        log.info("── Indexes")
        existing = {
            r[0] for r in self._query_all(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"
            )
        }
        for idx in EXPECTED_INDEXES:
            self._check(f"index:{idx}", idx in existing)

    def verify_functions(self) -> None:
        log.info("── Functions / RPCs")
        existing = {
            r[0] for r in self._query_all(
                "SELECT routine_name FROM information_schema.routines "
                "WHERE routine_schema = 'public'"
            )
        }
        for fn in EXPECTED_FUNCTIONS:
            self._check(f"function:{fn}", fn in existing)

    def run_all(self) -> dict:
        log.info("=" * 55)
        log.info("CareSync AI — Migration Verification v1.0.0")
        log.info("=" * 55)
        self.verify_extensions()
        self.verify_enums()
        self.verify_tables()
        self.verify_columns()
        self.verify_indexes()
        self.verify_functions()
        log.info("=" * 55)
        log.info(
            "Result: %d passed, %d failed",
            self.passed, self.failed,
        )
        if self.failed == 0:
            log.info("✅ Schema verification PASSED — production ready.")
        else:
            log.error("❌ Schema verification FAILED — %d issue(s) found.", self.failed)
        log.info("=" * 55)

        return {
            "schema_version": "1.0.0",
            "passed":  self.passed,
            "failed":  self.failed,
            "success": self.failed == 0,
            "checks":  self.details,
        }


# =============================================================================
# Entry point
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Verify CareSync AI migration v1.0.0")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        log.error(
            "DATABASE_URL is not set. "
            "Set it to your Supabase direct PostgreSQL connection string.\n"
            "Find it at: Supabase → Settings → Database → Connection string (URI)"
        )
        sys.exit(1)

    try:
        import psycopg2
    except ImportError:
        log.error("psycopg2 is not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    try:
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
    except Exception as exc:
        log.error("Could not connect to PostgreSQL: %s", exc)
        sys.exit(1)

    try:
        verifier = MigrationVerifier(conn)
        result   = verifier.run_all()
    finally:
        conn.close()

    if args.json:
        print(json.dumps(result, indent=2))

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
