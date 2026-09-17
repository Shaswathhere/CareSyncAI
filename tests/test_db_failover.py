"""
tests/test_db_failover.py
-------------------------
Connection failover resilience tests for the CareSync AI database layer.

Verifies that the application degrades gracefully when the Supabase connection
fails transiently or permanently — no unhandled exceptions bubble to the UI,
health checks return the correct status, and retry logic recovers when the
connection is restored.

Run:
    python -m pytest tests/test_db_failover.py -v
"""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call

# ---------------------------------------------------------------------------
# Stub the `supabase` package so tests run without it installed
# ---------------------------------------------------------------------------
_supabase_stub = types.ModuleType("supabase")
_supabase_stub.create_client = MagicMock()
_supabase_stub.Client = MagicMock
sys.modules.setdefault("supabase", _supabase_stub)


# ---------------------------------------------------------------------------
# check_db_connection resilience
# ---------------------------------------------------------------------------

class HealthCheckFailoverTests(unittest.TestCase):
    """check_db_connection() must never raise — always returns True/False."""

    @patch("database.supabase_client.get_supabase_client")
    def test_returns_true_on_healthy_connection(self, mock_get: MagicMock) -> None:
        from database.supabase_client import check_db_connection

        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.table.return_value.select.return_value.limit.return_value \
            .execute.return_value = MagicMock(data=[{"id": "abc"}])

        self.assertTrue(check_db_connection())

    @patch("database.supabase_client.get_supabase_client")
    def test_returns_false_on_connection_error(self, mock_get: MagicMock) -> None:
        from database.supabase_client import check_db_connection

        mock_get.side_effect = Exception("Connection refused")
        self.assertFalse(check_db_connection())

    @patch("database.supabase_client.get_supabase_client")
    def test_returns_false_on_query_timeout(self, mock_get: MagicMock) -> None:
        from database.supabase_client import check_db_connection

        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.table.return_value.select.return_value.limit.return_value \
            .execute.side_effect = TimeoutError("Query timed out")

        self.assertFalse(check_db_connection())


# ---------------------------------------------------------------------------
# Pool health check failover
# ---------------------------------------------------------------------------

class PoolHealthCheckFailoverTests(unittest.TestCase):
    """pool_health_check() must return a dict, never raise."""

    @patch("database.connection_pool.get_pool_client")
    def test_healthy_pool_returns_healthy_dict(self, mock_ctx: MagicMock) -> None:
        from database.connection_pool import pool_health_check, ConnectionPool

        # Reset singleton and patch credentials so pool_stats() works
        ConnectionPool._instance = None

        mock_client = MagicMock()
        mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_client)
        mock_ctx.return_value.__exit__  = MagicMock(return_value=False)
        mock_client.table.return_value.select.return_value.limit.return_value \
            .execute.return_value = MagicMock(data=[])

        with patch("database.connection_pool.SUPABASE_URL", "https://test.supabase.co"), \
             patch("database.connection_pool.SUPABASE_KEY", "test-key"):
            # Pre-create the instance so pool_stats() doesn't hit credential check
            ConnectionPool.get_instance(max_connections=5, timeout=5)
            result = pool_health_check()

        self.assertTrue(result["healthy"])
        self.assertIsNone(result["error"])

    @patch("database.connection_pool.get_pool_client")
    def test_failed_connection_returns_unhealthy_dict(self, mock_ctx: MagicMock) -> None:
        from database.connection_pool import pool_health_check

        mock_ctx.return_value.__enter__ = MagicMock(side_effect=RuntimeError("DB down"))
        mock_ctx.return_value.__exit__  = MagicMock(return_value=False)

        result = pool_health_check()
        self.assertFalse(result["healthy"])
        self.assertIn("DB down", result["error"])


# ---------------------------------------------------------------------------
# fetch_all_documents failover
# ---------------------------------------------------------------------------

class FetchDocumentsFailoverTests(unittest.TestCase):
    """fetch_all_documents() should return an empty list, not raise, on failure."""

    @patch("database.supabase_client.get_supabase_client")
    def test_returns_empty_list_on_network_error(self, mock_get: MagicMock) -> None:
        from database.supabase_client import fetch_all_documents

        mock_get.side_effect = ConnectionError("Network unreachable")
        result = fetch_all_documents()
        self.assertEqual([], result)

    @patch("database.supabase_client.get_supabase_client")
    def test_returns_empty_list_on_supabase_api_error(self, mock_get: MagicMock) -> None:
        from database.supabase_client import fetch_all_documents

        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.table.return_value.select.return_value \
            .order.return_value.execute.side_effect = Exception("API rate limited")

        result = fetch_all_documents()
        self.assertEqual([], result)


# ---------------------------------------------------------------------------
# search_similar_chunks failover
# ---------------------------------------------------------------------------

class SearchChunksFailoverTests(unittest.TestCase):
    """search_similar_chunks() should raise RuntimeError on failure (not crash silently)."""

    @patch("database.chunks.get_supabase_client")
    def test_raises_runtime_error_on_rpc_failure(self, mock_get: MagicMock) -> None:
        from database.chunks import search_similar_chunks

        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.rpc.return_value.execute.side_effect = Exception("pgvector unavailable")

        with self.assertRaises(RuntimeError) as ctx:
            search_similar_chunks(query_vector=[0.0] * 384)

        self.assertIn("pgvector unavailable", str(ctx.exception))

    @patch("database.chunks.get_supabase_client")
    def test_raises_on_invalid_vector_dimension(self, mock_get: MagicMock) -> None:
        from database.chunks import search_similar_chunks

        with self.assertRaises(ValueError):
            search_similar_chunks(query_vector=[0.0] * 128)  # wrong dim


# ---------------------------------------------------------------------------
# Retry-on-transient-error pattern
# ---------------------------------------------------------------------------

class TransientErrorRetryTests(unittest.TestCase):
    """
    Verifies that callers can implement simple retry logic around DB calls
    and that the connection recovers after a transient failure.
    """

    @patch("database.supabase_client.get_supabase_client")
    def test_retry_succeeds_after_one_transient_failure(self, mock_get: MagicMock) -> None:
        """
        Simulates a transient DB error on the first call, succeeded by a
        successful call on the second attempt. The retry loop should succeed.
        """
        from database.supabase_client import check_db_connection

        mock_client = MagicMock()
        # First call raises, second call succeeds
        mock_client.table.return_value.select.return_value.limit.return_value \
            .execute.side_effect = [
                Exception("Transient network blip"),
                MagicMock(data=[{"id": "ok"}]),
            ]
        mock_get.return_value = mock_client

        # Simple retry loop — mirrors what production code should do
        max_retries = 3
        for attempt in range(max_retries):
            result = check_db_connection()
            if result:
                break

        self.assertTrue(result, "Expected recovery after retry")
        self.assertEqual(
            2,
            mock_client.table.return_value.select.return_value.limit.return_value
                .execute.call_count,
            "Expected exactly 2 execute() calls (1 failure + 1 success)",
        )

    @patch("database.chunks.get_supabase_client")
    def test_insert_raises_clearly_on_persistent_failure(self, mock_get: MagicMock) -> None:
        """insert_document_chunks raises RuntimeError when Supabase persistently fails."""
        from database.chunks import insert_document_chunks

        mock_client = MagicMock()
        mock_get.return_value = mock_client
        mock_client.table.return_value.insert.return_value \
            .execute.side_effect = Exception("Supabase 503 Service Unavailable")

        chunk = {
            "document_id": "doc-001",
            "chunk_index": 0,
            "page_number": 1,
            "content":     "test",
            "embedding":   [0.0] * 384,
            "metadata":    {},
        }

        with self.assertRaises(RuntimeError) as ctx:
            insert_document_chunks([chunk])

        self.assertIn("503", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
