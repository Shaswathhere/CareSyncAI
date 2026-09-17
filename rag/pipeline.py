"""
rag/pipeline.py
---------------
RAG pipeline orchestration for CareSync AI.
Connects multi-format text extraction (PDF, TXT, Markdown), metadata-aware chunking,
SentenceTransformer vector embeddings, Supabase database persistence, hybrid vector + keyword retrieval,
medical term query expansion, cross-encoder reranking for ultra-high retrieval precision,
version auto-superseding, conflicting guidance detection, query latency logging,
and Groq LLM answer generation.
"""

from __future__ import annotations
from typing import Dict, Any, List
import datetime
import time

from config import GROQ_MODEL

from utils.pdf_processor import extract_text_from_pdf
from utils.text_processor import extract_text_from_txt_or_md
from rag.chunker import chunk_document_pages
from rag.embeddings import generate_embeddings
from rag.retriever import (
    retrieve_relevant_chunks,
    retrieve_version_comparison_chunks,
    detect_guideline_conflicts,
    format_context_for_llm
)
from rag.reranker import rerank_chunks
from rag.query_contextualizer import reformulate_query_with_history
from rag.llm import (
    generate_grounded_answer,
    generate_version_comparison_answer,
    SAFE_FALLBACK_MESSAGE,
    SCOPE_REFUSAL_MESSAGE,
    is_out_of_scope
)
from database.documents import insert_document_record, supersede_previous_versions
from database.query_logger import log_query_performance
from database.chunks import insert_document_chunks
from database.conversation import get_session_messages, add_chat_message, update_session_title


def process_and_embed_document(
    file_bytes: bytes,
    document_metadata: Dict[str, Any] | None = None,
    auto_supersede: bool = True,
    file_type: str = "pdf"
) -> Dict[str, Any]:
    """
    Complete pipeline to process and ingest an uploaded document (PDF, TXT, Markdown):
    1. Extract page text using PyMuPDF (for PDFs) or text_processor (for TXT/MD).
    2. Split page text into metadata-tagged passage chunks.
    3. Generate 384-dimensional dense vector embeddings using Sentence Transformers.
    4. Store document metadata record in Supabase `documents` table.
    5. Automatically supersede older versions of the same document title if status is ACTIVE.
    6. Bulk insert chunks and vector embeddings into Supabase `document_chunks` table.

    Args:
        file_bytes: Raw binary bytes of uploaded file.
        document_metadata: Metadata dictionary containing title, version, effective_date, status.
        auto_supersede: Whether to automatically mark older versions as SUPERSEDED.
        file_type: Document format string ("pdf", "txt", "md").

    Returns:
        Dict with document processing summary, document_id, and superseded count.
    """
    if document_metadata is None:
        document_metadata = {}

    title = document_metadata.get("title") or "Untitled Guideline"
    version = document_metadata.get("version") or "v1"
    effective_date = document_metadata.get("effective_date")
    publication_date = document_metadata.get("publication_date")
    status = document_metadata.get("status") or "ACTIVE"

    # 1. Extract text pages based on document format
    file_type_lower = file_type.lower().strip()
    if file_type_lower in {"txt", "text", "md", "markdown"}:
        pages = extract_text_from_txt_or_md(file_bytes, file_name=title)
    else:
        pages = extract_text_from_pdf(file_bytes)

    if not pages:
        raise ValueError(f"No readable text found in uploaded {file_type.upper()} document.")

    # 2. Split into passage chunks
    chunks = chunk_document_pages(pages, chunk_size=500, chunk_overlap=50)
    if not chunks:
        raise ValueError("Could not generate text chunks from the document.")

    # 3. Generate 384-dimensional vector embeddings
    texts_to_embed = [c["content"] for c in chunks]
    embeddings = generate_embeddings(texts_to_embed)

    # 4. Save parent document record to database (with fallback for local offline testing)
    document_id = None
    try:
        document_id = insert_document_record(
            title=title,
            version=version,
            publication_date=publication_date,
            effective_date=effective_date,
            status=status
        )
    except Exception as exc:
        print(f"[pipeline] Supabase document insert warning: {exc}")
        import uuid
        document_id = str(uuid.uuid4())

    # 5. Automatically supersede older versions of the document if new status is ACTIVE
    superseded_count = 0
    if auto_supersede and status == "ACTIVE":
        try:
            superseded_count = supersede_previous_versions(title, version)
        except Exception as exc:
            print(f"[pipeline] Auto-supersede warning: {exc}")

    # 6. Prepare chunks for bulk database insertion
    chunks_for_db = []
    for i, chunk in enumerate(chunks):
        chunk_obj = {
            "document_id": document_id,
            "chunk_index": chunk["chunk_index"],
            "page_number": chunk["page_number"],
            "content": chunk["content"],
            "embedding": embeddings[i],
            "metadata": {
                "title": title,
                "version": version,
                "effective_date": str(effective_date) if effective_date else "",
                "status": status,
                "file_type": file_type_lower
            }
        }
        chunks_for_db.append(chunk_obj)

    # 7. Bulk insert chunks with vector embeddings to database
    inserted_chunk_count = len(chunks_for_db)
    try:
        inserted_chunk_count = insert_document_chunks(chunks_for_db)
    except Exception as exc:
        print(f"[pipeline] Supabase chunks insert warning: {exc}")

    return {
        "status": "success",
        "document_id": document_id,
        "page_count": len(pages),
        "chunk_count": len(chunks),
        "inserted_chunks": inserted_chunk_count,
        "superseded_older_versions": superseded_count,
        "metadata": {
            "title": title,
            "version": version,
            "status": status,
            "effective_date": str(effective_date) if effective_date else "",
            "file_type": file_type_lower
        }
    }


def query_rag_pipeline(
    user_query: str,
    status_filter: str = "ACTIVE",
    keyword: str | None = None,
    date_from: Any = None,
    date_to: Any = None,
    session_id: str | None = None,
    save_to_db: bool = True
) -> Dict[str, Any]:
    """
    Complete RAG Query Orchestrator for field worker Q&A with hybrid search & conflict detection:
    1. Rephrases follow-up queries using conversation history.
    2. Performs query expansion and hybrid vector + keyword retrieval with date-range filters.
    3. Runs conflict detection across top retrieved passages.
    4. Constructs context block from top matching passages.
    5. Generates grounded answer using Groq LLM.
    6. Automatically saves user/assistant messages to Supabase and updates session title.
    7. Returns answer, sources, and conflict warning flags.

    Args:
        user_query: Natural language question asked by field worker.
        status_filter: Document status filter ("ACTIVE").
        keyword: Optional keyword boost parameter.
        date_from: Optional effective date lower bound.
        date_to: Optional effective date upper bound.
        session_id: Optional UUID of the active chat session.
        save_to_db: Whether to automatically save the turns to database.

    Returns:
        Dict containing 'answer', 'sources', 'conflicts_detected', 'conflict_warning', 'standalone_query'.
    """
    if not user_query or not user_query.strip():
        return {
            "answer": "Please enter a valid question regarding public-health guidance.",
            "sources": [],
            "conflicts_detected": False,
            "conflict_warning": None,
            "standalone_query": ""
        }

    # 0. Scope-refusal pre-filter — fast path to block out-of-scope queries
    if is_out_of_scope(user_query):
        return {
            "answer": SCOPE_REFUSAL_MESSAGE,
            "sources": [],
            "conflicts_detected": False,
            "conflict_warning": None,
            "standalone_query": user_query
        }

    pipeline_start_ms = time.time() * 1000

    # 1. History-aware query reformulation
    standalone_query = user_query
    chat_history = []
    if session_id:
        try:
            chat_history = get_session_messages(session_id)
            standalone_query = reformulate_query_with_history(user_query, chat_history)
        except Exception as exc:
            print(f"[pipeline] Failed to load chat history or reformulate query: {exc}")

    # 2. Retrieve top-15 candidate chunks via hybrid search with medical term expansion
    with log_query_performance("retrieve_relevant_chunks", status=status_filter, keyword=keyword) as qlog:
        retrieved_chunks = retrieve_relevant_chunks(
            user_query=standalone_query,
            match_count=15,  # Fetch 15 candidates for cross-encoder reranking
            status_filter=status_filter,
            keyword=keyword,
            date_from=date_from,
            date_to=date_to
        )
        qlog.result_count = len(retrieved_chunks)

    if not retrieved_chunks:
        # Save empty results to DB if session_id is active
        if session_id and save_to_db:
            try:
                add_chat_message(session_id, "user", user_query)
                add_chat_message(session_id, "assistant", SAFE_FALLBACK_MESSAGE, citations=[])
                if len(chat_history) == 0:
                    update_session_title(session_id, user_query)
            except Exception as exc:
                print(f"[pipeline] Failed to save conversation to DB: {exc}")

        return {
            "answer": SAFE_FALLBACK_MESSAGE,
            "sources": [],
            "conflicts_detected": False,
            "conflict_warning": None,
            "standalone_query": standalone_query
        }

    # 3. Cross-encoder reranking — rerank top-15 candidates down to top-5
    with log_query_performance("cross_encoder_rerank", candidates=len(retrieved_chunks), top_k=5) as rlog:
        reranked_chunks, rerank_scores = rerank_chunks(
            user_query=standalone_query,
            candidate_chunks=retrieved_chunks,
            top_k=5
        )
        rlog.result_count = len(reranked_chunks)

    # Use reranked chunks for conflict detection and LLM context
    final_chunks = reranked_chunks if reranked_chunks else retrieved_chunks[:5]

    # 4. Detect potential guideline conflicts across retrieved documents
    has_conflicts, conflict_msg, _ = detect_guideline_conflicts(final_chunks)

    # 5. Format context for LLM prompt
    context_str = format_context_for_llm(final_chunks)

    # 6. Generate grounded LLM response using Groq
    with log_query_performance("generate_grounded_answer") as llmlog:
        answer = generate_grounded_answer(context_str, user_query)
        llmlog.result_count = 1

    # Prepend conflict warning if contradicting guidance was detected
    if has_conflicts and conflict_msg:
        answer = f"⚠️ **Guideline Discrepancy Alert:**\n{conflict_msg}\n\n" + answer

    # 7. Extract and deduplicate source citations (from reranked top-5)
    sources = []
    seen_sources = set()

    for chunk in final_chunks:
        meta = chunk.get("metadata") or {}
        title = chunk.get("title") or meta.get("title") or "Official Guidance Document"
        version = chunk.get("version") or meta.get("version") or "v1"
        page_num = chunk.get("page_number", 1)
        effective_date = chunk.get("effective_date") or meta.get("effective_date") or ""
        status = chunk.get("status") or meta.get("status") or "ACTIVE"

        source_key = (title, version, page_num)
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            sources.append({
                "title": title,
                "version": version,
                "page_number": page_num,
                "effective_date": str(effective_date),
                "status": status,
                "snippet": chunk.get("content") or "",
                "rerank_score": chunk.get("rerank_score")
            })

    # 8. Auto-save messages to DB if session_id is active and save_to_db is True
    if session_id and save_to_db:
        try:
            add_chat_message(session_id, "user", user_query)
            add_chat_message(session_id, "assistant", answer, citations=sources)
            # Update session title if this is the first user question
            if len(chat_history) == 0:
                update_session_title(session_id, user_query)
        except Exception as exc:
            print(f"[pipeline] Failed to save conversation turn to DB: {exc}")

    # 9. Log end-to-end pipeline latency and outcome to system_metrics
    try:
        from database.feedback import log_metrics
        total_ms = (time.time() * 1000) - pipeline_start_ms
        log_metrics(
            user_id=session_id or "anonymous",
            total_ms=total_ms,
            session_id=session_id,
            query_text=user_query,
            chunk_count=len(final_chunks),
            model_name=GROQ_MODEL,
            status="success"
        )
    except Exception as metrics_exc:
        print(f"[pipeline] Metrics logging skipped: {metrics_exc}")

    return {
        "answer": answer,
        "sources": sources,
        "conflicts_detected": has_conflicts,
        "conflict_warning": conflict_msg if has_conflicts else None,
        "standalone_query": standalone_query
    }



def query_version_comparison_pipeline(
    user_query: str,
    document_title: str | None = None
) -> Dict[str, Any]:
    """
    Multi-version comparison pipeline to compare protocol changes between
    superseded guidelines and current active guidelines.

    Args:
        user_query: Comparison question asked by field worker.
        document_title: Optional title filter.

    Returns:
        Dict containing comparison answer string and tagged source citations.
    """
    if not user_query or not user_query.strip():
        return {
            "answer": "Please enter a valid version comparison question.",
            "sources": []
        }

    # 1. Retrieve chunks from both ACTIVE and SUPERSEDED documents
    retrieved_chunks = retrieve_version_comparison_chunks(
        user_query=user_query,
        document_title=document_title,
        match_count=6
    )

    if not retrieved_chunks:
        return {
            "answer": SAFE_FALLBACK_MESSAGE,
            "sources": []
        }

    # 2. Format multi-version context
    context_str = format_context_for_llm(retrieved_chunks)

    # 3. Generate version comparison summary via Groq
    answer = generate_version_comparison_answer(context_str, user_query)

    # 4. Extract source citations with version status badges
    sources = []
    seen_sources = set()

    for chunk in retrieved_chunks:
        meta = chunk.get("metadata") or {}
        title = chunk.get("title") or meta.get("title") or "Guideline"
        version = chunk.get("version") or meta.get("version") or "v1"
        page_num = chunk.get("page_number", 1)
        effective_date = chunk.get("effective_date") or meta.get("effective_date") or ""
        status = chunk.get("status") or meta.get("status") or "ACTIVE"

        source_key = (title, version, page_num)
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            sources.append({
                "title": title,
                "version": version,
                "page_number": page_num,
                "effective_date": str(effective_date),
                "status": status,
                "snippet": chunk.get("content") or ""
            })

    return {
        "answer": answer,
        "sources": sources
    }


def process_voice_query(
    user_id: str,
    audio_file_path: str,
    target_lang: str = "en",
    session_id: str | None = None,
    save_to_db: bool = True
) -> Dict[str, Any]:
    """
    Complete audio query pipeline:
    1. Logs the incoming audio query.
    2. Transcribes the audio using Groq Whisper STT.
    3. Handles success/failure logging for the transcription.
    4. Pipes the transcribed text into the multilingual RAG pipeline.
    
    Args:
        user_id: User making the request.
        audio_file_path: Local path to the audio file.
        target_lang: Expected language of the audio and response.
        session_id: Optional session ID for conversation tracking.
        save_to_db: Whether to save the conversation.
        
    Returns:
        Dict matching the output of multilingual_rag_query, with an added 'transcription' field.
    """
    from database.audio import (
        log_audio_query,
        update_audio_query_transcription,
        fail_audio_query,
        insert_transcription_audit
    )
    from rag.transcriber import transcribe_audio_groq
    from rag.translator import multilingual_rag_query
    
    # 1. Log incoming query
    audio_log = None
    try:
        audio_log = log_audio_query(
            user_id=user_id,
            language=target_lang,
            session_id=session_id,
            audio_file_ref=audio_file_path
        )
        audio_query_id = audio_log.get("id")
    except Exception as exc:
        print(f"[pipeline] Failed to log audio query: {exc}")
        audio_query_id = None
        
    # 2. Transcribe Audio
    start_time = time.time()
    try:
        transcription = transcribe_audio_groq(audio_file_path)
        transcription_ms = int((time.time() - start_time) * 1000)
    except Exception as exc:
        error_msg = str(exc)
        if audio_query_id:
            fail_audio_query(audio_query_id, error_message=error_msg)
        raise RuntimeError(f"Voice query failed during transcription: {error_msg}")
        
    # 3. Handle success logging and audit
    if audio_query_id:
        try:
            update_audio_query_transcription(
                audio_query_id=audio_query_id,
                transcription=transcription,
                transcription_ms=transcription_ms,
                status="success"
            )
            insert_transcription_audit(
                audio_query_id=audio_query_id,
                stt_engine="whisper",
                raw_transcript=transcription
            )
        except Exception as log_exc:
            print(f"[pipeline] Warning: failed to log transcription success/audit: {log_exc}")

    # 4. Pipe into Multilingual RAG
    print(f"[pipeline] Transcribed Audio ({target_lang}): {transcription}")
    result = multilingual_rag_query(
        user_query=transcription,
        target_lang=target_lang,
        status_filter="ACTIVE",
        session_id=session_id,
        save_to_db=save_to_db
    )
    
    # Inject transcription into result for frontend visibility
    result["transcription"] = transcription
    return result
