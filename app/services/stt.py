import asyncio
import io
import logging
from typing import Optional, Union

from fastapi import HTTPException, UploadFile
from google import genai
from google.genai import types as genai_types
from groq import AsyncGroq

from app.config import (
    GEMINI_API_KEY,
    GEMINI_API_KEYS,
    GEMINI_CHAT_MODELS,
    GROQ_API_KEY,
    GROQ_API_KEYS,
    GROQ_WHISPER_MODEL,
    GROQ_WHISPER_MODELS,
)

logger = logging.getLogger(__name__)

# Groq Whisper hard limit
_MAX_FILE_BYTES: int = 25 * 1024 * 1024  # 25 MB


async def transcribe(
    audio: Optional[Union[UploadFile, bytes]] = None,
    transcript_override: Optional[str] = None,
    filename: Optional[str] = None,
    content_type: Optional[str] = None,
) -> str:
    """
    Transcribe an audio file using Groq's Whisper large-v3 model with key-pool failover
    and Gemini multimodal audio transcription fallback.
    """
    # ── Test bypass ──────────────────────────────────────────────────────────
    if transcript_override and transcript_override.strip():
        logger.info("STT: using transcript_override (test mode).")
        return transcript_override.strip()

    # ── Input validation ─────────────────────────────────────────────────────
    if audio is None:
        raise HTTPException(
            status_code=400,
            detail="Provide either an 'audio' file or a 'transcript_override' string.",
        )

    # Extract bytes safely from UploadFile or raw bytes
    if isinstance(audio, bytes):
        content = audio
    elif hasattr(audio, "read"):
        content = await audio.read()
        if hasattr(audio, "filename") and not filename:
            filename = audio.filename
        if hasattr(audio, "content_type") and not content_type:
            content_type = audio.content_type
    else:
        raise HTTPException(status_code=400, detail="Invalid audio payload format.")

    if not content:
        raise HTTPException(status_code=400, detail="Empty audio recording received.")

    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Audio file exceeds the 25 MB limit "
                f"({len(content) / 1_048_576:.1f} MB received)."
            ),
        )

    clean_filename: str = filename or "recording.webm"
    clean_content_type: str = content_type or "audio/webm"

    logger.info(
        "STT: transcribing '%s' (%s, %.1f KB).",
        clean_filename, clean_content_type, len(content) / 1024,
    )

    # ── 1. Groq Whisper call with multi-key and model rotation ──────────────
    groq_keys = GROQ_API_KEYS or ([GROQ_API_KEY] if GROQ_API_KEY else [])
    whisper_models = GROQ_WHISPER_MODELS or [GROQ_WHISPER_MODEL]
    last_exc = None

    for k in groq_keys:
        for model_name in whisper_models:
            try:
                client = AsyncGroq(api_key=k)
                transcription = await client.audio.transcriptions.create(
                    file=(clean_filename, content, clean_content_type),
                    model=model_name,
                )
                text: str = (transcription.text or "").strip()
                logger.info("STT: (Groq Whisper:%s) transcript='%s'", model_name, text)
                return text
            except Exception as exc:
                logger.warning(
                    "STT: Groq Whisper (model=%s) failed (%s). Trying next.",
                    model_name, exc,
                )
                last_exc = exc

    # ── 2. Fallback: Google Gemini Multimodal Audio Transcription ───────────
    logger.info("STT: Groq Whisper unavailable — attempting Gemini audio transcription fallback.")
    gemini_keys = GEMINI_API_KEYS or ([GEMINI_API_KEY] if GEMINI_API_KEY else [])

    for k in gemini_keys:
        for model_name in GEMINI_CHAT_MODELS:
            try:
                client = genai.Client(api_key=k)
                loop = asyncio.get_event_loop()
                mime = clean_content_type.split(";")[0].strip() or "audio/webm"
                
                res = await loop.run_in_executor(
                    None,
                    lambda m=model_name: client.models.generate_content(
                        model=m,
                        contents=[
                            genai_types.Part.from_bytes(data=content, mime_type=mime),
                            "Transcribe this spoken voice command verbatim in its original language (Hindi, English, or Hinglish). Return ONLY the transcription text, nothing else. If silence or inaudible, return an empty string.",
                        ],
                    ),
                )
                text = (res.text or "").strip()
                logger.info("STT: (Gemini:%s fallback) transcript='%s'", model_name, text)
                return text
            except Exception as exc:
                logger.warning("STT: Gemini audio fallback (model=%s) failed (%s). Trying next.", model_name, exc)
                last_exc = exc

    logger.error("STT: All speech-to-text providers failed — %s", last_exc)
    raise HTTPException(
        status_code=502,
        detail=f"Speech-to-Text transcription failed: {last_exc}",
    ) from last_exc
