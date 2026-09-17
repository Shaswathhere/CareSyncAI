"""
components/chat.py
-------------------
Q&A chat layout: sample question prompt chips for a cold start, a voice
recorder for spoken questions, message history display, conflict alert banners
for contradicting guidance, styled citation cards with status and reranker
relevance badges plus expandable, query-highlighted passage snippet previews,
per-answer copy / PDF / TXT summary export actions, and thumbs-up/down answer
ratings.

Each completed turn is handed to components.chat_history for persistence, so
the sidebar drawer can reopen the conversation later and so a feedback vote
has a message UUID to attach itself to. Persistence is best-effort — when
Supabase is unreachable the chat runs entirely out of st.session_state.

All chrome is localized through utils.i18n.t(). Two things deliberately stay
English: the question a prompt chip sends to the retriever (the corpus is
English, so a translated chip would retrieve poorly), and the downloadable
summary export.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Dict, List

import streamlit as st

from components.audio_input import render_voice_recorder
from components.chat_history import persist_assistant_message, persist_user_message
from components.feedback import render_feedback_buttons
from utils.i18n import current_language, t
from utils.export import (
    build_summary_pdf,
    build_summary_text,
    pdf_export_available,
    summary_filename,
)
from utils.ui_helpers import (
    STATUS_ANY,
    conflict_banner_html,
    confidence_badge_html,
    confidence_label,
    extract_query_terms,
    highlight_snippet_html,
    normalize_status,
    rerank_confidence,
    snippet_text,
    status_badge_html,
    status_hint,
)

# Session key written by the sidebar search filters (components/document_list.py).
FILTER_STATE_KEY = "search_filters"

# query_rag_pipeline() prepends this block to the answer when it detects
# conflicting guidance. The UI shows it as a banner instead, so it is stripped
# from the answer body to avoid saying the same thing twice.
_INLINE_CONFLICT_PREFIX = re.compile(
    r"^⚠️\s*\*\*Guideline Discrepancy Alert:\*\*.*?\n\n",
    re.DOTALL,
)

# The welcome message carries a catalog key rather than fixed text, so the
# greeting already sitting in the chat history re-renders when the language
# changes instead of freezing in whichever language created it.
WELCOME_MESSAGE: Dict[str, Any] = {
    "role": "assistant",
    "content": "",
    "i18n_key": "chat.welcome",
    "sources": [],
}

# One-click starter questions shown until the field worker asks something of
# their own. They double as a hint at what the indexed corpus can answer.
#
# The chip label is localized; the question actually sent to the retriever is
# always the English one, because the indexed guidance is English and a
# translated query would retrieve badly.
SAMPLE_PROMPT_KEYS: tuple[str, ...] = (
    "chat.prompt.1",
    "chat.prompt.2",
    "chat.prompt.3",
    "chat.prompt.4",
)


def _active_filters() -> Dict[str, Any]:
    """Returns the sidebar search filters, or an empty dict before they render."""
    return st.session_state.get(FILTER_STATE_KEY) or {}


def _retrieval_kwargs(filters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translates the sidebar filters into query_rag_pipeline() arguments.

    Retrieval accepts exactly one lifecycle status, so the "All statuses"
    sidebar option falls back to ACTIVE — field workers must never be answered
    from withdrawn guidance by accident.
    """
    status = filters.get("status") or "ACTIVE"
    if status == STATUS_ANY:
        status = "ACTIVE"

    return {
        "status_filter": normalize_status(status),
        "keyword": filters.get("keyword") or None,
        "date_from": filters.get("date_from"),
        "date_to": filters.get("date_to"),
    }


def _filter_summary_text(filters: Dict[str, Any], language: str | None = None) -> str:
    """
    Describes which sidebar filters are narrowing retrieval, in one line.

    Shared by the on-screen caption and the exported guidance summary. The
    export passes language="en" so a downloaded record stays English even
    when the interface does not.
    """
    parts: List[str] = []

    status = filters.get("status") or "ACTIVE"
    if status == STATUS_ANY:
        parts.append(t("chat.filter_status_any", language=language))
    else:
        parts.append(t("chat.filter_status", language=language,
                       status=t(f"status.{status}", language=language)))

    if filters.get("date_from") and filters.get("date_to"):
        parts.append(t("chat.filter_dates", language=language,
                       date_from=filters["date_from"], date_to=filters["date_to"]))
    if filters.get("keyword"):
        parts.append(t("chat.filter_keyword", language=language, keyword=filters["keyword"]))

    return " · ".join(parts)


def _render_filter_summary(filters: Dict[str, Any]) -> None:
    """Shows which sidebar filters are narrowing the retrieval, if any."""
    st.caption(t("chat.searching", filters=_filter_summary_text(filters)))


def _conflict_level(sources: List[Dict[str, Any]] | None) -> str:
    """
    Escalates the banner from yellow to red when the conflicting passages come
    from documents that are no longer current — a stale-vs-current contradiction
    is the more dangerous case for a field worker.
    """
    statuses = {normalize_status(src.get("status")) for src in (sources or [])}
    return "danger" if statuses - {"ACTIVE"} else "warning"


def _render_conflict_banner(message: Dict[str, Any]) -> None:
    """Renders the yellow/red contradiction banner above an assistant answer."""
    if not message.get("conflicts_detected"):
        return

    warning = message.get("conflict_warning") or t("conflict.fallback")
    st.markdown(
        conflict_banner_html(warning, level=_conflict_level(message.get("sources"))),
        unsafe_allow_html=True,
    )


def _popover(label: str):
    """
    Returns a popover for inline detail panels, falling back to an expander on
    Streamlit builds without st.popover.
    """
    popover = getattr(st, "popover", None)
    if callable(popover):
        return popover(label)
    return st.expander(label)


def _render_citation_card(src: Dict[str, Any], terms: List[str], rank: int) -> None:
    """
    Renders one citation: metadata card, status badge, reranker relevance
    badge, and passage preview.

    Args:
        src:   One entry from the pipeline's "sources" list.
        terms: Query terms to highlight inside the passage preview.
        rank:  1-based position in the reranked list. Sources arrive already
               ordered by cross-encoder score, so this is the rank the
               reranker assigned — worth showing beside the score, because
               "3rd of 5" is the part a field worker can act on.
    """
    title = src.get("title", "Untitled Document")
    page_number = src.get("page_number", "—")
    status = normalize_status(src.get("status"))
    is_stale = status != "ACTIVE"

    card_class = "csa-citation-card csa-citation-card--stale" if is_stale else "csa-citation-card"
    stale_note = (
        f'<div class="csa-citation-warning">⚠️ {status_hint(status)}</div>' if is_stale else ""
    )

    # None whenever the cross-encoder was unavailable and retrieval fell back
    # to vector-similarity ordering; the badge is then simply left off rather
    # than showing a confidence nobody measured.
    confidence = rerank_confidence(src.get("rerank_score"))

    st.markdown(
        f"""
        <div class="csa-card {card_class}">
            <div class="csa-citation-head">
                <strong>{title}</strong>
                <span class="csa-citation-tags">
                    {status_badge_html(status)}{confidence_badge_html(confidence)}
                </span>
            </div>
            <span class="csa-muted">{t("chat.citation_meta",
                                       page=page_number,
                                       version=src.get("version", "—"),
                                       effective=src.get("effective_date", "—"))}</span>
            {stale_note}
        </div>
        """,
        unsafe_allow_html=True,
    )

    passage = snippet_text(src)
    with _popover(t("chat.passage_preview", title=title, page=page_number)):
        if confidence:
            st.caption(
                t(
                    "confidence.detail",
                    rank=rank,
                    label=confidence_label(confidence["band"]),
                    percent=confidence["percent"],
                )
            )
        st.markdown(
            f'<div class="csa-snippet">{highlight_snippet_html(passage, terms)}</div>',
            unsafe_allow_html=True,
        )
        if passage and terms:
            st.caption(t("chat.highlight_note"))


def _render_citations(sources: List[Dict[str, Any]] | None, query: str | None = None) -> None:
    """Renders the source cards beneath an assistant message."""
    if not sources:
        return

    terms = extract_query_terms(query)
    stale_count = sum(1 for src in sources if normalize_status(src.get("status")) != "ACTIVE")

    st.markdown('<div class="csa-citation-box">', unsafe_allow_html=True)
    caption = t("chat.sources", count=len(sources))
    if stale_count:
        caption += t("chat.sources_stale", count=stale_count)
    # Said once above the cards rather than on each of them: the percentage on
    # a badge is meaningless until you know what scored it.
    if any(rerank_confidence(src.get("rerank_score")) for src in sources):
        caption += t("chat.sources_scored")
    st.caption(caption)

    for rank, src in enumerate(sources, start=1):
        _render_citation_card(src, terms, rank)

    st.markdown("</div>", unsafe_allow_html=True)


# ── Copy & export actions ────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _summary_pdf_bytes(summary: str) -> bytes | None:
    """
    Renders a summary to PDF, cached on the summary text so scrolling the chat
    doesn't re-render the same file on every Streamlit rerun.

    Returns None when PyMuPDF is unavailable or rendering fails, so the caller
    can degrade to the TXT export instead of breaking the whole chat.
    """
    if not pdf_export_available():
        return None
    try:
        return build_summary_pdf(summary)
    except Exception as exc:  # PDF export must never take the chat down.
        print(f"[chat] PDF export failed: {exc}")
        return None


def _message_summary(message: Dict[str, Any]) -> str:
    """
    Builds the exportable guidance summary for one answered question.

    Always English: the summary mirrors English source guidance, and PyMuPDF's
    base-14 PDF fonts cannot render Devanagari or Tamil script.
    """
    return build_summary_text(
        question=message.get("query"),
        answer=message.get("content", ""),
        sources=message.get("sources"),
        conflict_warning=(
            message.get("conflict_warning") if message.get("conflicts_detected") else None
        ),
        filters_summary=message.get("filters_summary"),
        generated_at=message.get("generated_at"),
    )


def _render_message_actions(message: Dict[str, Any], key_suffix: str) -> None:
    """
    Renders the action row under an assistant answer: copy-to-clipboard, plus
    one-click PDF and TXT exports of the answer with its citations.

    Only answers to a real question get actions — the welcome message has
    nothing to cite or export.
    """
    if message.get("role") != "assistant" or not message.get("query"):
        return

    summary = _message_summary(message)
    question = message.get("query")

    copy_col, pdf_col, txt_col, _spacer = st.columns([1.3, 1.2, 1.2, 3.3])

    with copy_col:
        with _popover(t("chat.copy")):
            st.caption(t("chat.copy_hint"))
            st.code(_message_text(message), language=None)

    pdf_bytes = _summary_pdf_bytes(summary)
    with pdf_col:
        if pdf_bytes:
            st.download_button(
                t("chat.export_pdf"),
                data=pdf_bytes,
                file_name=summary_filename(question, "pdf"),
                mime="application/pdf",
                key=f"csa_export_pdf_{key_suffix}",
                help=t("chat.export_pdf_help"),
                use_container_width=True,
            )
        else:
            st.button(
                t("chat.export_pdf"),
                key=f"csa_export_pdf_{key_suffix}",
                disabled=True,
                help=t("chat.export_pdf_unavailable"),
                use_container_width=True,
            )

    with txt_col:
        st.download_button(
            t("chat.export_txt"),
            data=summary.encode("utf-8"),
            file_name=summary_filename(question, "txt"),
            mime="text/plain",
            key=f"csa_export_txt_{key_suffix}",
            help=t("chat.export_txt_help"),
            use_container_width=True,
        )

    # The exports are English while the interface is not — say so once, rather
    # than letting the field worker discover it after downloading.
    if current_language() != "en":
        st.caption(t("chat.export_note"))


# ── Prompt chips ─────────────────────────────────────────────────────────────
def _render_prompt_chips() -> str | None:
    """
    Renders the sample question chips and returns the question that was
    clicked, or None. Shown only until the field worker asks something.

    The chip is labelled in the active language but returns the English
    question, which is what the English guidance corpus can actually match.
    """
    st.caption(t("chat.chips_intro"))

    clicked: str | None = None
    for row_start in range(0, len(SAMPLE_PROMPT_KEYS), 2):
        row = SAMPLE_PROMPT_KEYS[row_start:row_start + 2]
        columns = st.columns(len(row))
        for offset, prompt_key in enumerate(row):
            with columns[offset]:
                if st.button(
                    t(prompt_key),
                    key=f"csa_chip_{row_start + offset}",
                    use_container_width=True,
                ):
                    clicked = t(prompt_key, language="en")
    return clicked


def _message_text(message: Dict[str, Any]) -> str:
    """
    The body of a message: a catalog lookup for UI-authored messages such as
    the welcome greeting, and stored content for anything the pipeline or the
    field worker produced.
    """
    key = message.get("i18n_key")
    return t(key) if key else message.get("content", "")


def _render_message(message: Dict[str, Any], key_suffix: str) -> None:
    """Renders one stored chat message with its banner, citations, and actions."""
    with st.chat_message(message["role"]):
        _render_conflict_banner(message)
        st.markdown(_message_text(message))
        _render_citations(message.get("sources"), message.get("query"))
        _render_message_actions(message, key_suffix)
        render_feedback_buttons(message, key_suffix)


def _answer_question(question: str, filters: Dict[str, Any]) -> None:
    """
    Runs one question through the RAG pipeline, renders the answer inline, and
    appends both turns to the chat history.
    """
    st.session_state.messages.append({"role": "user", "content": question, "sources": []})
    with st.chat_message("user"):
        st.markdown(question)

    # Opens the chat_sessions row on the first question of a conversation, so
    # the sidebar drawer only ever lists chats that actually contain something.
    persist_user_message(question)

    with st.chat_message("assistant"):
        st.session_state.is_loading = True
        try:
            with st.spinner(t("chat.spinner")):
                from rag.pipeline import query_rag_pipeline

                result = query_rag_pipeline(question, **_retrieval_kwargs(filters))
        except Exception as exc:
            st.error(f"⚠️ Service temporary disruption: {exc}")
            result = {
                "answer": (
                    "⚠️ **Unable to retrieve public health guidance at this moment.**\n\n"
                    "Please verify your network connection and credentials, or rephrase your question. "
                    f"(System note: `{exc}`)"
                ),
                "sources": [],
                "conflicts_detected": False,
                "conflict_warning": None,
            }
        finally:
            st.session_state.is_loading = False

        answer = _INLINE_CONFLICT_PREFIX.sub("", result["answer"], count=1)
        assistant_message = {
            "role": "assistant",
            "content": answer,
            "sources": result.get("sources", []),
            "query": question,
            "conflicts_detected": bool(result.get("conflicts_detected")),
            "conflict_warning": result.get("conflict_warning"),
            # Captured once so the export summary — and therefore its cache key
            # and file name — stay stable across reruns. English, to match the
            # rest of the export.
            "filters_summary": _filter_summary_text(filters, language="en"),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            # Identity for the rating buttons while the answer is unsaved, so a
            # vote cast on this render is still recognised after the rerun that
            # redraws the same answer from history.
            "local_id": uuid.uuid4().hex[:12],
        }

        # The stored UUID is what a feedback vote attaches itself to; None when
        # Supabase is unreachable, which downgrades the vote rather than the chat.
        assistant_message["message_id"] = persist_assistant_message(
            answer, assistant_message["sources"]
        )

        _render_conflict_banner(assistant_message)
        st.markdown(answer)
        _render_citations(assistant_message["sources"], question)

        st.session_state.messages.append(assistant_message)
        _render_message_actions(assistant_message, key_suffix="live")
        render_feedback_buttons(assistant_message, key_suffix="live")


def render_chat_component() -> None:
    """Renders the natural language Chat Assistant interface."""
    st.subheader(t("chat.heading"))

    filters = _active_filters()
    if filters:
        _render_filter_summary(filters)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if not st.session_state.messages:
        st.session_state.messages.append(dict(WELCOME_MESSAGE))

    for index, message in enumerate(st.session_state.messages):
        _render_message(message, key_suffix=str(index))

    # Chips live in their own slot so they can be cleared the moment a question
    # is in flight, instead of hanging above the answer being generated.
    chips_slot = st.empty()
    chip_question: str | None = None
    if not any(msg.get("role") == "user" for msg in st.session_state.messages):
        with chips_slot.container():
            chip_question = _render_prompt_chips()

    # Voice input sits directly above the text box: same job, different hands.
    # It returns a question only once the transcript has been confirmed.
    voice_slot = st.empty()
    with voice_slot.container():
        voice_question = render_voice_recorder()

    typed_question = st.chat_input(t("chat.input_placeholder"))

    question = typed_question or voice_question or chip_question
    if question:
        chips_slot.empty()
        voice_slot.empty()
        _answer_question(question, filters)
