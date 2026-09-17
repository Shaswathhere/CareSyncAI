"""
utils/ui_helpers.py
--------------------
Shared Streamlit UI helpers (status badges, retrieval confidence badges,
conflict banners, passage snippet highlighting, version timelines) used across
components/ so styling stays consistent between the chat, document list, and
upload views.

Every user-visible string here goes through utils.i18n.t(), so a helper
renders in whatever language the sidebar picker has selected. Status values
themselves stay English — they are data written to Supabase, and only their
badge *label* is localized.
"""

from __future__ import annotations

import html
import math
import re
from typing import Any, Dict, Iterable, List

from utils.i18n import t

# Document lifecycle statuses, in the order they should appear in dropdowns.
STATUS_OPTIONS: tuple[str, ...] = ("ACTIVE", "SUPERSEDED", "ARCHIVED")

# Sentinel used by the sidebar filters to mean "do not filter by status".
STATUS_ANY = "All statuses"

# Maps a document lifecycle status to its CSS badge class (see assets/style.css).
_STATUS_BADGE_CLASS = {
    "ACTIVE": "csa-status-active",
    "SUPERSEDED": "csa-status-superseded",
    "ARCHIVED": "csa-status-archived",
}

# English status hints, resolved once at import. Kept as a plain dict because
# the summary export (utils/export.py) is deliberately English-only; the UI
# calls status_hint() instead so it follows the selected language.
STATUS_HINTS = {status: t(f"status.hint.{status}", language="en") for status in STATUS_OPTIONS}

# ── Retrieval confidence ─────────────────────────────────────────────────────
# rag/reranker.py scores every (question, passage) pair with the
# cross-encoder/ms-marco-MiniLM-L-6-v2 model and stamps the result onto the
# citation as "rerank_score". That score is a raw logit — unbounded, and in
# practice somewhere between about -11 (unrelated) and +11 (near-verbatim
# answer). A logit is not a number to put in front of a field worker, so it is
# squashed through a logistic curve into a 0-100% reading first.
#
# The bands below are cut on that percentage, not on the logit, so they stay
# meaningful if the reranker model is ever swapped for another cross-encoder.
CONFIDENCE_BANDS: tuple[str, ...] = ("high", "medium", "low")

# Divisor applied to the logit before the logistic squash. A plain sigmoid
# saturates far too early for this model — ms-marco logits of 2 and of 9 both
# come out as "99%", which would badge every citation identically and tell the
# field worker nothing. Dividing by 3 first spreads the band the model actually
# uses (about -11 to +11) across the middle of the curve, so a score of 5 reads
# 84% and a score of 2 reads 66% instead of both reading full marks.
_CONFIDENCE_TEMPERATURE = 3.0

# (minimum percentage, band). Checked high-to-low; anything under the last
# threshold is "low". At the temperature above these cut at roughly logit
# +3.3 and -1.2, which is about where ms-marco separates a passage that
# answers the question from one that merely shares its vocabulary.
_CONFIDENCE_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (75.0, "high"),
    (40.0, "medium"),
)

# Three-dot meter drawn inside the badge. Colour alone must never be what tells
# a strong citation from a weak one — a red/green pair is exactly the contrast
# a deuteranopic reader cannot make — so the glyph carries the ranking too, and
# the percentage spells it out in full.
_CONFIDENCE_GLYPH = {
    "high": "●●●",
    "medium": "●●○",
    "low": "●○○",
}

_CONFIDENCE_BADGE_CLASS = {
    "high": "csa-confidence-high",
    "medium": "csa-confidence-medium",
    "low": "csa-confidence-low",
}


def rerank_confidence(score: Any) -> Dict[str, Any] | None:
    """
    Converts a raw cross-encoder score into a displayable confidence reading.

    Args:
        score: The "rerank_score" stamped on a citation by rag/reranker.py, or
               None when the reranker fell back to vector-similarity ordering
               and never scored the passage.

    Returns:
        Dict with keys:
            band    — "high" | "medium" | "low"
            percent — the score as an integer 0-100
            score   — the original logit, kept for the tooltip
        or None when there is no score to show. Returning None rather than a
        default band matters: an unscored citation must look unscored, not
        confidently mediocre.
    """
    if score is None or isinstance(score, bool):
        return None

    try:
        raw = float(score)
    except (TypeError, ValueError):
        return None

    if raw != raw or raw in (float("inf"), float("-inf")):  # NaN / ±inf
        return None

    # Logistic squash of the calibrated logit. math.exp overflows for large
    # negative inputs, so the exponent is clamped to the range where float
    # arithmetic stays exact enough — beyond it the answer is 0% or 100% anyway.
    calibrated = raw / _CONFIDENCE_TEMPERATURE
    percent = 100.0 / (1.0 + math.exp(-max(-60.0, min(60.0, calibrated))))

    band = "low"
    for minimum, candidate in _CONFIDENCE_THRESHOLDS:
        if percent >= minimum:
            band = candidate
            break

    return {"band": band, "percent": int(round(percent)), "score": raw}


def confidence_label(band: str, language: str | None = None) -> str:
    """Localized name for a confidence band, e.g. "high" -> "High relevance"."""
    band = band if band in CONFIDENCE_BANDS else "low"
    return t(f"confidence.{band}", language=language)


def confidence_badge_html(confidence: Dict[str, Any] | None) -> str:
    """
    Renders the relevance badge shown on a citation card.

    Args:
        confidence: A rerank_confidence() reading, or None.

    Returns:
        An HTML <span>, or "" when the passage was never scored — the card then
        simply carries no badge, which is honest about what is not known.
    """
    if not confidence:
        return ""

    band = confidence.get("band") if confidence.get("band") in CONFIDENCE_BANDS else "low"
    percent = int(confidence.get("percent") or 0)
    css_class = _CONFIDENCE_BADGE_CLASS[band]

    # The title attribute is the only place the raw model score appears: useful
    # when tuning retrieval, meaningless to the field worker reading the answer.
    tooltip = t(
        "confidence.help",
        label=confidence_label(band),
        percent=percent,
        score=f"{float(confidence.get('score') or 0.0):.2f}",
    )

    return (
        f'<span class="csa-confidence-tag {css_class}" title="{html.escape(tooltip)}">'
        f'<span class="csa-confidence-meter">{_CONFIDENCE_GLYPH[band]}</span>'
        f'{html.escape(t("confidence.badge", percent=percent))}'
        f"</span>"
    )


# Words stripped before highlighting so common question words don't light up
# the whole passage. Mirrors the keyword extraction in rag/retriever.py.
_HIGHLIGHT_STOPWORDS = {
    "what", "when", "where", "which", "how", "does", "with", "from",
    "that", "this", "the", "and", "for", "are", "was", "were", "should",
}


def status_badge_html(status: str) -> str:
    """
    Returns an HTML <span> rendered as a colored status tag for the given
    document status. Unrecognized statuses fall back to the ARCHIVED style.

    Args:
        status: One of "ACTIVE", "SUPERSEDED", "ARCHIVED".

    Returns:
        HTML string, e.g. '<span class="csa-status-tag csa-status-active">ACTIVE</span>'
    """
    css_class = _STATUS_BADGE_CLASS.get(status, "csa-status-archived")
    label = t(f"status.{status}") if status in _STATUS_BADGE_CLASS else str(status)
    return f'<span class="csa-status-tag {css_class}">{html.escape(label)}</span>'


def normalize_status(status: Any, default: str = "ACTIVE") -> str:
    """Uppercases a status value, falling back to `default` when unrecognized."""
    candidate = str(status or "").strip().upper()
    return candidate if candidate in STATUS_OPTIONS else default


def status_hint(status: str, language: str | None = None) -> str:
    """
    Returns the short explanation shown beside a status badge, in the active
    language. Pass language="en" for text that must stay English.
    """
    return t(f"status.hint.{normalize_status(status)}", language=language)


def status_filter_label(value: str) -> str:
    """
    Localized label for a status dropdown option, including the STATUS_ANY
    sentinel. The option *values* stay English so filtering logic and stored
    document data never depend on the selected language.
    """
    if value == STATUS_ANY:
        return t("status.any")
    return t(f"status.{value}") if value in STATUS_OPTIONS else str(value)


def conflict_banner_html(message: str, level: str = "warning") -> str:
    """
    Builds the alert banner shown above an answer when the retriever flags
    contradicting guidance across the retrieved documents.

    Args:
        message: Conflict summary produced by detect_guideline_conflicts().
        level:   "warning" (yellow — discrepancy between active documents) or
                 "danger"  (red — discrepancy involving superseded guidance).

    Returns:
        HTML string for a full-width banner.
    """
    level = level if level in {"warning", "danger"} else "warning"
    icon, heading = (
        ("⚠️", t("conflict.title_warning"))
        if level == "warning"
        else ("🚨", t("conflict.title_danger"))
    )

    # detect_guideline_conflicts() returns one "• ..." bullet per conflicting pair.
    lines = [line.strip(" •-\t") for line in str(message).splitlines() if line.strip(" •-\t")]
    body = "".join(f"<li>{html.escape(line)}</li>" for line in lines)

    return f"""
    <div class="csa-banner csa-banner-{level}">
        <div class="csa-banner-title">{icon} {heading}</div>
        <ul class="csa-banner-body">{body}</ul>
        <div class="csa-banner-footer">{html.escape(t("conflict.footer"))}</div>
    </div>
    """


def extract_query_terms(query: str | None) -> List[str]:
    """
    Pulls the meaningful words out of a user question so they can be
    highlighted inside a retrieved passage.

    Args:
        query: The natural-language question, or None.

    Returns:
        Lowercased terms of 4+ characters, stopwords removed, de-duplicated.
    """
    if not query:
        return []

    terms: List[str] = []
    for word in re.findall(r"[a-zA-Z0-9]{4,}", query.lower()):
        if word not in _HIGHLIGHT_STOPWORDS and word not in terms:
            terms.append(word)
    return terms


def highlight_snippet_html(
    text: str,
    terms: Iterable[str] | None = None,
    max_chars: int = 700,
) -> str:
    """
    Escapes a retrieved passage and wraps every occurrence of the query terms
    in a <mark> tag so field workers can see *why* a passage was cited.

    Args:
        text:      Raw passage content from the retrieved chunk.
        terms:     Query terms to highlight (see extract_query_terms()).
        max_chars: Truncation limit — long chunks are cut on a word boundary.

    Returns:
        HTML string safe to render with unsafe_allow_html=True.
    """
    snippet = " ".join(str(text or "").split())
    if not snippet:
        return '<em class="csa-muted">No passage text was stored for this citation.</em>'

    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rsplit(" ", 1)[0] + " …"

    escaped = html.escape(snippet)

    term_list = [t for t in (terms or []) if t]
    if term_list:
        pattern = re.compile(
            "(" + "|".join(re.escape(html.escape(t)) for t in term_list) + ")",
            re.IGNORECASE,
        )
        escaped = pattern.sub(r'<mark class="csa-highlight">\1</mark>', escaped)

    return escaped


def snippet_text(source: Dict[str, Any]) -> str:
    """
    Reads the passage text off a citation dict, tolerating the different keys
    the RAG pipeline has used for it (snippet / content / passage / text).
    """
    for key in ("snippet", "content", "passage", "text"):
        value = source.get(key)
        if value:
            return str(value)
    return ""


def base_document_title(title: str | None) -> str:
    """
    Strips a trailing version suffix from a document title so every version of
    the same guideline groups onto one timeline.

    Examples:
        "Vaccination Protocol v3"  -> "Vaccination Protocol"
        "Outbreak Guidelines (v2)" -> "Outbreak Guidelines"
    """
    cleaned = str(title or "").strip()
    cleaned = re.sub(
        r"[\s\-–—]*\(?\bv(?:ersion)?\s*\.?\s*\d+(?:\.\d+)*\)?$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip(" -–—:") or str(title or "").strip()


def version_timeline_html(
    versions: List[Dict[str, Any]],
    current_version: str | None = None,
) -> str:
    """
    Renders a document's version history as a vertical timeline tree, oldest
    version first, with a status badge per node.

    Args:
        versions:        Document dicts (title, version, effective_date, status).
        current_version: Version string to mark as the row being expanded.

    Returns:
        HTML string for the timeline.
    """
    if not versions:
        return f'<div class="csa-muted">{html.escape(t("timeline.empty"))}</div>'

    nodes: List[str] = []
    for index, doc in enumerate(versions):
        status = normalize_status(doc.get("status"))
        version = str(doc.get("version") or "—")
        effective = str(doc.get("effective_date") or doc.get("publication_date") or "—")
        is_current = current_version is not None and version == str(current_version)
        dot_class = (
            "csa-timeline-dot--current" if is_current else f"csa-timeline-dot--{status.lower()}"
        )
        here_tag = (
            f'<span class="csa-timeline-here">{html.escape(t("timeline.this_row"))}</span>'
            if is_current
            else ""
        )
        superseded_note = t("timeline.superseded_note") if status == "SUPERSEDED" else ""

        nodes.append(
            f"""
            <li class="csa-timeline-item">
                <span class="csa-timeline-dot {dot_class}"></span>
                <div class="csa-timeline-body">
                    <div class="csa-timeline-head">
                        <strong>{html.escape(version)}</strong>
                        {status_badge_html(status)}
                        {here_tag}
                    </div>
                    <div class="csa-muted">
                        {html.escape(t("timeline.effective", date=effective))}
                        {html.escape(superseded_note)}
                    </div>
                </div>
            </li>
            """
        )
        # Connector arrow between consecutive versions in the tree.
        if index < len(versions) - 1:
            nodes.append('<li class="csa-timeline-connector">↓</li>')

    return f'<ul class="csa-timeline">{"".join(nodes)}</ul>'
