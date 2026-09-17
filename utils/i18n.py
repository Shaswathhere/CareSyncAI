"""
utils/i18n.py
--------------
Runtime side of the UI localization: the active-language accessor, the t()
lookup used everywhere in components/, and the sidebar language picker.

The active language lives in st.session_state under LANGUAGE_STATE_KEY, which
is also the picker widget's key. Streamlit restores widget state before the
script body runs, so by the time app.py renders its header the new language is
already in place — one rerun re-labels the entire app, top to bottom.

Lookups degrade instead of failing: a missing key falls back to English, and
then to the key itself, so a half-translated language renders as mixed text
rather than crashing or showing blanks.
"""

from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from utils.translations import DEFAULT_LANGUAGE, LANGUAGES, TRANSLATIONS

# Session key holding the active language code; also the picker's widget key.
LANGUAGE_STATE_KEY = "app_language"


def language_options() -> List[str]:
    """Language codes in the order the picker should offer them."""
    return list(LANGUAGES)


def language_name(code: str) -> str:
    """Native display name for a language code, e.g. 'hi' -> 'हिन्दी'."""
    return LANGUAGES.get(code, code)


def current_language() -> str:
    """
    Returns the active language code, defaulting to English.

    Reads session_state defensively so helpers that call t() stay usable
    outside a Streamlit script run (tests, the export builders).
    """
    try:
        code = st.session_state.get(LANGUAGE_STATE_KEY)
    except Exception:  # No Streamlit session (e.g. imported by a test).
        return DEFAULT_LANGUAGE
    return code if code in TRANSLATIONS else DEFAULT_LANGUAGE


def set_language(code: str) -> None:
    """Sets the active language, ignoring codes with no catalog."""
    if code in TRANSLATIONS:
        st.session_state[LANGUAGE_STATE_KEY] = code


def t(key: str, language: str | None = None, **params: Any) -> str:
    """
    Looks up a UI string and fills in its placeholders.

    Args:
        key:      Catalog key, e.g. "docs.delete" (see utils/translations.py).
        language: Language code, or None for the active one. Pass "en"
                  explicitly for text that must not be localized, such as the
                  downloadable summary export.
        **params: Values for the string's {placeholders}.

    Returns:
        The translated string, falling back to English and then to `key`.
    """
    code = language if language in TRANSLATIONS else current_language()

    template = TRANSLATIONS[code].get(key)
    if template is None:
        template = TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)

    if not params:
        return template

    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        # A translation whose placeholders don't match the call — fall back to
        # English rather than showing a raw template or raising mid-render.
        english = TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key)
        try:
            return english.format(**params)
        except (KeyError, IndexError, ValueError):
            return english


def render_language_selector() -> str:
    """
    Renders the language picker at the top of the sidebar and returns the
    active language code.

    The selectbox owns LANGUAGE_STATE_KEY directly, so changing it is all the
    state change needed — Streamlit's own rerun re-renders every label.
    """
    with st.sidebar:
        st.subheader(t("lang.heading"))

        options = language_options()
        current = current_language()

        st.selectbox(
            t("lang.label"),
            options=options,
            index=options.index(current),
            key=LANGUAGE_STATE_KEY,
            format_func=language_name,
            help=t("lang.help"),
        )
        st.caption(t("lang.note"))

    return current_language()


def missing_keys(language: str) -> List[str]:
    """
    Catalog keys a language has not translated yet, for maintenance.

    Returns the English keys absent from `language`, sorted. An unknown
    language code reports every key as missing.
    """
    english = set(TRANSLATIONS[DEFAULT_LANGUAGE])
    return sorted(english - set(TRANSLATIONS.get(language, {})))


def coverage() -> Dict[str, float]:
    """Fraction of the English catalog each language currently translates."""
    total = len(TRANSLATIONS[DEFAULT_LANGUAGE]) or 1
    return {
        code: round((total - len(missing_keys(code))) / total, 4)
        for code in TRANSLATIONS
    }
