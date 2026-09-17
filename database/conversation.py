"""
database/conversation.py
------------------------
CRUD handlers for chat_sessions and chat_messages tables.

Responsibilities:
- Create and manage multi-turn conversation sessions per user.
- Insert user and assistant messages with optional citations.
- Retrieve full session history ordered chronologically.
- List all sessions for a user, most recent first.
- Delete a session and all its messages (cascade).

Usage:
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
"""

from __future__ import annotations

from typing import Any

from database.supabase_client import get_supabase_client

# Valid message roles — must match the CHECK constraint in schema.sql
VALID_ROLES = {"user", "assistant"}


# =============================================================================
# Session handlers
# =============================================================================

def create_chat_session(
    user_id: str,
    title: str | None = None,
) -> dict[str, Any]:
    """
    Creates a new chat session for a user.

    Args:
        user_id: External user identifier (matches user_locale_preferences.user_id).
        title:   Optional human-readable session title. When omitted the session
                 title is NULL — callers can update it after the first message
                 using update_session_title().

    Returns:
        The created session record dict with keys:
            id, user_id, title, created_at, updated_at.

    Raises:
        ValueError:   If user_id is empty.
        RuntimeError: If the Supabase insert fails.
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id must not be empty.")

    payload: dict[str, Any] = {"user_id": user_id.strip()}
    if title and title.strip():
        payload["title"] = title.strip()

    try:
        client = get_supabase_client()
        response = client.table("chat_sessions").insert(payload).execute()

        if not response.data:
            raise RuntimeError("Insert returned no data — check Supabase RLS policies.")

        session = response.data[0]
        print(f"[conversation] Created session id={session['id']} for user_id={user_id!r}.")
        return session

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to create chat session for user_id={user_id!r}: {exc}") from exc


def get_chat_session(session_id: str) -> dict[str, Any] | None:
    """
    Retrieves a single chat session by its UUID.

    Args:
        session_id: UUID string of the session.

    Returns:
        Session record dict, or None if not found.

    Raises:
        ValueError:   If session_id is empty.
        RuntimeError: If the Supabase query fails.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty.")

    try:
        client = get_supabase_client()
        response = (
            client.table("chat_sessions")
            .select("id, user_id, title, created_at, updated_at")
            .eq("id", session_id.strip())
            .limit(1)
            .execute()
        )

        data = response.data or []
        return data[0] if data else None

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch session id={session_id!r}: {exc}") from exc


def list_user_sessions(
    user_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Returns all chat sessions for a user, ordered by most recently updated first.

    Args:
        user_id: External user identifier.
        limit:   Maximum number of sessions to return. Defaults to 20.

    Returns:
        List of session dicts with keys: id, user_id, title, created_at, updated_at.
        Ordered by updated_at descending (most recent first).

    Raises:
        ValueError:   If user_id is empty or limit < 1.
        RuntimeError: If the Supabase query fails.
    """
    if not user_id or not user_id.strip():
        raise ValueError("user_id must not be empty.")
    if limit < 1:
        raise ValueError("limit must be at least 1.")

    try:
        client = get_supabase_client()
        response = (
            client.table("chat_sessions")
            .select("id, user_id, title, created_at, updated_at")
            .eq("user_id", user_id.strip())
            .order("updated_at", desc=True)
            .limit(limit)
            .execute()
        )

        sessions: list[dict[str, Any]] = response.data or []
        print(f"[conversation] list_user_sessions: user_id={user_id!r} → {len(sessions)} session(s).")
        return sessions

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to list sessions for user_id={user_id!r}: {exc}") from exc


def update_session_title(session_id: str, title: str) -> bool:
    """
    Updates the human-readable title of an existing session.

    Typically called after the first user message is saved, using the
    truncated question text as the title.

    Args:
        session_id: UUID of the target session.
        title:      New title string (will be stripped and truncated to 200 chars).

    Returns:
        True  — title was updated.
        False — no session matched the given session_id.

    Raises:
        ValueError:   If session_id or title are empty.
        RuntimeError: If the Supabase update fails.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty.")
    if not title or not title.strip():
        raise ValueError("title must not be empty.")

    # Truncate to 200 chars to keep session list readable
    trimmed_title = title.strip()[:200]

    try:
        client = get_supabase_client()
        response = (
            client.table("chat_sessions")
            .update({"title": trimmed_title})
            .eq("id", session_id.strip())
            .execute()
        )

        updated = response.data or []
        if not updated:
            print(f"[conversation] update_session_title: No session found id={session_id!r}.")
            return False

        print(f"[conversation] Session id={session_id!r} title updated → {trimmed_title!r}.")
        return True

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to update title for session id={session_id!r}: {exc}") from exc


def delete_chat_session(session_id: str) -> bool:
    """
    Deletes a chat session and all its messages (ON DELETE CASCADE).

    Args:
        session_id: UUID of the session to delete.

    Returns:
        True  — session was deleted.
        False — no session matched the given session_id.

    Raises:
        ValueError:   If session_id is empty.
        RuntimeError: If the Supabase delete fails.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty.")

    try:
        client = get_supabase_client()
        response = (
            client.table("chat_sessions")
            .delete()
            .eq("id", session_id.strip())
            .execute()
        )

        deleted = response.data or []
        if not deleted:
            print(f"[conversation] delete_chat_session: No session found id={session_id!r}.")
            return False

        print(f"[conversation] Deleted session id={session_id!r} (messages cascaded).")
        return True

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(f"Failed to delete session id={session_id!r}: {exc}") from exc


# =============================================================================
# Message handlers
# =============================================================================

def add_chat_message(
    session_id: str,
    role: str,
    content: str,
    citations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Inserts a new message into a chat session.

    Also touches the parent session's updated_at timestamp so the session
    list remains sorted by most-recently-active.

    Args:
        session_id: UUID of the parent session.
        role:       Message author. Must be "user" or "assistant".
        content:    Raw message text.
        citations:  Optional list of citation dicts for assistant messages.
                    Each dict typically contains: title, version, page_number,
                    effective_date, document_id.

    Returns:
        The inserted message record dict with keys:
            id, session_id, role, content, citations, created_at.

    Raises:
        ValueError:   If session_id/content are empty or role is invalid.
        RuntimeError: If the Supabase insert fails.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty.")
    if not content or not content.strip():
        raise ValueError("content must not be empty.")

    role = role.strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(
            f"Invalid role '{role}'. Must be one of: {', '.join(VALID_ROLES)}."
        )

    payload: dict[str, Any] = {
        "session_id": session_id.strip(),
        "role":       role,
        "content":    content.strip(),
        "citations":  citations or None,
    }

    try:
        client = get_supabase_client()

        # Insert the message
        response = client.table("chat_messages").insert(payload).execute()

        if not response.data:
            raise RuntimeError("Insert returned no data — check Supabase RLS policies.")

        message = response.data[0]

        # Touch the session's updated_at so it bubbles to top of session list
        client.table("chat_sessions").update(
            {"updated_at": message["created_at"]}
        ).eq("id", session_id.strip()).execute()

        print(
            f"[conversation] Message added: session={session_id!r}, "
            f"role={role!r}, id={message['id']}."
        )
        return message

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to add message to session id={session_id!r}: {exc}"
        ) from exc


def get_session_messages(
    session_id: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieves all messages in a session ordered chronologically (oldest first).

    This is the primary method for reconstructing conversation context to pass
    to the LLM as multi-turn history.

    Args:
        session_id: UUID of the target session.
        limit:      Optional cap on the number of most-recent messages to
                    return. Pass None to return all messages.

    Returns:
        List of message dicts with keys:
            id, session_id, role, content, citations, created_at.
        Ordered by created_at ascending (oldest first).

    Raises:
        ValueError:   If session_id is empty.
        RuntimeError: If the Supabase query fails.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty.")

    try:
        client = get_supabase_client()
        query = (
            client.table("chat_messages")
            .select("id, session_id, role, content, citations, created_at")
            .eq("session_id", session_id.strip())
            .order("created_at", desc=False)   # chronological order for LLM context
        )

        if limit is not None and limit > 0:
            query = query.limit(limit)

        response = query.execute()
        messages: list[dict[str, Any]] = response.data or []
        print(
            f"[conversation] get_session_messages: session={session_id!r} → "
            f"{len(messages)} message(s)."
        )
        return messages

    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Failed to fetch messages for session id={session_id!r}: {exc}"
        ) from exc


def get_session_message_count(session_id: str) -> int:
    """
    Returns the total number of messages in a session.

    Useful for checking whether a session is empty before displaying it,
    or for paginating long conversation histories.

    Args:
        session_id: UUID of the target session.

    Returns:
        Integer message count. Returns 0 if the session does not exist.

    Raises:
        ValueError: If session_id is empty.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty.")

    try:
        client = get_supabase_client()
        response = (
            client.table("chat_messages")
            .select("id", count="exact")
            .eq("session_id", session_id.strip())
            .execute()
        )
        return response.count or 0

    except Exception as exc:
        print(f"[conversation] get_session_message_count failed: {exc}")
        return 0
