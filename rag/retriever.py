"""
rag/retriever.py
----------------
Retriever interface for CareSync AI.
Converts user queries into 384-dim dense vectors and queries Supabase pgvector table via match_document_chunks.
Supports hybrid keyword + vector retrieval, date range metadata filtering, recency ranking, and conflicting guidance detection.
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple
from datetime import date
import re

from rag.embeddings import generate_query_embedding
from database.chunks import search_similar_chunks


def rank_chunks_by_version_and_effective_date(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ranks retrieved chunks prioritizing combined_score / vector similarity,
    ACTIVE status, and recent effective dates.

    Args:
        chunks: List of chunk dictionaries from vector similarity search.

    Returns:
        Sorted list of chunks.
    """
    def sort_key(chunk: Dict[str, Any]):
        metadata = chunk.get("metadata") or {}
        status = chunk.get("status") or metadata.get("status") or "ACTIVE"
        effective_date = str(chunk.get("effective_date") or metadata.get("effective_date") or "")
        score = float(chunk.get("combined_score") or chunk.get("vector_similarity") or chunk.get("similarity") or 0.0)

        # Priority score: ACTIVE = 2, SUPERSEDED = 1, ARCHIVED = 0
        status_score = 2 if status == "ACTIVE" else (1 if status == "SUPERSEDED" else 0)
        return (status_score, score, effective_date)

    return sorted(chunks, key=sort_key, reverse=True)


# Public health medical term synonym & expansion dictionary
MEDICAL_SYNONYM_DICT = {
    "dengue": "dengue virus DENV hemorrhagic fever mosquito vector Aedes",
    "malaria": "malaria Plasmodium falciparum vivax mosquito vector Anopheles antimalarial",
    "tb": "tuberculosis Mycobacterium RIF INH DOTS chest x-ray sputum",
    "tuberculosis": "tb Mycobacterium RIF INH DOTS chest x-ray sputum",
    "covid": "COVID-19 SARS-CoV-2 coronavirus vaccine mRNA booster isolation",
    "polio": "poliomyelitis OPV IPV vaccine immunization paralysis",
    "measles": "measles MMR vaccine rash rubeola Koplik spots",
    "ppe": "personal protective equipment mask N95 gloves gown face shield goggles",
    "vaccine": "vaccination immunization booster dose schedule contraindications",
    "dosage": "dosage dose administration Schedule frequency mg ml oral injection",
    "outbreak": "outbreak epidemic surge cluster quarantine response vector control",
}


def expand_query_terms(user_query: str) -> str:
    """
    Expands user query terms with public health medical synonyms and acronyms
    to improve vector and full-text keyword retrieval recall.

    Args:
        user_query: Natural language question from field worker.

    Returns:
        Expanded query string containing original query + expanded synonyms.
    """
    if not user_query or not user_query.strip():
        return user_query

    query_lower = user_query.lower()
    expansions = []

    for term, synonym_string in MEDICAL_SYNONYM_DICT.items():
        if re.search(rf'\b{re.escape(term)}\b', query_lower):
            expansions.append(synonym_string)

    if expansions:
        expanded_query = f"{user_query} {' '.join(expansions)}"
        print(f"[retriever] Query expansion applied: '{user_query}' -> '{expanded_query}'")
        return expanded_query

    return user_query


def retrieve_relevant_chunks(
    user_query: str,
    match_count: int = 5,
    status_filter: str = "ACTIVE",
    keyword: str | None = None,
    date_from: date | str | None = None,
    date_to: date | str | None = None
) -> List[Dict[str, Any]]:
    """
    Retrieves top relevant document passages for a user question using hybrid search
    (cosine vector similarity + full-text keyword ranking + date range metadata filters).

    Args:
        user_query: Natural language question from field worker.
        match_count: Maximum number of top passages to return (default: 5).
        status_filter: Filter by document lifecycle status (default: "ACTIVE").
        keyword: Optional explicit keyword filter. If None, extracts keywords from user_query.
        date_from: Optional lower bound on effective_date (inclusive).
        date_to: Optional upper bound on effective_date (inclusive).

    Returns:
        List of matching chunk dicts with similarity scores and document metadata.
    """
    if not user_query or not user_query.strip():
        return []

    # Run query expansion for medical terms
    expanded_query = expand_query_terms(user_query)

    # Extract keyword string if not explicitly provided
    if not keyword:
        # Extract alphanumeric words longer than 3 chars for full-text search
        words = [w for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', user_query) if w.lower() not in {"what", "when", "where", "which", "how", "does", "with", "from", "that", "this"}]
        keyword = " ".join(words[:4]) if words else None

    # 1. Generate 384-dim embedding for expanded user query
    query_vector = generate_query_embedding(expanded_query)

    # 2. Perform hybrid search in Supabase vector & full-text index
    try:
        results = search_similar_chunks(
            query_vector=query_vector,
            match_count=match_count,
            status_filter=status_filter,
            keyword=keyword,
            date_from=date_from,
            date_to=date_to
        )
        return rank_chunks_by_version_and_effective_date(results)
    except Exception as exc:
        print(f"[retriever] Hybrid vector search fallback/warning: {exc}")
        return []



def detect_guideline_conflicts(chunks: List[Dict[str, Any]]) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """
    Scans top retrieved document passages across active guidelines to detect potential
    conflicting recommendations (e.g., differing dosage numbers or opposing advice).

    Args:
        chunks: List of retrieved passage dictionaries.

    Returns:
        Tuple: (has_conflicts: bool, summary_message: str, conflicting_chunks: list)
    """
    if len(chunks) < 2:
        return False, "", []

    # Group passages by document title
    doc_passages: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in chunks:
        meta = chunk.get("metadata") or {}
        title = chunk.get("title") or meta.get("title") or "Document"
        doc_passages.setdefault(title, []).append(chunk)

    # If all top chunks come from a single document, no cross-document conflict
    if len(doc_passages) < 2:
        return False, "", []

    # Scan for numerical pattern discrepancies (e.g. "1 dose" vs "2 doses" vs "3 doses", or differing age criteria)
    doc_numbers: Dict[str, set] = {}
    for title, passage_list in doc_passages.items():
        combined_text = " ".join([p.get("content", "").lower() for p in passage_list])
        # Find dosage or frequency numbers (e.g., "1 dose", "2 doses", "3 times", "4 weeks")
        found_matches = set(re.findall(r'\b\d+\s*(?:dose|doses|mg|ml|weeks|days|times|hours)\b', combined_text))
        if found_matches:
            doc_numbers[title] = found_matches

    # Compare numbers across different documents
    conflicting_docs = []
    titles = list(doc_numbers.keys())
    for i in range(len(titles)):
        for j in range(i + 1, len(titles)):
            t1, t2 = titles[i], titles[j]
            # If both documents specify dosages/frequencies but have non-overlapping numbers
            if doc_numbers[t1] and doc_numbers[t2] and not (doc_numbers[t1] & doc_numbers[t2]):
                conflicting_docs.append((t1, list(doc_numbers[t1]), t2, list(doc_numbers[t2])))

    if conflicting_docs:
        summary_lines = []
        for t1, n1, t2, n2 in conflicting_docs:
            summary_lines.append(
                f"• Potential Discrepancy between '{t1}' ({', '.join(n1)}) and '{t2}' ({', '.join(n2)})."
            )
        summary_msg = "\n".join(summary_lines)
        return True, summary_msg, chunks

    return False, "", []


def retrieve_version_comparison_chunks(
    user_query: str,
    document_title: str | None = None,
    match_count: int = 6
) -> List[Dict[str, Any]]:
    """
    Retrieves passages across BOTH ACTIVE and SUPERSEDED versions of guidelines
    to enable multi-version comparison (e.g. "What changed between v2 and v3?").

    Args:
        user_query: User question asking for version changes or comparison.
        document_title: Optional filter for a specific guideline title.
        match_count: Number of passage chunks to retrieve.

    Returns:
        List of matching chunks from active and superseded documents.
    """
    if not user_query or not user_query.strip():
        return []

    query_vector = generate_query_embedding(user_query)
    combined_results = []

    # Retrieve active chunks
    try:
        active_chunks = search_similar_chunks(
            query_vector=query_vector,
            match_count=match_count // 2 or 3,
            status_filter="ACTIVE"
        )
        combined_results.extend(active_chunks)
    except Exception as exc:
        print(f"[retriever] Active search warning: {exc}")

    # Retrieve superseded chunks for comparison
    try:
        superseded_chunks = search_similar_chunks(
            query_vector=query_vector,
            match_count=match_count // 2 or 3,
            status_filter="SUPERSEDED"
        )
        combined_results.extend(superseded_chunks)
    except Exception as exc:
        print(f"[retriever] Superseded search warning: {exc}")

    # Filter by specific document title if provided
    if document_title and document_title.strip():
        title_lower = document_title.strip().lower()
        combined_results = [
            c for c in combined_results
            if title_lower in (c.get("title") or c.get("metadata", {}).get("title", "")).lower()
        ]

    return rank_chunks_by_version_and_effective_date(combined_results)


def format_context_for_llm(chunks: List[Dict[str, Any]]) -> str:
    """
    Formats retrieved document chunks into a structured context block for the LLM.

    Args:
        chunks: List of retrieved chunk dictionaries.

    Returns:
        Formatted context string ready for prompt injection.
    """
    if not chunks:
        return ""

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        metadata = chunk.get("metadata") or {}
        title = chunk.get("title") or metadata.get("title") or "Unknown Document"
        version = chunk.get("version") or metadata.get("version") or "v1"
        status = chunk.get("status") or metadata.get("status") or "ACTIVE"
        page_num = chunk.get("page_number", 1)
        content = chunk.get("content", "").strip()

        context_parts.append(
            f"--- [Source {i}]: {title} ({version} - {status}), Page {page_num} ---\n{content}"
        )

    return "\n\n".join(context_parts)
