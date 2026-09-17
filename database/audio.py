"""
database/audio.py
-----------------
CRUD handlers for audio_query_log and transcription_audit tables.

Responsibilities:
- Log incoming audio query events with status tracking.
- Update transcription result and status on completion or failure.
- Insert detailed STT audit records for quality review.
- Query audio logs by user, session, and status.
- Fetch unreviewed transcriptions for human audit workflows.

Usage:
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
"""

from __future__ import annotations

from typing import Any

from database.supabase_client import get_supabase_client

VALID_STATUSES  = {"pending", "processing", "success", "failed"}
VALID_STT_ENGINES = {"whisper", "google", "azure", "deepgram", "aws"}


# =============================================================================
# audio_query_log handlers
# =============================================================================

def log_audio_query(
    user_id: str,
    language: str = "en",
    session_id: str | None = None,
    audio_file_ref: str | None = None,
    audio_duration_ms: int | None = None,
) -> dict[str, Any]:
    """
    Creates a new audio query log entry with status 'pending'.

    Call this as soon as an audio file is received, before transcription starts,
    to establish the log record. Update the record using
    update_audio_query_transcription() or fail_audio_query() once processing
    completes.

    Args:
        user_id:            External user identifier.
        language:           BCP-47 language tag of the audio. Defaults to "en".
        session_id:         Optional UUID of the related chat session.
        audio_file_ref:     Storage path or URL of the uploaded audio file.
        audio_duration_ms:  Duration of the audio clip in milliseconds.

    Returns:
        The created audio_query_log record dict with keys:
            id, user_id, session_id, audio_file_ref, audio_duration_ms,
            language, status, created_at.

    Raises:
        ValueError:   If user_id is empty.
        RuntimeError: If the Supabase insert fails.
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id must not be empty.")

    payload: dict[str, Any] = {
        "user_id":  user_id.strip(),
        "language": language.strip().lower() if language else "en",
        "status":   "pending",
    }
    if session_id and session_id.strip():
        payload["session_id"] = session_id.strip()
    if audio_file_ref and audio_file_ref.strip():
        payload["audio_file_ref"] = audio_file_ref.strip()
    if audio_duration_ms is not None:
        payload["audio_duration_ms"] = int(audio_duration_ms)

    try:
        client = get_supabase_client()
        response = client.table("audio_query_log").insert(payload).execute()

        if not response.data:
            raise RuntimeError("Insert returned no data — check Supabase RLS policies.")

        record = response.data[0]
        print(f"[audio] Logged audio query id={record['id']} for user_id={user_id!r}.")
        return record

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to log audio query for user_id={user_id!r}: {exc}") from exc


def update_audio_query_transcription(
    audio_query_id: str,
    transcription: str,
    transcription_ms: int | None = None,
    status: str = "success",
) -> bool:
    """
    Updates an audio query log record with the completed transcription result.

    Args:
        audio_query_id:   UUID of the audio_query_log record to update.
        transcription:    Raw transcript text produced by the STT engine.
        transcription_ms: Wall-clock time for the transcription call in ms.
        status:           Final status. Defaults to "success".

    Returns:
        True  — record was updated.
        False — no record matched the given audio_query_id.

    Raises:
        ValueError:   If audio_query_id or transcription are empty.
        RuntimeError: If the Supabase update fails.
    """
    if not audio_query_id or not audio_query_id.strip():
        raise ValueError("audio_query_id must not be empty.")
    if not transcription or not transcription.strip():
        raise ValueError("transcription must not be empty.")

    status = status.lower()
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {', '.join(VALID_STATUSES)}.")

    payload: dict[str, Any] = {
        "transcription": transcription.strip(),
        "status":        status,
    }
    if transcription_ms is not None:
        payload["transcription_ms"] = int(transcription_ms)

    try:
        client = get_supabase_client()
        response = (
            client.table("audio_query_log")
            .update(payload)
            .eq("id", audio_query_id.strip())
            .execute()
        )

        updated = response.data or []
        if not updated:
            print(f"[audio] update_audio_query_transcription: No record found id={audio_query_id!r}.")
            return False

        print(f"[audio] Audio query id={audio_query_id!r} updated → status={status}.")
        return True

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to update transcription for audio_query_id={audio_query_id!r}: {exc}"
        ) from exc


def fail_audio_query(
    audio_query_id: str,
    error_message: str,
) -> bool:
    """
    Marks an audio query log entry as failed with an error message.

    Args:
        audio_query_id: UUID of the audio_query_log record.
        error_message:  Description of the failure reason.

    Returns:
        True  — record was updated.
        False — no record matched the given audio_query_id.

    Raises:
        ValueError:   If audio_query_id or error_message are empty.
        RuntimeError: If the Supabase update fails.
    """
    if not audio_query_id or not audio_query_id.strip():
        raise ValueError("audio_query_id must not be empty.")
    if not error_message or not error_message.strip():
        raise ValueError("error_message must not be empty.")

    try:
        client = get_supabase_client()
        response = (
            client.table("audio_query_log")
            .update({"status": "failed", "error_message": error_message.strip()})
            .eq("id", audio_query_id.strip())
            .execute()
        )

        updated = response.data or []
        if not updated:
            print(f"[audio] fail_audio_query: No record found id={audio_query_id!r}.")
            return False

        print(f"[audio] Audio query id={audio_query_id!r} marked FAILED: {error_message!r}.")
        return True

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to mark audio query as failed id={audio_query_id!r}: {exc}"
        ) from exc


def get_audio_query(audio_query_id: str) -> dict[str, Any] | None:
    """
    Retrieves a single audio query log record by UUID.

    Args:
        audio_query_id: UUID of the record.

    Returns:
        Record dict or None if not found.

    Raises:
        ValueError:   If audio_query_id is empty.
        RuntimeError: If the Supabase query fails.
    """
    if not audio_query_id or not audio_query_id.strip():
        raise ValueError("audio_query_id must not be empty.")

    try:
        client = get_supabase_client()
        response = (
            client.table("audio_query_log")
            .select("*")
            .eq("id", audio_query_id.strip())
            .limit(1)
            .execute()
        )
        data = response.data or []
        return data[0] if data else None

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch audio query id={audio_query_id!r}: {exc}") from exc


def list_user_audio_queries(
    user_id: str,
    status_filter: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Returns audio query log entries for a user, ordered most recent first.

    Args:
        user_id:       External user identifier.
        status_filter: Optional status to filter by (pending/processing/success/failed).
        limit:         Maximum records to return. Defaults to 50.

    Returns:
        List of audio_query_log dicts ordered by created_at DESC.

    Raises:
        ValueError:   If user_id is empty or status_filter is invalid.
        RuntimeError: If the Supabase query fails.
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id must not be empty.")

    if status_filter is not None:
        status_filter = status_filter.lower()
        if status_filter not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status_filter '{status_filter}'. "
                f"Must be one of: {', '.join(VALID_STATUSES)}."
            )

    try:
        client = get_supabase_client()
        query = (
            client.table("audio_query_log")
            .select("*")
            .eq("user_id", user_id.strip())
            .order("created_at", desc=True)
            .limit(limit)
        )

        if status_filter:
            query = query.eq("status", status_filter)

        response = query.execute()
        records: list[dict[str, Any]] = response.data or []
        print(
            f"[audio] list_user_audio_queries: user_id={user_id!r}, "
            f"status={status_filter} → {len(records)} record(s)."
        )
        return records

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to list audio queries for user_id={user_id!r}: {exc}") from exc


# =============================================================================
# transcription_audit handlers
# =============================================================================

def insert_transcription_audit(
    audio_query_id: str,
    stt_engine: str,
    raw_transcript: str,
    confidence_score: float | None = None,
    word_timestamps: list[dict[str, Any]] | None = None,
    engine_response: dict[str, Any] | None = None,
    post_processed: str | None = None,
) -> dict[str, Any]:
    """
    Inserts a detailed STT audit record for a completed transcription.

    Call this after a transcription completes to capture the full engine
    output for quality analysis and model comparison.

    Args:
        audio_query_id:   UUID of the parent audio_query_log record.
        stt_engine:       Identifier of the STT engine, e.g. "whisper-large-v3".
        raw_transcript:   Unprocessed transcript string from the engine.
        confidence_score: Overall confidence (0.0–1.0) if provided by engine.
        word_timestamps:  List of per-word dicts with start_ms, end_ms, word, confidence.
        engine_response:  Full raw JSON response from the STT API.
        post_processed:   Transcript after cleaning / normalisation.

    Returns:
        The inserted transcription_audit record dict.

    Raises:
        ValueError:   If audio_query_id, stt_engine, or raw_transcript are empty.
        RuntimeError: If the Supabase insert fails.
    """
    if not audio_query_id or not audio_query_id.strip():
        raise ValueError("audio_query_id must not be empty.")
    if not stt_engine or not stt_engine.strip():
        raise ValueError("stt_engine must not be empty.")
    if not raw_transcript or not raw_transcript.strip():
        raise ValueError("raw_transcript must not be empty.")

    if confidence_score is not None and not (0.0 <= confidence_score <= 1.0):
        raise ValueError("confidence_score must be between 0.0 and 1.0.")

    payload: dict[str, Any] = {
        "audio_query_id": audio_query_id.strip(),
        "stt_engine":     stt_engine.strip(),
        "raw_transcript": raw_transcript.strip(),
    }
    if confidence_score is not None:
        payload["confidence_score"] = float(confidence_score)
    if word_timestamps is not None:
        payload["word_timestamps"] = word_timestamps
    if engine_response is not None:
        payload["engine_response"] = engine_response
    if post_processed and post_processed.strip():
        payload["post_processed"] = post_processed.strip()

    try:
        client = get_supabase_client()
        response = client.table("transcription_audit").insert(payload).execute()

        if not response.data:
            raise RuntimeError("Insert returned no data — check Supabase RLS policies.")

        record = response.data[0]
        print(
            f"[audio] Transcription audit inserted id={record['id']} "
            f"(engine={stt_engine!r}, query={audio_query_id!r})."
        )
        return record

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to insert transcription audit for audio_query_id={audio_query_id!r}: {exc}"
        ) from exc


def get_transcription_audit(audio_query_id: str) -> dict[str, Any] | None:
    """
    Retrieves the transcription audit record for an audio query.

    Args:
        audio_query_id: UUID of the parent audio_query_log record.

    Returns:
        Audit record dict, or None if no audit exists for this query.

    Raises:
        ValueError:   If audio_query_id is empty.
        RuntimeError: If the Supabase query fails.
    """
    if not audio_query_id or not audio_query_id.strip():
        raise ValueError("audio_query_id must not be empty.")

    try:
        client = get_supabase_client()
        response = (
            client.table("transcription_audit")
            .select("*")
            .eq("audio_query_id", audio_query_id.strip())
            .limit(1)
            .execute()
        )
        data = response.data or []
        return data[0] if data else None

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch transcription audit for audio_query_id={audio_query_id!r}: {exc}"
        ) from exc


def list_unreviewed_transcriptions(limit: int = 50) -> list[dict[str, Any]]:
    """
    Returns transcription audit records that have not yet been reviewed by a
    human, ordered oldest first (FIFO review queue).

    Args:
        limit: Maximum records to return. Defaults to 50.

    Returns:
        List of transcription_audit dicts where reviewed_at IS NULL,
        ordered by created_at ascending.

    Raises:
        RuntimeError: If the Supabase query fails.
    """
    try:
        client = get_supabase_client()
        response = (
            client.table("transcription_audit")
            .select("*")
            .is_("reviewed_at", "null")
            .order("created_at", desc=False)
            .limit(limit)
            .execute()
        )
        records: list[dict[str, Any]] = response.data or []
        print(f"[audio] list_unreviewed_transcriptions → {len(records)} record(s).")
        return records

    except Exception as exc:
        raise RuntimeError(f"Failed to list unreviewed transcriptions: {exc}") from exc


def mark_transcription_reviewed(
    audit_id: str,
    reviewed_by: str,
) -> bool:
    """
    Marks a transcription audit record as reviewed by a staff member.

    Args:
        audit_id:    UUID of the transcription_audit record.
        reviewed_by: user_id of the staff member completing the review.

    Returns:
        True  — record was updated.
        False — no record matched the given audit_id.

    Raises:
        ValueError:   If audit_id or reviewed_by are empty.
        RuntimeError: If the Supabase update fails.
    """
    if not audit_id or not audit_id.strip():
        raise ValueError("audit_id must not be empty.")
    if not reviewed_by or not reviewed_by.strip():
        raise ValueError("reviewed_by must not be empty.")

    try:
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()

        client = get_supabase_client()
        response = (
            client.table("transcription_audit")
            .update({"reviewed_by": reviewed_by.strip(), "reviewed_at": now_iso})
            .eq("id", audit_id.strip())
            .execute()
        )

        updated = response.data or []
        if not updated:
            print(f"[audio] mark_transcription_reviewed: No record found id={audit_id!r}.")
            return False

        print(f"[audio] Audit id={audit_id!r} marked reviewed by {reviewed_by!r}.")
        return True

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to mark transcription reviewed id={audit_id!r}: {exc}"
        ) from exc
