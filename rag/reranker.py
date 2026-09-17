"""
rag/reranker.py
---------------
Cross-encoder reranker for CareSync AI.

Implements a lightweight cross-encoder reranking step that scores (query, passage)
pairs using a dedicated cross-attention model, producing precision-ranked results
from the top-15 vector candidates down to the top-5 most relevant passages.

Architecture:
    1. Vector similarity retriever fetches top-15 candidate chunks.
    2. Cross-encoder reranker scores each (query, passage) pair jointly.
    3. Top-5 highest-scoring passages are forwarded to the LLM for grounded Q&A.

Cross-encoder Model:
    Uses `cross-encoder/ms-marco-MiniLM-L-6-v2` from sentence-transformers.
    This model is trained on MS MARCO and reranks passages by relevance to the query
    using full cross-attention (not bi-encoder dot product).
    Falls back gracefully to original vector similarity ordering if model unavailable.
"""

from __future__ import annotations

import time
from typing import List, Dict, Any, Tuple

from rag.rerank_cache import (
    get_cached_rerank,
    set_cached_rerank,
    get_cache_stats,
    clear_rerank_cache,
)

# ─── Cross-encoder model (lazy-loaded) ──────────────────────────────────────
_cross_encoder = None
_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def _get_cross_encoder():
    """Lazy-loads the cross-encoder model on first call."""
    global _cross_encoder
    if _cross_encoder is None:
        try:
            from sentence_transformers import CrossEncoder
            _cross_encoder = CrossEncoder(_CROSS_ENCODER_MODEL)
            print(f"[reranker] Cross-encoder model '{_CROSS_ENCODER_MODEL}' loaded.")
        except Exception as exc:
            print(f"[reranker] Cross-encoder model load failed: {exc}. Falling back to score ordering.")
            _cross_encoder = None
    return _cross_encoder


def rerank_chunks(
    user_query: str,
    candidate_chunks: List[Dict[str, Any]],
    top_k: int = 5,
) -> Tuple[List[Dict[str, Any]], List[float]]:
    """
    Reranks candidate passage chunks against the user query using a cross-encoder model.

    The cross-encoder evaluates (query, passage) pairs jointly using cross-attention,
    producing higher precision relevance scores than bi-encoder cosine similarity alone.
    Uses in-memory query-passage caching to eliminate redundant neural inference for repeated queries.

    Args:
        user_query: Field worker's natural language question.
        candidate_chunks: Up to 15 candidate passage chunks from vector search.
        top_k: Number of top passages to return after reranking (default: 5).

    Returns:
        Tuple of:
        - Reranked list of top_k chunk dicts ordered by cross-encoder score DESC.
        - Corresponding list of float scores (same order as returned chunks).

    Notes:
        - Checks in-memory cache first; skips neural inference on cache hit.
        - Falls back to original vector similarity ordering if the cross-encoder
          model fails to load or inference throws an exception.
        - Attaches 'rerank_score' field to each returned chunk for UI display.
    """
    if not candidate_chunks:
        return [], []

    if not user_query or not user_query.strip():
        return candidate_chunks[:top_k], []

    # 0. Check cache before running expensive cross-encoder inference
    cached_result = get_cached_rerank(user_query, candidate_chunks, top_k=top_k)
    if cached_result is not None:
        cached_chunks, cached_scores = cached_result
        print(f"[reranker] Cache HIT for query '{user_query[:35]}...' -> returned {len(cached_chunks)} cached chunks.")
        return cached_chunks, cached_scores

    print(f"[reranker] Cache MISS for query '{user_query[:35]}...' -> computing cross-encoder scores.")

    cross_encoder = _get_cross_encoder()

    if cross_encoder is None:
        # Graceful fallback: return top_k by existing combined_score / similarity
        fallback = sorted(
            candidate_chunks,
            key=lambda c: float(c.get("combined_score") or c.get("vector_similarity") or 0.0),
            reverse=True
        )[:top_k]
        scores = [float(c.get("combined_score") or c.get("vector_similarity") or 0.0) for c in fallback]
        print(f"[reranker] Fallback mode — returning top {len(fallback)} by vector score.")
        return fallback, scores

    # Build (query, passage_text) pairs for cross-encoder
    query_passage_pairs = []
    for chunk in candidate_chunks:
        passage_text = chunk.get("content") or chunk.get("text") or ""
        query_passage_pairs.append([user_query, passage_text])

    try:
        t0 = time.perf_counter()
        scores = cross_encoder.predict(query_passage_pairs)
        latency_ms = (time.perf_counter() - t0) * 1000
        print(f"[reranker] Cross-encoder scored {len(scores)} candidates in {latency_ms:.1f}ms.")
    except Exception as exc:
        print(f"[reranker] Cross-encoder inference error: {exc}. Using fallback ordering.")
        fallback = candidate_chunks[:top_k]
        return fallback, []

    # Pair scores with chunks and sort descending
    scored_chunks = sorted(
        zip(scores, candidate_chunks),
        key=lambda x: float(x[0]),
        reverse=True
    )

    top_chunks = []
    top_scores = []
    for score, chunk in scored_chunks[:top_k]:
        chunk_with_score = dict(chunk)
        chunk_with_score["rerank_score"] = float(score)
        top_chunks.append(chunk_with_score)
        top_scores.append(float(score))

    # Store computed results in cache for subsequent calls
    set_cached_rerank(user_query, candidate_chunks, top_chunks, top_scores)

    return top_chunks, top_scores


def get_reranker_model_name() -> str:
    """Returns the cross-encoder model name used for reranking."""
    return _CROSS_ENCODER_MODEL
