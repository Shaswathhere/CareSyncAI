"""
database/feedback.py
--------------------
CRUD handlers for chat_feedback and system_metrics tables.

Responsibilities:
- Submit user upvote/downvote ratings on LLM answers with optional comments.
- Query and aggregate feedback by message, session, or user.
- Log end-to-end latency breakdowns for every RAG pipeline execution.
- Query latency summaries and identify slow/failed requests.

Usage:
    from database.feedback import (
        submit_feedback,
        get_message_feedback_summary,
        list_session_feedback,
        list_user_feedback,
        log_metrics,
        get_latency_summary,
        list_slow_queries,
        list_failed_queries,
    )
"""

from __future__ import annotations

from typing import Any

from database.supabase_client import get_supabase_client

VALID_VOTES   = {"upvote", "downvote"}
VALID_STATUSES = {"success", "failed", "timeout"}


# =============================================================================
# chat_feedback handlers
# =============================================================================

def submit_feedback(
    user_id: str,
    vote: str,
    message_id: str | None = None,
    session_id: str | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    """
    Submits a user upvote or downvote on an LLM-generated answer via the
    log_chat_feedback SQL RPC.

    Args:
        user_id:    External user identifier.
        vote:       Rating value — "upvote" or "downvote".
        message_id: UUID of the specific assistant chat_message being rated.
                    Optional but recommended for per-message analytics.
        session_id: UUID of the chat session. Optional.
        comment:    Free-text comment explaining the rating. Optional.

    Returns:
        The created chat_feedback record dict with keys:
            id, user_id, vote, message_id, session_id, comment, created_at.

    Raises:
        ValueError:   If user_id is empty or vote is invalid.
        RuntimeError: If the Supabase RPC call fails.
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id must not be empty.")

    vote = vote.strip().lower()
    if vote not in VALID_VOTES:
        raise ValueError(
            f"Invalid vote '{vote}'. Must be one of: {', '.join(VALID_VOTES)}."
        )

    rpc_params: dict[str, Any] = {
        "p_user_id": user_id.strip(),
        "p_vote":    vote,
    }
    if message_id and message_id.strip():
        rpc_params["p_message_id"] = message_id.strip()
    if session_id and session_id.strip():
        rpc_params["p_session_id"] = session_id.strip()
    if comment and comment.strip():
        rpc_params["p_comment"] = comment.strip()

    try:
        client = get_supabase_client()
        response = client.rpc("log_chat_feedback", rpc_params).execute()

        if not response.data:
            raise RuntimeError("RPC returned no data — check Supabase RLS policies.")

        record = response.data[0]
        print(
            f"[feedback] Feedback submitted: user={user_id!r}, vote={vote}, "
            f"message_id={message_id!r}, id={record['id']}."
        )
        return record

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to submit feedback for user_id={user_id!r}: {exc}") from exc


def get_message_feedback_summary(message_id: str) -> dict[str, Any]:
    """
    Returns aggregated upvote/downvote counts for a specific assistant message
    via the get_feedback_summary SQL RPC.

    Args:
        message_id: UUID of the chat_messages record to summarise.

    Returns:
        Dict with keys: message_id, upvotes (int), downvotes (int), total (int).

    Raises:
        ValueError:   If message_id is empty.
        RuntimeError: If the Supabase RPC call fails.
    """
    if not message_id or not message_id.strip():
        raise ValueError("message_id must not be empty.")

    try:
        client = get_supabase_client()
        response = client.rpc(
            "get_feedback_summary",
            {"p_message_id": message_id.strip()},
        ).execute()

        data = response.data or []
        if not data:
            return {"message_id": message_id, "upvotes": 0, "downvotes": 0, "total": 0}

        return data[0]

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to get feedback summary for message_id={message_id!r}: {exc}"
        ) from exc


def list_session_feedback(
    session_id: str,
    vote_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    Returns all feedback records for a chat session, ordered newest first.

    Args:
        session_id:  UUID of the chat session.
        vote_filter: Optional — filter to "upvote" or "downvote" only.

    Returns:
        List of chat_feedback dicts ordered by created_at DESC.

    Raises:
        ValueError:   If session_id is empty or vote_filter is invalid.
        RuntimeError: If the Supabase query fails.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty.")

    if vote_filter is not None:
        vote_filter = vote_filter.strip().lower()
        if vote_filter not in VALID_VOTES:
            raise ValueError(
                f"Invalid vote_filter '{vote_filter}'. Must be one of: {', '.join(VALID_VOTES)}."
            )

    try:
        client = get_supabase_client()
        query = (
            client.table("chat_feedback")
            .select("id, user_id, vote, message_id, session_id, comment, created_at")
            .eq("session_id", session_id.strip())
            .order("created_at", desc=True)
        )
        if vote_filter:
            query = query.eq("vote", vote_filter)

        response = query.execute()
        records: list[dict[str, Any]] = response.data or []
        print(
            f"[feedback] list_session_feedback: session={session_id!r}, "
            f"vote_filter={vote_filter} → {len(records)} record(s)."
        )
        return records

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to list feedback for session_id={session_id!r}: {exc}"
        ) from exc


def list_user_feedback(
    user_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Returns all feedback submissions by a user, most recent first.

    Args:
        user_id: External user identifier.
        limit:   Maximum records to return. Defaults to 50.

    Returns:
        List of chat_feedback dicts ordered by created_at DESC.

    Raises:
        ValueError:   If user_id is empty.
        RuntimeError: If the Supabase query fails.
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id must not be empty.")

    try:
        client = get_supabase_client()
        response = (
            client.table("chat_feedback")
            .select("id, user_id, vote, message_id, session_id, comment, created_at")
            .eq("user_id", user_id.strip())
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        records: list[dict[str, Any]] = response.data or []
        print(f"[feedback] list_user_feedback: user_id={user_id!r} → {len(records)} record(s).")
        return records

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to list feedback for user_id={user_id!r}: {exc}") from exc


# =============================================================================
# system_metrics handlers
# =============================================================================

def log_metrics(
    user_id: str,
    total_ms: float,
    session_id: str | None = None,
    message_id: str | None = None,
    query_text: str | None = None,
    embedding_ms: float | None = None,
    retrieval_ms: float | None = None,
    rerank_ms: float | None = None,
    llm_ms: float | None = None,
    chunk_count: int | None = None,
    model_name: str | None = None,
    status: str = "success",
    error_message: str | None = None,
) -> dict[str, Any]:
    """
    Logs a RAG pipeline latency breakdown via the log_system_metrics SQL RPC.

    Call this at the end of every query_rag_pipeline() execution to record
    timing data for SLA monitoring and bottleneck analysis.

    Args:
        user_id:       External user identifier.
        total_ms:      Total end-to-end wall-clock time in milliseconds.
        session_id:    Optional UUID of the related chat session.
        message_id:    Optional UUID of the assistant message this relates to.
        query_text:    The user's question (stored for correlation).
        embedding_ms:  Time in ms to generate the query embedding.
        retrieval_ms:  Time in ms for the vector similarity search.
        rerank_ms:     Time in ms for the optional reranking step.
        llm_ms:        Time in ms for the LLM generation call.
        chunk_count:   Number of chunks retrieved and passed to the LLM.
        model_name:    LLM model identifier, e.g. "gemini-3.5-flash".
        status:        Pipeline outcome — "success", "failed", or "timeout".
        error_message: Error detail when status is "failed" or "timeout".

    Returns:
        The created system_metrics record dict.

    Raises:
        ValueError:   If user_id is empty, total_ms < 0, or status is invalid.
        RuntimeError: If the Supabase RPC call fails.
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id must not be empty.")
    if total_ms < 0:
        raise ValueError("total_ms must be a non-negative number.")

    status = status.lower()
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {', '.join(VALID_STATUSES)}."
        )

    rpc_params: dict[str, Any] = {
        "p_user_id":  user_id.strip(),
        "p_total_ms": float(total_ms),
        "p_status":   status,
    }

    # Optional params — only include when provided to keep payload minimal
    optional_map = {
        "p_session_id":   session_id,
        "p_message_id":   message_id,
        "p_query_text":   query_text,
        "p_embedding_ms": embedding_ms,
        "p_retrieval_ms": retrieval_ms,
        "p_rerank_ms":    rerank_ms,
        "p_llm_ms":       llm_ms,
        "p_chunk_count":  chunk_count,
        "p_model_name":   model_name,
        "p_error_message":error_message,
    }
    for key, val in optional_map.items():
        if val is not None:
            rpc_params[key] = val

    try:
        client = get_supabase_client()
        response = client.rpc("log_system_metrics", rpc_params).execute()

        if not response.data:
            raise RuntimeError("RPC returned no data — check Supabase RLS policies.")

        record = response.data[0]
        print(
            f"[feedback] Metrics logged: user={user_id!r}, total={total_ms:.1f}ms, "
            f"status={status}, id={record['id']}."
        )
        return record

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to log metrics for user_id={user_id!r}: {exc}") from exc


def get_latency_summary(since_hours: int = 24) -> dict[str, Any]:
    """
    Returns aggregated latency statistics for a rolling time window via the
    get_latency_summary SQL RPC.

    Args:
        since_hours: Number of hours to look back. Defaults to 24.

    Returns:
        Dict with keys:
            avg_total_ms, p95_total_ms, max_total_ms,
            avg_embedding_ms, avg_retrieval_ms, avg_llm_ms,
            total_queries, failed_queries.
        All float/int values. Returns zeros if no data exists.

    Raises:
        ValueError:   If since_hours < 1.
        RuntimeError: If the Supabase RPC call fails.
    """
    if since_hours < 1:
        raise ValueError("since_hours must be at least 1.")

    from datetime import datetime, timezone, timedelta
    since_ts = (
        datetime.now(timezone.utc) - timedelta(hours=since_hours)
    ).isoformat()

    try:
        client = get_supabase_client()
        response = client.rpc(
            "get_latency_summary",
            {"since_ts": since_ts},
        ).execute()

        data = response.data or []
        if not data:
            return {
                "avg_total_ms": 0.0, "p95_total_ms": 0.0, "max_total_ms": 0.0,
                "avg_embedding_ms": 0.0, "avg_retrieval_ms": 0.0, "avg_llm_ms": 0.0,
                "total_queries": 0, "failed_queries": 0,
            }

        summary = data[0]
        # Replace None with 0 for safety (SQL AVG returns NULL on empty sets)
        for k, v in summary.items():
            if v is None:
                summary[k] = 0.0 if k.endswith('_ms') else 0

        print(
            f"[feedback] Latency summary (last {since_hours}h): "
            f"avg={summary.get('avg_total_ms', 0.0):.1f}ms, "
            f"p95={summary.get('p95_total_ms', 0.0):.1f}ms, "
            f"total={summary.get('total_queries', 0)}."
        )
        return summary

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to get latency summary: {exc}") from exc


def list_slow_queries(
    threshold_ms: float = 5000.0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Returns system_metrics records where total_ms exceeded threshold_ms,
    ordered slowest first.

    Args:
        threshold_ms: Latency threshold in milliseconds. Defaults to 5000ms.
        limit:        Maximum records to return. Defaults to 50.

    Returns:
        List of system_metrics dicts ordered by total_ms DESC.

    Raises:
        ValueError:   If threshold_ms < 0.
        RuntimeError: If the Supabase query fails.
    """
    if threshold_ms < 0:
        raise ValueError("threshold_ms must be non-negative.")

    try:
        client = get_supabase_client()
        response = (
            client.table("system_metrics")
            .select("*")
            .gt("total_ms", threshold_ms)
            .order("total_ms", desc=True)
            .limit(limit)
            .execute()
        )
        records: list[dict[str, Any]] = response.data or []
        print(
            f"[feedback] list_slow_queries: threshold={threshold_ms}ms → "
            f"{len(records)} record(s)."
        )
        return records

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to list slow queries: {exc}") from exc


def list_failed_queries(limit: int = 50) -> list[dict[str, Any]]:
    """
    Returns system_metrics records with status 'failed' or 'timeout',
    ordered most recent first.

    Args:
        limit: Maximum records to return. Defaults to 50.

    Returns:
        List of system_metrics dicts ordered by created_at DESC.

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    try:
        client = get_supabase_client()
        response = (
            client.table("system_metrics")
            .select("*")
            .in_("status", ["failed", "timeout"])
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        records: list[dict[str, Any]] = response.data or []
        print(f"[feedback] list_failed_queries → {len(records)} record(s).")
        return records

    except Exception as exc:
        raise RuntimeError(f"Failed to list failed queries: {exc}") from exc
