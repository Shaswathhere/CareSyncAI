# 🩺 CareSync AI — Core API Specification

> **Version:** `1.0.0`  
> **Package Base:** `SW2627_CareSyncAI`  
> **Author:** Shaswath (AI/RAG) & Engineering Team  

This document specifies the internal and exported API contracts across the CareSync AI repository.

---

## 1. `rag` Package

### 1.1 `rag.pipeline`
#### `query_rag_pipeline(user_query: str, **kwargs) -> Dict[str, Any]`
Executes end-to-end question answering over the clinical guidance vector database.
- **Parameters:**
  - `user_query` (*str*): The question from the user or field worker.
  - `document_filter` (*Optional[str]*): Specific document title filter.
  - `version_filter` (*Optional[str]*): Specific document version filter.
  - `status_filter` (*Optional[str]*): Lifecycle status (`ACTIVE`, `SUPERSEDED`, or `None` for all).
  - `top_k` (*int*, default=10): Initial vector candidate count.
  - `top_rerank` (*int*, default=3): Reranked chunk count passed to Gemini LLM.
  - `save_to_db` (*bool*, default=True): Whether to persist telemetry to `system_metrics`.
- **Returns:**
  ```python
  {
      "answer": str,                  # Grounded markdown response or guardrail refusal
      "sources": List[Dict[str, Any]],# Ranked retrieved source chunks with metadata
      "confidence": float,            # Aggregate grounding confidence [0.0 - 1.0]
      "conflicts_detected": bool,     # True if contradictory guidance was detected
      "conflict_warning": Optional[str],# Guideline Discrepancy warning banner if detected
      "is_out_of_scope": bool,        # True if query was intercepted by refusal guardrail
  }
  ```

#### `process_and_embed_document(file_bytes: bytes, metadata: Dict[str, Any]) -> Dict[str, Any]`
Ingests a raw PDF, performs sentence-window chunking, generates 384-dimensional embeddings, and returns chunk objects ready for DB persistence.
- **Parameters:**
  - `file_bytes` (*bytes*): Raw PDF binary data.
  - `metadata` (*Dict[str, Any]*): Must contain `title`, `version`, `effective_date`, `status`.
- **Returns:**
  ```python
  {
      "page_count": int,
      "chunk_count": int,
      "chunks": List[Dict[str, Any]],  # List of chunks with content, embedding, metadata
  }
  ```

#### `process_voice_query(audio_bytes: bytes, audio_format: str = "wav", **kwargs) -> Dict[str, Any]`
Transcribes audio input using Gemini Multimodal transcription and feeds the transcript into `query_rag_pipeline`.

---

### 1.2 `rag.embedding_cache`
#### `class EmbeddingCache(ttl_seconds: int = 1800, max_size: int = 1000)`
Thread-safe LRU + TTL query embedding cache.
- **Methods:**
  - `get(query: str) -> Optional[List[float]]`: Retrieves cached 384-dim embedding if not expired.
  - `put(query: str, embedding: List[float], inference_ms: float = 0.0) -> None`: Stores embedding vector.
  - `clear() -> None`: Clears all entries.
  - `stats() -> Dict[str, Any]`: Returns `{hits, misses, evictions, hit_ratio, estimated_latency_saved_ms}`.

#### `get_embedding_cache() -> EmbeddingCache`
Singleton factory providing the process-wide embedding cache instance.

---

### 1.3 `rag.reranker`
#### `rerank_chunks(query: str, chunks: List[Dict[str, Any]], top_k: int = 3) -> List[Dict[str, Any]]`
Applies `ms-marco-MiniLM-L-6-v2` cross-encoder scoring to rank retrieval candidates by precise passage relevance.

---

### 1.4 `rag.evaluation`
#### `run_rag_benchmark(dataset=None, query_fn=None, llm_judge=False) -> BenchmarkSummary`
Executes automated benchmark evaluation over a dataset of `BenchmarkTestCase` objects.
- **Returns `BenchmarkSummary`:**
  - `total_tests` (*int*)
  - `passed_tests` (*int*)
  - `pass_rate_pct` (*float*)
  - `avg_retrieval_precision` (*float*)
  - `avg_faithfulness` (*float*)
  - `avg_answer_correctness` (*float*)
  - `avg_overall_score` (*float*)
  - `avg_latency_ms` (*float*)
  - `category_breakdown` (*Dict[str, Dict[str, Any]]*)

---

## 2. `database` Package

### 2.1 `database.documents`
- `fetch_all_documents() -> List[Dict[str, Any]]`: Returns all guideline documents ordered by effective date.
- `fetch_document_version_history(title: str) -> List[Dict[str, Any]]`: Returns version lineage for a title.
- `update_document_status(document_id: str, new_status: str) -> bool`: Updates lifecycle status (`ACTIVE`, `SUPERSEDED`, `ARCHIVED`).
- `delete_document(document_id: str, hard_delete: bool = False) -> bool`: Soft-archives or hard-deletes record.

### 2.2 `database.chunks`
- `search_similar_chunks(query_embedding: List[float], top_k: int = 10, **filters) -> List[Dict[str, Any]]`: Performs cosine similarity HNSW vector search (`<=>`) in Supabase PostgreSQL.
- `bulk_insert_chunks(chunks: List[Dict[str, Any]]) -> int`: Batch inserts chunk records with vectors.
- `delete_chunks_by_document_id(document_id: str) -> int`: Cascades chunk deletion.

### 2.3 `database.connection_pool`
- `get_connection_pool()`: Returns thread-safe connection pool with health probes.
- `execute_pooled_query(query: str, params: tuple = ()) -> List[dict]`: Executes query with automatic retry on disconnect.

---

## 3. `utils` Package

- `utils.i18n.t(key: str, **kwargs) -> str`: Multilingual translation resolver.
- `utils.i18n.render_language_selector()`: Language switch dropdown component.
- `utils.export.build_summary_pdf(message: dict) -> bytes`: Generates branded PDF summary sheet.
- `utils.export.build_summary_text(message: dict) -> str`: Generates plain-text export.
- `utils.ui_helpers.status_badge_html(status: str) -> str`: HTML pill with theme status styling.
