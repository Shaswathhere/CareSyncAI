# RAG module
from rag.pipeline import process_and_embed_document, query_rag_pipeline, query_version_comparison_pipeline, process_voice_query
from rag.reranker import rerank_chunks, get_reranker_model_name
from rag.query_contextualizer import reformulate_query_with_history
from rag.transcriber import transcribe_audio_groq, transcribe_audio_gemini
from rag.translator import (
    detect_query_language,
    translate_query_to_english,
    translate_answer_to_language,
    multilingual_rag_query,
    LANGUAGE_NAMES,
)

from rag.evaluation import (
    BenchmarkTestCase,
    BenchmarkSummary,
    EvaluationMetrics,
    EvaluationResult,
    DEFAULT_BENCHMARK_DATASET,
    evaluate_response,
    run_rag_benchmark,
    format_benchmark_markdown,
)

from rag.rerank_cache import (
    RerankCache,
    get_rerank_cache,
    clear_rerank_cache,
    get_cache_stats,
)
from rag.embedding_cache import (
    EmbeddingCache,
    clear_embedding_cache,
    get_embedding_cache,
    get_embedding_cache_stats,
)

__all__ = [
    "process_and_embed_document",
    "query_rag_pipeline",
    "query_version_comparison_pipeline",
    "process_voice_query",
    "rerank_chunks",
    "get_reranker_model_name",
    "reformulate_query_with_history",
    "transcribe_audio_gemini",
    "detect_query_language",
    "translate_query_to_english",
    "translate_answer_to_language",
    "multilingual_rag_query",
    "LANGUAGE_NAMES",
    "BenchmarkTestCase",
    "BenchmarkSummary",
    "EvaluationMetrics",
    "EvaluationResult",
    "DEFAULT_BENCHMARK_DATASET",
    "evaluate_response",
    "run_rag_benchmark",
    "format_benchmark_markdown",
    "RerankCache",
    "get_rerank_cache",
    "clear_rerank_cache",
    "get_cache_stats",
    "EmbeddingCache",
    "get_embedding_cache",
    "clear_embedding_cache",
    "get_embedding_cache_stats",
]
