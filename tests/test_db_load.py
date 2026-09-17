"""
tests/test_db_load.py
---------------------
Load and stress tests for the CareSync AI database layer.

Tests concurrent access patterns against the connection pool, bulk insert
throughput for document chunks, and parallel search_similar_chunks performance.
All Supabase calls are mocked so the suite runs without a live database.

Run:
    python -m pytest tests/test_db_load.py -v
    # or directly:
    python tests/test_db_load.py
"""

from __future__ import annotations

import sys
import types
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stub the `supabase` package so tests run without it installed
# ---------------------------------------------------------------------------
_supabase_stub = types.ModuleType("supabase")
_supabase_stub.create_client = MagicMock()
_supabase_stub.Client = MagicMock
sys.modules.setdefault("supabase", _supabase_stub)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_embedding(dim: int = 384) -> list[float]:
    """Returns a zeroed embedding of `dim` floats."""
    return [0.0] * dim


def _make_chunk(index: int, doc_id: str = "doc-001") -> dict:
    return {
        "document_id": doc_id,
        "chunk_index": index,
        "page_number": index + 1,
        "content":     f"Sample chunk content number {index}.",
        "embedding":   _make_fake_embedding(),
        "metadata":    {"source": "test"},
    }


# ---------------------------------------------------------------------------
# Connection pool stress tests
# ---------------------------------------------------------------------------

class ConnectionPoolStressTests(unittest.TestCase):
    """Verifies the pool handles concurrent acquire/release correctly."""

    def _make_pool(self, max_connections: int = 10, timeout: int = 5):
        """Create a pool with patched credentials."""
        from database.connection_pool import ConnectionPool
        with patch("database.connection_pool.SUPABASE_URL", "https://test.supabase.co"), \
             patch("database.connection_pool.SUPABASE_KEY", "test-key"):
            return ConnectionPool(max_connections=max_connections, timeout=timeout)

    def test_concurrent_acquires_within_pool_limit(self) -> None:
        """N threads each acquire and release a client — no deadlock or error."""
        pool = self._make_pool(max_connections=10)

        errors: list[Exception] = []
        results: list[str] = []
        lock = threading.Lock()

        def _worker(worker_id: int) -> None:
            try:
                client = pool.acquire()
                time.sleep(0.01)   # simulate a short DB operation
                pool.release(client)
                with lock:
                    results.append(f"ok-{worker_id}")
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual([], errors, f"Unexpected errors: {errors}")
        self.assertEqual(20, len(results))

    def test_pool_timeout_raised_when_exhausted(self) -> None:
        """When all slots are held, acquire() raises PoolTimeoutError."""
        from database.connection_pool import PoolTimeoutError

        pool = self._make_pool(max_connections=2, timeout=1)

        # Hold all connections in background threads
        acquired: list = []
        ready   = threading.Event()
        release = threading.Event()

        def _hold() -> None:
            c = pool.acquire()
            acquired.append(c)
            ready.set()
            release.wait(timeout=5)
            pool.release(c)

        holders = [threading.Thread(target=_hold) for _ in range(2)]
        for h in holders:
            h.start()

        # Wait until both slots are taken
        for _ in range(2):
            ready.wait(timeout=2)
            ready.clear()

        # Now a third acquire should timeout
        with self.assertRaises(PoolTimeoutError):
            pool.acquire()

        release.set()
        for h in holders:
            h.join()

    def test_pool_stats_reflect_active_connections(self) -> None:
        """pool_stats() returns accurate active/idle counts."""
        pool   = self._make_pool(max_connections=5)
        client = pool.acquire()

        stats = pool.pool_stats()
        self.assertEqual(1, stats["total_created"])
        self.assertEqual(0, stats["idle"])
        self.assertEqual(1, stats["active"])

        pool.release(client)
        stats = pool.pool_stats()
        self.assertEqual(1, stats["idle"])
        self.assertEqual(0, stats["active"])


# ---------------------------------------------------------------------------
# Bulk insert throughput tests
# ---------------------------------------------------------------------------

class BulkInsertThroughputTests(unittest.TestCase):
    """Verifies insert_document_chunks handles large batches correctly."""

    @patch("database.chunks.get_supabase_client")
    def test_bulk_insert_1000_chunks(self, mock_get_client: MagicMock) -> None:
        """1000 chunks are inserted across batches without error."""
        from database.chunks import insert_document_chunks

        # Mock the Supabase client
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.table.return_value.insert.return_value.execute.return_value = \
            MagicMock(data=[{"id": "chunk-uuid"}] * 100)

        chunks = [_make_chunk(i) for i in range(1000)]

        start    = time.perf_counter()
        inserted = insert_document_chunks(chunks)
        elapsed  = (time.perf_counter() - start) * 1000

        # Should have processed all 1000 rows across 10 batches of 100
        self.assertEqual(1000, inserted)
        print(f"[load_test] 1000-chunk bulk insert: {elapsed:.1f}ms")

    @patch("database.chunks.get_supabase_client")
    def test_batch_boundary_respected(self, mock_get_client: MagicMock) -> None:
        """Insert is called in batches of _INSERT_BATCH_SIZE, not one big call."""
        from database import chunks as chunks_module
        from database.chunks import insert_document_chunks

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        insert_mock = mock_client.table.return_value.insert.return_value
        insert_mock.execute.return_value = MagicMock(data=[{"id": "x"}] * 100)

        batch_size = chunks_module._INSERT_BATCH_SIZE
        n_chunks   = batch_size * 3  # exactly 3 full batches

        insert_document_chunks([_make_chunk(i) for i in range(n_chunks)])

        expected_calls = 3
        actual_calls   = mock_client.table.return_value.insert.call_count
        self.assertEqual(expected_calls, actual_calls)


# ---------------------------------------------------------------------------
# Parallel search stress tests
# ---------------------------------------------------------------------------

class ParallelSearchStressTests(unittest.TestCase):
    """Fires multiple concurrent search_similar_chunks calls."""

    @patch("database.chunks.get_supabase_client")
    def test_concurrent_searches_return_correct_results(
        self, mock_get_client: MagicMock
    ) -> None:
        """20 concurrent search calls all receive their own result list."""
        from database.chunks import search_similar_chunks

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_client.rpc.return_value.execute.return_value = MagicMock(
            data=[{"chunk_id": "c1", "content": "result", "combined_score": 0.9}]
        )

        results: list[list] = [[] for _ in range(20)]
        errors:  list[Exception] = []

        def _search(idx: int) -> None:
            try:
                res = search_similar_chunks(
                    query_vector=_make_fake_embedding(),
                    match_count=5,
                    status_filter="ACTIVE",
                )
                results[idx] = res
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_search, args=(i,)) for i in range(20)]
        start   = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = (time.perf_counter() - start) * 1000

        self.assertEqual([], errors, f"Search errors: {errors}")
        for i, r in enumerate(results):
            self.assertEqual(1, len(r), f"Thread {i} got wrong result count")

        print(f"[load_test] 20 concurrent searches completed in {elapsed:.1f}ms")

    @patch("database.chunks.get_supabase_client")
    def test_search_latency_under_mock(self, mock_get_client: MagicMock) -> None:
        """Single search completes in <100ms under mock (no network overhead)."""
        from database.chunks import search_similar_chunks

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.rpc.return_value.execute.return_value = MagicMock(data=[])

        start   = time.perf_counter()
        search_similar_chunks(query_vector=_make_fake_embedding(), match_count=5)
        elapsed = (time.perf_counter() - start) * 1000

        self.assertLess(elapsed, 100, f"Mock search took {elapsed:.1f}ms — unexpectedly slow")
        print(f"[load_test] Single mock search latency: {elapsed:.2f}ms")


if __name__ == "__main__":
    unittest.main(verbosity=2)
