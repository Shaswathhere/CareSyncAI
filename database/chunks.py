"""
database/chunks.py
------------------
CRUD handlers for the `document_chunks` table in Supabase.

Responsibilities:
- Bulk-insert text chunks with 384-dim vector embeddings.
- Run hybrid cosine similarity + full-text search against the pgvector index
  via the `match_document_chunks` SQL function defined in schema.sql.
  Supports keyword search and effective_date range filters.
- Bulk-fetch all chunks for multiple document IDs in a single RPC call.
- All retrieval operations are wrapped with query performance logging.

Usage:
    from database.chunks import (
        insert_document_chunks,
        search_similar_chunks,
        bulk_fetch_chunks_by_documents,
    )
"""

from __future__ import annotations

from datetime import date
from typing import Any

from database.supabase_client import get_supabase_client
from database.query_logger import log_query_performance

# Batch size for bulk inserts — keeps individual Supabase requests manageable
_INSERT_BATCH_SIZE = 100


def insert_document_chunks(
    chunks_with_embeddings: list[dict[str, Any]],
) -> int:
    """
    Bulk-inserts document chunks with their 384-dimensional vector embeddings
    into the `document_chunks` table.

    Each chunk dict must contain:
        document_id (str):       UUID of the parent document.
        chunk_index (int):       0-based position of this chunk within the document.
        page_number (int):       Source page number — used for citation display.
        content     (str):       Raw text content of the chunk.
        embedding   (list[float]): 384-dimensional vector from Sentence Transformers.
        metadata    (dict):      Optional JSONB bag (title, version, status, etc.).

    Args:
        chunks_with_embeddings: List of chunk dicts as described above.

    Returns:
        Total number of rows successfully inserted.

    Raises:
        ValueError:   If the input list is empty or a chunk is missing required fields.
        RuntimeError: If the Supabase insert fails.
    """
    if not chunks_with_embeddings:
        raise ValueError("chunks_with_embeddings must not be empty.")

    required_fields = {"document_id", "chunk_index", "page_number", "content", "embedding"}

    rows: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks_with_embeddings):
        missing = required_fields - chunk.keys()
        if missing:
            raise ValueError(
                f"Chunk at index {i} is missing required fields: {', '.join(sorted(missing))}."
            )

        embedding = chunk["embedding"]
        if not isinstance(embedding, (list, tuple)) or len(embedding) != 384:
            raise ValueError(
                f"Chunk at index {i} has an invalid embedding — "
                f"expected a list of 384 floats, got length {len(embedding) if hasattr(embedding, '__len__') else 'unknown'}."
            )

        rows.append({
            "document_id": str(chunk["document_id"]),
            "chunk_index": int(chunk["chunk_index"]),
            "page_number": int(chunk["page_number"]),
            "content":     str(chunk["content"]),
            "embedding":   list(embedding),          # pgvector expects a plain list
            "metadata":    chunk.get("metadata") or {},
        })

    try:
        client = get_supabase_client()
        total_inserted = 0

        # Insert in batches to avoid hitting Supabase request size limits
        for batch_start in range(0, len(rows), _INSERT_BATCH_SIZE):
            batch = rows[batch_start : batch_start + _INSERT_BATCH_SIZE]
            response = client.table("document_chunks").insert(batch).execute()

            if response.data is None:
                raise RuntimeError(
                    f"Batch insert returned no data for batch starting at index {batch_start}. "
                    "Check Supabase RLS policies."
                )

            total_inserted += len(response.data)

        print(
            f"[chunks] Inserted {total_inserted} chunk(s) across "
            f"{len(rows) // _INSERT_BATCH_SIZE + 1} batch(es)."
        )
        return total_inserted

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to insert document chunks: {exc}") from exc


def search_similar_chunks(
    query_vector: list[float],
    match_count: int = 5,
    status_filter: str = "ACTIVE",
    keyword: str | None = None,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
) -> list[dict[str, Any]]:
    """
    Hybrid search: combines cosine vector similarity with optional full-text
    keyword matching and effective_date range filtering.

    Calls the `match_document_chunks` SQL RPC function (schema.sql) which:
      1. Scores each chunk by cosine similarity to query_vector.
      2. Adds a ts_rank full-text score when keyword is provided.
      3. Filters by document status, and optionally by effective_date range.
      4. Returns results ordered by combined_score DESC.

    Args:
        query_vector:  384-dimensional query embedding from Sentence Transformers.
                       Must be exactly 384 floats.
        match_count:   Maximum number of results to return. Defaults to 5.
        status_filter: Restrict to documents with this lifecycle status.
                       One of ACTIVE | SUPERSEDED | ARCHIVED. Defaults to "ACTIVE".
        keyword:       Optional keyword string for full-text boosting.
                       Uses PostgreSQL plainto_tsquery with english dictionary.
                       Pass None or "" to use pure vector similarity only.
        date_from:     Optional lower bound on document effective_date (inclusive).
                       Accepts a date object or ISO string "YYYY-MM-DD".
        date_to:       Optional upper bound on document effective_date (inclusive).
                       Accepts a date object or ISO string "YYYY-MM-DD".

    Returns:
        List of result dicts ordered by combined_score DESC, each containing:
            chunk_id, document_id, title, version, effective_date, status,
            chunk_index, page_number, content, metadata,
            vector_similarity (float 0–1),
            text_rank         (float, 0 when no keyword given),
            combined_score    (float, vector_similarity + text_rank).

    Raises:
        ValueError:   If query_vector is not 384-dimensional, status_filter is
                      invalid, or date values cannot be parsed.
        RuntimeError: If the Supabase RPC call fails.
    """
    VALID_STATUSES = {"ACTIVE", "SUPERSEDED", "ARCHIVED"}

    # --- Input validation ---
    if not isinstance(query_vector, (list, tuple)) or len(query_vector) != 384:
        raise ValueError(
            f"query_vector must be a list of 384 floats, "
            f"got length {len(query_vector) if hasattr(query_vector, '__len__') else 'unknown'}."
        )

    status_filter = status_filter.upper()
    if status_filter not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status_filter '{status_filter}'. "
            f"Must be one of: {', '.join(VALID_STATUSES)}."
        )

    if match_count < 1:
        raise ValueError("match_count must be at least 1.")

    # Normalise date args to ISO strings for Supabase REST API
    def _to_iso(d: date | str | None) -> str | None:
        if d is None:
            return None
        if isinstance(d, date):
            return d.isoformat()
        return str(d)

    date_from_iso = _to_iso(date_from)
    date_to_iso   = _to_iso(date_to)

    # Normalise keyword — treat empty string same as None
    kw = keyword.strip() if keyword and keyword.strip() else None

    # --- Build RPC params ---
    rpc_params: dict[str, Any] = {
        "query_embedding": list(query_vector),
        "match_count":     match_count,
        "filter_status":   status_filter,
        "keyword":         kw,
        "date_from":       date_from_iso,
        "date_to":         date_to_iso,
    }

    try:
        client = get_supabase_client()

        with log_query_performance(
            "search_similar_chunks",
            match_count=match_count,
            status_filter=status_filter,
            keyword=kw,
            date_from=date_from_iso,
            date_to=date_to_iso,
            query_embedding=list(query_vector),  # will be sanitised to vector[384]
        ) as perf_log:
            response = client.rpc("match_document_chunks", rpc_params).execute()
            results: list[dict[str, Any]] = response.data or []
            perf_log.result_count = len(results)

        print(
            f"[chunks] Hybrid search returned {len(results)} result(s) "
            f"(match_count={match_count}, status={status_filter}, "
            f"keyword={kw!r}, date_from={date_from_iso}, date_to={date_to_iso})."
        )
        return results

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Hybrid vector search failed: {exc}") from exc


def delete_chunks_by_document_id(document_id: str) -> int:
    """
    Explicitly deletes all chunk vectors belonging to a specific document_id.

    Args:
        document_id: UUID string of the parent document.

    Returns:
        Number of chunk records deleted.
    """
    if not document_id or not document_id.strip():
        raise ValueError("document_id must not be empty.")

    try:
        client = get_supabase_client()
        response = (
            client.table("document_chunks")
            .delete()
            .eq("document_id", document_id.strip())
            .execute()
        )
        deleted = response.data or []
        count = len(deleted)
        print(f"[chunks] Deleted {count} chunk(s) for document_id={document_id}.")
        return count
    except Exception as exc:
        raise RuntimeError(f"Failed to delete chunks for document_id={document_id}: {exc}") from exc


def fetch_chunk_count_by_document(document_id: str) -> int:
    """
    Returns the total number of chunks stored for a document_id.

    Args:
        document_id: UUID string of the document.

    Returns:
        Chunk count integer.
    """
    if not document_id or not document_id.strip():
        return 0

    try:
        client = get_supabase_client()
        response = (
            client.table("document_chunks")
            .select("id", count="exact")
            .eq("document_id", document_id.strip())
            .execute()
        )
        return response.count or 0
    except Exception as exc:
        print(f"[chunks] Failed to fetch chunk count for document_id={document_id}: {exc}")
        return 0



def bulk_fetch_chunks_by_documents(
    document_ids: list[str],
) -> list[dict[str, Any]]:
    """
    Fetches all chunks for a list of document UUIDs in a single optimised
    RPC call to the `bulk_fetch_chunks_by_documents` SQL function.

    Use this instead of calling search_similar_chunks per document when you
    need to retrieve the complete chunk set for multiple documents at once —
    for example, when re-indexing, exporting, or inspecting document content.

    Args:
        document_ids: List of document UUID strings to fetch chunks for.
                      Must contain at least one entry.

    Returns:
        List of chunk dicts ordered by (document_id, chunk_index), each containing:
            chunk_id, document_id, title, version, effective_date, status,
            chunk_index, page_number, content, metadata, created_at.

    Raises:
        ValueError:   If document_ids is empty or contains blank strings.
        RuntimeError: If the Supabase RPC call fails.
    """
    if not document_ids:
        raise ValueError("document_ids must not be empty.")

    clean_ids = [d.strip() for d in document_ids if d and d.strip()]
    if not clean_ids:
        raise ValueError("document_ids contains no valid UUID strings.")

    try:
        client = get_supabase_client()

        with log_query_performance(
            "bulk_fetch_chunks_by_documents",
            document_count=len(clean_ids),
        ) as perf_log:
            response = client.rpc(
                "bulk_fetch_chunks_by_documents",
                {"doc_ids": clean_ids},
            ).execute()

            results: list[dict[str, Any]] = response.data or []
            perf_log.result_count = len(results)

        print(
            f"[chunks] bulk_fetch_chunks_by_documents: fetched {len(results)} chunk(s) "
            f"across {len(clean_ids)} document(s) "
            f"in {perf_log.latency_ms:.2f}ms."
        )
        return results

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"bulk_fetch_chunks_by_documents failed for {len(clean_ids)} doc(s): {exc}"
        ) from exc
