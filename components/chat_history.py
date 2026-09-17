"""
components/chat_history.py
---------------------------
Sidebar chat history drawer: a "New Chat" button, the field worker's recent
conversations, one-click session switching, and per-session rename/delete.

This module also owns chat persistence, because the drawer is only ever as
good as what got written. components/chat.py calls persist_user_message() and
persist_assistant_message() as each turn completes; the chat_sessions row
itself is created lazily on the first real question, so simply opening the app
never leaves an empty conversation in the list.

Everything here degrades to a local-only chat. The first Supabase failure sets
a session flag, after which the drawer shows a notice instead of a list and the
chat keeps working entirely out of st.session_state — a field worker offline in
the district must still be able to ask questions.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import streamlit as st

from utils.i18n import t
from utils.user import current_user_id

# UUID of the chat_sessions row backing the on-screen conversation, or None
# when nothing has been persisted yet (a fresh chat, or Supabase unreachable).
CHAT_SESSION_KEY = "chat_session_id"

# Set once any Supabase call fails, so the drawer stops retrying on every
# rerun and the chat quietly continues as a local-only conversation.
_UNAVAILABLE_KEY = "_chat_history_unavailable"

# Success/error notice to show after the st.rerun() that follows an action.
_FLASH_KEY = "_chat_history_flash"

# Session being renamed inline, set by a row's rename button.
_RENAME_TARGET_KEY = "_chat_history_rename_target"

# Sessions offered in the drawer. Deliberately short — this is a quick way back
# to yesterday's question, not an archive browser.
_SESSION_LIMIT = 15

# Longest auto-generated session title, derived from the first question.
_TITLE_CHARS = 60


# ── Availability ─────────────────────────────────────────────────────────────
def history_available() -> bool:
    """False once a Supabase call has failed in this browser session."""
    return not st.session_state.get(_UNAVAILABLE_KEY, False)


def _mark_unavailable(operation: str, exc: Exception) -> None:
    """Records that persistence is down and logs why, exactly once."""
    if history_available():
        print(f"[chat_history] {operation} failed, falling back to local-only chat: {exc}")
    st.session_state[_UNAVAILABLE_KEY] = True


def active_session_id() -> str | None:
    """UUID of the persisted session backing this conversation, if any."""
    return st.session_state.get(CHAT_SESSION_KEY)


# ── Persistence ──────────────────────────────────────────────────────────────
def _session_title(question: str) -> str:
    """Condenses the first question of a chat into a sidebar-sized title."""
    title = " ".join(str(question or "").split())
    if len(title) > _TITLE_CHARS:
        title = title[:_TITLE_CHARS].rsplit(" ", 1)[0] + "…"
    return title or t("history.untitled", language="en")


def _ensure_session(first_question: str) -> str | None:
    """
    Returns the active session UUID, creating the chat_sessions row on first
    use. Returns None when persistence is unavailable.
    """
    existing = active_session_id()
    if existing:
        return existing

    if not history_available():
        return None

    try:
        from database.conversation import create_chat_session

        session = create_chat_session(
            user_id=current_user_id(),
            title=_session_title(first_question),
        )
        st.session_state[CHAT_SESSION_KEY] = session["id"]
        return session["id"]
    except Exception as exc:
        _mark_unavailable("create_chat_session", exc)
        return None


def _persist(role: str, content: str, citations: List[Dict[str, Any]] | None) -> str | None:
    """Inserts one message, returning its UUID, or None if it wasn't stored."""
    session_id = active_session_id()
    if not session_id or not history_available() or not str(content or "").strip():
        return None

    try:
        from database.conversation import add_chat_message

        record = add_chat_message(
            session_id=session_id,
            role=role,
            content=content,
            citations=citations or None,
        )
        return record.get("id")
    except Exception as exc:
        _mark_unavailable(f"add_chat_message({role})", exc)
        return None


def persist_user_message(question: str) -> str | None:
    """
    Stores the field worker's question, creating the session if this is the
    first turn. Returns the message UUID, or None when running local-only.
    """
    _ensure_session(question)
    return _persist("user", question, None)


def persist_assistant_message(
    answer: str,
    sources: List[Dict[str, Any]] | None = None,
) -> str | None:
    """
    Stores an answer with its citations and returns the message UUID.

    The UUID is what components/feedback.py votes against, so an answer that
    could not be stored simply gets un-attributed feedback rather than none.
    """
    return _persist("assistant", answer, sources)


# ── Loading a stored conversation ────────────────────────────────────────────
def _citations(raw: Any) -> List[Dict[str, Any]]:
    """Normalizes a stored citations column, which may arrive as JSON text."""
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def _to_chat_messages(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Converts stored chat_messages rows into the message dicts chat.py renders.

    Each answer is paired back with the question above it, which the citation
    highlighter and the summary export both need. Conflict banners are not
    restored: add_chat_message() stores content and citations only, so a
    reloaded answer shows its sources without re-asserting a discrepancy the
    row cannot actually vouch for.
    """
    messages: List[Dict[str, Any]] = []
    last_question: str | None = None

    for row in rows:
        role = str(row.get("role") or "").lower()
        content = row.get("content") or ""

        if role == "user":
            last_question = content
            messages.append({"role": "user", "content": content, "sources": []})
        elif role == "assistant":
            messages.append({
                "role": "assistant",
                "content": content,
                "sources": _citations(row.get("citations")),
                "query": last_question,
                "message_id": row.get("id"),
                "generated_at": row.get("created_at"),
                "conflicts_detected": False,
                "conflict_warning": None,
                "filters_summary": None,
            })

    return messages


def _load_session(session_id: str) -> bool:
    """Replaces the on-screen conversation with a stored one. True on success."""
    try:
        from database.conversation import get_session_messages

        rows = get_session_messages(session_id)
    except Exception as exc:
        _mark_unavailable("get_session_messages", exc)
        return False

    st.session_state["messages"] = _to_chat_messages(rows)
    st.session_state[CHAT_SESSION_KEY] = session_id
    return True


def start_new_chat() -> None:
    """
    Clears the conversation so the next question opens a fresh session.

    The welcome greeting is not re-added here — chat.py re-seeds it whenever it
    finds the history empty, which keeps that decision in one place.
    """
    st.session_state["messages"] = []
    st.session_state.pop(CHAT_SESSION_KEY, None)
    st.session_state.pop(_RENAME_TARGET_KEY, None)


# ── Drawer rendering ─────────────────────────────────────────────────────────
def _list_sessions() -> List[Dict[str, Any]]:
    """Recent sessions for this user, newest first, or [] if unavailable."""
    if not history_available():
        return []

    try:
        from database.conversation import list_user_sessions

        return list_user_sessions(current_user_id(), limit=_SESSION_LIMIT)
    except Exception as exc:
        _mark_unavailable("list_user_sessions", exc)
        return []


def _relative_time(raw: Any) -> str:
    """Renders a stored timestamp as 'just now' / '3h ago' / a plain date."""
    text = str(raw or "").strip()
    if not text:
        return ""

    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text[:10]

    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)

    minutes = int((datetime.now(timezone.utc) - stamp).total_seconds() // 60)
    if minutes < 1:
        return t("history.just_now")
    if minutes < 60:
        return t("history.minutes_ago", count=minutes)
    if minutes < 60 * 24:
        return t("history.hours_ago", count=minutes // 60)
    if minutes < 60 * 24 * 7:
        return t("history.days_ago", count=minutes // (60 * 24))
    return stamp.strftime("%Y-%m-%d")


def _flash() -> None:
    """Shows and clears the notice left behind by the last drawer action."""
    notice = st.session_state.pop(_FLASH_KEY, None)
    if not notice:
        return
    level, text = notice
    (st.success if level == "success" else st.error)(text)


def _delete_session(session_id: str, title: str) -> None:
    """Deletes a stored session, resetting the chat if it was the open one."""
    try:
        from database.conversation import delete_chat_session

        deleted = delete_chat_session(session_id)
    except Exception as exc:
        _mark_unavailable("delete_chat_session", exc)
        st.session_state[_FLASH_KEY] = ("error", t("history.delete_failed", title=title))
        return

    if not deleted:
        st.session_state[_FLASH_KEY] = ("error", t("history.delete_missing"))
        return

    if active_session_id() == session_id:
        start_new_chat()
    st.session_state[_FLASH_KEY] = ("success", t("history.deleted", title=title))


def _rename_session(session_id: str, title: str) -> None:
    """Applies an inline rename from the drawer."""
    try:
        from database.conversation import update_session_title

        update_session_title(session_id, title)
    except Exception as exc:
        _mark_unavailable("update_session_title", exc)
        st.session_state[_FLASH_KEY] = ("error", t("history.rename_failed", title=title))
        return

    st.session_state.pop(_RENAME_TARGET_KEY, None)
    st.session_state[_FLASH_KEY] = ("success", t("history.renamed", title=title))


def _render_rename_form(session_id: str, current_title: str) -> None:
    """Inline title editor, shown in place of the row being renamed."""
    new_title = st.text_input(
        t("history.rename_label"),
        value=current_title,
        key=f"csa_history_rename_input_{session_id}",
        label_visibility="collapsed",
    )
    save_col, cancel_col = st.columns(2)
    with save_col:
        if st.button(t("history.rename_save"), key=f"csa_history_rename_save_{session_id}",
                     use_container_width=True):
            if new_title.strip():
                _rename_session(session_id, new_title.strip())
                st.rerun()
    with cancel_col:
        if st.button(t("history.rename_cancel"), key=f"csa_history_rename_cancel_{session_id}",
                     use_container_width=True):
            st.session_state.pop(_RENAME_TARGET_KEY, None)
            st.rerun()


def _render_session_row(session: Dict[str, Any], is_active: bool) -> None:
    """One conversation in the drawer: switch, rename, delete."""
    session_id = session.get("id")
    title = session.get("title") or t("history.untitled")

    if st.session_state.get(_RENAME_TARGET_KEY) == session_id:
        _render_rename_form(session_id, title)
        return

    open_col, rename_col, delete_col = st.columns([5, 1, 1])

    with open_col:
        # The active conversation is already on screen, so its row becomes a
        # marker rather than a button that would reload what is already there.
        label = f"{'🟢' if is_active else '💬'} {title}"
        if st.button(
            label,
            key=f"csa_history_open_{session_id}",
            use_container_width=True,
            disabled=is_active,
            help=t("history.open_help", when=_relative_time(session.get("updated_at"))),
        ):
            if _load_session(session_id):
                st.rerun()

    with rename_col:
        if st.button("✏️", key=f"csa_history_rename_{session_id}",
                     help=t("history.rename_help"), use_container_width=True):
            st.session_state[_RENAME_TARGET_KEY] = session_id
            st.rerun()

    with delete_col:
        if st.button("🗑️", key=f"csa_history_delete_{session_id}",
                     help=t("history.delete_help"), use_container_width=True):
            _delete_session(session_id, title)
            st.rerun()

    st.caption(_relative_time(session.get("updated_at")))


def render_chat_history_drawer() -> None:
    """
    Renders the chat history drawer in the Streamlit sidebar.

    Call this from app.py before the tabs render, so a session switch is
    already reflected in st.session_state.messages by the time the Chat tab
    draws the conversation.
    """
    with st.sidebar:
        st.subheader(t("history.heading"))

        if st.button(t("history.new_chat"), key="csa_history_new_chat",
                     use_container_width=True, type="primary",
                     help=t("history.new_chat_help")):
            start_new_chat()
            st.rerun()

        _flash()

        if not history_available():
            st.caption(t("history.unavailable"))
            return

        sessions = _list_sessions()
        if not history_available():  # the listing itself just failed
            st.caption(t("history.unavailable"))
            return

        if not sessions:
            st.caption(t("history.empty"))
            return

        with st.expander(t("history.recent", count=len(sessions)), expanded=True):
            current = active_session_id()
            for session in sessions:
                _render_session_row(session, is_active=session.get("id") == current)
