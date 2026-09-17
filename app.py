"""
app.py
------
Main entry point for the CareSync AI Streamlit application.

Responsibilities:
    - Configure the Streamlit page (title, icon, layout).
    - Load the custom CSS theme (card shadows, dark/light accents, status tags).
    - Initialize global session_state used across all components.
    - Render the sidebar (language picker, chat history drawer, search filters),
      the header, and the tabbed navigation shell (chat, documents, upload,
      and the admin analytics dashboard).

Every label here goes through utils.i18n.t(). The language picker sits in the
sidebar, below the header in source order, but Streamlit restores widget state
before the script body runs — so the header is already in the newly chosen
language on the same rerun.
"""

import html
from pathlib import Path

import streamlit as st

from components.analytics import render_analytics_component
from components.chat import render_chat_component
from components.chat_history import render_chat_history_drawer
from components.document_list import (
    render_document_list_component,
    render_sidebar_filters,
)
from components.guidelines_admin import render_guideline_management
from components.upload import render_upload_component
from utils.i18n import render_language_selector, t

APP_DIR = Path(__file__).resolve().parent


st.set_page_config(
    page_title=t("app.page_title"),
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner=False)
def _get_css_content(css_path_str: str) -> str:
    path = Path(css_path_str)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def load_css(css_path: Path) -> None:
    """Injects a local CSS file into the page, if it exists."""
    css = _get_css_content(str(css_path))
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def init_session_state() -> None:
    """
    Initializes the global session_state keys shared across components.
    Guarded so re-runs never clobber existing state.
    """
    defaults = {
        # Chat history — list of {"role", "content", "sources"} dicts.
        "messages": [],
        # Active document inventory shown in the Documents tab and used by
        # the Upload tab to append newly indexed guidance.
        "documents": [
            {"title": "Vaccination Protocol v3", "version": "v3", "effective_date": "2026-08-08", "status": "ACTIVE"},
            {"title": "Outbreak Guidelines v2", "version": "v2", "effective_date": "2026-08-05", "status": "ACTIVE"},
            {"title": "Vaccination Protocol v2", "version": "v2", "effective_date": "2026-07-20", "status": "SUPERSEDED"},
        ],
        # True while a chat query or document upload is being processed.
        "is_loading": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


load_css(APP_DIR / "assets" / "style.css")
init_session_state()

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <div class="csa-header">
        <h1>🩺 {html.escape(t("app.title"))}</h1>
        <p>{html.escape(t("app.tagline"))}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title(t("app.sidebar_title"))
st.sidebar.caption(t("app.sidebar_caption"))
st.sidebar.divider()

# Language picker first: it owns st.session_state["app_language"], which every
# other t() call reads, so it belongs at the top of the sidebar.
render_language_selector()

st.sidebar.divider()

# Chat history drawer — rendered before the tabs so that switching sessions or
# starting a new chat has already rewritten st.session_state["messages"] by the
# time the Chat tab draws the conversation.
render_chat_history_drawer()

st.sidebar.divider()

# Advanced search filters — shared by the Documents tab (inventory filtering)
# and the Chat Assistant (retrieval narrowing). Rendered before the tabs so the
# selections are in session_state by the time either component runs.
render_sidebar_filters()

st.sidebar.divider()
st.sidebar.info(t("app.sidebar_about"))

# ── Tabbed navigation ────────────────────────────────────────────────────────
chat_tab, documents_tab, upload_tab, analytics_tab = st.tabs(
    [
        t("app.tab.chat"),
        t("app.tab.documents"),
        t("app.tab.upload"),
        t("app.tab.analytics"),
    ]
)

with chat_tab:
    render_chat_component()

with documents_tab:
    render_document_list_component()

with upload_tab:
    render_upload_component()

# Last tab: an operations view rather than a field-worker one — deliberately
# the rightmost tab, because nothing in it is needed mid-visit. Two halves:
# the analytics dashboard, which only reads, and guideline management, which
# can retire a document from retrieval and so confirms before it writes.
with analytics_tab:
    render_analytics_component()
    st.divider()
    render_guideline_management()
