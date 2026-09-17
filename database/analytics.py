"""
database/analytics.py
---------------------
Analytics aggregation handlers for CareSync AI.

Wraps the four analytics SQL RPCs defined in schema.sql to provide
a clean Python API for the admin dashboard and monitoring views.

Functions:
    get_daily_active_users()       — distinct users per day
    get_total_queries_over_time()  — query volume bucketed by hour/day/week
    get_top_queried_topics()       — most frequent terms from user questions
    get_feedback_satisfaction_rate() — upvote/downvote ratio
    get_system_health_metrics()    — p95 latency, error rates, fallback counts

Usage:
    from database.analytics import (
        get_daily_active_users,
        get_total_queries_over_time,
        get_top_queried_topics,
        get_feedback_satisfaction_rate,
        get_system_health_metrics,
    )
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from database.supabase_client import get_supabase_client


def _since_iso(days: int) -> str:
    """Returns an ISO-format UTC timestamp `days` days ago."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# =============================================================================
# User activity
# =============================================================================

def get_daily_active_users(since_days: int = 30) -> list[dict[str, Any]]:
    """
    Returns the count of distinct active users per calendar day for the
    given rolling window.

    An "active user" is any unique user_id that sent at least one chat
    message (role='user') on that day.

    Args:
        since_days: Number of days to look back. Defaults to 30.

    Returns:
        List of dicts ordered by day ascending, each containing:
            day          (str)  — ISO date string "YYYY-MM-DD"
            active_users (int)  — distinct user count for that day

    Raises:
        ValueError:   If since_days < 1.
        RuntimeError: If the Supabase RPC call fails.
    """
    if since_days < 1:
        raise ValueError("since_days must be at least 1.")

    try:
        client = get_supabase_client()
        response = client.rpc(
            "get_daily_active_users",
            {"since_ts": _since_iso(since_days)},
        ).execute()

        results: list[dict[str, Any]] = response.data or []
        print(
            f"[analytics] get_daily_active_users: {len(results)} day(s) "
            f"over last {since_days} day(s)."
        )
        return results

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"get_daily_active_users failed: {exc}") from exc


def get_total_queries_over_time(
    since_days: int = 30,
    bucket_size: str = "day",
) -> list[dict[str, Any]]:
    """
    Returns the total number of user queries bucketed by time interval.

    Args:
        since_days:  Number of days to look back. Defaults to 30.
        bucket_size: Time bucket granularity — "hour", "day", or "week".
                     Defaults to "day".

    Returns:
        List of dicts ordered by bucket ascending, each containing:
            bucket        (str)  — ISO timestamp of the bucket start
            total_queries (int)  — number of user queries in that bucket

    Raises:
        ValueError:   If since_days < 1 or bucket_size is invalid.
        RuntimeError: If the Supabase RPC call fails.
    """
    if since_days < 1:
        raise ValueError("since_days must be at least 1.")

    bucket_size = bucket_size.lower()
    if bucket_size not in {"hour", "day", "week"}:
        raise ValueError(
            f"Invalid bucket_size '{bucket_size}'. Must be 'hour', 'day', or 'week'."
        )

    try:
        client = get_supabase_client()
        response = client.rpc(
            "get_total_queries_over_time",
            {
                "since_ts":    _since_iso(since_days),
                "bucket_size": bucket_size,
            },
        ).execute()

        results: list[dict[str, Any]] = response.data or []
        print(
            f"[analytics] get_total_queries_over_time: {len(results)} bucket(s) "
            f"(bucket={bucket_size}, last {since_days} day(s))."
        )
        return results

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"get_total_queries_over_time failed: {exc}") from exc


# =============================================================================
# Topic analysis
# =============================================================================

def get_top_queried_topics(
    since_days: int = 30,
    top_n: int = 20,
) -> list[dict[str, Any]]:
    """
    Returns the most frequently occurring terms extracted from user queries
    using PostgreSQL full-text lexeme analysis.

    Stop words, short tokens (<=3 chars), and common English words are
    filtered out by the PostgreSQL 'english' text-search dictionary.
    The remaining terms represent the dominant topics and medical keywords
    field workers are asking about.

    Args:
        since_days: Number of days to look back. Defaults to 30.
        top_n:      Number of top terms to return. Defaults to 20.

    Returns:
        List of dicts ordered by frequency descending, each containing:
            term      (str) — extracted lexeme / keyword
            frequency (int) — number of times the term appeared in queries

    Raises:
        ValueError:   If since_days < 1 or top_n < 1.
        RuntimeError: If the Supabase RPC call fails.
    """
    if since_days < 1:
        raise ValueError("since_days must be at least 1.")
    if top_n < 1:
        raise ValueError("top_n must be at least 1.")

    try:
        client = get_supabase_client()
        response = client.rpc(
            "get_top_queried_topics",
            {
                "since_ts": _since_iso(since_days),
                "top_n":    top_n,
            },
        ).execute()

        results: list[dict[str, Any]] = response.data or []
        print(
            f"[analytics] get_top_queried_topics: {len(results)} term(s) "
            f"(top_n={top_n}, last {since_days} day(s))."
        )
        return results

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"get_top_queried_topics failed: {exc}") from exc


# =============================================================================
# Feedback satisfaction
# =============================================================================

def get_feedback_satisfaction_rate(since_days: int = 30) -> dict[str, Any]:
    """
    Returns the overall user satisfaction rate based on upvote/downvote
    feedback on LLM-generated answers.

    Args:
        since_days: Number of days to look back. Defaults to 30.

    Returns:
        Dict containing:
            upvotes           (int)         — total upvotes in window
            downvotes         (int)         — total downvotes in window
            total_votes       (int)         — upvotes + downvotes
            satisfaction_rate (float|None)  — upvotes / total * 100,
                                              None when no votes exist

    Raises:
        ValueError:   If since_days < 1.
        RuntimeError: If the Supabase RPC call fails.
    """
    if since_days < 1:
        raise ValueError("since_days must be at least 1.")

    try:
        client = get_supabase_client()
        response = client.rpc(
            "get_feedback_satisfaction_rate",
            {"since_ts": _since_iso(since_days)},
        ).execute()

        data = response.data or []
        if not data:
            return {
                "upvotes": 0, "downvotes": 0,
                "total_votes": 0, "satisfaction_rate": None,
            }

        result = data[0]
        rate = result.get("satisfaction_rate")
        print(
            f"[analytics] get_feedback_satisfaction_rate: "
            f"upvotes={result.get('upvotes', 0)}, "
            f"downvotes={result.get('downvotes', 0)}, "
            f"rate={rate}% (last {since_days} day(s))."
        )
        return result

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"get_feedback_satisfaction_rate failed: {exc}") from exc


# =============================================================================
# System health
# =============================================================================

def get_system_health_metrics(since_hours: int = 24) -> dict[str, Any]:
    """
    Returns a comprehensive system health snapshot covering latency,
    error rates, timeout rates, and fallback trigger counts.

    A "fallback trigger" is any query that either failed or produced an
    answer containing the no-results fallback message — indicating the
    knowledge base lacked sufficient information to answer the question.

    Args:
        since_hours: Number of hours to look back. Defaults to 24.

    Returns:
        Dict containing:
            total_queries    (int)   — all pipeline executions
            success_count    (int)   — executions with status='success'
            failed_count     (int)   — executions with status='failed'
            timeout_count    (int)   — executions with status='timeout'
            fallback_count   (int)   — failed + fallback-message queries
            error_rate_pct   (float) — failed / total * 100
            timeout_rate_pct (float) — timeout / total * 100
            avg_total_ms     (float) — mean end-to-end latency
            p95_total_ms     (float) — 95th percentile end-to-end latency
            max_total_ms     (float) — worst-case end-to-end latency
            avg_embedding_ms (float) — mean embedding generation time
            avg_retrieval_ms (float) — mean vector search time
            avg_llm_ms       (float) — mean LLM generation time

        All float values are in milliseconds. Returns zeros when no data.

    Raises:
        ValueError:   If since_hours < 1.
        RuntimeError: If the Supabase RPC call fails.
    """
    if since_hours < 1:
        raise ValueError("since_hours must be at least 1.")

    since_ts = (
        datetime.now(timezone.utc) - timedelta(hours=since_hours)
    ).isoformat()

    _zero: dict[str, Any] = {
        "total_queries": 0, "success_count": 0, "failed_count": 0,
        "timeout_count": 0, "fallback_count": 0,
        "error_rate_pct": 0.0, "timeout_rate_pct": 0.0,
        "avg_total_ms": 0.0, "p95_total_ms": 0.0, "max_total_ms": 0.0,
        "avg_embedding_ms": 0.0, "avg_retrieval_ms": 0.0, "avg_llm_ms": 0.0,
    }

    try:
        client = get_supabase_client()
        response = client.rpc(
            "get_system_health_metrics",
            {"since_ts": since_ts},
        ).execute()

        data = response.data or []
        if not data:
            return _zero

        result = data[0]
        print(
            f"[analytics] get_system_health_metrics: "
            f"total={result.get('total_queries', 0)}, "
            f"errors={result.get('error_rate_pct', 0):.1f}%, "
            f"p95={result.get('p95_total_ms', 0):.1f}ms "
            f"(last {since_hours}h)."
        )
        return result

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"get_system_health_metrics failed: {exc}") from exc
