"""
components/document_list.py
----------------------------
Document inventory and version-status admin panel.

Renders:
    - The sidebar search filters (title, lifecycle status, effective-date range,
      keyword boost) shared by the Documents tab and the Chat Assistant.
    - One card per document with a colored status badge, admin controls to
      manually move it between ACTIVE / SUPERSEDED / ARCHIVED, and an
      expandable version timeline tree.
    - A delete confirmation modal that distinguishes a recoverable archive
      from a permanent removal of the document and its indexed passages.

Inventory is sourced live from Supabase via database.documents, with a
session/mock fallback so the UI still renders without database credentials.
"""

from __future__ import annotations

import html
from datetime import date, timedelta
from typing import Any, Dict, List, Tuple

import streamlit as st

from database.chunks import delete_chunks_by_document_id
from database.documents import (
    delete_document,
    fetch_all_documents,
    fetch_document_version_history,
    update_document_status,
)
from utils.i18n import t
from utils.ui_helpers import (
    STATUS_ANY,
    STATUS_OPTIONS,
    base_document_title,
    normalize_status,
    status_badge_html,
    status_filter_label,
    version_timeline_html,
)

# Session key holding the sidebar filter selections. Read by components/chat.py
# to narrow retrieval the same way the Documents tab is narrowed.
FILTER_STATE_KEY = "search_filters"

# Widget keys owned by the sidebar filter form — cleared by "Reset filters".
_FILTER_WIDGET_KEYS = (
    "filter_title_query",
    "filter_status",
    "filter_use_dates",
    "filter_date_range",
    "filter_keyword",
)

# Holds the result of the last status change so it survives the st.rerun()
# triggered by the admin controls.
_FLASH_KEY = "_document_status_flash"

# Holds the document awaiting delete confirmation. Set by a row's Delete
# button, read by the confirmation modal, cleared on cancel or completion.
_DELETE_TARGET_KEY = "_document_delete_target"

# Widget keys owned by the delete modal — reset every time it is reopened so a
# previous "permanent" choice can never carry over to the next document.
_DELETE_WIDGET_KEYS = ("doc_delete_mode", "doc_delete_ack")

# Stable option values for the delete-mode radio. The labels shown to the user
# come from the catalog via format_func, so the comparison below never depends
# on the selected language.
_MODE_ARCHIVE = "archive"
_MODE_PERMANENT = "permanent"

# Fallback mock inventory used when Supabase isn't reachable/configured yet
# (e.g. local dev without a .env), or when the component is rendered
# standalone without app.py's init_session_state() having run first.
_MOCK_DOCUMENTS = [
    {"title": "Vaccination Protocol v3", "version": "v3", "effective_date": "2026-08-08", "status": "ACTIVE"},
    {"title": "Outbreak Guidelines v2", "version": "v2", "effective_date": "2026-08-05", "status": "ACTIVE"},
    {"title": "Vaccination Protocol v2", "version": "v2", "effective_date": "2026-07-20", "status": "SUPERSEDED"},
]


# ── Sidebar search filters ───────────────────────────────────────────────────
def _parse_date(value: Any) -> date | None:
    """Coerces a date object or ISO 'YYYY-MM-DD' string to a date, else None."""
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _read_date_range(raw: Any) -> Tuple[str | None, str | None]:
    """
    Normalizes st.date_input's return value into ISO strings.

    A range picker returns a 1-tuple while the user is mid-selection, so the
    single-date case is treated as "from == to".
    """
    if isinstance(raw, (list, tuple)):
        dates = [d for d in (_parse_date(item) for item in raw) if d]
    else:
        single = _parse_date(raw)
        dates = [single] if single else []

    if not dates:
        return None, None
    return dates[0].isoformat(), dates[-1].isoformat()


def render_sidebar_filters() -> Dict[str, Any]:
    """
    Renders the Advanced Search Filters panel in the Streamlit sidebar and
    stores the selections in st.session_state[FILTER_STATE_KEY].

    Returns:
        The active filter dict: title_query, status, date_from, date_to, keyword.
    """
    with st.sidebar:
        st.subheader(t("filters.heading"))

        title_query = st.text_input(
            t("filters.title_label"),
            key="filter_title_query",
            placeholder=t("filters.title_placeholder"),
            help=t("filters.title_help"),
        )

        # Values stay English (STATUS_ANY / STATUS_OPTIONS) because they are
        # compared against document data; only the labels are localized.
        status = st.selectbox(
            t("filters.status_label"),
            options=(STATUS_ANY, *STATUS_OPTIONS),
            key="filter_status",
            format_func=status_filter_label,
            help=t("filters.status_help"),
        )

        use_dates = st.checkbox(t("filters.use_dates"), key="filter_use_dates")
        date_from = date_to = None
        if use_dates:
            today = date.today()
            raw_range = st.date_input(
                t("filters.date_label"),
                value=(today - timedelta(days=365), today),
                key="filter_date_range",
                help=t("filters.date_help"),
            )
            date_from, date_to = _read_date_range(raw_range)
            if date_from and date_to and date_from > date_to:
                st.warning(t("filters.date_order_warning"))

        keyword = st.text_input(
            t("filters.keyword_label"),
            key="filter_keyword",
            placeholder=t("filters.keyword_placeholder"),
            help=t("filters.keyword_help"),
        )

        if st.button(t("filters.reset"), use_container_width=True):
            for widget_key in _FILTER_WIDGET_KEYS:
                st.session_state.pop(widget_key, None)
            st.session_state.pop(FILTER_STATE_KEY, None)
            st.rerun()

    filters: Dict[str, Any] = {
        "title_query": (title_query or "").strip(),
        "status": status,
        "date_from": date_from,
        "date_to": date_to,
        "keyword": (keyword or "").strip(),
    }
    st.session_state[FILTER_STATE_KEY] = filters
    return filters


# ── Inventory loading & filtering ────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _cached_fetch_all_documents() -> List[Dict[str, Any]]:
    return fetch_all_documents() or []


@st.cache_data(ttl=60, show_spinner=False)
def _cached_fetch_version_history(title: str) -> List[Dict[str, Any]]:
    return fetch_document_version_history(title) or []


def invalidate_document_cache() -> None:
    """Explicitly clears the cached document list and version histories."""
    try:
        _cached_fetch_all_documents.clear()
        _cached_fetch_version_history.clear()
    except Exception as exc:
        print(f"[document_list] invalidate_document_cache notice: {exc}")


def _load_documents() -> Tuple[List[Dict[str, Any]], bool]:
    """
    Loads the document inventory.

    Returns:
        (documents, db_backed) — db_backed is False when the list came from
        session/mock data, in which case status edits cannot be persisted.
    """
    try:
        documents = _cached_fetch_all_documents()
        if documents:
            return documents, True
    except Exception as exc:  # Supabase unreachable / not configured yet
        print(f"[document_list] fetch_all_documents failed: {exc}")

    return list(st.session_state.get("documents") or _MOCK_DOCUMENTS), False


def _matches_filters(doc: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    """Applies the sidebar filters to a single document row."""
    title_query = (filters.get("title_query") or "").lower()
    if title_query and title_query not in str(doc.get("title", "")).lower():
        return False

    status = filters.get("status") or STATUS_ANY
    if status != STATUS_ANY and normalize_status(doc.get("status")) != status:
        return False

    date_from = _parse_date(filters.get("date_from"))
    date_to = _parse_date(filters.get("date_to"))
    if date_from or date_to:
        effective = _parse_date(doc.get("effective_date"))
        if effective is None:
            return False
        if date_from and effective < date_from:
            return False
        if date_to and effective > date_to:
            return False

    return True


def _version_history(doc: Dict[str, Any], documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Builds the version history for a document: authoritative history from
    Supabase when available, otherwise every loaded document sharing the same
    base title (so "Vaccination Protocol v2/v3" still form one timeline).
    """
    title = str(doc.get("title") or "")

    try:
        history = _cached_fetch_version_history(title)
        if len(history) > 1:
            return history
    except Exception as exc:
        print(f"[document_list] fetch_document_version_history failed: {exc}")

    base = base_document_title(title).lower()
    siblings = [
        other for other in documents
        if base_document_title(other.get("title")).lower() == base
    ]
    return sorted(siblings, key=lambda d: str(d.get("effective_date") or ""))


# ── Admin status controls ────────────────────────────────────────────────────
def _apply_status_change(doc: Dict[str, Any], new_status: str, db_backed: bool) -> None:
    """
    Writes a manual status change back to Supabase (when the row has an id),
    mirrors it into the session inventory, then reruns so every row — and the
    version timeline — reflects the new status.

    The outcome is stashed in session_state because st.rerun() would otherwise
    wipe the message before it is seen.
    """
    title = str(doc.get("title") or "document")
    document_id = doc.get("id")

    if db_backed and document_id:
        try:
            updated = update_document_status(str(document_id), new_status)
        except Exception as exc:
            st.session_state[_FLASH_KEY] = ("error", t("docs.status_failed", title=title, error=exc))
            st.rerun()
            return
        if not updated:
            st.session_state[_FLASH_KEY] = ("error", t("docs.status_missing", id=document_id))
            st.rerun()
            return
        st.session_state[_FLASH_KEY] = (
            "success",
            t("docs.status_changed", title=title, status=t(f"status.{new_status}")),
        )
    else:
        st.session_state[_FLASH_KEY] = (
            "warning",
            t("docs.status_session_only", title=title, status=t(f"status.{new_status}")),
        )

    doc["status"] = new_status
    for entry in st.session_state.get("documents") or []:
        if entry.get("title") == doc.get("title") and entry.get("version") == doc.get("version"):
            entry["status"] = new_status

    invalidate_document_cache()
    st.rerun()


# ── Delete confirmation modal ────────────────────────────────────────────────
def _dialog_decorator(title: str):
    """
    Returns st.dialog (Streamlit ≥1.37) or st.experimental_dialog (1.35–1.36)
    bound to `title`, or None on builds with neither — in which case the
    confirmation renders inline instead of in a modal.
    """
    for attribute in ("dialog", "experimental_dialog"):
        factory = getattr(st, attribute, None)
        if callable(factory):
            return factory(title)
    return None


def _same_document(entry: Dict[str, Any], target: Dict[str, Any]) -> bool:
    """Matches an inventory row against the delete target, by id when present."""
    if target.get("id") and entry.get("id"):
        return str(entry["id"]) == str(target["id"])
    return (
        entry.get("title") == target.get("title")
        and entry.get("version") == target.get("version")
    )


def _request_delete(doc: Dict[str, Any], db_backed: bool) -> None:
    """Opens the confirmation modal for one document."""
    st.session_state[_DELETE_TARGET_KEY] = {
        "id": doc.get("id"),
        "title": str(doc.get("title") or "Untitled document"),
        "version": doc.get("version"),
        "effective_date": doc.get("effective_date"),
        "status": normalize_status(doc.get("status")),
        "db_backed": db_backed,
    }
    for widget_key in _DELETE_WIDGET_KEYS:
        st.session_state.pop(widget_key, None)
    st.rerun()


def _close_delete_modal() -> None:
    """Dismisses the modal and reruns so the inventory re-renders without it."""
    st.session_state.pop(_DELETE_TARGET_KEY, None)
    for widget_key in _DELETE_WIDGET_KEYS:
        st.session_state.pop(widget_key, None)
    st.rerun()


def _update_session_inventory(target: Dict[str, Any], permanent: bool) -> None:
    """Mirrors the deletion into st.session_state.documents."""
    inventory = st.session_state.get("documents") or []
    if permanent:
        st.session_state["documents"] = [
            entry for entry in inventory if not _same_document(entry, target)
        ]
        return

    for entry in inventory:
        if _same_document(entry, target):
            entry["status"] = "ARCHIVED"


def _perform_delete(target: Dict[str, Any], permanent: bool) -> None:
    """
    Carries out the confirmed deletion, records the outcome in the flash slot,
    and closes the modal.

    A permanent delete purges the document's chunk vectors first: an answer
    index must never outlive the guidance a reviewer just removed.
    """
    title = target.get("title") or "document"
    document_id = target.get("id")
    done_key = "delete.done_deleted" if permanent else "delete.done_archived"
    session_key = "delete.session_deleted" if permanent else "delete.session_archived"

    if target.get("db_backed") and document_id:
        try:
            if permanent:
                delete_chunks_by_document_id(str(document_id))
            removed = delete_document(str(document_id), hard_delete=permanent)
        except Exception as exc:
            st.session_state[_FLASH_KEY] = ("error", t("delete.failed", title=title, error=exc))
            _close_delete_modal()
            return

        if removed:
            st.session_state[_FLASH_KEY] = ("success", t(done_key, title=title))
        else:
            st.session_state[_FLASH_KEY] = ("error", t("delete.not_found", id=document_id))
    else:
        st.session_state[_FLASH_KEY] = ("warning", t(session_key, title=title))

    _update_session_inventory(target, permanent)
    invalidate_document_cache()
    _close_delete_modal()


def _render_delete_confirmation(target: Dict[str, Any]) -> None:
    """Renders the modal body: what is being removed, how, and the two actions."""
    st.markdown(
        f"""
        <div class="csa-card csa-delete-card">
            <div class="csa-doc-title">
                {html.escape(str(target.get('title')))}
                {status_badge_html(normalize_status(target.get('status')))}
            </div>
            <div class="csa-muted">
                {html.escape(t("docs.version_effective",
                               version=target.get("version") or "—",
                               effective=target.get("effective_date") or "—"))}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    mode = st.radio(
        t("delete.mode_question"),
        options=(_MODE_ARCHIVE, _MODE_PERMANENT),
        key="doc_delete_mode",
        format_func=lambda value: t(f"delete.mode.{value}"),
        captions=(
            t("delete.mode.archive_caption"),
            t("delete.mode.permanent_caption"),
        ),
    )
    permanent = mode == _MODE_PERMANENT

    if permanent:
        st.warning(t("delete.permanent_warning"))
        acknowledged = st.checkbox(t("delete.ack"), key="doc_delete_ack")
    else:
        acknowledged = True

    if not target.get("db_backed"):
        st.info(t("delete.session_notice"))

    cancel_col, confirm_col = st.columns(2)
    with cancel_col:
        if st.button(t("delete.cancel"), key="doc_delete_cancel", use_container_width=True):
            _close_delete_modal()
    with confirm_col:
        if st.button(
            t("delete.confirm_permanent") if permanent else t("delete.confirm_archive"),
            key="doc_delete_confirm",
            type="primary",
            disabled=not acknowledged,
            use_container_width=True,
        ):
            _perform_delete(target, permanent)


def _render_delete_modal() -> None:
    """Shows the confirmation modal when a row has requested a deletion."""
    target = st.session_state.get(_DELETE_TARGET_KEY)
    if not target:
        return

    decorator = _dialog_decorator(t("delete.modal_title"))
    if decorator is None:
        # Streamlit build without modal support — confirm inline instead.
        with st.container(border=True):
            st.subheader(t("delete.inline_title"))
            _render_delete_confirmation(target)
        return

    @decorator
    def _modal() -> None:
        _render_delete_confirmation(target)

    _modal()


def _render_document_row(
    doc: Dict[str, Any],
    row_key: str,
    documents: List[Dict[str, Any]],
    db_backed: bool,
) -> None:
    """Renders one inventory card: metadata, admin controls, version timeline."""
    title = doc.get("title", "—")
    version = doc.get("version", "—")
    current_status = normalize_status(doc.get("status"))

    with st.container(border=True):
        meta_col, action_col = st.columns([3, 2])

        with meta_col:
            st.markdown(
                f"""
                <div class="csa-doc-row">
                    <div class="csa-doc-title">{title} {status_badge_html(current_status)}</div>
                    <div class="csa-muted">
                        {html.escape(t("docs.version_effective",
                                       version=version,
                                       effective=doc.get("effective_date", "—")))}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with action_col:
            selected_status = st.selectbox(
                t("docs.set_status"),
                options=STATUS_OPTIONS,
                index=STATUS_OPTIONS.index(current_status),
                key=f"status_select_{row_key}",
                format_func=status_filter_label,
            )
            apply_col, delete_col = st.columns(2)
            with apply_col:
                if st.button(
                    t("docs.apply"),
                    key=f"status_apply_{row_key}",
                    help=t("docs.apply_help"),
                    use_container_width=True,
                    disabled=selected_status == current_status,
                ):
                    _apply_status_change(doc, selected_status, db_backed)
            with delete_col:
                if st.button(
                    t("docs.delete"),
                    key=f"doc_delete_{row_key}",
                    help=t("docs.delete_help"),
                    use_container_width=True,
                ):
                    _request_delete(doc, db_backed)

        with st.expander(t("docs.timeline", title=base_document_title(title))):
            st.markdown(
                version_timeline_html(_version_history(doc, documents), current_version=version),
                unsafe_allow_html=True,
            )


# ── Main component ───────────────────────────────────────────────────────────
def render_document_list_component() -> None:
    """Renders the Uploaded PDF Documents inventory with admin status controls."""
    st.subheader(t("docs.heading"))

    flash = st.session_state.pop(_FLASH_KEY, None)
    if flash:
        level, text = flash
        getattr(st, level, st.info)(text)

    # Rendered before the rows so the modal survives the target being filtered
    # out of view while the confirmation is open.
    _render_delete_modal()

    documents, db_backed = _load_documents()
    if not documents:
        st.info(t("docs.empty"))
        return

    if not db_backed:
        st.caption(t("docs.session_notice"))

    filters = st.session_state.get(FILTER_STATE_KEY) or {}
    visible = [doc for doc in documents if _matches_filters(doc, filters)]

    active_count = sum(1 for doc in visible if normalize_status(doc.get("status")) == "ACTIVE")
    st.caption(t("docs.showing", visible=len(visible), total=len(documents), active=active_count))

    if not visible:
        st.info(t("docs.no_match"))
        return

    for index, doc in enumerate(visible):
        row_key = str(doc.get("id") or f"{doc.get('title', '')}-{doc.get('version', '')}-{index}")
        _render_document_row(doc, row_key, documents, db_backed)
