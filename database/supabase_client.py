"""
database/supabase_client.py
---------------------------
Supabase client initialisation, database health-check, and query optimisation
helpers for CareSync AI.

Provides:
  - Singleton client via get_supabase_client() (backward-compatible)
  - Pool-aware client via get_pool_client() context manager
  - check_db_connection() health check
  - set_hnsw_ef_search() to tune pgvector recall at session level

Usage:
    from database.supabase_client import get_supabase_client, check_db_connection
    from database.connection_pool import get_pool_client
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from supabase import create_client, Client

from config import SUPABASE_URL, SUPABASE_KEY, HNSW_EF_SEARCH

logger = logging.getLogger("caresync.db")

# Supabase/PostgREST caps request payload size — chunk bulk inserts to stay safe.
_CHUNK_INSERT_BATCH_SIZE = 200

# Module-level singleton — reuse across calls within the same process.
_client: Client | None = None


def get_supabase_client() -> Client:
    """
    Returns a singleton Supabase client initialised with credentials
    from environment variables (SUPABASE_URL, SUPABASE_KEY).

    Raises:
        ValueError: If SUPABASE_URL or SUPABASE_KEY are not set.
    """
    global _client

    if _client is not None:
        return _client

    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY must be set. "
            "Copy .env.example to .env and populate the values."
        )

    _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def check_db_connection() -> bool:
    """
    Validates the Supabase connection by executing a lightweight query
    against the documents table.

    Returns:
        True  — connection is healthy and the documents table is reachable.
        False — connection failed or the table does not exist yet.
    """
    try:
        client = get_supabase_client()
        # Minimal read — only fetch one id to keep it cheap
        client.table("documents").select("id").limit(1).execute()
        print("[CareSync AI] Database connection: OK")
        return True
    except Exception as exc:
        print(f"[CareSync AI] Database connection failed: {exc}")
        return False


def insert_document_record(
    document_metadata: Dict[str, Any],
    chunks: List[Dict[str, Any]] | None = None,
) -> str:
    """
    Persists a processed document to the knowledge base: one row in
    `documents`, plus one row per chunk (with its embedding) in
    `document_chunks`.

    Args:
        document_metadata: Dict with title, version, effective_date, status
            — same shape passed into process_and_embed_document().
        chunks: Chunk dicts produced by process_and_embed_document()
            (chunk_index, page_number, content, embedding, metadata).

    Returns:
        The newly created document's UUID (str).
    """
    client = get_supabase_client()

    effective_date = document_metadata.get("effective_date")
    doc_row = {
        "title": document_metadata.get("title", "Untitled Document"),
        "version": document_metadata.get("version", "v1"),
        "effective_date": str(effective_date) if effective_date else None,
        "status": document_metadata.get("status", "ACTIVE"),
    }

    doc_response = client.table("documents").insert(doc_row).execute()
    document_id = doc_response.data[0]["id"]

    if chunks:
        chunk_rows = [
            {
                "document_id": document_id,
                "chunk_index": chunk["chunk_index"],
                "page_number": chunk["page_number"],
                "content": chunk["content"],
                "embedding": chunk["embedding"],
                "metadata": chunk.get("metadata", {}),
            }
            for chunk in chunks
        ]
        for i in range(0, len(chunk_rows), _CHUNK_INSERT_BATCH_SIZE):
            batch = chunk_rows[i : i + _CHUNK_INSERT_BATCH_SIZE]
            client.table("document_chunks").insert(batch).execute()

    return document_id


def fetch_all_documents() -> List[Dict[str, Any]]:
    """
    Fetches the full document inventory from `documents`, most recently
    uploaded first, for the Document Inventory view.

    Returns:
        List of dicts with title, version, effective_date, status.
        Returns an empty list on any failure (e.g. Supabase not configured
        yet) — callers should fall back to session/mock data in that case.
    """
    try:
        client = get_supabase_client()
        response = (
            client.table("documents")
            .select("title, version, effective_date, status, created_at")
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as exc:
        print(f"[CareSync AI] fetch_all_documents failed: {exc}")
        return []
