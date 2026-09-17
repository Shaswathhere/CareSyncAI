"""
rag/rerank_cache.py
-------------------
In-memory caching layer for the cross-encoder reranker in CareSync AI.

Cross-encoder inference is computationally expensive (multi-head cross-attention over
up to 15 query-passage pairs). Identical or repeated questions in field deployments
(e.g., standard triage questions, common dosages) can skip expensive neural scoring
by utilizing a fast query-passage hash cache.

Features:
- Deterministic SHA-256 key generation based on normalized query and candidate chunk IDs.
- TTL-based expiration (default: 600s / 10 minutes) for automatic stale entry eviction.
- LRU eviction when capacity exceeds `max_size` (default: 500 entries).
- Thread-safe operations using `threading.Lock`.
- Performance telemetry (hits, misses, hit rate, latency saved).
"""

from __future__ import annotations

import copy
import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# Default TTL in seconds: 10 minutes
DEFAULT_CACHE_TTL_SECONDS = 600
DEFAULT_MAX_CACHE_SIZE = 500


@dataclass
class CacheEntry:
    """Represents a cached rerank result with timestamp and hit counter."""
    key: str
    reranked_chunks: List[Dict[str, Any]]
    scores: List[float]
    created_at: float
    hits: int = 0


class RerankCache:
    """
    Thread-safe in-memory cache for cross-encoder reranking results.
    """

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        max_size: int = DEFAULT_MAX_CACHE_SIZE,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.Lock()

        # Telemetry metrics
        self._total_hits = 0
        self._total_misses = 0
        self._total_evictions = 0

    @staticmethod
    def generate_cache_key(user_query: str, candidate_chunks: List[Dict[str, Any]]) -> str:
        """
        Generates a deterministic SHA-256 digest from the normalized query
        and the list of candidate chunk IDs (or content hash if ID missing).
        """
        norm_query = " ".join(user_query.strip().lower().split())

        # Collect unique chunk identifiers
        chunk_identifiers: List[str] = []
        for c in candidate_chunks:
            cid = str(c.get("chunk_id") or c.get("id") or "")
            if cid:
                chunk_identifiers.append(cid)
            else:
                # Fallback: hash the chunk content if no explicit ID is present
                content_snippet = str(c.get("content") or c.get("text") or "")[:128]
                chunk_identifiers.append(content_snippet)

        chunk_identifiers.sort()
        payload = f"{norm_query}::" + ",".join(chunk_identifiers)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(
        self,
        user_query: str,
        candidate_chunks: List[Dict[str, Any]],
        top_k: int = 5,
    ) -> Optional[Tuple[List[Dict[str, Any]], List[float]]]:
        """
        Retrieves cached reranking result if present and not expired.

        Returns:
            Tuple of (top_k chunks, top_k scores) if cache hit, else None.
        """
        key = self.generate_cache_key(user_query, candidate_chunks)
        now = time.time()

        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._total_misses += 1
                return None

            # Check expiration
            if (now - entry.created_at) > self.ttl_seconds:
                # Expired -> delete and count as miss
                del self._cache[key]
                self._total_evictions += 1
                self._total_misses += 1
                return None

            # Cache hit: record hit and move to most recently used
            entry.hits += 1
            self._total_hits += 1
            self._cache.move_to_end(key)

            # Deepcopy to prevent downstream mutations from corrupting cache
            cached_chunks = copy.deepcopy(entry.reranked_chunks[:top_k])
            cached_scores = list(entry.scores[:top_k])

            return cached_chunks, cached_scores

    def put(
        self,
        user_query: str,
        candidate_chunks: List[Dict[str, Any]],
        reranked_chunks: List[Dict[str, Any]],
        scores: List[float],
    ) -> None:
        """
        Stores reranked chunks and scores in the cache. Evicts LRU if max_size reached.
        """
        key = self.generate_cache_key(user_query, candidate_chunks)
        now = time.time()

        with self._lock:
            # If key already exists, overwrite and move to end
            if key in self._cache:
                self._cache[key] = CacheEntry(
                    key=key,
                    reranked_chunks=copy.deepcopy(reranked_chunks),
                    scores=list(scores),
                    created_at=now,
                    hits=self._cache[key].hits,
                )
                self._cache.move_to_end(key)
                return

            # Check capacity and evict oldest (LRU)
            if len(self._cache) >= self.max_size:
                oldest_key, _ = self._cache.popitem(last=False)
                self._total_evictions += 1

            self._cache[key] = CacheEntry(
                key=key,
                reranked_chunks=copy.deepcopy(reranked_chunks),
                scores=list(scores),
                created_at=now,
                hits=0,
            )

    def evict_expired(self) -> int:
        """
        Explicitly sweeps and evicts all expired items. Returns count of evicted entries.
        """
        now = time.time()
        evicted_count = 0

        with self._lock:
            keys_to_remove = [
                k for k, entry in self._cache.items()
                if (now - entry.created_at) > self.ttl_seconds
            ]
            for k in keys_to_remove:
                del self._cache[k]
                evicted_count += 1
            self._total_evictions += evicted_count

        return evicted_count

    def clear(self) -> None:
        """Clears all cached entries and resets operational counters."""
        with self._lock:
            self._cache.clear()
            self._total_hits = 0
            self._total_misses = 0
            self._total_evictions = 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Returns performance telemetry for monitoring and logging.
        """
        with self._lock:
            total_lookups = self._total_hits + self._total_misses
            hit_rate = round(self._total_hits / total_lookups, 3) if total_lookups > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "total_lookups": total_lookups,
                "hits": self._total_hits,
                "misses": self._total_misses,
                "hit_rate": hit_rate,
                "evictions": self._total_evictions,
            }


# ── Global Singleton Instance ────────────────────────────────────────────────
_GLOBAL_RERANK_CACHE: Optional[RerankCache] = None
_GLOBAL_LOCK = threading.Lock()


def get_rerank_cache() -> RerankCache:
    """
    Returns the process-level singleton instance of `RerankCache`.
    """
    global _GLOBAL_RERANK_CACHE
    if _GLOBAL_RERANK_CACHE is None:
        with _GLOBAL_LOCK:
            if _GLOBAL_RERANK_CACHE is None:
                _GLOBAL_RERANK_CACHE = RerankCache()
    return _GLOBAL_RERANK_CACHE


def get_cached_rerank(
    user_query: str,
    candidate_chunks: List[Dict[str, Any]],
    top_k: int = 5,
) -> Optional[Tuple[List[Dict[str, Any]], List[float]]]:
    """Helper shortcut to lookup cached reranked chunks."""
    return get_rerank_cache().get(user_query, candidate_chunks, top_k=top_k)


def set_cached_rerank(
    user_query: str,
    candidate_chunks: List[Dict[str, Any]],
    reranked_chunks: List[Dict[str, Any]],
    scores: List[float],
) -> None:
    """Helper shortcut to store reranked chunks in cache."""
    get_rerank_cache().put(user_query, candidate_chunks, reranked_chunks, scores)


def get_cache_stats() -> Dict[str, Any]:
    """Helper shortcut to retrieve cache telemetry."""
    return get_rerank_cache().get_stats()


def clear_rerank_cache() -> None:
    """Helper shortcut to clear cache."""
    get_rerank_cache().clear()
