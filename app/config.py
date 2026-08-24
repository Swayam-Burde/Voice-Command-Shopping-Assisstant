"""
Application configuration.
Loads environment variables from .env and exposes them as typed constants and key pools.
"""
import os
from typing import List

from dotenv import load_dotenv

load_dotenv()

# ── API keys & Key Pools (Supports multi-key rotation to prevent 429 rate limits) ──
def _collect_keys(prefix: str) -> List[str]:
    keys = []
    # Primary key
    primary = os.getenv(prefix, "").strip()
    if primary:
        keys.append(primary)
    # Numbered keys (e.g., GEMINI_API_KEY2, GEMINI_API_KEY3... or GROQ_API_KEY2)
    for i in range(2, 11):
        k = os.getenv(f"{prefix}{i}", "").strip()
        if k and k not in keys:
            keys.append(k)
    return keys

GROQ_API_KEYS: List[str] = _collect_keys("GROQ_API_KEY")
GEMINI_API_KEYS: List[str] = _collect_keys("GEMINI_API_KEY")

# Primary fallback single string constants for backward compatibility
GROQ_API_KEY: str = GROQ_API_KEYS[0] if GROQ_API_KEYS else os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY: str = GEMINI_API_KEYS[0] if GEMINI_API_KEYS else os.getenv("GEMINI_API_KEY", "")

# ── FastAPI metadata ──────────────────────────────────────────────────────────
APP_TITLE: str = "Voice Command Shopping Assistant"
APP_VERSION: str = "1.0.0"
API_PREFIX: str = "/api/v1"

# ── LLM model identifiers & cascades ──────────────────────────────────────────
GROQ_CHAT_MODEL: str = "openai/gpt-oss-20b"
GROQ_CHAT_MODELS: list[str] = [
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
    "groq/compound-mini",
    "openai/gpt-oss-120b",
]

GROQ_WHISPER_MODEL: str = "whisper-large-v3"
GROQ_WHISPER_MODELS: list[str] = [
    "whisper-large-v3",
    "whisper-large-v3-turbo",
]

GEMINI_CHAT_MODEL: str = "gemini-flash-latest"
GEMINI_CHAT_MODELS: list[str] = [
    "gemini-flash-latest",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]
