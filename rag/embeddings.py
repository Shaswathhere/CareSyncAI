"""
rag/embeddings.py
-----------------
Sentence Transformer model loader and vector generation utility for CareSync AI.
Default model: all-MiniLM-L6-v2 (384-dimensional dense vectors).
"""

from __future__ import annotations
from typing import List
from config import EMBEDDING_MODEL_NAME
from rag.embedding_cache import get_or_compute_query_embedding

_embedding_model = None


def get_embedding_model():
    """
    Lazy loader singleton for the SentenceTransformer embedding model.
    Reuses model instance across function calls within the process.
    """
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load SentenceTransformer model '{EMBEDDING_MODEL_NAME}': {exc}"
            ) from exc
    return _embedding_model


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """
    Generates 384-dimensional vector embeddings for a list of text passages.

    Args:
        texts: List of string chunks to encode.

    Returns:
        List of float lists representing dense vector embeddings.
    """
    if not texts:
        return []

    model = get_embedding_model()
    embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
    return embeddings.tolist()


def generate_query_embedding(query: str) -> List[float]:
    """
    Generates a single 384-dimensional vector embedding for a search query.

    Args:
        query: Search prompt string from user.

    Returns:
        Single vector embedding as a list of floats.
    """
    if not query.strip():
        raise ValueError("Search query string cannot be empty.")

    return get_or_compute_query_embedding(
        query,
        lambda: generate_embeddings([query])[0],
    )

