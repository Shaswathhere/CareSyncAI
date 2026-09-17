"""
database/query_logger.py
------------------------
Query performance logger for CareSync AI database operations.

Measures and records latency for every retrieval call so slow queries
can be identified during development and production monitoring.

Usage:
    from database.query_logger import log_query_performance, QueryLog

    with log_query_performance("search_similar_chunks", match_count=5) as log:
        results = ...  # your query here

    # Or call directly after a timed block:
    log_query_performance.record(operation="bulk_fetch", latency_ms=42.3, result_count=10)
"""

from __future__ import annotations

import time
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generator

# ---------------------------------------------------------------------------
# Module-level logger — writes to the standard Python logging pipeline.
# Set LOG_LEVEL=DEBUG in env to see every query log in the console.
# ---------------------------------------------------------------------------
logger = logging.getLogger("caresync.db")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s %(name)s — %(message)s",
                          datefmt="%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(_handler)
logger.setLevel(logging.DEBUG)


# ---------------------------------------------------------------------------
# QueryLog dataclass — one record per timed operation
# ---------------------------------------------------------------------------
@dataclass
class QueryLog:
    """Captures metadata and timing for a single database query."""
    operation:    str                        # e.g. "search_similar_chunks"
    started_at:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    latency_ms:   float    = 0.0            # wall-clock time in milliseconds
    result_count: int      = 0              # rows / chunks returned
    params:       dict[str, Any] = field(default_factory=dict)  # logged context
    success:      bool     = True
    error:        str | None = None

    def __str__(self) -> str:
        status = "OK" if self.success else f"ERROR({self.error})"
        return (
            f"[QueryLog] op={self.operation!r} "
            f"latency={self.latency_ms:.2f}ms "
            f"rows={self.result_count} "
            f"status={status} "
            f"params={self.params}"
        )


# ---------------------------------------------------------------------------
# In-memory log store — bounded ring buffer (last 500 entries)
# ---------------------------------------------------------------------------
_MAX_LOG_ENTRIES = 500
_query_log_store: list[QueryLog] = []


def _store_log(log: QueryLog) -> None:
    """Append to in-memory store, evicting oldest entry when full."""
    if len(_query_log_store) >= _MAX_LOG_ENTRIES:
        _query_log_store.pop(0)
    _query_log_store.append(log)


def get_recent_logs(n: int = 50) -> list[QueryLog]:
    """
    Returns the n most recent QueryLog entries (newest last).

    Args:
        n: Number of entries to return. Defaults to 50.

    Returns:
        List of QueryLog objects, most recent last.
    """
    return _query_log_store[-n:]


def get_slow_queries(threshold_ms: float = 1000.0) -> list[QueryLog]:
    """
    Returns all logged queries whose latency exceeded threshold_ms.

    Args:
        threshold_ms: Latency threshold in milliseconds. Defaults to 1000ms.

    Returns:
        List of QueryLog objects where latency_ms > threshold_ms.
    """
    return [log for log in _query_log_store if log.latency_ms > threshold_ms]


def get_average_latency(operation: str | None = None) -> float:
    """
    Returns the average latency in milliseconds across all (or operation-
    specific) logged queries.

    Args:
        operation: If provided, averages only logs matching this operation name.

    Returns:
        Average latency in milliseconds, or 0.0 if no matching logs exist.
    """
    logs = (
        [l for l in _query_log_store if l.operation == operation]
        if operation
        else _query_log_store
    )
    if not logs:
        return 0.0
    return sum(l.latency_ms for l in logs) / len(logs)


# ---------------------------------------------------------------------------
# Context manager — primary way to time a block of code
# ---------------------------------------------------------------------------
@contextmanager
def log_query_performance(
    operation: str,
    **params: Any,
) -> Generator[QueryLog, None, None]:
    """
    Context manager that times the enclosed block and writes a QueryLog entry.

    Usage:
        with log_query_performance("search_similar_chunks", match_count=5, status="ACTIVE") as log:
            results = search_similar_chunks(...)
            log.result_count = len(results)

    Args:
        operation: Human-readable operation name, e.g. "search_similar_chunks".
        **params:  Arbitrary key-value pairs logged as context (sanitised —
                   embedding vectors are replaced with their length to avoid
                   flooding the log).

    Yields:
        QueryLog instance — caller can set .result_count on it.
    """
    # Sanitise params: replace long lists (e.g. embeddings) with their length
    safe_params = {
        k: (f"vector[{len(v)}]" if isinstance(v, (list, tuple)) and len(v) > 10 else v)
        for k, v in params.items()
    }

    log = QueryLog(operation=operation, params=safe_params)
    t_start = time.perf_counter()

    try:
        yield log
        log.success = True
    except Exception as exc:
        log.success = False
        log.error = str(exc)
        raise
    finally:
        log.latency_ms = (time.perf_counter() - t_start) * 1000

        _store_log(log)

        # Log at WARNING when slow, DEBUG otherwise
        if log.latency_ms > 1000:
            logger.warning("SLOW QUERY — %s", log)
        elif not log.success:
            logger.error("FAILED QUERY — %s", log)
        else:
            logger.debug("%s", log)
