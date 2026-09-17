"""
rag/embedding_cache.py
----------------------
In-process query embedding cache for CareSync AI.

SentenceTransformer `.encode()` runs a full neural model forward pass for every
query — this is cheap per-call but adds meaningful latency in a multi-query
Streamlit session where many follow-up questions are semantically identical or
slightly rephrased variants of the same information need.

This module provides a thread-safe, TTL-based in-process cache that:
1. Normalises the raw query string (lowercase + whitespace collapse).
2. Computes a SHA-256 hash as the cache key.
3. Returns the stored 384-dim embedding vector for cache hits, skipping model inference.
4. Evicts entries beyond a configurable TTL (default: 30 minutes) or over max_size
   via LRU eviction (same OrderedDict approach as `rerank_cache.py`).
5. Exposes telemetry (hits, misses, hit-rate, estimated latency saved) for monitoring.

Usage:
    from rag.embedding_cache import (
        get_cached_query_embedding,
        set_cached_query_embedding,
        get_embedding_cache_stats,
        clear_embedding_cache,
    )
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from config import EMBEDDING_CACHE_MAX_SIZE, EMBEDDING_CACHE_TTL_SECONDS


# Default TTL: 30 minutes (query intent stays stable within a session)
DEFAULT_EMBEDDING_CACHE_TTL_SECONDS: int = EMBEDDING_CACHE_TTL_SECONDS
# Store up to 1 000 distinct query embeddings (~1 000 × 384 floats × 4 bytes ≈ 1.5 MB)
DEFAULT_EMBEDDING_CACHE_MAX_SIZE: int = EMBEDDING_CACHE_MAX_SIZE


@dataclass
class EmbeddingCacheEntry:
    """Cached embedding entry with provenance metadata."""
    key: str
    query_normalized: str
    embedding: List[float]
    created_at: float
    inference_ms: float = 0.0
    hits: int = 0


class EmbeddingCache:
    """
    Thread-safe, TTL-based in-process cache for query vector embeddings.

    Eliminates repeated SentenceTransformer model invocations for queries that
    are semantically equivalent (same text after normalisation).

    Attributes:
        ttl_seconds:  Maximum age of a cache entry before it is evicted on next access.
        max_size:     Maximum number of distinct query entries held simultaneously.
    """

    def __init__(
        self,
        ttl_seconds: int = DEFAULT_EMBEDDING_CACHE_TTL_SECONDS,
        max_size: int = DEFAULT_EMBEDDING_CACHE_MAX_SIZE,
    ) -> None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative.")
        if max_size < 0:
            raise ValueError("max_size must be non-negative.")

        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: OrderedDict[str, EmbeddingCacheEntry] = OrderedDict()
        self._lock = threading.Lock()
        # Events coalesce simultaneous requests for the same missing key. This
        # prevents a burst of identical queries from all running model.encode().
        self._inflight: Dict[str, threading.Event] = {}

        # Telemetry counters
        self._total_hits = 0
        self._total_misses = 0
        self._total_evictions = 0
        self._estimated_latency_saved_ms = 0.0

    # ── Key generation ────────────────────────────────────────────────────────

    @staticmethod
    def normalise_query(query: str) -> str:
        """Normalises a raw query to produce a stable, case-insensitive lookup key."""
        return " ".join(query.strip().lower().split())

    @classmethod
    def generate_cache_key(cls, query: str) -> str:
        """
        Computes a SHA-256 hex digest from the normalised query string.

        Ensures that minor variations in casing or leading/trailing whitespace
        map to the same cache slot.
        """
        norm = cls.normalise_query(query)
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, query: str) -> Optional[List[float]]:
        """
        Returns the cached embedding for ``query`` if present and not expired.

        Returns:
            The embedding as ``List[float]``, or ``None`` on cache miss / expiry.
        """
        key = self.generate_cache_key(query)
        now = time.time()

        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._total_misses += 1
                return None

            # Expired entry: remove and report miss
            if (now - entry.created_at) > self.ttl_seconds:
                del self._cache[key]
                self._total_evictions += 1
                self._total_misses += 1
                return None

            # Cache hit: update LRU order and telemetry
            entry.hits += 1
            self._total_hits += 1
            self._estimated_latency_saved_ms += entry.inference_ms
            self._cache.move_to_end(key)

            # Return a copy so callers can't mutate the cached vector
            return list(entry.embedding)

    def put(self, query: str, embedding: List[float], inference_ms: float = 0.0) -> None:
        """
        Stores an embedding in the cache for ``query``.

        If the cache is at capacity, the least-recently-used entry is evicted first.
        """
        if not embedding:
            raise ValueError("Cannot cache an empty query embedding.")

        key = self.generate_cache_key(query)
        norm = self.normalise_query(query)
        now = time.time()

        with self._lock:
            if key in self._cache:
                # Refresh existing entry (new embedding, reset timestamp)
                self._cache[key] = EmbeddingCacheEntry(
                    key=key,
                    query_normalized=norm,
                    embedding=list(embedding),
                    created_at=now,
                    inference_ms=max(inference_ms, 0.0),
                    hits=self._cache[key].hits,
                )
                self._cache.move_to_end(key)
                return

            # Evict LRU entry if capacity reached
            if self.max_size <= 0:
                return

            if len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
                self._total_evictions += 1

            self._cache[key] = EmbeddingCacheEntry(
                key=key,
                query_normalized=norm,
                embedding=list(embedding),
                created_at=now,
                inference_ms=max(inference_ms, 0.0),
            )

    def get_or_compute(self, query: str, compute: Callable[[], List[float]]) -> List[float]:
        """Returns a cached vector or computes it once for concurrent callers.

        The expensive callback runs outside the cache lock. Requests that arrive
        while the same query is being encoded wait for that result and then read
        the populated cache entry, eliminating duplicate model forward passes.
        """
        while True:
            cached = self.get(query)
            if cached is not None:
                return cached

            key = self.generate_cache_key(query)
            with self._lock:
                pending = self._inflight.get(key)
                if pending is None:
                    pending = threading.Event()
                    self._inflight[key] = pending
                    is_owner = True
                else:
                    is_owner = False

            if not is_owner:
                pending.wait()
                continue

            try:
                inference_start = time.perf_counter()
                embedding = compute()
                self.put(query, embedding, (time.perf_counter() - inference_start) * 1000)
                return list(embedding)
            finally:
                with self._lock:
                    self._inflight.pop(key, None)
                    pending.set()

    def evict_expired(self) -> int:
        """
        Proactively sweeps the cache and evicts all expired entries.

        Returns:
            Number of entries evicted.
        """
        now = time.time()
        evicted = 0
        with self._lock:
            expired_keys = [
                k for k, e in self._cache.items()
                if (now - e.created_at) > self.ttl_seconds
            ]
            for k in expired_keys:
                del self._cache[k]
                evicted += 1
            self._total_evictions += evicted
        return evicted

    def clear(self) -> None:
        """Clears all entries and resets all telemetry counters."""
        with self._lock:
            self._cache.clear()
            self._total_hits = 0
            self._total_misses = 0
            self._total_evictions = 0
            self._estimated_latency_saved_ms = 0.0

    def get_stats(self) -> Dict[str, Any]:
        """
        Returns current telemetry snapshot.

        Keys:
            size               — current number of cached entries
            max_size           — configured capacity ceiling
            ttl_seconds        — configured TTL
            total_lookups      — total ``get()`` calls
            hits               — cache hits
            misses             — cache misses (including expiry misses)
            hit_rate           — hits / total_lookups (0.0 – 1.0)
            evictions          — total entries evicted (TTL + LRU)
        """
        with self._lock:
            total = self._total_hits + self._total_misses
            hit_rate = round(self._total_hits / total, 4) if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "total_lookups": total,
                "hits": self._total_hits,
                "misses": self._total_misses,
                "hit_rate": hit_rate,
                "evictions": self._total_evictions,
                "estimated_latency_saved_ms": round(self._estimated_latency_saved_ms, 2),
            }


# ── Global Singleton ──────────────────────────────────────────────────────────

_GLOBAL_EMBEDDING_CACHE: Optional[EmbeddingCache] = None
_GLOBAL_INIT_LOCK = threading.Lock()


def get_embedding_cache() -> EmbeddingCache:
    """Returns the process-level singleton ``EmbeddingCache`` instance."""
    global _GLOBAL_EMBEDDING_CACHE
    if _GLOBAL_EMBEDDING_CACHE is None:
        with _GLOBAL_INIT_LOCK:
            if _GLOBAL_EMBEDDING_CACHE is None:
                _GLOBAL_EMBEDDING_CACHE = EmbeddingCache()
    return _GLOBAL_EMBEDDING_CACHE


# ── Helper shorthands ─────────────────────────────────────────────────────────

def get_cached_query_embedding(query: str) -> Optional[List[float]]:
    """Returns the cached embedding for ``query``, or ``None`` on miss."""
    return get_embedding_cache().get(query)


def set_cached_query_embedding(query: str, embedding: List[float]) -> None:
    """Stores ``embedding`` in the global cache keyed by ``query``."""
    get_embedding_cache().put(query, embedding)


def get_or_compute_query_embedding(query: str, compute: Callable[[], List[float]]) -> List[float]:
    """Gets a query vector from cache, computing it once on a shared miss."""
    return get_embedding_cache().get_or_compute(query, compute)


def get_embedding_cache_stats() -> Dict[str, Any]:
    """Returns telemetry stats from the global embedding cache."""
    return get_embedding_cache().get_stats()


def clear_embedding_cache() -> None:
    """Clears all entries from the global embedding cache and resets counters."""
    get_embedding_cache().clear()
