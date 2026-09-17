"""
config.py
---------
Central configuration for CareSync AI.
All values are loaded from environment variables (via .env).
Import from this module instead of calling os.getenv() directly elsewhere.
"""

import os
from dotenv import load_dotenv

# Load .env file if present (no-op in production where env vars are set externally)
load_dotenv()


# ── Supabase ──────────────────────────────────────────────────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

# ── Groq LLM (free tier) ─────────────────────────────────────────────────────
# Get a free key at https://console.groq.com/keys
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")

# ── Embedding Model ───────────────────────────────────────────────────────────
# all-MiniLM-L6-v2 produces 384-dimensional vectors — matches schema vector(384)
EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

# Query embedding cache. The cache is process-local and avoids repeated model
# inference for equivalent high-frequency search queries.
EMBEDDING_CACHE_TTL_SECONDS: int = int(os.getenv("EMBEDDING_CACHE_TTL_SECONDS", "1800"))
EMBEDDING_CACHE_MAX_SIZE: int = int(os.getenv("EMBEDDING_CACHE_MAX_SIZE", "1000"))

# ── Chunking ──────────────────────────────────────────────────────────────────
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

# ── Identity ──────────────────────────────────────────────────────────────────
CARESYNC_USER_ID: str = os.getenv("CARESYNC_USER_ID", "")

# ── Guidelines Sync ───────────────────────────────────────────────────────────
# URL of the external public-health guidelines source.
# Set to "mock" to use the built-in mock endpoint (no HTTP call made).
GUIDELINES_SOURCE_URL: str = os.getenv("GUIDELINES_SOURCE_URL", "mock")

# Comma-separated document titles to watch — empty means watch all ACTIVE docs.
GUIDELINES_WATCH_TITLES: str = os.getenv("GUIDELINES_WATCH_TITLES", "")

# User ID written to system_metrics for cron-initiated sync operations.
SYNC_USER_ID: str = os.getenv("SYNC_USER_ID", "sync-cron")

# ── Connection Pool ───────────────────────────────────────────────────────────
# Maximum number of simultaneous Supabase REST API connections the pool will
# open. The Supabase free tier supports ~60 concurrent DB connections; the pro
# tier supports 200+. Keep this well below the project limit.
DB_POOL_MAX_CONNECTIONS: int = int(os.getenv("DB_POOL_MAX_CONNECTIONS", "10"))

# Seconds to wait for an idle connection from the pool before raising an error.
DB_POOL_TIMEOUT_SECONDS: int = int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30"))

# pgvector HNSW ef_search parameter set at query time via RPC.
# Higher values → better recall, slower queries.
# Recommended: 40 (dev) | 100 (prod) | 200 (high-recall audit).
HNSW_EF_SEARCH: int = int(os.getenv("HNSW_EF_SEARCH", "100"))


def validate_config() -> None:
    """
    Raises ValueError if any required environment variable is missing.
    Call this at application startup to catch misconfiguration early.
    """
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_KEY")
    if not GROQ_API_KEY:
        missing.append("GROQ_API_KEY")

    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and populate the values."
        )
