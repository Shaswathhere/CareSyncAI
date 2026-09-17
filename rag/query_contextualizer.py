"""
rag/query_contextualizer.py
---------------------------
History-aware query reformulator for CareSync AI.
Uses the Groq LLM to reformulate a follow-up query based on multi-turn chat history
into a self-contained, standalone question suitable for vector embedding and retrieval.
"""

from __future__ import annotations
from typing import List, Dict, Any
from rag.llm import get_llm

CONTEXTUALIZE_SYSTEM_PROMPT = """Given the following conversation history and a follow-up question, rephrase the follow-up question to be a self-contained, standalone question in English.
Do NOT answer the question. Just return the rephrased standalone question.
If the follow-up question is already self-contained or does not refer to previous context, return it exactly as it is.

Chat History:
{chat_history_text}

Follow-up Question: {user_query}
Standalone Question:"""


def reformulate_query_with_history(
    user_query: str,
    chat_history: List[Dict[str, Any]]
) -> str:
    """
    Reformulates a user's follow-up query using chat history to make it standalone.

    Args:
        user_query: The latest query from the field worker.
        chat_history: Chronological list of previous messages in the session.
                      Each dict should contain 'role' ('user' or 'assistant') and 'content'.

    Returns:
        The standalone, self-contained query.
    """
    if not chat_history:
        return user_query

    # Clean and format previous turns for the prompt (e.g. limit to last 6 messages to keep context short and relevant)
    recent_history = chat_history[-6:]
    history_lines = []
    for msg in recent_history:
        role = "User" if msg.get("role") == "user" else "Assistant"
        content = msg.get("content", "").strip()
        if content:
            history_lines.append(f"{role}: {content}")

    if not history_lines:
        return user_query

    chat_history_text = "\n".join(history_lines)
    prompt_text = CONTEXTUALIZE_SYSTEM_PROMPT.format(
        chat_history_text=chat_history_text,
        user_query=user_query
    )

    llm = get_llm()
    if llm is None:
        print("[query_contextualizer] LLM not available, returning original query.")
        return user_query

    try:
        if hasattr(llm, "invoke"):
            from langchain_core.messages import HumanMessage
            response = llm.invoke([HumanMessage(content=prompt_text)])
            rephrased = getattr(response, "content", str(response)).strip()
        elif hasattr(llm, "generate_content"):
            response = llm.generate_content(prompt_text)
            rephrased = response.text.strip()
        else:
            rephrased = user_query

        # Remove quotes if LLM added any
        rephrased = rephrased.strip("\"'")
        print(f"[query_contextualizer] Reformulated: '{user_query}' -> '{rephrased}'")
        return rephrased if rephrased else user_query

    except Exception as exc:
        print(f"[query_contextualizer] Reformulation error: {exc}. Returning original query.")
        return user_query
