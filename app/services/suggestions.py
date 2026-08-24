"""
Smart Suggestions Service — dynamic, cart-aware.

Generates three types of personalised grocery suggestions via LLM:
  - historical_recommendations : restock items from purchase history (varied each call)
  - seasonal_recommendations   : in-season / trending items for the current month
  - substitutes                : smart alternatives relevant to the current cart + item

Provider strategy: Groq primary → Gemini fallback → empty SuggestionResult on total failure.
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import List, Optional

from google import genai
from google.genai import types as genai_types
from groq import AsyncGroq

from app.config import (
    GEMINI_API_KEY,
    GEMINI_API_KEYS,
    GEMINI_CHAT_MODEL,
    GEMINI_CHAT_MODELS,
    GROQ_API_KEY,
    GROQ_API_KEYS,
    GROQ_CHAT_MODEL,
    GROQ_CHAT_MODELS,
)
from app.data.mock_db import PURCHASE_HISTORY
from app.models import CartItem, SubstitutePair, SuggestionResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Season helpers
# ─────────────────────────────────────────────────────────────────────────────

_SEASON_MAP: dict[int, str] = {
    12: "Winter", 1: "Winter", 2: "Winter",
    3: "Spring",  4: "Spring", 5: "Spring",
    6: "Summer",  7: "Summer", 8: "Summer",
    9: "Autumn",  10: "Autumn", 11: "Autumn",
}

# India-specific season overrides (monsoon / harvest context)
_INDIA_SEASON_MAP: dict[int, str] = {
    6: "Monsoon", 7: "Monsoon", 8: "Monsoon", 9: "Monsoon",
    10: "Post-Monsoon / Festival Season (Navratri, Diwali)",
    11: "Early Winter / Festival Season",
    12: "Winter",  1: "Winter",  2: "Winter",
    3: "Spring / Holi",  4: "Summer",  5: "Peak Summer",
}


def _current_season() -> str:
    month = datetime.now().month
    return _INDIA_SEASON_MAP.get(month, _SEASON_MAP.get(month, "Current Season"))


# ─────────────────────────────────────────────────────────────────────────────
#  Prompt builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_prompt(item_name: Optional[str], cart_items: List[CartItem]) -> str:
    cart_names = [c.item_name for c in cart_items]
    cart_desc = ", ".join(cart_names) if cart_names else "empty"
    history_desc = ", ".join(PURCHASE_HISTORY)
    season = _current_season()

    item_focus = (
        f'The user just mentioned or added: "{item_name}".'
        if item_name
        else "No single item mentioned; suggest based on current cart and history."
    )

    return f"""You are a smart retail grocery recommendation engine.
Return a JSON object with THREE distinct suggestion sections based on the context below.

Context:
- Current Cart: {cart_desc}
- User Purchase History: {history_desc}
- Current Season: {season}
- {item_focus}

Return ONLY a valid JSON object matching this schema (no markdown, no extra text):
{{
  "historical_recommendations": ["<item1>", "<item2>", "<item3>", "<item4>"],
  "seasonal_recommendations":   ["<item1>", "<item2>", "<item3>", "<item4>"],
  "substitutes": [
    {{
      "original": "<item name>",
      "substitute": "<alternative product>",
      "reason": "<short 4-8 word benefit/difference>"
    }}
  ]
}}

Rules:
HISTORICAL RECOMMENDATIONS:
  - Select 3-4 items from or inspired by the purchase history ({history_desc}) that are NOT currently in the cart.
  - Vary the selection so repeated calls provide fresh restock suggestions.
  - Must be complementary to the current cart if cart is non-empty.

SEASONAL RECOMMENDATIONS:
  - Season: {season}.
  - Include seasonal fruits, vegetables, or festival foods appropriate for this time.
  - Do NOT repeat items already in the cart.
  - Examples for Monsoon: corn, jamun, litchi, green tea, ginger, tulsi.
  - Examples for Winter: gajar (carrot), methi, sarson, peanuts, jaggery.
  - Examples for Summer: watermelon, mango, kokum, coconut water, cucumber.

SUBSTITUTES:
  - If an item is mentioned, provide 1-3 smart practical substitutes with brief reasons.
  - If no specific item is mentioned but cart is non-empty, suggest substitutes for 1-2 cart items.
  - If cart is empty, suggest 2 common healthy swaps from purchase history.
  - Keep reasons short (under 10 words).
  - Do NOT suggest swaps for items not relevant to grocery/FMCG.

Keep all suggestions realistic, practical grocery items only. Do not repeat cart items."""


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

async def generate_suggestions(
    item_name: Optional[str] = None,
    cart_items: Optional[List[CartItem]] = None,
) -> SuggestionResult:
    """
    Generate dynamic, cart-aware personalised suggestions.
    Multi-Key Groq pool → Multi-Key Gemini pool → empty SuggestionResult on failure.
    """
    prompt = _build_prompt(item_name, cart_items or [])

    groq_keys = GROQ_API_KEYS or ([GROQ_API_KEY] if GROQ_API_KEY else [])
    for k in groq_keys:
        try:
            return await _suggest_with_groq(prompt, k)
        except Exception as exc:
            logger.warning("Suggestions: Groq key failed (%s). Trying next key/fallback.", exc)

    gemini_keys = GEMINI_API_KEYS or ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
    for k in gemini_keys:
        try:
            return await _suggest_with_gemini(prompt, k)
        except Exception as exc:
            logger.warning("Suggestions: Gemini key failed (%s). Trying next Gemini key.", exc)

    logger.error("Suggestions: All keys failed. Returning empty result.")
    return SuggestionResult()


# ─────────────────────────────────────────────────────────────────────────────
#  Provider implementations
# ─────────────────────────────────────────────────────────────────────────────

async def _suggest_with_groq(prompt: str, api_key: str) -> SuggestionResult:
    client = AsyncGroq(api_key=api_key)
    last_exc = None
    for model_name in GROQ_CHAT_MODELS:
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.8,
                max_tokens=900,
            )
            raw: str = response.choices[0].message.content or "{}"
            logger.debug("Suggestions (Groq:%s) raw: %s", model_name, raw)
            return _parse(raw)
        except Exception as exc:
            logger.warning("Suggestions (Groq:%s) failed (%s). Trying next model.", model_name, exc)
            last_exc = exc
    raise last_exc or RuntimeError("All Groq models failed")


async def _suggest_with_gemini(prompt: str, api_key: str) -> SuggestionResult:
    client = genai.Client(api_key=api_key)
    loop = asyncio.get_event_loop()
    last_exc = None
    for model_name in GEMINI_CHAT_MODELS:
        try:
            response = await loop.run_in_executor(
                None,
                lambda m=model_name: client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.8,
                    ),
                ),
            )
            raw: str = response.text or "{}"
            logger.debug("Suggestions (Gemini:%s) raw: %s", model_name, raw)
            return _parse(raw)
        except Exception as exc:
            logger.warning("Suggestions (Gemini:%s) failed (%s). Trying next model.", model_name, exc)
            last_exc = exc
    raise last_exc or RuntimeError("All Gemini models failed")


# ─────────────────────────────────────────────────────────────────────────────
#  JSON parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse(raw: str) -> SuggestionResult:
    try:
        data: dict = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Suggestions: JSON decode failed — '%s'", raw)
        return SuggestionResult()

    substitutes: list[SubstitutePair] = []
    for entry in data.get("substitutes", []):
        if isinstance(entry, dict) and entry.get("original") and entry.get("substitute"):
            substitutes.append(
                SubstitutePair(
                    original=entry["original"],
                    substitute=entry["substitute"],
                    reason=entry.get("reason", ""),
                )
            )

    return SuggestionResult(
        historical_recommendations=data.get("historical_recommendations", []),
        seasonal_recommendations=data.get("seasonal_recommendations", []),
        substitutes=substitutes,
    )
