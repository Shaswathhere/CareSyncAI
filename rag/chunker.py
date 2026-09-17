"""
rag/chunker.py
--------------
Text chunking module for breaking extracted PDF pages into searchable semantic passages.
Preserves page metadata and chunk indices for citation accuracy.
"""

from __future__ import annotations
from typing import List, Dict, Any


def chunk_document_pages(
    pages: List[Dict[str, Any]],
    chunk_size: int = 500,
    chunk_overlap: int = 50
) -> List[Dict[str, Any]]:
    """
    Splits extracted PDF page contents into smaller chunks while preserving page metadata.

    Args:
        pages: List of dicts containing 'page_number' and 'text'.
        chunk_size: Maximum character length per chunk (default: 500).
        chunk_overlap: Overlapping character count between consecutive chunks (default: 50).

    Returns:
        List of chunk dicts:
        [
            {
                "chunk_index": 0,
                "page_number": 1,
                "content": "Text chunk content...",
                "metadata": {
                    "page_number": 1,
                    "character_count": 240
                }
            },
            ...
        ]
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer.")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be strictly smaller than chunk_size.")

    chunks: List[Dict[str, Any]] = []
    chunk_counter = 0

    for page in pages:
        page_num = page.get("page_number", 1)
        text = page.get("text", "").strip()

        if not text:
            continue

        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + chunk_size, text_len)
            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append({
                    "chunk_index": chunk_counter,
                    "page_number": page_num,
                    "content": chunk_text,
                    "metadata": {
                        "page_number": page_num,
                        "character_count": len(chunk_text)
                    }
                })
                chunk_counter += 1

            if end == text_len:
                break
            start += chunk_size - chunk_overlap

    return chunks

