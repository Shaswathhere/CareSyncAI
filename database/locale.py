"""
database/locale.py
------------------
CRUD handlers for user locale preferences and language-filtered document queries.

Responsibilities:
- Upsert a user's preferred language setting.
- Fetch a user's locale preference record.
- Fetch documents filtered by language tag.
- List all distinct languages available in the knowledge base.

Usage:
    from database.locale import (
        upsert_user_locale,
        get_user_locale,
        fetch_documents_by_language,
        list_available_languages,
    )
"""

from __future__ import annotations

from typing import Any

from database.supabase_client import get_supabase_client

# Sensible set of supported BCP-47 tags for validation.
# Extend this list as new languages are added to the knowledge base.
SUPPORTED_LANGUAGES = {
    "en", "hi", "fr", "ta", "te", "kn", "ml", "bn",
    "mr", "gu", "pa", "ur", "ar", "es", "pt", "sw",
}


def _validate_lang(tag: str, field_name: str = "language") -> str:
    """Normalise to lowercase and validate against supported BCP-47 tags."""
    tag = tag.strip().lower()
    if not tag:
        raise ValueError(f"{field_name} must not be empty.")
    if tag not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported {field_name} tag '{tag}'. "
            f"Supported tags: {', '.join(sorted(SUPPORTED_LANGUAGES))}."
        )
    return tag


def upsert_user_locale(
    user_id: str,
    preferred_lang: str,
    fallback_lang: str = "en",
) -> dict[str, Any]:
    """
    Creates or updates the locale preference record for a user.

    If a record already exists for the given user_id, it is updated in-place
    (the updated_at trigger fires automatically). Otherwise a new record is
    inserted.

    Args:
        user_id:        External user identifier (e.g. Supabase Auth UUID,
                        session token, or device ID).
        preferred_lang: Primary language preference as a BCP-47 tag,
                        e.g. "en", "hi", "fr".
        fallback_lang:  Language to fall back to when no documents are
                        available in preferred_lang. Defaults to "en".

    Returns:
        The upserted preference record dict with keys:
            id, user_id, preferred_lang, fallback_lang, created_at, updated_at.

    Raises:
        ValueError:   If user_id is empty or a language tag is unsupported.
        RuntimeError: If the Supabase upsert fails.
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id must not be empty.")

    preferred_lang = _validate_lang(preferred_lang, "preferred_lang")
    fallback_lang  = _validate_lang(fallback_lang, "fallback_lang")

    payload = {
        "user_id":        user_id.strip(),
        "preferred_lang": preferred_lang,
        "fallback_lang":  fallback_lang,
    }

    try:
        client = get_supabase_client()
        response = (
            client.table("user_locale_preferences")
            .upsert(payload, on_conflict="user_id")   # update if user_id already exists
            .execute()
        )

        if not response.data:
            raise RuntimeError("Upsert returned no data — check Supabase RLS policies.")

        record: dict[str, Any] = response.data[0]
        print(
            f"[locale] upsert_user_locale: user_id={user_id!r} → "
            f"preferred={preferred_lang}, fallback={fallback_lang}."
        )
        return record

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to upsert locale preference for user_id={user_id!r}: {exc}") from exc


def get_user_locale(user_id: str) -> dict[str, Any] | None:
    """
    Retrieves the locale preference record for a user.

    Args:
        user_id: External user identifier.

    Returns:
        Preference record dict, or None if no record exists for this user.

    Raises:
        ValueError:   If user_id is empty.
        RuntimeError: If the Supabase query fails.
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id must not be empty.")

    try:
        client = get_supabase_client()
        response = (
            client.table("user_locale_preferences")
            .select("id, user_id, preferred_lang, fallback_lang, created_at, updated_at")
            .eq("user_id", user_id.strip())
            .limit(1)
            .execute()
        )

        data = response.data or []
        if not data:
            print(f"[locale] get_user_locale: No preference found for user_id={user_id!r}.")
            return None

        return data[0]

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch locale for user_id={user_id!r}: {exc}") from exc


def fetch_documents_by_language(
    language: str,
    status_filter: str | None = "ACTIVE",
) -> list[dict[str, Any]]:
    """
    Returns all documents tagged with the given language, optionally filtered
    by lifecycle status.

    Useful for showing field workers only the documents written in their
    preferred language, and for language-aware retrieval routing.

    Args:
        language:      BCP-47 language tag to filter by, e.g. "hi", "en".
        status_filter: Lifecycle status filter. Defaults to "ACTIVE".
                       Pass None to return documents of all statuses.

    Returns:
        List of document dicts with keys:
            id, title, version, language, effective_date, status, created_at.
        Ordered by created_at descending.

    Raises:
        ValueError:   If language tag is unsupported.
        RuntimeError: If the Supabase query fails.
    """
    language = _validate_lang(language, "language")

    VALID_STATUSES = {"ACTIVE", "SUPERSEDED", "ARCHIVED"}
    if status_filter is not None:
        status_filter = status_filter.upper()
        if status_filter not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status_filter '{status_filter}'. "
                f"Must be one of: {', '.join(VALID_STATUSES)} or None."
            )

    try:
        client = get_supabase_client()
        query = (
            client.table("documents")
            .select("id, title, version, language, effective_date, status, created_at")
            .eq("language", language)
            .order("created_at", desc=True)
        )

        if status_filter is not None:
            query = query.eq("status", status_filter)

        response = query.execute()
        docs: list[dict[str, Any]] = response.data or []
        print(
            f"[locale] fetch_documents_by_language: language={language!r}, "
            f"status={status_filter} → {len(docs)} document(s)."
        )
        return docs

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch documents for language={language!r}: {exc}") from exc


def list_available_languages() -> list[str]:
    """
    Returns a sorted list of all distinct language tags present in the
    documents table — regardless of document status.

    Useful for populating a language-selector dropdown in the UI.

    Returns:
        Sorted list of BCP-47 language tag strings, e.g. ["en", "fr", "hi"].

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    try:
        client = get_supabase_client()
        response = (
            client.table("documents")
            .select("language")
            .execute()
        )

        data = response.data or []
        languages = sorted({row["language"] for row in data if row.get("language")})
        print(f"[locale] list_available_languages: {languages}")
        return languages

    except Exception as exc:
        raise RuntimeError(f"Failed to list available languages: {exc}") from exc
