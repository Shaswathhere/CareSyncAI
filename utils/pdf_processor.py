"""
utils/pdf_processor.py
----------------------
PyMuPDF text extraction utility for PDF documents.
"""

from __future__ import annotations
try:
    import pymupdf as fitz  # Recommended modern import
except ImportError:
    import fitz  # Legacy import fallback
from typing import List, Dict, Any


def extract_text_from_pdf(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Extracts text per page from a PDF file buffer using PyMuPDF.

    Args:
        file_bytes: Raw bytes of the uploaded PDF file.

    Returns:
        List of dictionaries with page_number (1-indexed) and page text:
        [
            {"page_number": 1, "text": "Page text content..."},
            ...
        ]

    Raises:
        ValueError: If file_bytes is empty or invalid PDF data.
    """
    if not file_bytes:
        raise ValueError("File bytes cannot be empty.")

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        raise ValueError(f"Failed to parse PDF document: {exc}") from exc

    pages: List[Dict[str, Any]] = []

    try:
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text("text").strip()
            pages.append({
                "page_number": page_num + 1,
                "text": text
            })
    finally:
        doc.close()

    return pages


