"""
scripts/backup_db.py
--------------------
Database backup script for CareSync AI.

Exports all core knowledge-base and operational tables to timestamped
JSON files in a local backup directory. Uses the Supabase REST API (no
direct PostgreSQL connection required) so it works with any Supabase plan.

What is backed up:
  - documents          — guideline metadata registry
  - document_chunks    — text chunks with metadata (embeddings excluded by default)
  - user_locale_preferences
  - chat_sessions
  - chat_messages      — full conversation history
  - chat_feedback
  - system_metrics     — pipeline latency records
  - audio_query_log
  - query_performance_log

What is NOT backed up:
  - Embeddings (VECTOR columns) — large binary data, regenerate from PDFs if needed
  - transcription_audit         — large JSONB blobs, optional backup flag available

Output structure:
  backups/
    YYYY-MM-DD_HHMMSS/
      documents.json
      document_chunks.json
      ...
      backup_manifest.json      <- summary of all tables backed up

Usage:
    python scripts/backup_db.py
    python scripts/backup_db.py --output-dir /path/to/backups
    python scripts/backup_db.py --include-embeddings    # include vector columns
    python scripts/backup_db.py --include-audit         # include transcription_audit
    python scripts/backup_db.py --dry-run               # list tables without writing

Environment:
    SUPABASE_URL  — required
    SUPABASE_KEY  — required (use service role key for full read access)
    BACKUP_DIR    — optional override for backup output directory
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s backup_db — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("backup_db")

# ---------------------------------------------------------------------------
# Tables to back up and their configuration
# ---------------------------------------------------------------------------
# Each entry: (table_name, select_columns, batch_size)
# select_columns = "*" to include all columns, or a comma-separated list
# Use a restricted list to exclude large/binary columns (e.g. embedding).
# ---------------------------------------------------------------------------
BACKUP_TABLES = [
    # Core knowledge base
    ("documents",
     "id,title,version,publication_date,effective_date,status,language,created_at",
     500),
    # Chunks without embeddings (vectors are large and regenerable)
    ("document_chunks",
     "id,document_id,chunk_index,page_number,content,metadata,created_at",
     200),
    # Users
    ("user_locale_preferences", "*", 1000),
    # Conversations
    ("chat_sessions",  "*", 1000),
    ("chat_messages",  "*", 500),
    # Feedback & metrics
    ("chat_feedback",  "*", 1000),
    ("system_metrics", "*", 500),
    # Audio
    ("audio_query_log", "*", 500),
    # Operational log
    ("query_performance_log",
     "id,operation,latency_ms,result_count,success,error,logged_at",
     1000),
]

AUDIT_TABLE = (
    "transcription_audit",
    "id,audio_query_id,stt_engine,raw_transcript,confidence_score,post_processed,reviewed_by,reviewed_at,created_at",
    200,
)

EMBEDDING_COLUMN_TABLE = (
    "document_chunks",
    "id,document_id,chunk_index,page_number,content,embedding,metadata,created_at",
    100,  # smaller batch due to vector size
)


# =============================================================================
# Backup logic
# =============================================================================

class DatabaseBackup:
    def __init__(
        self,
        output_dir: Path,
        include_embeddings: bool = False,
        include_audit: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.output_dir         = output_dir
        self.include_embeddings = include_embeddings
        self.include_audit      = include_audit
        self.dry_run            = dry_run
        self.manifest: list[dict] = []

        from config import SUPABASE_URL, SUPABASE_KEY
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY must be set. "
                "Use the service role key for full read access."
            )
        try:
            from supabase import create_client
            self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
        except ImportError:
            raise ImportError("supabase package not installed. Run: pip install supabase")

    def _fetch_table(
        self,
        table: str,
        columns: str,
        batch_size: int,
    ) -> list[dict]:
        """
        Fetches all rows from a table using paginated range queries.
        Returns a flat list of row dicts.
        """
        all_rows: list[dict] = []
        offset = 0

        while True:
            response = (
                self.client.table(table)
                .select(columns)
                .range(offset, offset + batch_size - 1)
                .execute()
            )
            batch = response.data or []
            all_rows.extend(batch)

            if len(batch) < batch_size:
                break  # last page
            offset += batch_size

        return all_rows

    def _write_json(self, filename: str, data: list[dict]) -> Path:
        """Writes data as pretty-printed JSON to the output directory."""
        filepath = self.output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)
        return filepath

    def backup_table(
        self,
        table: str,
        columns: str,
        batch_size: int,
    ) -> dict:
        """Backs up a single table and returns a manifest entry."""
        log.info("Backing up table: %s (columns: %s)", table, columns[:60] + "..." if len(columns) > 60 else columns)

        if self.dry_run:
            entry = {"table": table, "rows": 0, "file": f"{table}.json", "status": "dry-run"}
            self.manifest.append(entry)
            return entry

        try:
            rows    = self._fetch_table(table, columns, batch_size)
            outfile = f"{table}.json"
            self._write_json(outfile, rows)
            entry = {
                "table":  table,
                "rows":   len(rows),
                "file":   outfile,
                "status": "success",
            }
            log.info("  → %d row(s) → %s", len(rows), outfile)
        except Exception as exc:
            entry = {
                "table":  table,
                "rows":   0,
                "file":   f"{table}.json",
                "status": "error",
                "error":  str(exc),
            }
            log.error("  ✗ Failed to back up %s: %s", table, exc)

        self.manifest.append(entry)
        return entry

    def run(self) -> dict:
        """Runs the full backup and returns a summary dict."""
        started_at = datetime.now(timezone.utc)
        log.info("=" * 55)
        log.info("CareSync AI — Database Backup")
        log.info("Started : %s", started_at.isoformat())
        log.info("Output  : %s", self.output_dir)
        log.info("Dry run : %s", self.dry_run)
        log.info("=" * 55)

        if not self.dry_run:
            self.output_dir.mkdir(parents=True, exist_ok=True)

        # Build table list
        tables_to_backup = list(BACKUP_TABLES)

        if self.include_embeddings:
            # Replace the no-embedding chunks entry with the full version
            tables_to_backup = [
                t for t in tables_to_backup if t[0] != "document_chunks"
            ]
            tables_to_backup.insert(1, EMBEDDING_COLUMN_TABLE)
            log.info("Including embedding vectors in document_chunks backup.")

        if self.include_audit:
            tables_to_backup.append(AUDIT_TABLE)
            log.info("Including transcription_audit table.")

        for table, columns, batch_size in tables_to_backup:
            self.backup_table(table, columns, batch_size)

        completed_at = datetime.now(timezone.utc)
        total_rows   = sum(e.get("rows", 0) for e in self.manifest)
        errors       = [e for e in self.manifest if e["status"] == "error"]

        summary = {
            "schema_version": "1.0.0",
            "started_at":     started_at.isoformat(),
            "completed_at":   completed_at.isoformat(),
            "total_tables":   len(self.manifest),
            "total_rows":     total_rows,
            "errors":         len(errors),
            "success":        len(errors) == 0,
            "tables":         self.manifest,
        }

        if not self.dry_run:
            self._write_json("backup_manifest.json", [summary])
            log.info("Manifest written → backup_manifest.json")

        log.info("=" * 55)
        log.info(
            "Backup complete — %d table(s), %d row(s), %d error(s)",
            len(self.manifest), total_rows, len(errors),
        )
        if errors:
            log.error("Failed tables: %s", [e["table"] for e in errors])
        else:
            log.info("✅ Backup succeeded.")
        log.info("=" * 55)

        return summary


# =============================================================================
# Entry point
# =============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="CareSync AI database backup")
    parser.add_argument(
        "--output-dir", "-o",
        default=os.getenv("BACKUP_DIR", "backups"),
        help="Parent directory for backup output (default: ./backups)",
    )
    parser.add_argument(
        "--include-embeddings",
        action="store_true",
        help="Include VECTOR embedding columns in document_chunks backup",
    )
    parser.add_argument(
        "--include-audit",
        action="store_true",
        help="Include transcription_audit table in backup",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List tables that would be backed up without writing any files",
    )
    args = parser.parse_args()

    # Create timestamped subdirectory
    timestamp  = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    output_dir = Path(args.output_dir) / timestamp

    try:
        backup = DatabaseBackup(
            output_dir         = output_dir,
            include_embeddings = args.include_embeddings,
            include_audit      = args.include_audit,
            dry_run            = args.dry_run,
        )
        result = backup.run()
    except (ValueError, ImportError) as exc:
        log.error("%s", exc)
        sys.exit(1)
    except Exception as exc:
        log.critical("Unhandled backup error: %s", exc, exc_info=True)
        sys.exit(1)

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
