"""
database/connection_pool.py
---------------------------
Connection pool for Supabase REST API clients in CareSync AI.

The Supabase Python SDK uses HTTP under the hood (not raw TCP sockets), so
"pooling" here means managing a bounded set of pre-initialised Supabase Client
objects and lending them to callers via a thread-safe queue.  This avoids the
overhead of re-constructing the SDK client (which validates credentials, sets
up headers, etc.) on every request in high-concurrency scenarios such as the
Streamlit app serving multiple concurrent users.

Key features:
  - Bounded pool with configurable max_connections (default: DB_POOL_MAX_CONNECTIONS)
  - Thread-safe get/release using queue.Queue
  - Configurable timeout — raises PoolTimeoutError when no connection is free
  - Context-manager interface for automatic release
  - Pool health-check via pool_health_check()
  - Lazy initialisation — connections created on first use

Usage:
    from database.connection_pool import get_pool_client, ConnectionPool

    # Context manager (recommended — auto-releases on exit)
    with get_pool_client() as client:
        client.table("documents").select("id").limit(1).execute()

    # Manual get/release
    pool = ConnectionPool.get_instance()
    client = pool.acquire()
    try:
        client.table("documents").select("id").execute()
    finally:
        pool.release(client)
"""

from __future__ import annotations

import logging
import queue
import threading
from contextlib import contextmanager
from typing import Generator

from supabase import create_client, Client

from config import (
    SUPABASE_URL,
    SUPABASE_KEY,
    DB_POOL_MAX_CONNECTIONS,
    DB_POOL_TIMEOUT_SECONDS,
)

logger = logging.getLogger("caresync.db.pool")


class PoolTimeoutError(RuntimeError):
    """Raised when no connection becomes available within the timeout window."""


class ConnectionPool:
    """
    Thread-safe bounded pool of Supabase Client objects.

    Attributes:
        max_connections (int): Maximum number of simultaneous clients.
        timeout (int):         Seconds to wait for a free slot.
    """

    _instance: ConnectionPool | None = None
    _lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        max_connections: int = DB_POOL_MAX_CONNECTIONS,
        timeout: int = DB_POOL_TIMEOUT_SECONDS,
    ) -> None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_KEY must be set before initialising the connection pool."
            )

        self.max_connections = max(1, max_connections)
        self.timeout         = max(1, timeout)
        self._pool: queue.Queue[Client] = queue.Queue(maxsize=self.max_connections)
        self._created        = 0
        self._create_lock    = threading.Lock()

        logger.info(
            "ConnectionPool initialised: max_connections=%d, timeout=%ds",
            self.max_connections,
            self.timeout,
        )

    # -------------------------------------------------------------------------
    # Singleton
    # -------------------------------------------------------------------------

    @classmethod
    def get_instance(
        cls,
        max_connections: int = DB_POOL_MAX_CONNECTIONS,
        timeout: int = DB_POOL_TIMEOUT_SECONDS,
    ) -> "ConnectionPool":
        """
        Returns the process-wide singleton pool, creating it on first call.

        Thread-safe — multiple threads calling this simultaneously will all
        receive the same instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(max_connections=max_connections, timeout=timeout)
        return cls._instance

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _create_client(self) -> Client:
        """Creates a new Supabase client and logs the event."""
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.debug("Created new Supabase client (total created: %d).", self._created)
        return client

    # -------------------------------------------------------------------------
    # Public interface
    # -------------------------------------------------------------------------

    def acquire(self) -> Client:
        """
        Borrows a Supabase Client from the pool.

        If a pre-created idle client is available it is returned immediately.
        If the pool has not yet reached max_connections a new client is created.
        Otherwise the caller blocks for up to `timeout` seconds.

        Returns:
            An idle Supabase Client ready for use.

        Raises:
            PoolTimeoutError: If no client becomes available within the timeout.
        """
        # Try to get an idle client without blocking first
        try:
            client = self._pool.get_nowait()
            logger.debug("Acquired idle client from pool.")
            return client
        except queue.Empty:
            pass

        # Pool is empty — create a new client if below the cap
        with self._create_lock:
            if self._created < self.max_connections:
                self._created += 1
                client = self._create_client()
                logger.debug(
                    "Created new client (%d/%d in use).",
                    self._created,
                    self.max_connections,
                )
                return client

        # At capacity — wait for a release
        logger.debug(
            "Pool at capacity (%d/%d). Waiting up to %ds for a free client ...",
            self._created,
            self.max_connections,
            self.timeout,
        )
        try:
            client = self._pool.get(timeout=self.timeout)
            logger.debug("Acquired client after wait.")
            return client
        except queue.Empty:
            raise PoolTimeoutError(
                f"No Supabase connection became available within {self.timeout}s. "
                f"Pool size: {self.max_connections}. "
                "Consider increasing DB_POOL_MAX_CONNECTIONS or DB_POOL_TIMEOUT_SECONDS."
            )

    def release(self, client: Client) -> None:
        """
        Returns a client to the pool for reuse.

        If the pool queue is somehow full (shouldn't happen in normal use),
        the client is discarded rather than blocking.

        Args:
            client: The client borrowed via acquire().
        """
        try:
            self._pool.put_nowait(client)
            logger.debug("Released client back to pool.")
        except queue.Full:
            # Pool is already full — discard the extra client
            logger.warning("Pool queue full on release — discarding extra client.")

    @property
    def idle_count(self) -> int:
        """Number of clients currently idle in the pool."""
        return self._pool.qsize()

    @property
    def active_count(self) -> int:
        """Approximate number of clients currently in use."""
        return self._created - self._pool.qsize()

    def pool_stats(self) -> dict:
        """Returns a snapshot of pool utilisation metrics."""
        return {
            "max_connections": self.max_connections,
            "total_created":   self._created,
            "idle":            self.idle_count,
            "active":          self.active_count,
            "timeout_seconds": self.timeout,
        }


# =============================================================================
# Convenience helpers
# =============================================================================

@contextmanager
def get_pool_client() -> Generator[Client, None, None]:
    """
    Context manager that acquires a Supabase client from the singleton pool
    and automatically releases it on exit — even if an exception is raised.

    Usage:
        with get_pool_client() as client:
            response = client.table("documents").select("id").execute()

    Raises:
        PoolTimeoutError: If the pool is exhausted and the timeout expires.
    """
    pool   = ConnectionPool.get_instance()
    client = pool.acquire()
    try:
        yield client
    finally:
        pool.release(client)


def pool_health_check() -> dict:
    """
    Verifies the pool is operational by acquiring a client, running a
    lightweight query, and releasing the client.

    Returns:
        Dict with keys:
            healthy      (bool)  — True if the check passed
            idle         (int)   — idle connections in the pool
            active       (int)   — connections currently in use
            max          (int)   — pool capacity
            error        (str|None) — error message if health check failed
    """
    try:
        with get_pool_client() as client:
            client.table("documents").select("id").limit(1).execute()
        pool  = ConnectionPool.get_instance()
        stats = pool.pool_stats()
        logger.info(
            "Pool health check: OK — idle=%d, active=%d, max=%d",
            stats["idle"],
            stats["active"],
            stats["max_connections"],
        )
        return {
            "healthy": True,
            "idle":    stats["idle"],
            "active":  stats["active"],
            "max":     stats["max_connections"],
            "error":   None,
        }
    except Exception as exc:
        logger.error("Pool health check FAILED: %s", exc)
        return {
            "healthy": False,
            "idle":    0,
            "active":  0,
            "max":     DB_POOL_MAX_CONNECTIONS,
            "error":   str(exc),
        }
