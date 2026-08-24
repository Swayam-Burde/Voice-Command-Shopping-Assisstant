"""
Catalog Search Service — two-layer product lookup.

Layer 1 (Fast): Local mock catalog in mock_db.py — 25 pre-seeded FMCG items.
Layer 2 (Universal): LLM-powered lookup for anything not found locally.
             The LLM has knowledge of virtually all real FMCG brands and SKUs
             and generates realistic product data (name, brand, price, tags) on demand.

This ensures the assistant handles *any* product query during testing or production —
regardless of whether it exists in the local catalog.
"""
import asyncio
import json
import logging
from typing import Optional

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
from app.data.mock_db import search_catalog
from app.models import FilterCriteria, ProductResult

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

def sort_by_price_relevance(
    results: list[ProductResult],
    filter_criteria: Optional[FilterCriteria],
) -> list[ProductResult]:
    """
    Sort products so the ones closest to the requested price limit appear first,
    followed by others in progressive price order.
    """
    if not filter_criteria or not results:
        return results

    target_max = filter_criteria.max_price
    target_min = filter_criteria.min_price

    if target_max is not None:
        target_usd = target_max / 83.0 if target_max > 15 else target_max
        # Sort closest to target_max first (smallest distance), then descending
        return sorted(results, key=lambda p: (abs((p.price or 0) - target_usd), -(p.price or 0)))

    if target_min is not None:
        target_min_usd = target_min / 83.0 if target_min > 15 else target_min
        return sorted(results, key=lambda p: (abs((p.price or 0) - target_min_usd), (p.price or 0)))

    return results


async def search_products(
    item_name: Optional[str],
    filter_criteria: Optional[FilterCriteria],
) -> list[ProductResult]:
    """
    Two-layer product search:
      1. Local catalog (instant, deterministic).
      2. LLM universal FMCG lookup (fallback for any unknown product/brand).

    Results from both layers are sorted by price proximity when a price filter is provided.
    """
    # ── Layer 1: local catalog ────────────────────────────────────────────────
    local_results = search_catalog(item_name, filter_criteria)

    if local_results:
        logger.info("Catalog search: %d local result(s) for '%s'.", len(local_results), item_name)
        return sort_by_price_relevance(local_results, filter_criteria)

    # ── Layer 2: LLM universal lookup ────────────────────────────────────────
    logger.info(
        "Catalog search: no local results for '%s' — querying LLM.", item_name
    )
    llm_results = await _llm_search(item_name, filter_criteria)
    return sort_by_price_relevance(llm_results, filter_criteria)


# ─────────────────────────────────────────────────────────────────────────────
#  LLM universal search helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_search_prompt(
    item_name: Optional[str],
    filter_criteria: Optional[FilterCriteria],
) -> str:
    """Build a targeted product-search prompt for the LLM."""
    query_desc = item_name or "grocery items"

    filter_lines: list[str] = []
    price_target_hint = ""
    if filter_criteria:
        if filter_criteria.brand:
            filter_lines.append(f"- Brand must include: {filter_criteria.brand}")
        if filter_criteria.max_price is not None:
            mp = filter_criteria.max_price
            if mp > 15:
                filter_lines.append(f"- Price budget limit: must be ≤ ₹{mp:.0f} INR (approximately ≤ ${mp/83.0:.2f} USD)")
                price_target_hint = f"Rank products so the one closest to ₹{mp:.0f} (~${mp/83.0:.2f} USD) appears FIRST, followed by other options ordered price-wise."
            else:
                filter_lines.append(f"- Price budget limit: must be ≤ ${mp:.2f} USD (or ₹{mp*83:.0f} INR)")
                price_target_hint = f"Rank products so the one closest to ${mp:.2f} USD appears FIRST, followed by other options ordered price-wise."
        if filter_criteria.min_price is not None:
            min_p = filter_criteria.min_price
            filter_lines.append(f"- Price must be ≥ ${min_p:.2f} USD")
        if filter_criteria.tags:
            filter_lines.append(f"- Must match tags: {', '.join(filter_criteria.tags)}")

    filters_block = "\n".join(filter_lines) if filter_lines else "None (return popular options)"

    return f"""You are an FMCG product catalogue database.
Find real products matching the search query and filters below.

Query   : {query_desc}
Filters :
{filters_block}

CRITICAL RULES:
1. Product `price` MUST be returned as a realistic USD number (e.g. 0.95, 1.15, 2.49, 4.99) because the frontend converts USD to INR ($1.00 ≈ ₹83).
2. Strictly enforce price budget limits — do NOT return items exceeding the maximum budget.
3. PRICE-WISE RANKING: {price_target_hint or 'Sort products in logical order of relevance and price.'}
4. Use real, well-known FMCG brands wherever applicable (e.g. Amul, Nestlé, Britannia, Dabur, Mother Dairy, Heinz, Kellogg's).

Return ONLY a valid JSON array of up to 6 realistic matching products (no markdown, no extra text):
[
  {{
    "name": "<full product name>",
    "brand": "<real or realistic brand name>",
    "category": "<Dairy | Produce | Snacks | Beverages | Pantry | Personal Care | Bakery | Meat | Frozen | Other>",
    "price": <realistic USD price number>,
    "tags": ["<tag1>", "<tag2>", "<tag3>"]
  }}
]"""


async def _llm_search(
    item_name: Optional[str],
    filter_criteria: Optional[FilterCriteria],
) -> list[ProductResult]:
    """Call Groq (primary) → Gemini (fallback) for universal FMCG product lookup with multi-key pools and model cascades."""
    prompt = _build_search_prompt(item_name, filter_criteria)

    groq_keys = GROQ_API_KEYS or ([GROQ_API_KEY] if GROQ_API_KEY else [])
    for k in groq_keys:
        try:
            return await _search_with_groq(prompt, k)
        except Exception as exc:
            logger.warning("Catalog LLM (Groq) key failed (%s). Trying next key/fallback.", exc)

    gemini_keys = GEMINI_API_KEYS or ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
    for k in gemini_keys:
        try:
            return await _search_with_gemini(prompt, k)
        except Exception as exc:
            logger.warning("Catalog LLM (Gemini) key failed (%s). Trying next Gemini key.", exc)

    logger.error("Catalog LLM: All keys and models failed. Returning empty results.")
    return []


async def _search_with_groq(prompt: str, api_key: str) -> list[ProductResult]:
    client = AsyncGroq(api_key=api_key)
    last_exc = None
    for model_name in GROQ_CHAT_MODELS:
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=1024,
            )
            raw: str = response.choices[0].message.content or "[]"
            logger.debug("Catalog LLM (Groq:%s) raw: %s", model_name, raw)
            return _parse_products(raw)
        except Exception as exc:
            logger.warning("Catalog LLM (Groq:%s) failed (%s). Trying next model.", model_name, exc)
            last_exc = exc
    raise last_exc or RuntimeError("All Groq models failed")


async def _search_with_gemini(prompt: str, api_key: str) -> list[ProductResult]:
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
                        temperature=0.3,
                    ),
                ),
            )
            raw: str = response.text or "[]"
            logger.debug("Catalog LLM (Gemini:%s) raw: %s", model_name, raw)
            return _parse_products(raw)
        except Exception as exc:
            logger.warning("Catalog LLM (Gemini:%s) failed (%s). Trying next model.", model_name, exc)
            last_exc = exc
    raise last_exc or RuntimeError("All Gemini models failed")


def _parse_products(raw: str) -> list[ProductResult]:
    """Parse LLM JSON output into a validated list of ProductResult objects."""
    clean = raw.strip()
    if clean.startswith("```"):
        lines = clean.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        clean = "\n".join(lines).strip()

    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        logger.error("Catalog LLM: JSON decode failed — '%s'", raw)
        return []

    # LLM might wrap list in an object key — handle both formats
    if isinstance(data, dict):
        for key in ("products", "results", "items", "data"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            logger.error("Catalog LLM: unexpected dict shape — '%s'", raw)
            return []

    if not isinstance(data, list):
        return []

    products: list[ProductResult] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name:
            continue
        products.append(
            ProductResult(
                name=str(name),
                brand=entry.get("brand"),
                category=entry.get("category"),
                price=entry.get("price"),
                tags=entry.get("tags") or [],
            )
        )
    return products
