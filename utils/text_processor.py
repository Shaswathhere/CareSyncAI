"""
utils/text_processor.py
-----------------------
Text extraction utility for TXT and Markdown (.md) public health documents.
Splits text into logical page blocks matching the extract_text_from_pdf interface.
"""

from __future__ import annotations
from typing import List, Dict, Any
import re


def extract_text_from_txt_or_md(file_bytes: bytes, file_name: str = "document.txt") -> List[Dict[str, Any]]:
    """
    Extracts text page-by-page from raw TXT or Markdown file bytes.

    Splits text by:
    1. Markdown `#` header sections if available.
    2. Logical character page blocks (~1500 chars) if no headers exist.

    Args:
        file_bytes: Raw bytes of uploaded TXT/MD file.
        file_name: Name of file (used for extension detection).

    Returns:
        List of dicts: [{"page_number": int, "text": str}]
    """
    if not file_bytes:
        raise ValueError("File bytes cannot be empty.")

    try:
        raw_text = file_bytes.decode("utf-8", errors="replace").strip()
    except Exception as exc:
        raise ValueError(f"Failed to decode text file: {exc}") from exc

    if not raw_text:
        return []

    # Check if Markdown headers (# H1, ## H2) exist
    header_splits = [sec.strip() for sec in re.split(r'\n(?=#\s+|\n##\s+)', raw_text) if sec.strip()]

    pages: List[Dict[str, Any]] = []

    if len(header_splits) > 1:
        # Use header sections as pages
        for idx, section in enumerate(header_splits, 1):
            pages.append({
                "page_number": idx,
                "text": section
            })
    else:
        # Fallback to ~1500 character logical page blocks
        page_size = 1500
        start = 0
        total_len = len(raw_text)
        page_counter = 1

        while start < total_len:
            end = min(start + page_size, total_len)
            page_text = raw_text[start:end].strip()
            if page_text:
                pages.append({
                    "page_number": page_counter,
                    "text": page_text
                })
                page_counter += 1
            start = end

    return pages
