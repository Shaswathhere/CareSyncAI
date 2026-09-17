"""
components/analytics.py
------------------------
Admin Analytics Dashboard: the operational view of CareSync AI.

Four questions, in the order an operator asks them:

    1. How much is it being used, and how fast is it?  — the KPI row
    2. Where does the time go?                          — pipeline stage breakdown
    3. Is it getting slower?                            — latency by lookback window
    4. Are the answers any good?                        — helpful rate and downvote notes

...followed by the two tables worth reading when one of those goes red: the
slowest queries and the outright failures.

Data sources
------------
Every figure is read through the resolver in the "Data access" section below,
which prefers Akhil's `database.analytics` module and falls back to the
`database.feedback` handlers already in the tree.

As of the Day 11 merge that module exists but answers different questions than
this dashboard asks — get_system_health_metrics(), get_feedback_satisfaction_rate(),
plus daily-active-user and top-topic series — and its rows are shaped
differently too (failed_count rather than failed_queries; a since_days window
rather than since_hours). So the resolver finds none of its own handlers there
and the figures below still come from `database.feedback`. The footer reports
whichever module actually answered, so the attribution is never a guess.

Nothing here writes. A failure in any panel degrades that panel to an
explanatory message and leaves the rest of the dashboard standing, because a
dashboard that shows nothing when one query fails is worse than no dashboard.

Charts
------
Colors are picked per theme, not flipped: two validated teal/orange
categorical steps and a single-hue teal ramp for magnitude, each stepped
separately for the light and dark chart surface. Every chart carries direct
value labels and a "Show data table" expander, so no reading depends on
telling two colors apart.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Tuple

import streamlit as st

from utils.i18n import t

# Charting is optional at import time. Streamlit depends on both pandas and
# altair, so in a working deployment these are always present — but the
# dashboard degrades to plain tables rather than taking the whole app down if
# a slimmed-down environment is missing them.
try:
    import pandas as pd
    import altair as alt

    CHARTS_AVAILABLE = True
except Exception as exc:  # pragma: no cover — depends on the install, not the code.
    pd = None  # type: ignore[assignment]
    alt = None  # type: ignore[assignment]
    CHARTS_AVAILABLE = False
    print(f"[analytics] Charting unavailable ({exc}); falling back to tables.")


# ── Dashboard configuration ──────────────────────────────────────────────────
# Lookback windows offered in the picker, in hours. Also the x-axis of the
# "response time by lookback window" chart, so keep them ascending.
WINDOW_HOURS: Tuple[int, ...] = (1, 6, 24, 168, 720)

DEFAULT_WINDOW_HOURS = 24

# Session key holding the selected lookback window.
WINDOW_STATE_KEY = "analytics_window_hours"

# Session key holding the slow-query threshold in milliseconds.
THRESHOLD_STATE_KEY = "analytics_slow_threshold_ms"

DEFAULT_SLOW_THRESHOLD_MS = 5000.0

# Seconds a fetched figure is reused for. Long enough that clicking around the
# dashboard does not re-run five Supabase queries per rerun, short enough that
# "refresh" is rarely what an operator actually needs.
CACHE_TTL_SECONDS = 60

# Rows pulled for the tables and the feedback aggregation. The dashboard is a
# health check, not an export — utils/export.py is where bulk output belongs.
ROW_LIMIT = 200


# ── Chart palette ────────────────────────────────────────────────────────────
# Both modes are selected, not flipped: each is stepped for its own surface and
# validated there (categorical pairs clear the CVD, chroma, lightness and 3:1
# contrast gates; the ramps are monotone in lightness with visible step gaps).
#
# The sequential ramp is ordered largest-value-first, so magnitude reads as
# darker on the light surface and lighter on the dark one.
_PALETTE: Dict[str, Dict[str, Any]] = {
    "light": {
        "sequential": ["#0a544d", "#0c7a70", "#12a596", "#39c9b6"],
        "categorical": ["#0d9488", "#eb6834"],
        "grid": "#e2e8f0",
        "text": "#0f172a",
        "muted": "#64748b",
    },
    "dark": {
        "sequential": ["#4fd6c4", "#1cb3a2", "#0e8578", "#0b5c53"],
        "categorical": ["#17a897", "#e06a30"],
        "grid": "#334155",
        "text": "#e2e8f0",
        "muted": "#94a3b8",
    },
}


def _theme_mode() -> str:
    """
    Which chart palette to draw with: "light" or "dark".

    Streamlit resolves the viewer's theme server-side, but which attribute
    carries it has moved between releases, so both known spellings are tried
    before defaulting to light.
    """
    try:
        theme = getattr(st, "context", None)
        theme_type = getattr(getattr(theme, "theme", None), "type", None)
        if theme_type:
            return "dark" if str(theme_type).lower() == "dark" else "light"
    except Exception:
        pass

    try:
        base = st.get_option("theme.base")
        if base:
            return "dark" if str(base).lower() == "dark" else "light"
    except Exception:
        pass

    return "light"


def _palette() -> Dict[str, Any]:
    """The chart palette for the viewer's current theme."""
    return _PALETTE[_theme_mode()]


# ── Data access ──────────────────────────────────────────────────────────────
# `database.analytics` is the module this dashboard is meant to read; the
# fallbacks below keep it working until that module lands, and are a safety net
# afterwards if a handler is renamed.
_ANALYTICS_MODULE = "database.analytics"


def _analytics_attr(*names: str) -> Callable[..., Any] | None:
    """
    Returns the first of `names` that exists as a callable on
    `database.analytics`, or None when the module or all of the names are absent.

    Several spellings are accepted per lookup because this UI is written
    against a module being built in parallel; the alternatives are the names
    the same figure plausibly carries.
    """
    try:
        module = importlib.import_module(_ANALYTICS_MODULE)
    except Exception:
        return None

    for name in names:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    return None


def analytics_module_available() -> bool:
    """
    True when `database.analytics` actually serves this dashboard's figures.

    Deliberately stricter than "the module imports". `database.analytics` now
    exists, but it exposes a different set of handlers than the ones read here
    (get_system_health_metrics, get_feedback_satisfaction_rate, and the daily
    active user / top topic series), so every fetch below still resolves to
    `database.feedback`. Reporting the module as the source merely because it
    is importable would put a false attribution in the footer.
    """
    return _analytics_attr("get_latency_summary", "latency_summary") is not None


def _since_timestamp(hours: int) -> str:
    """ISO-8601 UTC timestamp `hours` ago, the cutoff every window query uses."""
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_latency_summary(hours: int) -> Dict[str, Any]:
    """
    Aggregated latency and query counts for the last `hours` hours.

    Returns the dict shape documented by database.feedback.get_latency_summary:
    avg/p95/max total_ms, per-stage averages, total_queries and failed_queries.

    Raises whatever the underlying handler raises — the caller decides how a
    failure is shown.
    """
    handler = _analytics_attr("get_latency_summary", "latency_summary")
    if handler is None:
        from database.feedback import get_latency_summary as handler  # type: ignore[no-redef]

    return handler(since_hours=hours) or {}


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_slow_queries(threshold_ms: float, limit: int = ROW_LIMIT) -> List[Dict[str, Any]]:
    """system_metrics rows slower than `threshold_ms`, slowest first."""
    handler = _analytics_attr("list_slow_queries", "get_slow_queries")
    if handler is None:
        from database.feedback import list_slow_queries as handler  # type: ignore[no-redef]

    return handler(threshold_ms=threshold_ms, limit=limit) or []


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_failed_queries(limit: int = ROW_LIMIT) -> List[Dict[str, Any]]:
    """system_metrics rows that failed or timed out, most recent first."""
    handler = _analytics_attr("list_failed_queries", "get_failed_queries")
    if handler is None:
        from database.feedback import list_failed_queries as handler  # type: ignore[no-redef]

    return handler(limit=limit) or []


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def fetch_feedback_totals(hours: int) -> Dict[str, Any]:
    """
    Site-wide upvote/downvote counts, plus the most recent downvote comments.

    Returns:
        Dict with keys: upvotes, downvotes, total, comments (list of
        {vote, comment, created_at} dicts, newest first).

    `database.feedback` aggregates votes per message, per session and per user
    but never across the whole deployment, which is the only figure an admin
    dashboard wants. So when `database.analytics` does not supply it, this
    falls back to reading chat_feedback directly — a stopgap that should be
    deleted the moment that module exposes the aggregate.
    """
    handler = _analytics_attr(
        "get_feedback_totals", "get_feedback_summary_all", "get_vote_summary"
    )
    if handler is not None:
        totals = handler(since_hours=hours) or {}
        totals.setdefault("comments", [])
        return totals

    from database.supabase_client import get_supabase_client

    client = get_supabase_client()
    response = (
        client.table("chat_feedback")
        .select("vote, comment, created_at")
        .gte("created_at", _since_timestamp(hours))
        .order("created_at", desc=True)
        .limit(ROW_LIMIT)
        .execute()
    )
    rows: List[Dict[str, Any]] = response.data or []

    upvotes = sum(1 for row in rows if row.get("vote") == "upvote")
    downvotes = sum(1 for row in rows if row.get("vote") == "downvote")

    return {
        "upvotes": upvotes,
        "downvotes": downvotes,
        "total": upvotes + downvotes,
        "comments": [row for row in rows if (row.get("comment") or "").strip()],
    }


def _safe(fetch: Callable[[], Any], default: Any) -> Tuple[Any, str | None]:
    """
    Runs one fetch, returning (value, error_message).

    Every panel goes through this: a dashboard whose Supabase connection is
    down should say so once per panel and still render the panels that do not
    need it, rather than raising out of render_analytics_component().
    """
    try:
        return fetch(), None
    except Exception as exc:
        print(f"[analytics] fetch failed: {exc}")
        return default, str(exc)


# ── Formatting ───────────────────────────────────────────────────────────────
def _number(value: Any, default: Any = 0.0) -> Any:
    """
    Coerces a metric to float, tolerating None and non-numeric junk.

    `default` is returned unchanged for anything uncoercible, so a caller that
    needs to tell "missing" from "zero" can pass a sentinel instead of 0.0.
    """
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return default if result != result else result  # NaN -> default


def format_ms(value: Any) -> str:
    """
    Renders a millisecond figure at a readable magnitude.

    Under a second it stays in milliseconds, where a field worker's patience is
    actually measured; above it, seconds with one decimal.

    A missing or unparseable figure renders as an em-dash rather than as
    "0 ms" — a NULL stage timing means the stage was not measured, and showing
    it as zero would read as "this stage was instant".
    """
    missing = object()
    ms = _number(value, default=missing)  # type: ignore[arg-type]
    if ms is missing:
        return t("analytics.kpi.none")

    if ms >= 1000:
        return t("analytics.seconds", value=f"{ms / 1000:.1f}")
    return t("analytics.millis", value=f"{ms:.0f}")


def _percent(part: float, whole: float) -> float | None:
    """Percentage of `whole` that `part` represents, or None when whole is 0."""
    if whole <= 0:
        return None
    return max(0.0, min(100.0, (part / whole) * 100.0))


def _window_label(hours: int) -> str:
    """Localized name for a lookback window, e.g. 168 -> 'Last 7 days'."""
    return t(f"analytics.window.{hours}")


def _relative_time(value: Any) -> str:
    """Formats an ISO timestamp as a short 'x min ago', falling back to raw text."""
    if not value:
        return "—"
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return str(value)

    delta = datetime.now(timezone.utc) - stamp
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return t("history.just_now")
    if minutes < 60:
        return t("history.minutes_ago", count=minutes)
    if minutes < 60 * 24:
        return t("history.hours_ago", count=minutes // 60)
    return t("history.days_ago", count=minutes // (60 * 24))


# ── Stat tiles & meter ───────────────────────────────────────────────────────
def _stat_tile(label: str, value: str, sub: str = "", help_text: str = "") -> str:
    """
    One KPI tile: a label, a large value, and an optional supporting line.

    A single current number is a stat tile, not a one-bar chart — the value is
    the whole message, and a bar would only add an axis to read it against.
    """
    import html as _html

    sub_html = f'<div class="csa-stat-sub">{_html.escape(sub)}</div>' if sub else ""
    title = f' title="{_html.escape(help_text)}"' if help_text else ""
    return f"""
    <div class="csa-card csa-stat"{title}>
        <div class="csa-stat-label">{_html.escape(label)}</div>
        <div class="csa-stat-value">{_html.escape(value)}</div>
        {sub_html}
    </div>
    """


def _meter(percent: float | None, caption: str) -> str:
    """
    A single ratio against its limit, drawn as a filled track.

    Deliberately one hue on a neutral track rather than a two-color split:
    "helpful vs not helpful" invites a green/red pair, and green against red is
    the one pair a deuteranopic reader cannot separate. The percentage and the
    counts beside it carry the reading instead.
    """
    import html as _html

    if percent is None:
        return f'<div class="csa-muted">{_html.escape(caption)}</div>'

    return f"""
    <div class="csa-meter">
        <div class="csa-meter-track">
            <div class="csa-meter-fill" style="width: {percent:.1f}%;"></div>
        </div>
        <div class="csa-meter-caption">{_html.escape(caption)}</div>
    </div>
    """


# ── Charts ───────────────────────────────────────────────────────────────────
def _chart_base(source: Any) -> Any:
    """Applies the shared axis, grid and font treatment to a chart."""
    palette = _palette()
    return (
        source.configure_view(strokeWidth=0)
        .configure_axis(
            grid=False,
            domainColor=palette["grid"],
            tickColor=palette["grid"],
            labelColor=palette["muted"],
            titleColor=palette["muted"],
            labelFontSize=12,
            titleFontSize=11,
        )
        .configure_legend(
            labelColor=palette["text"],
            titleColor=palette["muted"],
            labelFontSize=12,
            titleFontSize=11,
            orient="top",
            direction="horizontal",
        )
    )


def _stage_breakdown_chart(rows: List[Dict[str, Any]]) -> Any:
    """
    Horizontal bars of average milliseconds per pipeline stage, longest first.

    Magnitude comparison, so the color job is sequential: one hue, more-is-
    darker (more-is-lighter on the dark surface). Every bar is direct-labelled,
    which is what makes the ranking readable without consulting a legend.
    """
    palette = _palette()
    frame = pd.DataFrame(rows)

    bars = (
        alt.Chart(frame)
        .mark_bar(cornerRadiusEnd=4, height=22)
        .encode(
            y=alt.Y("stage:N", sort=None, title=None),
            x=alt.X("ms:Q", title=t("analytics.col.ms"), axis=alt.Axis(grid=False)),
            color=alt.Color(
                "stage:N",
                sort=None,
                scale=alt.Scale(
                    domain=[row["stage"] for row in rows],
                    range=palette["sequential"][: len(rows)],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("stage:N", title=t("analytics.col.stage")),
                alt.Tooltip("label:N", title=t("analytics.col.ms")),
                alt.Tooltip("share:N", title=t("analytics.col.share")),
            ],
        )
    )

    labels = bars.mark_text(
        align="left", baseline="middle", dx=6, fontSize=12, color=palette["text"]
    ).encode(text="label:N", color=alt.value(palette["text"]))

    return _chart_base((bars + labels).properties(height=max(120, 34 * len(rows))))


def _window_latency_chart(rows: List[Dict[str, Any]]) -> Any:
    """
    Average and 95th-percentile response time across the lookback windows.

    Two series that share a unit, so they share one axis — never a second
    y-scale. Identity is carried by a legend plus the direct labels on every
    bar, so the two validated categorical steps are reinforcement rather than
    the only signal.
    """
    palette = _palette()
    frame = pd.DataFrame(rows)

    # Window order comes from the data, which _window_rows() emits shortest
    # window first; dict.fromkeys dedupes without disturbing that order.
    windows = list(dict.fromkeys(row["window"] for row in rows))
    series = [t("analytics.series.avg"), t("analytics.series.p95")]

    bars = (
        alt.Chart(frame)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("window:N", sort=windows, title=None, axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset("metric:N", sort=series),
            y=alt.Y("ms:Q", title=t("analytics.col.ms")),
            color=alt.Color(
                "metric:N",
                sort=series,
                scale=alt.Scale(domain=series, range=palette["categorical"]),
                title=None,
            ),
            tooltip=[
                alt.Tooltip("window:N", title=t("analytics.col.window")),
                alt.Tooltip("metric:N", title=t("analytics.col.metric")),
                alt.Tooltip("label:N", title=t("analytics.col.ms")),
            ],
        )
    )

    labels = bars.mark_text(
        baseline="bottom", dy=-4, fontSize=11, color=palette["text"]
    ).encode(text="label:N", color=alt.value(palette["muted"]))

    return _chart_base((bars + labels).properties(height=260))


def _session_stage_chart(rows: List[Dict[str, Any]]) -> Any:
    """Average milliseconds per timed operation in this browser process."""
    palette = _palette()
    frame = pd.DataFrame(rows)

    bars = (
        alt.Chart(frame)
        .mark_bar(cornerRadiusEnd=4, height=20)
        .encode(
            y=alt.Y("operation:N", sort=None, title=None),
            x=alt.X("ms:Q", title=t("analytics.col.avg_ms")),
            color=alt.value(palette["sequential"][1]),
            tooltip=[
                alt.Tooltip("operation:N", title=t("analytics.col.operation")),
                alt.Tooltip("label:N", title=t("analytics.col.avg_ms")),
                alt.Tooltip("calls:Q", title=t("analytics.col.calls")),
            ],
        )
    )

    labels = bars.mark_text(
        align="left", baseline="middle", dx=6, fontSize=12
    ).encode(text="label:N", color=alt.value(palette["text"]))

    return _chart_base((bars + labels).properties(height=max(120, 30 * len(rows))))


def _render_chart(chart_rows: List[Dict[str, Any]], builder: Callable[[List[Dict[str, Any]]], Any],
                  table_columns: Dict[str, str]) -> None:
    """
    Draws one chart with its data table underneath.

    The table is not a fallback — it ships with every chart, so a reading that
    depends on comparing two bar lengths (or two colors) is always available as
    plain numbers as well.
    """
    if CHARTS_AVAILABLE:
        st.altair_chart(builder(chart_rows), use_container_width=True)

    with st.expander(t("analytics.table.show"), expanded=not CHARTS_AVAILABLE):
        st.dataframe(
            _table_frame(chart_rows, table_columns),
            use_container_width=True,
            hide_index=True,
        )


def _table_frame(rows: List[Dict[str, Any]], columns: Dict[str, str]) -> Any:
    """
    Projects raw rows onto the localized columns a table should show.

    Returns a DataFrame when pandas is available and a list of dicts otherwise;
    st.dataframe accepts both.
    """
    projected = [
        {label: row.get(key) for key, label in columns.items()} for row in rows
    ]
    return pd.DataFrame(projected) if CHARTS_AVAILABLE else projected


# ── Panels ───────────────────────────────────────────────────────────────────
def _render_controls() -> Tuple[int, float]:
    """
    The filter row: lookback window, slow-query threshold, and refresh.

    Filters sit in one row above every panel rather than beside the chart each
    one happens to affect, so it is obvious that they scope the whole page.
    """
    window_col, threshold_col, refresh_col = st.columns([2, 2, 1.2])

    with window_col:
        hours = st.selectbox(
            t("analytics.window_label"),
            options=list(WINDOW_HOURS),
            index=list(WINDOW_HOURS).index(
                st.session_state.get(WINDOW_STATE_KEY, DEFAULT_WINDOW_HOURS)
            ),
            format_func=_window_label,
            key=WINDOW_STATE_KEY,
        )

    with threshold_col:
        threshold = st.number_input(
            t("analytics.slow.threshold_label"),
            min_value=100.0,
            max_value=60000.0,
            step=500.0,
            value=float(st.session_state.get(THRESHOLD_STATE_KEY, DEFAULT_SLOW_THRESHOLD_MS)),
            key=THRESHOLD_STATE_KEY,
            help=t("analytics.slow.threshold_help"),
        )

    with refresh_col:
        # Vertical padding so the button's baseline lines up with the inputs
        # beside it rather than with their labels.
        st.markdown('<div class="csa-control-spacer"></div>', unsafe_allow_html=True)
        if st.button(
            t("analytics.refresh"),
            key="csa_analytics_refresh",
            help=t("analytics.refresh_help"),
            use_container_width=True,
        ):
            fetch_latency_summary.clear()
            fetch_slow_queries.clear()
            fetch_failed_queries.clear()
            fetch_feedback_totals.clear()
            st.rerun()

    return int(hours), float(threshold)


def _render_kpi_row(summary: Dict[str, Any], feedback: Dict[str, Any], hours: int) -> None:
    """The four headline numbers, as stat tiles rather than a chart."""
    total_queries = int(_number(summary.get("total_queries")))
    failed_queries = int(_number(summary.get("failed_queries")))

    success_rate = _percent(total_queries - failed_queries, total_queries)
    upvotes = int(_number(feedback.get("upvotes")))
    downvotes = int(_number(feedback.get("downvotes")))
    helpful_rate = _percent(upvotes, upvotes + downvotes)

    # Throughput rather than a second copy of the failure count — the tile to
    # its right already reports that, and load is what the volume tile is for.
    per_hour = (total_queries / hours) if hours else 0.0

    dash = t("analytics.kpi.none")
    tiles = [
        _stat_tile(
            t("analytics.kpi.queries"),
            f"{total_queries:,}",
            t("analytics.kpi.queries_sub", rate=f"{per_hour:,.1f}"),
            t("analytics.kpi.queries_help"),
        ),
        _stat_tile(
            t("analytics.kpi.latency"),
            # Raw values, not coerced ones: format_ms renders an unmeasured
            # stage as an em-dash, where _number() would report it as 0 ms.
            format_ms(summary.get("avg_total_ms")) if total_queries else dash,
            t(
                "analytics.kpi.latency_sub",
                p95=format_ms(summary.get("p95_total_ms")),
                max=format_ms(summary.get("max_total_ms")),
            )
            if total_queries
            else "",
            t("analytics.kpi.latency_help"),
        ),
        _stat_tile(
            t("analytics.kpi.success"),
            f"{success_rate:.0f}%" if success_rate is not None else dash,
            t("analytics.kpi.success_sub", failed=failed_queries),
            t("analytics.kpi.success_help"),
        ),
        _stat_tile(
            t("analytics.kpi.helpful"),
            f"{helpful_rate:.0f}%" if helpful_rate is not None else dash,
            t("analytics.kpi.helpful_sub", up=upvotes, down=downvotes),
            t("analytics.kpi.helpful_help"),
        ),
    ]

    for column, tile in zip(st.columns(4), tiles):
        with column:
            st.markdown(tile, unsafe_allow_html=True)


def _stage_rows(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Average milliseconds per pipeline stage, longest first.

    "Other" is whatever the total does not account for — reranking, conflict
    detection, and the gaps between the timed stages. It is clamped at zero:
    the stage averages and the total average are computed over independent row
    sets, so a stage that is NULL on some rows can make the parts sum past the
    whole, and a negative bar would be a rendering of that artifact rather than
    of anything real.
    """
    embedding = _number(summary.get("avg_embedding_ms"))
    retrieval = _number(summary.get("avg_retrieval_ms"))
    llm = _number(summary.get("avg_llm_ms"))
    total = _number(summary.get("avg_total_ms"))
    other = max(0.0, total - (embedding + retrieval + llm))

    stages = [
        (t("analytics.stage.embedding"), embedding),
        (t("analytics.stage.retrieval"), retrieval),
        (t("analytics.stage.llm"), llm),
        (t("analytics.stage.other"), other),
    ]
    stages.sort(key=lambda pair: pair[1], reverse=True)

    denominator = sum(value for _, value in stages)
    rows: List[Dict[str, Any]] = []
    for stage, value in stages:
        share = _percent(value, denominator)
        rows.append(
            {
                "stage": stage,
                "ms": round(value, 1),
                "label": format_ms(value),
                "share": f"{share:.0f}%" if share is not None else "—",
            }
        )
    return rows


def _render_stage_breakdown(summary: Dict[str, Any]) -> None:
    """Panel 2: where the time goes inside one query."""
    st.markdown(f"#### {t('analytics.breakdown.heading')}")

    total_queries = int(_number(summary.get("total_queries")))
    if not total_queries:
        st.caption(t("analytics.no_data"))
        return

    st.caption(t("analytics.breakdown.caption", count=f"{total_queries:,}"))
    _render_chart(
        _stage_rows(summary),
        _stage_breakdown_chart,
        {
            "stage": t("analytics.col.stage"),
            "label": t("analytics.col.ms"),
            "share": t("analytics.col.share"),
        },
    )
    st.caption(t("analytics.stage.other_help"))


def _window_rows() -> Tuple[List[Dict[str, Any]], str | None]:
    """
    Average and p95 response time for every lookback window.

    One summary call per window. They are cached and cheap, and each window is
    cumulative — which the caption says out loud, because a reader who assumes
    these are per-period buckets would read the 7-day bar as a quiet week.
    """
    rows: List[Dict[str, Any]] = []
    error: str | None = None

    for hours in WINDOW_HOURS:
        summary, failure = _safe(lambda h=hours: fetch_latency_summary(h), {})
        if failure:
            error = failure
            continue
        if not int(_number(summary.get("total_queries"))):
            continue

        label = _window_label(hours)
        for metric_key, series_key in (
            ("avg_total_ms", "analytics.series.avg"),
            ("p95_total_ms", "analytics.series.p95"),
        ):
            value = _number(summary.get(metric_key))
            rows.append(
                {
                    "window": label,
                    "metric": t(series_key),
                    "ms": round(value, 1),
                    "label": format_ms(value),
                }
            )

    return rows, error


def _render_window_latency() -> None:
    """Panel 3: is it getting slower?"""
    st.markdown(f"#### {t('analytics.windows.heading')}")

    rows, error = _window_rows()
    if not rows:
        st.caption(t("analytics.unavailable", error=error) if error else t("analytics.no_data"))
        return

    st.caption(t("analytics.windows.caption"))
    _render_chart(
        rows,
        _window_latency_chart,
        {
            "window": t("analytics.col.window"),
            "metric": t("analytics.col.metric"),
            "label": t("analytics.col.ms"),
        },
    )


def _render_answer_quality(feedback: Dict[str, Any], error: str | None) -> None:
    """Panel 4: the helpful rate, and what the downvotes actually said."""
    st.markdown(f"#### {t('analytics.quality.heading')}")

    if error:
        st.caption(t("analytics.unavailable", error=error))
        return

    upvotes = int(_number(feedback.get("upvotes")))
    downvotes = int(_number(feedback.get("downvotes")))
    rated = upvotes + downvotes

    if not rated:
        st.caption(t("analytics.quality.none"))
        return

    rate = _percent(upvotes, rated)
    st.caption(t("analytics.quality.caption", count=rated))
    st.markdown(
        _meter(
            rate,
            t(
                "analytics.quality.summary",
                percent=f"{rate:.0f}" if rate is not None else "0",
                helpful=upvotes,
                unhelpful=downvotes,
            ),
        ),
        unsafe_allow_html=True,
    )

    comments = list(feedback.get("comments") or [])
    st.markdown(f"##### {t('analytics.comments.heading')}")
    if not comments:
        st.caption(t("analytics.comments.none"))
        return

    st.dataframe(
        _table_frame(
            [
                {
                    "when": _relative_time(row.get("created_at")),
                    "vote": row.get("vote"),
                    "comment": row.get("comment"),
                }
                for row in comments[:20]
            ],
            {
                "when": t("analytics.col.when"),
                "vote": t("analytics.col.vote"),
                "comment": t("analytics.col.comment"),
            },
        ),
        use_container_width=True,
        hide_index=True,
    )


def _render_query_tables(threshold_ms: float) -> None:
    """Panels 5 and 6: the slowest queries, and the ones that never finished."""
    slow_col, failed_col = st.columns(2)

    with slow_col:
        st.markdown(f"#### {t('analytics.slow.heading')}")
        rows, error = _safe(lambda: fetch_slow_queries(threshold_ms), [])
        if error:
            st.caption(t("analytics.unavailable", error=error))
        elif not rows:
            st.caption(t("analytics.slow.none", threshold=f"{threshold_ms:,.0f}"))
        else:
            st.caption(t("analytics.slow.caption", threshold=f"{threshold_ms:,.0f}"))
            st.dataframe(
                _table_frame(
                    [
                        {
                            "when": _relative_time(row.get("created_at")),
                            "query_text": row.get("query_text"),
                            "total": format_ms(row.get("total_ms")),
                            "llm": format_ms(row.get("llm_ms")),
                        }
                        for row in rows
                    ],
                    {
                        "when": t("analytics.col.when"),
                        "query_text": t("analytics.col.query"),
                        "total": t("analytics.col.total"),
                        "llm": t("analytics.stage.llm"),
                    },
                ),
                use_container_width=True,
                hide_index=True,
                height=280,
            )

    with failed_col:
        st.markdown(f"#### {t('analytics.failed.heading')}")
        rows, error = _safe(fetch_failed_queries, [])
        if error:
            st.caption(t("analytics.unavailable", error=error))
        elif not rows:
            st.caption(t("analytics.failed.none"))
        else:
            st.caption(t("analytics.failed.caption", count=len(rows)))
            st.dataframe(
                _table_frame(
                    [
                        {
                            "when": _relative_time(row.get("created_at")),
                            "query_text": row.get("query_text"),
                            "status": row.get("status"),
                            "error_message": row.get("error_message"),
                        }
                        for row in rows
                    ],
                    {
                        "when": t("analytics.col.when"),
                        "query_text": t("analytics.col.query"),
                        "status": t("analytics.col.status"),
                        "error_message": t("analytics.col.error"),
                    },
                ),
                use_container_width=True,
                hide_index=True,
                height=280,
            )


def _session_rows() -> List[Dict[str, Any]]:
    """
    Average latency per timed operation in this browser process.

    database.query_logger keeps an in-memory ring of every timed pipeline step,
    so this panel works with no database at all — which makes it the one place
    to look when the panels above are reporting a connection failure.
    """
    from database.query_logger import get_recent_logs

    totals: Dict[str, List[float]] = {}
    for log in get_recent_logs(ROW_LIMIT):
        totals.setdefault(log.operation, []).append(float(log.latency_ms))

    rows = [
        {
            "operation": operation,
            "ms": round(sum(values) / len(values), 1),
            "label": format_ms(sum(values) / len(values)),
            "calls": len(values),
        }
        for operation, values in totals.items()
    ]
    rows.sort(key=lambda row: row["ms"], reverse=True)
    return rows


def _render_session_panel() -> None:
    """Panel 7: this process's own timings, available with no database."""
    st.markdown(f"#### {t('analytics.session.heading')}")

    rows, error = _safe(_session_rows, [])
    if error or not rows:
        st.caption(t("analytics.session.none"))
        return

    st.caption(t("analytics.session.caption"))
    _render_chart(
        rows,
        _session_stage_chart,
        {
            "operation": t("analytics.col.operation"),
            "label": t("analytics.col.avg_ms"),
            "calls": t("analytics.col.calls"),
        },
    )


# ── Entry point ──────────────────────────────────────────────────────────────
def render_analytics_component() -> None:
    """Renders the Admin Analytics Dashboard tab."""
    st.subheader(t("analytics.heading"))
    st.caption(t("analytics.caption"))

    hours, threshold_ms = _render_controls()

    summary, summary_error = _safe(lambda: fetch_latency_summary(hours), {})
    feedback, feedback_error = _safe(lambda: fetch_feedback_totals(hours), {})

    # One banner for a dead connection, rather than the same message repeated
    # under each of the four tiles it takes out.
    if summary_error and feedback_error:
        st.warning(t("analytics.unavailable", error=summary_error))
        st.caption(t("analytics.unavailable_hint"))
    elif summary_error:
        st.warning(t("analytics.unavailable", error=summary_error))

    _render_kpi_row(summary, feedback, hours)
    st.caption(t("analytics.window_note", window=_window_label(hours)))

    st.divider()
    breakdown_col, quality_col = st.columns([3, 2])
    with breakdown_col:
        _render_stage_breakdown(summary)
    with quality_col:
        _render_answer_quality(feedback, feedback_error)

    st.divider()
    _render_window_latency()

    st.divider()
    _render_query_tables(threshold_ms)

    st.divider()
    _render_session_panel()

    st.caption(
        t(
            "analytics.source_note",
            module=_ANALYTICS_MODULE if analytics_module_available() else "database.feedback",
            seconds=CACHE_TTL_SECONDS,
        )
    )
