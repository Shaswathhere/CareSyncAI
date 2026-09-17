"""
rag/transcriber.py
------------------
Speech-to-Text transcription using Groq's Whisper API (whisper-large-v3-turbo).
Accepts a local audio file path, returns transcribed text.
"""

from __future__ import annotations
import os
from config import GROQ_API_KEY


def transcribe_audio_groq(file_path: str) -> str:
    """
    Transcribes an audio file using Groq's Whisper (whisper-large-v3-turbo).

    Args:
        file_path: Local path to the audio file (mp3, wav, m4a, ogg, etc.)

    Returns:
        Transcribed text string.

    Raises:
        RuntimeError: If GROQ_API_KEY is missing or transcription fails.
        FileNotFoundError: If the audio file does not exist.
    """
    if not GROQ_API_KEY:
        raise RuntimeError(
            "GROQ_API_KEY is missing. Cannot transcribe audio. "
            "Get a free key at https://console.groq.com/keys"
        )

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    try:
        from groq import Groq
        client = Groq(api_key=GROQ_API_KEY)

        with open(file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(file_path), audio_file.read()),
                model="whisper-large-v3-turbo",
                response_format="text",
            )

        # Groq returns a plain string when response_format="text"
        transcript = str(transcription).strip()
        print(f"[transcriber] Transcribed {os.path.basename(file_path)}: {len(transcript)} chars")
        return transcript

    except Exception as exc:
        raise RuntimeError(f"Audio transcription failed: {exc}") from exc


# Backward compatibility alias
transcribe_audio_gemini = transcribe_audio_groq
