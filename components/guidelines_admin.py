"""
components/guidelines_admin.py
-------------------------------
Guideline Management — the second half of the Admin tab.

Three things, in the order an administrator needs them:

    1. Sync warnings   — what is wrong with the registry right now
    2. The registry    — every document, its version, status, effective date
                         and how many passages of it retrieval can actually see
    3. Admin actions   — Archive, or force a version to SUPERSEDED

Ordering matters: the warnings sit above the table because the whole reason to
open this panel is usually that something is wrong, and a warning buried under
forty rows is a warning nobody reads.

Sync warnings
-------------
Akhil's batch job is meant to own this: it walks the registry and flags
documents that have drifted out of sync. That job does not publish its findings
yet, so `_sync_warnings()` resolves a real source first (see _WARNING_SOURCES)
and otherwise computes the same four checks live from the registry. The panel
says which of the two answered, so nobody mistakes a live check for a batch run.

Writes
------
Unlike components/analytics.py, this module writes. Archiving or superseding a
document changes what field workers are answered from, so both go through a
two-step confirmation naming the document and spelling out the consequence, and
neither is offered at all when the registry is running on local sample data.
"""

from __future__ import annotations

import html
import importlib
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Tuple

import streamlit as st

from utils.i18n import t
from utils.ui_helpers import (
    base_document_title,
    normalize_status,
    status_badge_html,
)

# Seconds the registry and passage counts are reused for. Short: an admin who
# has just archived something expects the table to agree with them, and the
# action path clears these caches explicitly anyway.
CACHE_TTL_SECONDS = 30

# Session key holding the action awaiting confirmation:
# {"action": "archive" | "supersede", "id", "title", "version"}.
_PENDING_KEY = "_guidelines_pending_action"

# Session key holding the outcome of the last applied action, so the message
# survives the st.rerun() that redraws the table.
_FLASH_KEY = "_guidelines_flash"

ACTION_ARCHIVE = "archive"
ACTION_SUPERSEDE = "supersede"

# Where a real, batch-produced warning feed might live once it exists, tried in
# order. Each entry is (module, *candidate function names).
_WARNING_SOURCES: Tuple[Tuple[str, ...], ...] = (
    ("database.sync", "list_sync_warnings", "get_sync_warnings", "fetch_sync_warnings"),
    ("database.documents", "list_sync_warnings", "list_flagged_documents"),
    ("database.analytics", "get_sync_warnings", "list_sync_warnings"),
)

# Warning codes, in the order they should be shown — most dangerous first.
# "serious" paints the red banner, "warning" the yellow one.
_WARNING_SEVERITY: Dict[str, str] = {
    "duplicate_active": "serious",
    "not_indexed": "serious",
    "future_effective": "warning",
    "no_effective_date": "warning",
}


# ── Registry loading ─────────────────────────────────────────────────────────
@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_documents() -> List[Dict[str, Any]]:
    """Every document in the registry, all statuses, newest upload first."""
    from database.documents import fetch_all_documents

    return fetch_all_documents() or []


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_chunk_counts(document_ids: Tuple[str, ...]) -> Dict[str, int]:
    """
    Indexed passage count per document id.

    One COUNT per document rather than bulk_fetch_chunks_by_documents(), which
    returns every chunk's full text — far too much to move for a number.
    """
    from database.chunks import fetch_chunk_count_by_document

    return {doc_id: fetch_chunk_count_by_document(doc_id) for doc_id in document_ids}


def _load_registry() -> Tuple[List[Dict[str, Any]], bool, str | None]:
    """
    Loads the document registry.

    Returns:
        (documents, db_backed, error) — db_backed is False when the rows came
        from st.session_state instead of Supabase, in which case the admin
        actions are shown disabled rather than silently doing nothing.
    """
    try:
        documents = _fetch_documents()
        if documents:
            return documents, True, None
        # An empty registry is a real answer, not a failure.
        return [], True, None
    except Exception as exc:
        print(f"[guidelines_admin] fetch_all_documents failed: {exc}")
        return list(st.session_state.get("documents") or []), False, str(exc)


def _chunk_counts(documents: List[Dict[str, Any]], db_backed: bool) -> Tuple[Dict[str, int], bool]:
    """
    Passage counts per document, and whether they can be trusted.

    fetch_chunk_count_by_document() swallows its own errors and returns 0, so a
    broken connection is indistinguishable from an unindexed document. When
    every document reports zero, a failed query is far likelier than a corpus
    where nothing was ever indexed — so the counts are reported as unverified
    and the not-indexed check is skipped rather than raising a row of false
    alarms. The cost is that a genuinely fresh, wholly unindexed corpus shows
    "unverified" instead of warnings, which is the safer way to be wrong.
    """
    ids = tuple(str(doc["id"]) for doc in documents if doc.get("id"))
    if not db_backed or not ids:
        return {}, False

    try:
        counts = _fetch_chunk_counts(ids)
    except Exception as exc:
        print(f"[guidelines_admin] chunk counts failed: {exc}")
        return {}, False

    return counts, any(value > 0 for value in counts.values())


# ── Sync warnings ────────────────────────────────────────────────────────────
def _batch_warning_source() -> Callable[..., Any] | None:
    """The first real sync-warning feed that exists, or None."""
    for module_name, *candidates in _WARNING_SOURCES:
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for name in candidates:
            handler = getattr(module, name, None)
            if callable(handler):
                return handler
    return None


def _normalize_warning(row: Any) -> Dict[str, Any]:
    """
    Coerces one row from a batch feed into the shape this panel renders.

    The batch job's exact output is not fixed yet, so several spellings of each
    field are accepted and anything unreadable degrades to its own repr rather
    than being dropped — an unrecognised warning is still a warning.
    """
    if not isinstance(row, dict):
        return {"code": "batch", "severity": "warning", "detail": str(row), "document_id": None}

    detail = (
        row.get("detail")
        or row.get("message")
        or row.get("description")
        or row.get("warning")
        or str(row)
    )
    severity = str(row.get("severity") or row.get("level") or "warning").lower()

    return {
        "code": str(row.get("code") or row.get("type") or "batch"),
        "severity": severity if severity in {"serious", "warning"} else "warning",
        "detail": str(detail),
        "document_id": row.get("document_id") or row.get("id"),
    }


def _parse_date(value: Any) -> date | None:
    """Reads a YYYY-MM-DD (or ISO timestamp) field, returning None when absent."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def _local_warnings(
    documents: List[Dict[str, Any]],
    counts: Dict[str, int],
    counts_verified: bool,
) -> List[Dict[str, Any]]:
    """
    Computes the sync checks live from the registry.

    Four checks, each answering "would a field worker be misled by this?":

      duplicate_active   two versions of one guideline both ACTIVE, so
                         retrieval may answer from either
      not_indexed        ACTIVE but with no passages, so retrieval cannot see
                         it at all — the document looks published and is not
      future_effective   ACTIVE but not in force until a future date
      no_effective_date  ACTIVE with no date, so currency cannot be checked
    """
    warnings: List[Dict[str, Any]] = []
    active = [doc for doc in documents if normalize_status(doc.get("status")) == "ACTIVE"]

    # duplicate_active — grouped by base title so "Protocol v2" and
    # "Protocol v3" are recognised as versions of one guideline.
    families: Dict[str, List[Dict[str, Any]]] = {}
    for doc in active:
        families.setdefault(base_document_title(doc.get("title")).lower(), []).append(doc)

    for members in families.values():
        if len(members) < 2:
            continue
        newest = max(members, key=lambda d: (str(d.get("effective_date") or ""), str(d.get("version") or "")))
        versions = ", ".join(str(d.get("version") or "—") for d in members)
        for doc in members:
            warnings.append(
                {
                    "code": "duplicate_active",
                    "severity": _WARNING_SEVERITY["duplicate_active"],
                    "document_id": doc.get("id"),
                    "detail": t(
                        "guidelines.sync.duplicate_active_detail",
                        title=base_document_title(doc.get("title")) or "—",
                        count=len(members),
                        versions=versions,
                        newest=str(newest.get("version") or "—"),
                    ),
                }
            )

    today = date.today()
    for doc in active:
        title = str(doc.get("title") or "—")
        version = str(doc.get("version") or "—")
        effective = _parse_date(doc.get("effective_date"))

        if counts_verified and doc.get("id") and counts.get(str(doc["id"]), 0) == 0:
            warnings.append(
                {
                    "code": "not_indexed",
                    "severity": _WARNING_SEVERITY["not_indexed"],
                    "document_id": doc.get("id"),
                    "detail": t("guidelines.sync.not_indexed_detail", title=title, version=version),
                }
            )

        if effective is None:
            warnings.append(
                {
                    "code": "no_effective_date",
                    "severity": _WARNING_SEVERITY["no_effective_date"],
                    "document_id": doc.get("id"),
                    "detail": t("guidelines.sync.no_effective_date_detail", title=title, version=version),
                }
            )
        elif effective > today:
            warnings.append(
                {
                    "code": "future_effective",
                    "severity": _WARNING_SEVERITY["future_effective"],
                    "document_id": doc.get("id"),
                    "detail": t(
                        "guidelines.sync.future_effective_detail",
                        title=title,
                        version=version,
                        date=effective.isoformat(),
                    ),
                }
            )

    return warnings


def _sync_warnings(
    documents: List[Dict[str, Any]],
    counts: Dict[str, int],
    counts_verified: bool,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Returns (warnings, source) where source is "batch" or "local".

    A batch feed that exists but throws is not allowed to take the panel down;
    it falls through to the live checks, which need nothing but the registry
    already loaded.
    """
    handler = _batch_warning_source()
    if handler is not None:
        try:
            rows = handler() or []
            return [_normalize_warning(row) for row in rows], "batch"
        except Exception as exc:
            print(f"[guidelines_admin] batch sync-warning feed failed: {exc}")

    return _local_warnings(documents, counts, counts_verified), "local"


def _warnings_by_document(warnings: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Groups warnings by document id, for the per-row flag in the table."""
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for warning in warnings:
        document_id = warning.get("document_id")
        if document_id:
            grouped.setdefault(str(document_id), []).append(warning)
    return grouped


def _warning_banner_html(code: str, severity: str, details: List[str]) -> str:
    """
    One grouped banner per warning code, reusing the conflict-banner styling so
    an admin alert looks like the alerts already in the app.
    """
    level = "danger" if severity == "serious" else "warning"
    icon = "🚨" if level == "danger" else "⚠️"
    heading = t(f"guidelines.sync.{code}") if code in _WARNING_SEVERITY else t("guidelines.sync.batch")

    body = "".join(f"<li>{html.escape(detail)}</li>" for detail in details)
    return f"""
    <div class="csa-banner csa-banner-{level}">
        <div class="csa-banner-title">{icon} {html.escape(heading)} ({len(details)})</div>
        <ul class="csa-banner-body">{body}</ul>
    </div>
    """


def _render_sync_warnings(
    warnings: List[Dict[str, Any]],
    source: str,
    document_count: int,
    counts_verified: bool,
    db_backed: bool,
) -> None:
    """Renders the sync-warning banners above the registry table."""
    st.markdown(f"##### {t('guidelines.sync.heading')}")

    if not db_backed:
        st.caption(t("guidelines.sync.needs_db"))
        return

    if not warnings:
        st.success(t("guidelines.sync.none", count=document_count))
    else:
        # Grouped by code so five unindexed documents are one banner listing
        # five, not five banners saying the same thing.
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for warning in warnings:
            grouped.setdefault(warning["code"], []).append(warning)

        ordered = sorted(
            grouped.items(),
            key=lambda item: (
                0 if item[1][0].get("severity") == "serious" else 1,
                list(_WARNING_SEVERITY).index(item[0]) if item[0] in _WARNING_SEVERITY else 99,
            ),
        )
        for code, items in ordered:
            # One bullet per distinct sentence. duplicate_active attaches the
            # same finding to every sibling version so each row gets its flag,
            # but the banner should state it once rather than once per version.
            details = list(dict.fromkeys(item["detail"] for item in items))
            st.markdown(
                _warning_banner_html(code, items[0].get("severity", "warning"), details),
                unsafe_allow_html=True,
            )
        st.caption(t("guidelines.sync.footer"))

    note = t("guidelines.sync.source_batch") if source == "batch" else t("guidelines.sync.source_local")
    if not counts_verified:
        note += " " + t("guidelines.sync.unverified")
    st.caption(note)


# ── Admin actions ────────────────────────────────────────────────────────────
def _request_action(action: str, doc: Dict[str, Any]) -> None:
    """Stages an action for confirmation and redraws with the confirm strip."""
    st.session_state[_PENDING_KEY] = {
        "action": action,
        "id": str(doc.get("id") or ""),
        "title": str(doc.get("title") or "—"),
        "version": str(doc.get("version") or "—"),
    }
    st.rerun()


def _clear_pending() -> None:
    """Drops the staged action without applying it."""
    st.session_state.pop(_PENDING_KEY, None)


def _apply_action(pending: Dict[str, Any]) -> None:
    """
    Applies a confirmed Archive or Supersede, then invalidates the caches so
    the table redraws from the database rather than from the pre-action copy.

    The outcome goes into session_state because the st.rerun() below would
    otherwise wipe any message written here before it could be seen.
    """
    from database.documents import archive_document, update_document_status

    action = pending["action"]
    document_id = pending["id"]
    label = {"title": pending["title"], "version": pending["version"]}

    try:
        if action == ACTION_ARCHIVE:
            changed = archive_document(document_id)
        else:
            changed = update_document_status(document_id, "SUPERSEDED")
    except Exception as exc:
        st.session_state[_FLASH_KEY] = ("error", t("guidelines.failed", error=exc, **label))
        _clear_pending()
        st.rerun()
        return

    if not changed:
        st.session_state[_FLASH_KEY] = ("error", t("guidelines.missing"))
    else:
        new_status = "ARCHIVED" if action == ACTION_ARCHIVE else "SUPERSEDED"
        st.session_state[_FLASH_KEY] = (
            "success",
            t(f"guidelines.done.{action}", **label),
        )
        # Keep the Documents tab's session inventory in step, so the two views
        # do not disagree about a document the admin just retired.
        for entry in st.session_state.get("documents") or []:
            if entry.get("title") == pending["title"] and entry.get("version") == pending["version"]:
                entry["status"] = new_status

    _fetch_documents.clear()
    _fetch_chunk_counts.clear()
    _clear_pending()
    st.rerun()


def _render_confirmation(pending: Dict[str, Any]) -> None:
    """
    The confirm strip for a staged action.

    Archiving or superseding changes what field workers are answered from, so
    the strip names the exact version and says what will happen to it — a bare
    "Are you sure?" is not a description of a consequence.
    """
    action = pending["action"]
    label = {"title": pending["title"], "version": pending["version"]}

    st.warning(t(f"guidelines.confirm.{action}_title", **label))
    st.caption(t(f"guidelines.confirm.{action}_body"))

    confirm_col, cancel_col, _spacer = st.columns([1.4, 1.2, 4.4])
    with confirm_col:
        if st.button(
            t("guidelines.confirm.yes"),
            key="csa_guideline_confirm",
            type="primary",
            use_container_width=True,
        ):
            _apply_action(pending)
    with cancel_col:
        if st.button(
            t("guidelines.confirm.no"),
            key="csa_guideline_cancel",
            use_container_width=True,
        ):
            _clear_pending()
            st.rerun()


# ── Registry table ───────────────────────────────────────────────────────────
# Title, version, status, effective date, passages, then the two action
# buttons. Wide enough for a title to survive without truncation.
_COLUMN_WIDTHS = [3.2, 1.0, 1.5, 1.4, 1.1, 2.4]


def _render_table_header() -> None:
    """The column headings, so the rows below read as a table rather than cards."""
    columns = st.columns(_COLUMN_WIDTHS)
    headings = (
        "guidelines.col.title",
        "guidelines.col.version",
        "guidelines.col.status",
        "guidelines.col.effective",
        "guidelines.col.indexed",
        "guidelines.col.actions",
    )
    for column, key in zip(columns, headings):
        with column:
            st.markdown(f'<div class="csa-table-head">{html.escape(t(key))}</div>',
                        unsafe_allow_html=True)


def _render_row(
    doc: Dict[str, Any],
    index: int,
    counts: Dict[str, int],
    counts_verified: bool,
    row_warnings: List[Dict[str, Any]],
    db_backed: bool,
    frozen: bool,
) -> None:
    """
    One document row: metadata, a flag when it has sync warnings, and the two
    admin actions.

    Args:
        frozen: True while another action is awaiting confirmation. Every
                button is disabled then, so an admin cannot stack a second
                irreversible change on top of one they have not confirmed.
    """
    document_id = str(doc.get("id") or "")
    status = normalize_status(doc.get("status"))
    title = str(doc.get("title") or "—")
    version = str(doc.get("version") or "—")
    effective = str(doc.get("effective_date") or "—")

    title_col, version_col, status_col, effective_col, indexed_col, action_col = st.columns(
        _COLUMN_WIDTHS
    )

    with title_col:
        flag = ""
        if row_warnings:
            flag = (
                f'<span class="csa-row-flag" title="'
                f'{html.escape(t("guidelines.sync.row_flag_help", count=len(row_warnings)))}">'
                f'{html.escape(t("guidelines.sync.row_flag", count=len(row_warnings)))}</span>'
            )
        st.markdown(
            f'<div class="csa-table-cell"><strong>{html.escape(title)}</strong>{flag}</div>',
            unsafe_allow_html=True,
        )

    with version_col:
        st.markdown(f'<div class="csa-table-cell">{html.escape(version)}</div>',
                    unsafe_allow_html=True)

    with status_col:
        st.markdown(f'<div class="csa-table-cell">{status_badge_html(status)}</div>',
                    unsafe_allow_html=True)

    with effective_col:
        st.markdown(f'<div class="csa-table-cell">{html.escape(effective)}</div>',
                    unsafe_allow_html=True)

    with indexed_col:
        if counts_verified and document_id in counts:
            passages = f"{counts[document_id]:,}"
        else:
            passages = t("guidelines.indexed_unknown")
        st.markdown(f'<div class="csa-table-cell csa-table-num">{html.escape(passages)}</div>',
                    unsafe_allow_html=True)

    with action_col:
        archive_col, supersede_col = st.columns(2)

        # A status the action would not change is disabled rather than hidden,
        # so the row keeps the same shape as every other row.
        archive_blocked = status == "ARCHIVED"
        supersede_blocked = status in {"SUPERSEDED", "ARCHIVED"}

        with archive_col:
            if st.button(
                t("guidelines.action.archive"),
                key=f"csa_guideline_archive_{index}",
                help=_action_help(ACTION_ARCHIVE, archive_blocked, db_backed, status),
                disabled=frozen or archive_blocked or not db_backed or not document_id,
                use_container_width=True,
            ):
                _request_action(ACTION_ARCHIVE, doc)

        with supersede_col:
            if st.button(
                t("guidelines.action.supersede"),
                key=f"csa_guideline_supersede_{index}",
                help=_action_help(ACTION_SUPERSEDE, supersede_blocked, db_backed, status),
                disabled=frozen or supersede_blocked or not db_backed or not document_id,
                use_container_width=True,
            ):
                _request_action(ACTION_SUPERSEDE, doc)


def _action_help(action: str, blocked: bool, db_backed: bool, status: str) -> str:
    """Tooltip for an action button, explaining a disabled one rather than going silent."""
    if not db_backed:
        return t("guidelines.action.needs_db")
    if blocked:
        return t("guidelines.action.no_change", status=t(f"status.{status}"))
    return t(f"guidelines.action.{action}_help")


def _render_flash() -> None:
    """Shows the outcome of the last applied action, once."""
    flash = st.session_state.pop(_FLASH_KEY, None)
    if not flash:
        return
    level, message = flash
    {"success": st.success, "error": st.error, "warning": st.warning}.get(level, st.info)(message)


# ── Entry point ──────────────────────────────────────────────────────────────
def render_guideline_management() -> None:
    """Renders the Guideline Management sub-section of the Admin tab."""
    st.subheader(t("guidelines.heading"))
    st.caption(t("guidelines.caption"))

    _render_flash()

    documents, db_backed, error = _load_registry()

    if error and not documents:
        st.warning(t("guidelines.unavailable", error=error))
        return
    if error:
        st.info(t("guidelines.session_only"))

    if not documents:
        st.caption(t("guidelines.empty"))
        return

    counts, counts_verified = _chunk_counts(documents, db_backed)
    warnings, source = _sync_warnings(documents, counts, counts_verified)

    _render_sync_warnings(warnings, source, len(documents), counts_verified, db_backed)

    st.divider()

    active_count = sum(
        1 for doc in documents if normalize_status(doc.get("status")) == "ACTIVE"
    )
    header_col, reload_col = st.columns([5, 1.2])
    with header_col:
        st.caption(t("guidelines.count", count=len(documents), active=active_count))
    with reload_col:
        if st.button(
            t("guidelines.refresh"),
            key="csa_guidelines_reload",
            help=t("guidelines.refresh_help"),
            use_container_width=True,
        ):
            _fetch_documents.clear()
            _fetch_chunk_counts.clear()
            st.rerun()

    # A staged action freezes every row's buttons until it is resolved.
    pending = st.session_state.get(_PENDING_KEY)
    if pending:
        _render_confirmation(pending)

    grouped = _warnings_by_document(warnings)

    _render_table_header()
    for index, doc in enumerate(documents):
        _render_row(
            doc,
            index,
            counts,
            counts_verified,
            grouped.get(str(doc.get("id") or ""), []),
            db_backed,
            frozen=bool(pending),
        )
