"""Unit tests for query embedding cache behavior and integration."""

from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from rag.embedding_cache import EmbeddingCache, clear_embedding_cache, get_embedding_cache_stats
from rag.embeddings import generate_query_embedding


class EmbeddingCacheTests(unittest.TestCase):
    def test_normalised_queries_share_one_cached_embedding(self) -> None:
        clear_embedding_cache()
        with patch("rag.embeddings.generate_embeddings", return_value=[[0.1, 0.2]]) as encode:
            first = generate_query_embedding("  Dengue   vaccine schedule ")
            second = generate_query_embedding("dengue vaccine schedule")

        self.assertEqual([0.1, 0.2], first)
        self.assertEqual(first, second)
        encode.assert_called_once_with(["  Dengue   vaccine schedule "])
        self.assertIn("estimated_latency_saved_ms", get_embedding_cache_stats())

    def test_expired_entries_are_not_returned(self) -> None:
        cache = EmbeddingCache(ttl_seconds=0, max_size=2)
        cache.put("dengue", [0.1])
        time.sleep(0.001)

        self.assertIsNone(cache.get("dengue"))
        self.assertEqual(1, cache.get_stats()["evictions"])

    def test_concurrent_miss_computes_embedding_once(self) -> None:
        cache = EmbeddingCache()
        calls = 0
        calls_lock = threading.Lock()
        results: list[list[float]] = []

        def compute() -> list[float]:
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.02)
            return [0.1, 0.2]

        threads = [
            threading.Thread(target=lambda: results.append(cache.get_or_compute("malaria dose", compute)))
            for _ in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(1, calls)
        self.assertEqual([[0.1, 0.2]] * 8, results)


if __name__ == "__main__":
    unittest.main()
