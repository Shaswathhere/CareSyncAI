"""
rag/translator.py
-----------------
Multilingual query translation & localized answer chain for CareSync AI.

Architecture:
    1. detect_query_language(user_query)
       → Identifies the language of a field worker's question (e.g. "hi", "ta", "es").

    2. translate_query_to_english(user_query, source_lang)
       → Translates a non-English query into English so it can be embedded and matched
         against English source documents in the vector store.

    3. translate_answer_to_language(english_answer, target_lang)
       → Translates the grounded English LLM answer back into the field worker's language.

    4. multilingual_rag_query(user_query, target_lang)
       → End-to-end wrapper: detect → translate query → RAG pipeline → translate answer.

Language detection uses lightweight heuristics + Unicode script ranges so it works
offline without requiring an external API call. The translation steps use the Groq
LLM which is already initialised in rag/llm.py.
"""

from __future__ import annotations

import re
from typing import Dict, Any

# BCP-47 tag → human-readable name map (subset used in display)
LANGUAGE_NAMES: Dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "bn": "Bengali",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "ur": "Urdu",
    "ar": "Arabic",
    "es": "Spanish",
    "pt": "Portuguese",
    "fr": "French",
    "sw": "Swahili",
}

# Unicode block ranges for script-based heuristic detection
_SCRIPT_RANGES: list[tuple[int, int, str]] = [
    (0x0900, 0x097F, "hi"),   # Devanagari → Hindi / Marathi
    (0x0980, 0x09FF, "bn"),   # Bengali
    (0x0A00, 0x0A7F, "pa"),   # Gurmukhi → Punjabi
    (0x0A80, 0x0AFF, "gu"),   # Gujarati
    (0x0B00, 0x0B7F, "or"),   # Oriya
    (0x0B80, 0x0BFF, "ta"),   # Tamil
    (0x0C00, 0x0C7F, "te"),   # Telugu
    (0x0C80, 0x0CFF, "kn"),   # Kannada
    (0x0D00, 0x0D7F, "ml"),   # Malayalam
    (0x0600, 0x06FF, "ar"),   # Arabic (also Urdu)
    (0x0750, 0x077F, "ur"),   # Arabic supplement → Urdu
]

# Common stop-word fingerprints per language
_STOP_WORD_HINTS: Dict[str, list[str]] = {
    "es": ["qué", "cómo", "cuál", "dónde", "cuándo", "protocolo", "vacuna", "dosis", "enfermedad"],
    "fr": ["quel", "comment", "protocole", "vaccin", "dose", "maladie", "fièvre"],
    "pt": ["qual", "como", "protocolo", "vacina", "dose", "doença", "febre"],
    "sw": ["nini", "jinsi", "chanjo", "kipimo", "ugonjwa", "homa"],
}


def detect_query_language(user_query: str) -> str:
    """
    Detects the probable language of a field worker's query.

    Uses two-phase heuristics:
    1. Unicode script range scanning — reliable for Indian scripts, Arabic, etc.
    2. Stop-word pattern matching for Latin-script languages (Spanish, French, etc.).

    Falls back to "en" (English) when language is ambiguous.

    Args:
        user_query: Natural language question from field worker.

    Returns:
        BCP-47 language tag string, e.g. "hi", "ta", "es", "en".
    """
    if not user_query or not user_query.strip():
        return "en"

    # Phase 1: Script range scanning
    script_votes: Dict[str, int] = {}
    for char in user_query:
        cp = ord(char)
        for lo, hi, lang in _SCRIPT_RANGES:
            if lo <= cp <= hi:
                script_votes[lang] = script_votes.get(lang, 0) + 1
                break

    if script_votes:
        detected = max(script_votes, key=lambda k: script_votes[k])
        # Require at least 2 non-ASCII chars to be confident
        if script_votes[detected] >= 2:
            print(f"[translator] Script detection: '{detected}' (votes={script_votes})")
            return detected

    # Phase 2: Stop-word hints for Latin-script languages
    query_lower = user_query.lower()
    for lang, hints in _STOP_WORD_HINTS.items():
        for hint in hints:
            if re.search(rf'\b{re.escape(hint)}\b', query_lower):
                print(f"[translator] Stop-word hint matched: '{lang}' (trigger='{hint}')")
                return lang

    return "en"


def translate_query_to_english(user_query: str, source_lang: str = "en") -> str:
    """
    Translates a non-English field worker query into English for vector search.

    Uses the Groq LLM translation capability. If source_lang is "en" or LLM
    is unavailable, returns the original query unchanged.

    Args:
        user_query: Query text in source_lang.
        source_lang: BCP-47 tag of the source language, e.g. "hi", "ta".

    Returns:
        English translation of user_query, or original query if no translation needed.
    """
    if not user_query or not user_query.strip():
        return user_query

    if source_lang == "en":
        return user_query

    lang_name = LANGUAGE_NAMES.get(source_lang, source_lang.upper())
    prompt = (
        f"Translate the following {lang_name} public health question into clear, accurate English.\n"
        f"Return ONLY the English translation, no explanations.\n\n"
        f"{lang_name} Question: {user_query}\n\n"
        f"English Translation:"
    )

    try:
        from rag.llm import get_llm
        llm = get_llm()
        if llm is None:
            print(f"[translator] LLM unavailable — returning original query.")
            return user_query

        if hasattr(llm, "invoke"):
            from langchain_core.messages import HumanMessage
            response = llm.invoke([HumanMessage(content=prompt)])
            translated = getattr(response, "content", str(response)).strip()
        elif hasattr(llm, "generate_content"):
            response = llm.generate_content(prompt)
            translated = response.text.strip()
        else:
            return user_query

        print(f"[translator] Query translated: '{user_query}' → '{translated}'")
        return translated or user_query

    except Exception as exc:
        print(f"[translator] Translation error: {exc}. Using original query.")
        return user_query


def translate_answer_to_language(english_answer: str, target_lang: str = "en") -> str:
    """
    Translates a grounded English LLM answer into the field worker's preferred language.

    Preserves citation markers and formatting. Falls back to English if LLM is
    unavailable or translation fails.

    Args:
        english_answer: Grounded answer text in English.
        target_lang: BCP-47 tag of the target output language.

    Returns:
        Localized answer string in target_lang, or english_answer if target is "en".
    """
    if not english_answer or not english_answer.strip():
        return english_answer

    if target_lang == "en":
        return english_answer

    lang_name = LANGUAGE_NAMES.get(target_lang, target_lang.upper())
    prompt = (
        f"Translate the following public health guidance answer into {lang_name}.\n"
        f"Preserve all medical terms, citation markers (e.g. [Source 1]), and formatting.\n"
        f"Return ONLY the {lang_name} translation.\n\n"
        f"English Answer:\n{english_answer}\n\n"
        f"{lang_name} Translation:"
    )

    try:
        from rag.llm import get_llm
        llm = get_llm()
        if llm is None:
            print(f"[translator] LLM unavailable — returning English answer.")
            return english_answer

        if hasattr(llm, "invoke"):
            from langchain_core.messages import HumanMessage
            response = llm.invoke([HumanMessage(content=prompt)])
            translated = getattr(response, "content", str(response)).strip()
        elif hasattr(llm, "generate_content"):
            response = llm.generate_content(prompt)
            translated = response.text.strip()
        else:
            return english_answer

        print(f"[translator] Answer translated to {lang_name} ({len(translated)} chars).")
        return translated or english_answer

    except Exception as exc:
        print(f"[translator] Answer translation error: {exc}. Returning English answer.")
        return english_answer


def multilingual_rag_query(
    user_query: str,
    target_lang: str | None = None,
    **pipeline_kwargs: Any
) -> Dict[str, Any]:
    """
    End-to-end multilingual RAG pipeline:
    1. Auto-detect query language if target_lang not provided.
    2. Translate query to English.
    3. Run standard RAG pipeline (hybrid search → rerank → Groq) using history.
    4. Translate English answer back to field worker's language.
    5. Save original query and localized response to DB session.

    Args:
        user_query: Question in any supported language.
        target_lang: BCP-47 output language tag. If None, auto-detected from query.
        **pipeline_kwargs: Passed through to query_rag_pipeline (status_filter, date_from, session_id, etc.)

    Returns:
        Standard RAG pipeline dict with additional keys:
            - 'detected_language': BCP-47 tag of detected/specified language.
            - 'english_query': Translated English query used for retrieval.
            - 'english_answer': Original English LLM answer (before localization).
    """
    from rag.pipeline import query_rag_pipeline

    if not user_query or not user_query.strip():
        return {
            "answer": "Please enter a valid question.",
            "sources": [],
            "conflicts_detected": False,
            "conflict_warning": None,
            "detected_language": "en",
            "english_query": user_query,
            "english_answer": ""
        }

    # Step 1: Detect language
    detected_lang = target_lang or detect_query_language(user_query)

    # Step 2: Translate query to English for vector search + LLM
    english_query = translate_query_to_english(user_query, source_lang=detected_lang)

    session_id = pipeline_kwargs.get("session_id")
    save_to_db = pipeline_kwargs.get("save_to_db", True)

    # Intercept session save to ensure we save the translated localized versions instead of English
    inner_kwargs = dict(pipeline_kwargs)
    if session_id:
        inner_kwargs["save_to_db"] = False

    # Step 3: Run RAG pipeline with English query
    result = query_rag_pipeline(english_query, **inner_kwargs)

    english_answer = result.get("answer", "")

    # Step 4: Translate answer back to field worker's language
    localized_answer = translate_answer_to_language(english_answer, target_lang=detected_lang)

    result["answer"] = localized_answer
    result["detected_language"] = detected_lang
    result["english_query"] = english_query
    result["english_answer"] = english_answer

    # Step 5: Save localized conversation to DB if session is active
    if session_id and save_to_db:
        try:
            from database.conversation import get_session_messages, add_chat_message, update_session_title
            chat_history = get_session_messages(session_id)
            add_chat_message(session_id, "user", user_query)
            add_chat_message(session_id, "assistant", localized_answer, citations=result.get("sources", []))
            if len(chat_history) == 0:
                update_session_title(session_id, user_query)
        except Exception as exc:
            print(f"[translator] Failed to save localized conversation turn: {exc}")

    return result

