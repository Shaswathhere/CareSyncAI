# Database module
from database.supabase_client import get_supabase_client, check_db_connection
from database.connection_pool import (
    ConnectionPool,
    get_pool_client,
    pool_health_check,
    PoolTimeoutError,
)
from database.documents import (
    insert_document_record,
    fetch_all_documents,
    update_document_status,
    supersede_previous_versions,
    fetch_document_version_history,
    archive_document,
    delete_document,
    bulk_delete_documents,
    restore_archived_document,
)
from database.chunks import (
    insert_document_chunks,
    search_similar_chunks,
    delete_chunks_by_document_id,
    fetch_chunk_count_by_document,
    bulk_fetch_chunks_by_documents,
)
from database.query_logger import (
    log_query_performance,
    get_recent_logs,
    get_slow_queries,
    get_average_latency,
    QueryLog,
)
from database.locale import (
    upsert_user_locale,
    get_user_locale,
    fetch_documents_by_language,
    list_available_languages,
)
from database.conversation import (
    create_chat_session,
    get_chat_session,
    list_user_sessions,
    update_session_title,
    delete_chat_session,
    add_chat_message,
    get_session_messages,
    get_session_message_count,
)
from database.audio import (
    log_audio_query,
    update_audio_query_transcription,
    fail_audio_query,
    get_audio_query,
    list_user_audio_queries,
    insert_transcription_audit,
    get_transcription_audit,
    list_unreviewed_transcriptions,
    mark_transcription_reviewed,
)
from database.feedback import (
    submit_feedback,
    get_message_feedback_summary,
    list_session_feedback,
    list_user_feedback,
    log_metrics,
    get_latency_summary,
    list_slow_queries,
    list_failed_queries,
)
from database.analytics import (
    get_daily_active_users,
    get_total_queries_over_time,
    get_top_queried_topics,
    get_feedback_satisfaction_rate,
    get_system_health_metrics,
)

__all__ = [
    # Supabase client
    "get_supabase_client",
    "check_db_connection",
    # Connection pool
    "ConnectionPool",
    "get_pool_client",
    "pool_health_check",
    "PoolTimeoutError",
    # Documents
    "insert_document_record",
    "fetch_all_documents",
    "update_document_status",
    "supersede_previous_versions",
    "fetch_document_version_history",
    "archive_document",
    "delete_document",
    "bulk_delete_documents",
    "restore_archived_document",
    # Chunks
    "insert_document_chunks",
    "search_similar_chunks",
    "delete_chunks_by_document_id",
    "fetch_chunk_count_by_document",
    "bulk_fetch_chunks_by_documents",
    # Query logger
    "log_query_performance",
    "get_recent_logs",
    "get_slow_queries",
    "get_average_latency",
    "QueryLog",
    # Locale
    "upsert_user_locale",
    "get_user_locale",
    "fetch_documents_by_language",
    "list_available_languages",
    # Conversation
    "create_chat_session",
    "get_chat_session",
    "list_user_sessions",
    "update_session_title",
    "delete_chat_session",
    "add_chat_message",
    "get_session_messages",
    "get_session_message_count",
    # Audio
    "log_audio_query",
    "update_audio_query_transcription",
    "fail_audio_query",
    "get_audio_query",
    "list_user_audio_queries",
    "insert_transcription_audit",
    "get_transcription_audit",
    "list_unreviewed_transcriptions",
    "mark_transcription_reviewed",
    # Feedback & metrics
    "submit_feedback",
    "get_message_feedback_summary",
    "list_session_feedback",
    "list_user_feedback",
    "log_metrics",
    "get_latency_summary",
    "list_slow_queries",
    "list_failed_queries",
    # Analytics
    "get_daily_active_users",
    "get_total_queries_over_time",
    "get_top_queried_topics",
    "get_feedback_satisfaction_rate",
    "get_system_health_metrics",
]

__all__ = [
    "get_supabase_client",
    "check_db_connection",
    "insert_document_record",
    "fetch_all_documents",
    "update_document_status",
    "supersede_previous_versions",
    "fetch_document_version_history",
    "archive_document",
    "delete_document",
    "bulk_delete_documents",
    "restore_archived_document",
    "insert_document_chunks",
    "search_similar_chunks",
    "delete_chunks_by_document_id",
    "fetch_chunk_count_by_document",
    "bulk_fetch_chunks_by_documents",
    "log_query_performance",
    "get_recent_logs",
    "get_slow_queries",
    "get_average_latency",
    "QueryLog",
    "upsert_user_locale",
    "get_user_locale",
    "fetch_documents_by_language",
    "list_available_languages",
]
