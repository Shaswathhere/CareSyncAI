"""
utils/user.py
--------------
Who the database handlers should attribute this browser session to.

CareSync AI has no sign-in yet, but database.conversation, database.feedback,
and database.audio all key their rows on a user_id. This module supplies one:

    * config.CARESYNC_USER_ID, when the deployment pins a shared device
      (a clinic tablet, a demo laptop) to a fixed identity — its chat history
      then survives a browser refresh.
    * otherwise a random id minted once per browser session, so two field
      workers on the same server never see each other's history or votes.

The id is deliberately opaque. Nothing here is authentication — it scopes
records, it does not protect them.
"""

from __future__ import annotations

import uuid

import streamlit as st

from config import CARESYNC_USER_ID

# Session key holding the minted per-browser id.
USER_ID_STATE_KEY = "caresync_user_id"

# Prefix on minted ids, so an anonymous browser session is distinguishable
# from a pinned CARESYNC_USER_ID when reading the tables directly.
_ANON_PREFIX = "anon-"


def current_user_id() -> str:
    """
    Returns the user id every database handler should be called with.

    Falls back to a fixed anonymous id outside a Streamlit script run (tests,
    imports) so callers never have to guard the lookup.
    """
    pinned = (CARESYNC_USER_ID or "").strip()
    if pinned:
        return pinned

    try:
        user_id = st.session_state.get(USER_ID_STATE_KEY)
        if not user_id:
            user_id = f"{_ANON_PREFIX}{uuid.uuid4()}"
            st.session_state[USER_ID_STATE_KEY] = user_id
        return user_id
    except Exception:  # No Streamlit session (e.g. imported by a test).
        return f"{_ANON_PREFIX}local"


def is_anonymous() -> bool:
    """True when the id was minted for this browser session rather than pinned."""
    return current_user_id().startswith(_ANON_PREFIX)
