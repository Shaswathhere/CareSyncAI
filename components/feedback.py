"""
components/feedback.py
-----------------------
👍 / 👎 rating buttons under every assistant answer, wired to the
chat_feedback table through database.feedback.submit_feedback().

A downvote opens an optional "what was wrong?" box, because a bare thumbs-down
tells the guidance team that an answer failed but not how — and for public
health guidance the how is the whole point.

Votes are attributed to:
    user_id     — utils.user.current_user_id()
    message_id  — the chat_messages UUID, when the answer was persisted
    session_id  — the chat_sessions UUID, likewise

Neither UUID is required by submit_feedback(), so an answer produced while
Supabase was unreachable still records a vote if the connection comes back;
it is simply attributed to the user rather than to a specific message.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from components.chat_history import active_session_id
from utils.i18n import t
from utils.user import current_user_id

# Votes cast in this browser session: {answer_key: {"vote", "stored", "comment"}}.
# Keeps the buttons in their chosen state across reruns, and stops a field
# worker double-logging by clicking twice.
FEEDBACK_STATE_KEY = "answer_feedback"

# Answer keys with the downvote comment box currently open.
_COMMENT_OPEN_KEY = "_feedback_comment_open"

UPVOTE = "upvote"
DOWNVOTE = "downvote"

# Longest comment accepted, matching what the chat_feedback.comment column and
# a field worker on a phone keyboard can reasonably carry.
_COMMENT_CHARS = 500


def _votes() -> Dict[str, Dict[str, Any]]:
    """The vote ledger for this browser session, created on first use."""
    if FEEDBACK_STATE_KEY not in st.session_state:
        st.session_state[FEEDBACK_STATE_KEY] = {}
    return st.session_state[FEEDBACK_STATE_KEY]


def _answer_key(message: Dict[str, Any], key_suffix: str) -> str:
    """
    Stable identity for the answer being rated.

    The persisted message UUID when there is one, so a vote survives the
    conversation being reloaded from the drawer; then the local id chat.py
    stamps on every answer, so a vote cast on the live render is still
    recognised after the rerun redraws it from history; and finally the render
    position, for anything that has neither.
    """
    return str(
        message.get("message_id")
        or message.get("local_id")
        or f"local-{key_suffix}"
    )


def _submit(vote: str, message: Dict[str, Any], comment: str | None = None) -> bool:
    """
    Sends one vote to Supabase. Returns True when it was stored.

    A failure is never surfaced as an exception: the vote stays recorded
    locally and the caller shows a "saved on this device only" note, because
    losing a rating must not cost the field worker their answer.
    """
    try:
        from database.feedback import submit_feedback

        submit_feedback(
            user_id=current_user_id(),
            vote=vote,
            message_id=message.get("message_id"),
            session_id=active_session_id(),
            comment=comment,
        )
        return True
    except Exception as exc:
        print(f"[feedback] submit_feedback({vote}) failed: {exc}")
        return False


def _record(answer_key: str, vote: str, stored: bool, comment: str | None = None) -> None:
    """Writes the outcome of a vote into the session ledger."""
    _votes()[answer_key] = {"vote": vote, "stored": stored, "comment": comment}


def _cast(answer_key: str, vote: str, message: Dict[str, Any]) -> None:
    """Handles a 👍/👎 click: submit, remember, and open the comment box."""
    stored = _submit(vote, message)
    _record(answer_key, vote, stored)

    # Only a downvote asks why — an upvote that interrupts to ask for an
    # explanation is a good way to stop getting upvotes.
    open_comments = set(st.session_state.get(_COMMENT_OPEN_KEY) or set())
    if vote == DOWNVOTE:
        open_comments.add(answer_key)
    else:
        open_comments.discard(answer_key)
    st.session_state[_COMMENT_OPEN_KEY] = open_comments


def _render_comment_box(answer_key: str, message: Dict[str, Any]) -> None:
    """Optional free-text detail after a downvote."""
    comment = st.text_area(
        t("feedback.comment_label"),
        key=f"csa_feedback_comment_{answer_key}",
        placeholder=t("feedback.comment_placeholder"),
        max_chars=_COMMENT_CHARS,
        height=80,
    )

    send_col, skip_col, _spacer = st.columns([1.4, 1.2, 3.4])

    with send_col:
        if st.button(t("feedback.comment_send"), key=f"csa_feedback_send_{answer_key}",
                     use_container_width=True, disabled=not comment.strip()):
            # A second row carrying the comment, rather than an update: the
            # feedback table is append-only, and both rows share the message_id.
            stored = _submit(DOWNVOTE, message, comment=comment.strip())
            _record(answer_key, DOWNVOTE, stored, comment=comment.strip())
            st.session_state[_COMMENT_OPEN_KEY] = {
                key for key in (st.session_state.get(_COMMENT_OPEN_KEY) or set())
                if key != answer_key
            }
            st.rerun()

    with skip_col:
        if st.button(t("feedback.comment_skip"), key=f"csa_feedback_skip_{answer_key}",
                     use_container_width=True):
            st.session_state[_COMMENT_OPEN_KEY] = {
                key for key in (st.session_state.get(_COMMENT_OPEN_KEY) or set())
                if key != answer_key
            }
            st.rerun()


def _render_receipt(record: Dict[str, Any]) -> None:
    """The one-line acknowledgement shown once a vote has been cast."""
    if record["vote"] == UPVOTE:
        st.caption(t("feedback.thanks_up"))
    elif record.get("comment"):
        st.caption(t("feedback.thanks_down_comment"))
    else:
        st.caption(t("feedback.thanks_down"))

    if not record["stored"]:
        st.caption(t("feedback.not_saved"))


def render_feedback_buttons(message: Dict[str, Any], key_suffix: str) -> None:
    """
    Renders the 👍 / 👎 row under one assistant answer.

    Only answers to a real question are rateable — the welcome greeting is not
    a retrieval result and rating it would pollute the quality metrics.

    Args:
        message:    The assistant message dict rendered by components/chat.py.
        key_suffix: Unique-per-render suffix for the Streamlit widget keys.
    """
    if message.get("role") != "assistant" or not message.get("query"):
        return

    answer_key = _answer_key(message, key_suffix)
    record = _votes().get(answer_key)
    current_vote = record["vote"] if record else None

    up_col, down_col, note_col = st.columns([1, 1, 5.6])

    with up_col:
        if st.button(
            "👍" if current_vote != UPVOTE else "👍 ✓",
            key=f"csa_feedback_up_{answer_key}",
            help=t("feedback.up_help"),
            use_container_width=True,
        ):
            _cast(answer_key, UPVOTE, message)
            st.rerun()

    with down_col:
        if st.button(
            "👎" if current_vote != DOWNVOTE else "👎 ✓",
            key=f"csa_feedback_down_{answer_key}",
            help=t("feedback.down_help"),
            use_container_width=True,
        ):
            _cast(answer_key, DOWNVOTE, message)
            st.rerun()

    with note_col:
        if record:
            _render_receipt(record)
        else:
            st.caption(t("feedback.prompt"))

    if answer_key in (st.session_state.get(_COMMENT_OPEN_KEY) or set()):
        _render_comment_box(answer_key, message)
