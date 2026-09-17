"""
rag/llm.py
----------
Groq LLM chain and grounding prompt generator for CareSync AI.
Enforces strict answer grounding in retrieved public-health documents to prevent hallucination.
Includes version comparison prompts for protocol change detection between superseded and active guidelines.
Includes scope-refusal guardrails to reject out-of-scope questions (patient diagnosis, prescriptions,
general chit-chat, and politically sensitive topics) before they reach the LLM.
"""

from __future__ import annotations
from typing import Optional
from config import GROQ_API_KEY, GROQ_MODEL


SAFE_FALLBACK_MESSAGE = (
    "No relevant guidance was found in the current knowledge base. "
    "Please verify with the appropriate public-health authority."
)

# Returned when the user's question is definitively out-of-scope for CareSync AI.
SCOPE_REFUSAL_MESSAGE = (
    "I'm CareSync AI — a public health guideline assistant for field workers. "
    "I can only answer questions about official public-health protocols, disease surveillance, "
    "vaccination schedules, and related field-work guidance.\n\n"
    "I'm not able to:\n"
    "- Diagnose individual patients or recommend personal treatment plans\n"
    "- Prescribe medications or advise on drug dosages for specific patients\n"
    "- Engage in general conversation unrelated to public health\n"
    "- Comment on political, religious, or personally sensitive topics\n\n"
    "Please consult a licensed medical professional for clinical advice."
)

# ── Scope Refusal Patterns ────────────────────────────────────────────────────
# These keyword clusters detect off-topic or dangerous requests that must never
# reach the LLM, regardless of what is in the retrieved context.

_OUT_OF_SCOPE_PATTERNS = [
    # Patient-level clinical diagnosis
    ["diagnose me", "do i have", "am i sick", "what disease do i have",
     "is this cancer", "is this serious", "what's wrong with me"],
    # Prescription / personal drug advice
    ["prescribe", "what medication should i take", "my dosage", "can i take",
     "drug interaction", "side effects for me", "is it safe for me to take"],
    # Chit-chat & off-topic
    ["tell me a joke", "what is the weather", "who are you", "what can you do",
     "play music", "write a poem", "write code for me", "write an essay",
     "what is the stock price", "sports", "movie"],
    # Politically or personally sensitive
    ["politics", "election", "abortion", "gun control", "religion",
     "which god", "is god real"],
]


def is_out_of_scope(user_query: str) -> bool:
    """
    Pre-screens a user query for out-of-scope topics before it reaches the LLM.

    Uses a fast keyword-cluster scan to detect:
    - Requests for personal patient diagnosis
    - Prescription or personal medication advice
    - General chit-chat unrelated to public health
    - Politically or personally sensitive topics

    Args:
        user_query: Raw question text from the field worker.

    Returns:
        True if the query is definitively out-of-scope and must be refused.
        False if the query could plausibly relate to public-health guidelines.
    """
    lowered = user_query.lower().strip()
    for cluster in _OUT_OF_SCOPE_PATTERNS:
        if any(pattern in lowered for pattern in cluster):
            print(f"[llm] Scope refusal triggered for query: {user_query!r}")
            return True
    return False


SYSTEM_GROUNDING_PROMPT = """You are CareSync AI, an AI guidance assistant for public health field workers.
Your primary role is to answer field questions based ONLY on official active public-health document guidelines.

STRICT GROUNDING RULES:
1. Rely ONLY on the clear facts provided in the Context below.
2. Do NOT use external or background knowledge.
3. If the Context does NOT contain sufficient details to answer the user's question, respond EXACTLY with:
   "No relevant guidance was found in the current knowledge base. Please verify with the appropriate public-health authority."
4. Be direct, clear, professional, and field-worker-friendly.
5. SCOPE ENFORCEMENT: You are STRICTLY limited to public health, disease surveillance, vaccination, and
   field-work protocols. If the user asks you to diagnose a patient, prescribe medication, engage in
   general chit-chat, or comment on politics/religion, you MUST respond EXACTLY with:
   "I'm CareSync AI — I can only answer questions about official public-health guidelines. Please consult
   a licensed medical professional for personal clinical advice."

Context:
{context}

User Question:
{query}

Answer:"""

SYSTEM_VERSION_COMPARISON_PROMPT = """You are CareSync AI, an AI guidance assistant for public health field workers.
Your task is to compare protocol changes between previous (SUPERSEDED) and current active (ACTIVE) guideline versions.

VERSION COMPARISON RULES:
1. Clearly state what changed, what was added/updated, and what the CURRENT ACTIVE guidance requires.
2. Highlight any superseded protocol steps so field workers avoid relying on outdated guidelines.
3. Cite the exact document versions (e.g., v1 vs v2) and page numbers for each point.
4. Rely ONLY on the provided Context below.

Context:
{context}

User Question:
{query}

Version Comparison Summary:"""


def get_llm():
    """Initializes and returns the Groq LLM client with automatic model fallback."""
    if not GROQ_API_KEY:
        print("[llm] GROQ_API_KEY not set — LLM disabled.")
        return None

    candidate_models = [GROQ_MODEL, "qwen/qwen3.8-27b", "openai/gpt-oss-120b", "groq/compound-mini"]
    # De-duplicate while preserving order
    seen = set()
    models_to_try = [m for m in candidate_models if m and not (m in seen or seen.add(m))]

    from langchain_groq import ChatGroq

    for model_name in models_to_try:
        try:
            return ChatGroq(
                model=model_name,
                api_key=GROQ_API_KEY,
                temperature=0.1,
            )
        except Exception as exc:
            print(f"[llm] Failed to initialize Groq model {model_name}: {exc}")

    return None


def generate_grounded_answer(context: str, user_query: str) -> str:
    """
    Generates a grounded LLM answer using Groq based on retrieved document context.

    Applies a scope-refusal pre-filter before calling the LLM. If the query is
    detected as out-of-scope (patient diagnosis, prescriptions, chit-chat, politics),
    returns SCOPE_REFUSAL_MESSAGE immediately without calling the LLM.

    Args:
        context: Formatted string of retrieved passage chunks.
        user_query: Question asked by the field worker.

    Returns:
        Generated answer string, or a refusal/fallback message if appropriate.
    """
    # Scope-refusal pre-filter — blocks off-topic queries before hitting the LLM
    if is_out_of_scope(user_query):
        return SCOPE_REFUSAL_MESSAGE

    if not context or not context.strip():
        return SAFE_FALLBACK_MESSAGE

    prompt_text = SYSTEM_GROUNDING_PROMPT.format(
        context=context,
        query=user_query
    )

    llm = get_llm()
    if llm is None:
        return (
            f"[CareSync AI Grounded Response]\nBased on active public-health guidelines:\n\n{context}"
        )

    def _extract_text(raw_content) -> str:
        """Safely extract plain text from various LLM response content formats."""
        if isinstance(raw_content, str):
            return raw_content.strip()
        # LangChain may return a list of content blocks: [{'type':'text','text':'...'}]
        if isinstance(raw_content, list):
            parts = []
            for block in raw_content:
                if isinstance(block, dict):
                    parts.append(str(block.get("text", "")))
                else:
                    parts.append(str(block))
            return " ".join(parts).strip()
        return str(raw_content).strip()

    try:
        if hasattr(llm, "invoke"):
            response = llm.invoke(prompt_text)
            content = getattr(response, "content", str(response))
            return _extract_text(content)
        elif hasattr(llm, "generate_content"):
            response = llm.generate_content(prompt_text)
            return response.text.strip()
    except Exception as exc:
        print(f"[llm] Groq LLM generation error: {exc}")
        # Try fallback model if the first choice produced a runtime error (e.g., model deprecation)
        for fallback_model in ["openai/gpt-oss-120b", "groq/compound-mini"]:
            if fallback_model != GROQ_MODEL:
                try:
                    from langchain_groq import ChatGroq
                    fallback_llm = ChatGroq(model=fallback_model, api_key=GROQ_API_KEY, temperature=0.1)
                    response = fallback_llm.invoke(prompt_text)
                    content = getattr(response, "content", str(response))
                    return _extract_text(content)
                except Exception:
                    continue

        return (
            f"Unable to generate response from Groq API at this time: {exc}. "
            f"Please check your API key or network connection.\n\nRetrieved context:\n{context[:300]}..."
        )

    return SAFE_FALLBACK_MESSAGE


def generate_version_comparison_answer(context: str, user_query: str) -> str:
    """
    Generates a multi-version comparison summary explaining protocol changes between document versions.

    Args:
        context: Formatted string of active and superseded passage chunks.
        user_query: Comparison question asked by the field worker.

    Returns:
        Generated comparison summary summary string.
    """
    if not context or not context.strip():
        return SAFE_FALLBACK_MESSAGE

    prompt_text = SYSTEM_VERSION_COMPARISON_PROMPT.format(
        context=context,
        query=user_query
    )

    llm = get_llm()
    if llm is None:
        return (
            f"[CareSync AI Version Comparison]\nComparison based on document version history:\n\n{context}"
        )

    try:
        if hasattr(llm, "invoke"):
            response = llm.invoke(prompt_text)
            content = getattr(response, "content", str(response))
            return str(content).strip()
        elif hasattr(llm, "generate_content"):
            response = llm.generate_content(prompt_text)
            return response.text.strip()
    except Exception as exc:
        print(f"[llm] Groq LLM version comparison error: {exc}")
        return (
            f"Unable to generate version comparison from Groq API at this time: {exc}.\n\nRetrieved version context:\n{context[:300]}..."
        )

    return SAFE_FALLBACK_MESSAGE
