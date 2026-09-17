"""
database/documents.py
---------------------
CRUD handlers for the `documents` table in Supabase.

Responsibilities:
- Insert a new document metadata record and return its UUID.
- Fetch all documents with optional status filtering.
- Update the status of an existing document (ACTIVE / SUPERSEDED / ARCHIVED).
- Automatically supersede older versions when a new version is uploaded.
- Fetch the full version history for a document title.
- Archive a document by document_id.

Usage:
    from database.documents import (
        insert_document_record,
        fetch_all_documents,
        update_document_status,
        supersede_previous_versions,
        fetch_document_version_history,
        archive_document,
    )
"""

from __future__ import annotations

from datetime import date
from typing import Any

from database.supabase_client import get_supabase_client

# Valid lifecycle statuses — must match the document_status ENUM in schema.sql
VALID_STATUSES = {"ACTIVE", "SUPERSEDED", "ARCHIVED"}


def insert_document_record(
    title: str,
    version: str = "v1",
    publication_date: date | str | None = None,
    effective_date: date | str | None = None,
    status: str = "ACTIVE",
    language: str = "en",
) -> str:
    """
    Inserts a new document metadata record into the `documents` table.

    Args:
        title:            Human-readable document name, e.g. "Vaccination Protocol".
        version:          Version string, e.g. "v3". Defaults to "v1".
        publication_date: Date the document was officially published (optional).
                          Accepts a date object or ISO-format string "YYYY-MM-DD".
        effective_date:   Date from which the document is in effect (optional).
                          Accepts a date object or ISO-format string "YYYY-MM-DD".
        status:           Initial lifecycle status. One of ACTIVE | SUPERSEDED | ARCHIVED.
                          Defaults to "ACTIVE".
        language:         BCP-47 language tag of the document content, e.g. "en", "hi".
                          Defaults to "en".

    Returns:
        document_id (str): UUID of the newly created document record.

    Raises:
        ValueError:   If title is empty or status is not a valid value.
        RuntimeError: If the Supabase insert fails.
    """
    if not title or not title.strip():
        raise ValueError("Document title must not be empty.")

    status = status.upper()
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {', '.join(VALID_STATUSES)}."
        )

    # Convert date objects to ISO strings — Supabase REST API expects strings
    payload: dict[str, Any] = {
        "title":    title.strip(),
        "version":  version.strip(),
        "status":   status,
        "language": language.strip().lower() if language else "en",
    }

    if publication_date is not None:
        payload["publication_date"] = (
            publication_date.isoformat()
            if isinstance(publication_date, date)
            else str(publication_date)
        )

    if effective_date is not None:
        payload["effective_date"] = (
            effective_date.isoformat()
            if isinstance(effective_date, date)
            else str(effective_date)
        )

    try:
        client = get_supabase_client()
        response = (
            client.table("documents")
            .insert(payload)
            .execute()
        )

        if not response.data:
            raise RuntimeError("Insert returned no data — check Supabase RLS policies.")

        document_id: str = response.data[0]["id"]
        print(f"[documents] Inserted document '{title}' (lang={language}) → id={document_id}")
        return document_id

    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to insert document record: {exc}") from exc


def fetch_all_documents(
    status_filter: str | list[str] | None = None,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieves all documents from the `documents` table, optionally filtered
    by one or more lifecycle statuses and/or language tag.

    Args:
        status_filter: A single status string (e.g. "ACTIVE"), a list of
                       statuses (e.g. ["ACTIVE", "SUPERSEDED"]), or None to
                       return all documents regardless of status.
        language:      BCP-47 language tag to filter by (e.g. "en", "hi").
                       Pass None to return documents in all languages.

    Returns:
        List of document dicts with keys:
            id, title, version, language, publication_date, effective_date, status, created_at.
        Ordered by created_at descending (newest first).

    Raises:
        ValueError:   If a supplied status value is not valid.
        RuntimeError: If the Supabase query fails.
    """
    try:
        client = get_supabase_client()
        query = (
            client.table("documents")
            .select("id, title, version, language, publication_date, effective_date, status, created_at")
            .order("created_at", desc=True)
        )

        # Apply status filter(s)
        if status_filter is not None:
            if isinstance(status_filter, str):
                statuses = [status_filter.upper()]
            else:
                statuses = [s.upper() for s in status_filter]

            for s in statuses:
                if s not in VALID_STATUSES:
                    raise ValueError(
                        f"Invalid status filter '{s}'. Must be one of: {', '.join(VALID_STATUSES)}."
                    )

            if len(statuses) == 1:
                query = query.eq("status", statuses[0])
            else:
                query = query.in_("status", statuses)

        # Apply language filter
        if language is not None:
            query = query.eq("language", language.strip().lower())

        response = query.execute()
        documents: list[dict[str, Any]] = response.data or []
        print(
            f"[documents] Fetched {len(documents)} document(s) — "
            f"status={status_filter}, language={language}"
        )
        return documents

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch documents: {exc}") from exc


def update_document_status(document_id: str, status: str) -> bool:
    """
    Updates the lifecycle status of an existing document.

    Common use cases:
    - Mark an older version as SUPERSEDED when a new version is uploaded.
    - Archive a document that is no longer relevant.
    - Reactivate a document by setting it back to ACTIVE.

    Args:
        document_id: UUID string of the target document.
        status:      New status value. One of ACTIVE | SUPERSEDED | ARCHIVED.

    Returns:
        True  — update was applied successfully.
        False — no document matched the given document_id.

    Raises:
        ValueError:   If document_id is empty or status is invalid.
        RuntimeError: If the Supabase update fails.
    """
    if not document_id or not document_id.strip():
        raise ValueError("document_id must not be empty.")

    status = status.upper()
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {', '.join(VALID_STATUSES)}."
        )

    try:
        client = get_supabase_client()
        response = (
            client.table("documents")
            .update({"status": status})
            .eq("id", document_id)
            .execute()
        )

        updated = response.data or []
        if not updated:
            print(f"[documents] No document found with id={document_id}")
            return False

        print(f"[documents] Updated document id={document_id} -> status={status}")
        return True

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to update status for document id={document_id}: {exc}"
        ) from exc


def supersede_previous_versions(title: str, new_version: str) -> int:
    """
    Marks all existing ACTIVE documents with the given title as SUPERSEDED,
    except for the document matching new_version.

    Call this immediately after inserting a new version of a document so that
    the retrieval system stops preferring stale guidance.

    Example:
        After uploading "Vaccination Protocol v3", call:
            supersede_previous_versions("Vaccination Protocol", "v3")
        This sets v1 and v2 to SUPERSEDED while v3 remains ACTIVE.

    Args:
        title:       Exact document title to match (case-insensitive).
        new_version: Version string of the newly uploaded document to exclude
                     from superseding, e.g. "v3".

    Returns:
        Number of document records updated to SUPERSEDED.

    Raises:
        ValueError:   If title or new_version are empty.
        RuntimeError: If the Supabase update fails.
    """
    if not title or not title.strip():
        raise ValueError("title must not be empty.")
    if not new_version or not new_version.strip():
        raise ValueError("new_version must not be empty.")

    try:
        client = get_supabase_client()

        # Find all ACTIVE records with the same title that are NOT the new version
        response = (
            client.table("documents")
            .update({"status": "SUPERSEDED"})
            .ilike("title", title.strip())       # case-insensitive title match
            .eq("status", "ACTIVE")
            .neq("version", new_version.strip())  # exclude the new version
            .execute()
        )

        updated = response.data or []
        count = len(updated)
        print(
            f"[documents] supersede_previous_versions: '{title}' — "
            f"{count} older version(s) marked SUPERSEDED (new version: {new_version})."
        )
        return count

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to supersede previous versions for title='{title}': {exc}"
        ) from exc


def fetch_document_version_history(title: str) -> list[dict[str, Any]]:
    """
    Returns all versions of a document with the given title, ordered by
    publication_date ascending (oldest first: v1, v2, v3, ...).

    Useful for displaying the full version timeline in the admin UI and for
    understanding which version superseded which.

    Args:
        title: Exact document title to match (case-insensitive).

    Returns:
        List of document dicts with keys:
            id, title, version, publication_date, effective_date, status, created_at.
        Ordered by publication_date ascending (nulls last), then created_at ascending.

    Raises:
        ValueError:   If title is empty.
        RuntimeError: If the Supabase query fails.
    """
    if not title or not title.strip():
        raise ValueError("title must not be empty.")

    try:
        client = get_supabase_client()

        response = (
            client.table("documents")
            .select("id, title, version, publication_date, effective_date, status, created_at")
            .ilike("title", title.strip())         # case-insensitive match
            .order("publication_date", desc=False)  # oldest version first
            .order("created_at", desc=False)        # tiebreak by upload time
            .execute()
        )

        history: list[dict[str, Any]] = response.data or []
        print(
            f"[documents] fetch_document_version_history: '{title}' — "
            f"{len(history)} version(s) found."
        )
        return history

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch version history for title='{title}': {exc}"
        ) from exc


def archive_document(document_id: str) -> bool:
    """
    Sets a document's status to ARCHIVED, removing it from active retrieval
    while retaining the record for audit and history purposes.

    An archived document will not appear in ACTIVE or SUPERSEDED queries and
    will not be returned by the vector similarity search (which defaults to
    status_filter="ACTIVE").

    Args:
        document_id: UUID string of the document to archive.

    Returns:
        True  — document was found and archived successfully.
        False — no document matched the given document_id.

    Raises:
        ValueError:   If document_id is empty.
        RuntimeError: If the Supabase update fails.
    """
    if not document_id or not document_id.strip():
        raise ValueError("document_id must not be empty.")

    try:
        client = get_supabase_client()

        response = (
            client.table("documents")
            .update({"status": "ARCHIVED"})
            .eq("id", document_id.strip())
            .execute()
        )

        updated = response.data or []
        if not updated:
            print(f"[documents] archive_document: No document found with id={document_id}.")
            return False

        print(f"[documents] archive_document: Document id={document_id} → ARCHIVED.")
        return True

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to archive document id={document_id}: {exc}"
        ) from exc


def delete_document(document_id: str, hard_delete: bool = False) -> bool:
    """
    Deletes or archives a document by document_id.

    Args:
        document_id: UUID of document to delete/archive.
        hard_delete: If True, permanently removes record from `documents` table
                     (cascading deletes `document_chunks`).
                     If False (default), soft-deletes by updating status to ARCHIVED.

    Returns:
        True if document was deleted/archived, False if document_id not found.
    """
    if not document_id or not document_id.strip():
        raise ValueError("document_id must not be empty.")

    if not hard_delete:
        return update_document_status(document_id, "ARCHIVED")

    try:
        client = get_supabase_client()
        response = (
            client.table("documents")
            .delete()
            .eq("id", document_id.strip())
            .execute()
        )
        deleted = response.data or []
        if not deleted:
            print(f"[documents] delete_document: No document found with id={document_id}.")
            return False

        print(f"[documents] delete_document: Hard deleted document id={document_id}.")
        return True
    except Exception as exc:
        raise RuntimeError(f"Failed to delete document id={document_id}: {exc}") from exc


def bulk_delete_documents(document_ids: list[str], hard_delete: bool = False) -> int:
    """
    Deletes or archives multiple documents by their UUIDs.

    Args:
        document_ids: List of document UUID strings.
        hard_delete: If True, permanently removes records from `documents` table.
                     If False (default), soft-deletes by setting status to ARCHIVED.

    Returns:
        Number of documents successfully deleted/archived.
    """
    if not document_ids:
        return 0

    ids = [d.strip() for d in document_ids if d and d.strip()]
    if not ids:
        return 0

    try:
        client = get_supabase_client()
        if not hard_delete:
            response = (
                client.table("documents")
                .update({"status": "ARCHIVED"})
                .in_("id", ids)
                .execute()
            )
        else:
            response = (
                client.table("documents")
                .delete()
                .in_("id", ids)
                .execute()
            )
        affected = response.data or []
        count = len(affected)
        print(f"[documents] bulk_delete_documents: {count} document(s) processed (hard_delete={hard_delete}).")
        return count
    except Exception as exc:
        raise RuntimeError(f"Failed to bulk delete documents: {exc}") from exc


def restore_archived_document(document_id: str) -> bool:
    """
    Restores an ARCHIVED document back to ACTIVE status.

    Args:
        document_id: UUID of document to restore.

    Returns:
        True if document was restored, False otherwise.
    """
    return update_document_status(document_id, "ACTIVE")

