"""
components/audio_input.py
--------------------------
Voice input for the Chat tab: a microphone recorder with live playback, Groq Whisper
speech-to-text, and an editable transcript the field worker confirms before it
is asked.

The confirm step is deliberate. A field worker records in a noisy clinic, often
in Hindi or Tamil, and an STT slip in a dosage or a disease name would send the
retriever after the wrong guidance entirely — so the transcript is shown and
editable, never auto-submitted.

Every recording is logged to audio_query_log through database.audio, giving the
guidance team the transcription latency and failure rate for real field audio.
Logging is best-effort: a Supabase outage costs the metrics, not the answer.
"""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
import time
from typing import Any, Dict

import streamlit as st

from components.chat_history import active_session_id
from utils.i18n import current_language, t
from utils.user import current_user_id

# The transcript awaiting confirmation: {"digest", "text", "engine_ms"}.
# Keyed by a digest of the audio so a Streamlit rerun re-uses the transcript
# instead of paying for the same Groq call twice.
TRANSCRIPT_STATE_KEY = "voice_transcript"

# Digest of the recording whose transcription failed, so the error persists on
# screen without the Transcribe button silently retrying on every rerun.
_FAILED_KEY = "_voice_transcribe_failed"

# Bumped to reset the recorder widget after a transcript is asked, which is how
# st.audio_input is cleared — it has no programmatic clear of its own.
_WIDGET_NONCE_KEY = "_voice_widget_nonce"

# Recordings longer than this are rejected before upload. A field question is a
# sentence or two; anything longer is usually a mic left running.
_MAX_AUDIO_BYTES = 10 * 1024 * 1024

# Accepted in the fallback uploader, for browsers or Streamlit builds without
# st.audio_input.
_UPLOAD_TYPES = ["wav", "mp3", "m4a", "ogg", "webm", "flac"]

# Groq Whisper STT engine wired up. Logged as "whisper" in database.audio.VALID_STT_ENGINES.
_STT_ENGINE = "whisper"


# ── Recorder widget ──────────────────────────────────────────────────────────
def recorder_available() -> bool:
    """True on Streamlit builds that ship st.audio_input (1.41+)."""
    return callable(getattr(st, "audio_input", None))


def _widget_key(prefix: str) -> str:
    """Widget key carrying the reset nonce, so the recorder can be cleared."""
    return f"{prefix}_{st.session_state.get(_WIDGET_NONCE_KEY, 0)}"


def _reset_recorder() -> None:
    """Clears the recorded clip and any transcript hanging off it."""
    st.session_state[_WIDGET_NONCE_KEY] = st.session_state.get(_WIDGET_NONCE_KEY, 0) + 1
    st.session_state.pop(TRANSCRIPT_STATE_KEY, None)
    st.session_state.pop(_FAILED_KEY, None)


def _capture_audio() -> Any | None:
    """
    Renders the microphone recorder, or a file uploader on builds without one,
    and returns the captured audio (an UploadedFile-like object) or None.
    """
    if recorder_available():
        return st.audio_input(
            t("voice.record_label"),
            key=_widget_key("csa_voice_recorder"),
            help=t("voice.record_help"),
        )

    st.caption(t("voice.recorder_unsupported"))
    return st.file_uploader(
        t("voice.upload_label"),
        type=_UPLOAD_TYPES,
        key=_widget_key("csa_voice_upload"),
        help=t("voice.upload_help"),
    )


# ── Audio inspection ─────────────────────────────────────────────────────────
def _digest(audio_bytes: bytes) -> str:
    """Short content hash identifying one recording across reruns."""
    return hashlib.sha256(audio_bytes).hexdigest()[:16]


def _suffix(clip: Any) -> str:
    """File extension for the temp file, from the clip's name or MIME type."""
    name = getattr(clip, "name", "") or ""
    if "." in name:
        return "." + name.rsplit(".", 1)[-1].lower()

    mime = (getattr(clip, "type", "") or "").lower()
    return "." + mime.rsplit("/", 1)[-1] if "/" in mime else ".wav"


def _wav_duration_ms(audio_bytes: bytes) -> int | None:
    """
    Duration of a PCM WAV clip in milliseconds, or None if it isn't one.

    st.audio_input hands back WAV, so this covers the recorder path; uploaded
    MP3/M4A clips are logged without a duration rather than pulling in a
    decoder just to fill one analytics column.
    """
    if len(audio_bytes) < 44 or audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        return None

    try:
        byte_rate = struct.unpack_from("<I", audio_bytes, 28)[0]
        data_size = struct.unpack_from("<I", audio_bytes, 40)[0]
    except struct.error:
        return None

    if byte_rate <= 0:
        return None
    return int((min(data_size, len(audio_bytes) - 44) / byte_rate) * 1000)


# ── Transcription ────────────────────────────────────────────────────────────
def _log_start(audio_bytes: bytes, clip: Any) -> str | None:
    """Opens a pending audio_query_log row, or None if logging isn't possible."""
    try:
        from database.audio import log_audio_query

        record = log_audio_query(
            user_id=current_user_id(),
            language=current_language(),
            session_id=active_session_id(),
            audio_file_ref=getattr(clip, "name", None),
            audio_duration_ms=_wav_duration_ms(audio_bytes),
        )
        return record.get("id")
    except Exception as exc:
        print(f"[audio_input] log_audio_query failed, continuing unlogged: {exc}")
        return None


def _log_success(audio_query_id: str | None, transcript: str, elapsed_ms: int) -> None:
    """Closes the log row with the transcript and how long the engine took."""
    if not audio_query_id:
        return
    try:
        from database.audio import insert_transcription_audit, update_audio_query_transcription

        update_audio_query_transcription(
            audio_query_id=audio_query_id,
            transcription=transcript,
            transcription_ms=elapsed_ms,
        )
        insert_transcription_audit(
            audio_query_id=audio_query_id,
            raw_transcript=transcript,
            stt_engine=_STT_ENGINE,
        )
    except Exception as exc:
        print(f"[audio_input] transcription logging failed: {exc}")


def _log_failure(audio_query_id: str | None, error: str) -> None:
    """Marks the log row failed so the failure rate stays honest."""
    if not audio_query_id:
        return
    try:
        from database.audio import fail_audio_query

        fail_audio_query(audio_query_id=audio_query_id, error_message=error)
    except Exception as exc:
        print(f"[audio_input] fail_audio_query failed: {exc}")


def _transcribe(audio_bytes: bytes, clip: Any) -> Dict[str, Any]:
    """
    Runs one recording through Groq Whisper STT, logging the attempt either way.

    Returns:
        {"text": transcript, "engine_ms": int} on success, or
        {"error": message} when transcription failed.
    """
    audio_query_id = _log_start(audio_bytes, clip)

    handle = tempfile.NamedTemporaryFile(suffix=_suffix(clip), delete=False)
    try:
        handle.write(audio_bytes)
        handle.close()

        from rag.transcriber import transcribe_audio_groq

        started = time.perf_counter()
        transcript = (transcribe_audio_groq(handle.name) or "").strip()
        elapsed_ms = int((time.perf_counter() - started) * 1000)

        if not transcript:
            _log_failure(audio_query_id, "Empty transcript returned by the STT engine.")
            return {"error": t("voice.empty_transcript")}

        _log_success(audio_query_id, transcript, elapsed_ms)
        return {"text": transcript, "engine_ms": elapsed_ms}

    except Exception as exc:
        _log_failure(audio_query_id, str(exc)[:500])
        print(f"[audio_input] transcription failed: {exc}")
        return {"error": t("voice.failed", error=exc)}

    finally:
        # Windows will not unlink a file that is still open, so close before
        # removing — close() is idempotent, so the success path is unaffected.
        try:
            handle.close()
            os.unlink(handle.name)
        except OSError as exc:
            print(f"[audio_input] could not remove temp file {handle.name}: {exc}")


# ── Transcript review ────────────────────────────────────────────────────────
def _render_transcript(digest: str) -> str | None:
    """
    Shows the editable transcript with its Ask / Discard actions.

    Returns the confirmed question, or None while the field worker is still
    reviewing it.
    """
    stored = st.session_state.get(TRANSCRIPT_STATE_KEY) or {}
    if stored.get("digest") != digest:
        return None

    st.caption(t("voice.transcript_caption", seconds=round(stored.get("engine_ms", 0) / 1000, 1)))
    edited = st.text_area(
        t("voice.transcript_label"),
        value=stored.get("text", ""),
        key=f"csa_voice_transcript_{digest}",
        height=90,
        help=t("voice.transcript_help"),
    )

    ask_col, discard_col, _spacer = st.columns([1.6, 1.4, 3])

    with ask_col:
        if st.button(t("voice.ask"), key=f"csa_voice_ask_{digest}", type="primary",
                     use_container_width=True, disabled=not edited.strip()):
            question = edited.strip()
            _reset_recorder()
            return question

    with discard_col:
        if st.button(t("voice.discard"), key=f"csa_voice_discard_{digest}",
                     use_container_width=True):
            _reset_recorder()
            st.rerun()

    return None


def render_voice_recorder() -> str | None:
    """
    Renders the voice input panel in the Chat tab.

    Returns:
        The confirmed question to ask, or None when there is nothing to send
        yet. components/chat.py treats the return value exactly like a typed
        question.
    """
    with st.expander(t("voice.heading"), expanded=False):
        st.caption(t("voice.intro"))

        clip = _capture_audio()
        if clip is None:
            return None

        audio_bytes = clip.getvalue()
        if not audio_bytes:
            return None

        if len(audio_bytes) > _MAX_AUDIO_BYTES:
            st.error(t("voice.too_large", limit=_MAX_AUDIO_BYTES // (1024 * 1024)))
            return None

        # Playback of what was actually captured, before spending an STT call
        # on a clip that turns out to be silence or the wrong question.
        st.audio(audio_bytes, format=getattr(clip, "type", None) or "audio/wav")

        digest = _digest(audio_bytes)
        stored = st.session_state.get(TRANSCRIPT_STATE_KEY) or {}

        if stored.get("digest") != digest:
            failure = st.session_state.get(_FAILED_KEY) or {}
            if failure.get("digest") == digest:
                st.error(failure["error"])

            if st.button(t("voice.transcribe"), key=f"csa_voice_transcribe_{digest}",
                         type="primary", help=t("voice.transcribe_help")):
                with st.spinner(t("voice.transcribing")):
                    result = _transcribe(audio_bytes, clip)

                if "error" in result:
                    st.session_state[_FAILED_KEY] = {"digest": digest, "error": result["error"]}
                    st.session_state.pop(TRANSCRIPT_STATE_KEY, None)
                else:
                    st.session_state[TRANSCRIPT_STATE_KEY] = {"digest": digest, **result}
                    st.session_state.pop(_FAILED_KEY, None)
                st.rerun()

            return None

        return _render_transcript(digest)
