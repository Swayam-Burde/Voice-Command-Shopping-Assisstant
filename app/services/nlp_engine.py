"""
NLP Engine — extracts structured intent and entities from a voice transcript.

Pipeline:
  1. Primary  : Groq (JSON mode enforced)
  2. Fallback : Gemini (google-genai SDK, JSON MIME type)
  3. Last resort: return NLPResult(intent=UNKNOWN)

Key capabilities:
  - Multi-item extraction from a single command
  - Implicit ADD_ITEM when no verb is present (e.g. "Almond milk and bread")
  - Desi unit normalisation (dazan→12pcs, quintal→100kg, paav→250g, etc.)
  - English + Hindi/Hinglish only; Hindi item names translated to English
  - Partial-quantity REMOVE ("Remove 2 mangoes" → qty=2 in the items array)
  - Long narrative scanning (wedding lists, stories) for all FMCG items
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
from app.models import Category, FilterCriteria, Intent, ItemEntity, NLPResult, SearchQuery


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  System prompt
# ─────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT: str = """You are the NLP extraction engine for a multilingual voice shopping assistant.
SUPPORTED LANGUAGES: English and Hindi/Hinglish ONLY.
- If the transcript is in Hindi (Devanagari or romanised Hinglish), translate all item names to English before filling item_name fields.
- Do NOT produce Urdu script or other languages. Treat Urdu as Hindi and translate to English.

Return ONLY a valid JSON object matching this exact schema (no markdown, no extra text):
{
  "intent": "<ADD_ITEM | REMOVE_ITEM | MODIFY_QUANTITY | SEARCH_FILTER | GET_SUGGESTIONS | UNKNOWN>",
  "items": [
    {
      "item_name": "<English item name to ADD in lowercase>",
      "quantity": <number>,
      "unit": "<normalised unit string or null>",
      "category": "<Dairy | Produce | Snacks | Beverages | Pantry | Other>"
    }
  ],
  "remove_items": [
    {
      "item_name": "<English item name to REMOVE in lowercase>",
      "quantity": <number or null>,
      "unit": "<normalised unit string or null>",
      "category": "<Dairy | Produce | Snacks | Beverages | Pantry | Other>"
    }
  ],
  "search_queries": [
    {
      "item_name": "<English item name to SEARCH in lowercase>",
      "max_price": <max price as number or null>,
      "min_price": <min price as number or null>,
      "brand": "<brand name or null>",
      "tags": ["<tag1>"]
    }
  ],
  "item_name": "<primary English item name in lowercase, or null>",
  "quantity": <numeric value or null>,
  "unit": "<unit string or null>",
  "category": "<Dairy | Produce | Snacks | Beverages | Pantry | Other | null>",
  "filter_criteria": {
    "brand": "<brand name or null>",
    "max_price": <max price as number or null>,
    "min_price": <min price as number or null>,
    "tags": ["<tag1>", "<tag2>"]
  }
}

═══════════════════════════════════════════
INTENT CLASSIFICATION & CORRECTION RULES:
═══════════════════════════════════════════
ADD_ITEM:
  - Explicit verbs: "add", "buy", "get me", "I need", "I want", "chahiye", "lena hai", "order", "put", "include", "lele", "lao", "bhi lagega", "list bana de", "daal de", "daalo"
  - IMPLICIT (no verb): if the user simply names grocery/FMCG items with no action verb, DEFAULT to ADD_ITEM.
    Examples: "almond milk", "apples and bread", "doodh aur chawal" → ADD_ITEM
  - Simultaneous ADD & REMOVE (CRITICAL):
    If the user asks to add some items AND remove others in the same sentence (e.g. "5 kg mutton bhi daal de aur pineapple hta de" or "Add 2 breads and remove milk"),
    set intent = "ADD_ITEM", put items to ADD into `items`, and put items to REMOVE into `remove_items`.
  - Conversational Narratives, Stories & Party Planning:
    Ignore conversational slang, profanity, and filler phrases (e.g. "bhai", "ek kaam kar", "party hai", "yaar", "list bna de", "sun", "arey", "yeh rakh liya abb").
    Scan the ENTIRE transcript from start to finish and exhaustively extract EVERY food, meat, vegetable, spice, grocery, or FMCG item mentioned.
    If an item is mentioned without an explicit quantity (e.g., "dhaniya", "chicken masala", "laal mirch", "kaali mirch"), DEFAULT to quantity = 1.0.
  - Mid-Sentence Self-Correction / Overrides:
    If user mentions an item and then corrects/cancels it mid-sentence (e.g. "add namkeen. Wait, cancel namkeen, add 2 packet chips instead"),
    ONLY extract the final desired items (e.g. 2 packet chips, milk, bananas) and DO NOT include the cancelled item (namkeen).
  - Specific Brands/Types in Item Name:
    If user specifies a brand or variant (e.g. "साबुन लक्स का ही होना चाहिए" or "Lux soap"), include the brand/type in the item name (e.g. "lux soap").

REMOVE_ITEM:
  - "remove", "delete", "take off", "don't need", "cancel", "drop", "hatao", "nikalo", "hta de", "hata de"
  - Clear / Empty Entire Cart (CRITICAL):
    If the user asks to empty or clear the entire cart or list (e.g., "khali kar de cart ko", "clear cart", "empty the list", "delete everything", "sab cancel kar do", "pura cart hata do", "empty shopping list"),
    set intent = "REMOVE_ITEM", items = [{"item_name": "all", "quantity": 1, "unit": null, "category": "Other"}], item_name = "all".
  - Full vs Partial Removal:
    - If user says "remove pineapple", "pineapple hata de", "delete milk" (NO quantity spoken):
      set quantity = null (deletes the entire item from the cart).
    - If user explicitly says a number like "remove 2 pineapples" or "remove 10 kg mango":
      set quantity = 2, unit = ... (partially reduces the quantity).

MODIFY_QUANTITY:
  - "change quantity", "update", "make it", "set X to Y", "badlo", "update karo"

SEARCH_FILTER:
  - Triggered by price filters, searches, brand lookups, and discovery:
    "find", "search", "look for", "show me", "<item> under <price>", "<item> below <price>", "<item> under ₹<price>", "<item> <price> ke andar", "organic", "brand <name>"
  - EXAMPLES (CRITICAL):
    - "chicken under 100" → intent="SEARCH_FILTER", item_name="chicken", filter_criteria={"max_price": 100.0, "min_price": null, "brand": null, "tags": []}, search_queries=[{"item_name":"chicken","max_price":100.0}]
    - "mango under 5" → intent="SEARCH_FILTER", item_name="mango", filter_criteria={"max_price": 5.0, "min_price": null, "brand": null, "tags": []}, search_queries=[{"item_name":"mango","max_price":5.0}]
    - "mangoes under 50" → intent="SEARCH_FILTER", item_name="mango", filter_criteria={"max_price": 50.0, "min_price": null, "brand": null, "tags": []}
    - "find organic milk under 100" → intent="SEARCH_FILTER", item_name="milk", filter_criteria={"max_price": 100.0, "tags": ["organic"]}
    - "show me brown rice below ₹50" → intent="SEARCH_FILTER", item_name="brown rice", filter_criteria={"max_price": 50.0}
  - Multi-Search / Compound Searches with Price Limits:
    If user specifies multiple products with price ranges or search filters in one sentence (e.g. "aam chahiye 10 ke andar aur chicken 100 ke andar" or "mangoes under 10 and chicken under 100"),
    put EACH search target into `search_queries` (e.g. [{"item_name": "mango", "max_price": 10.0}, {"item_name": "chicken", "max_price": 100.0}]).
  - Compound Add & Search in One Command (CRITICAL):
    If the user asks to search for some products AND add other items to cart in the same command (e.g. "mujhe aam chahiye 10 ke andar aur chicken 100 ke anadr aur 5 kg mango add kar de bhai"):
    set intent = "ADD_ITEM", put items to ADD into `items` (e.g. [{"item_name": "mango", "quantity": 5.0, "unit": "kg"}]), and put the search requests into `search_queries` (e.g. [{"item_name": "mango", "max_price": 10.0}, {"item_name": "chicken", "max_price": 100.0}]).
  - NOTE: Do NOT treat "under X" or "below X" or "X ke andar" as a quantity! It is always a maximum price filter in SEARCH_FILTER/search_queries.

GET_SUGGESTIONS:
  - "suggest", "recommend", "what should I buy", "ideas", "kya kharidun"

UNKNOWN:
  - Cannot determine intent

═══════════════════════════════════════════
DESI UNIT NORMALISATION (critical):
═══════════════════════════════════════════
Convert spoken/desi units to standard numerical values BEFORE filling the JSON:
- dazan / dozen                → quantity × 12, unit = "pieces"  (e.g. "2 dazan kela" → qty=24, unit="pieces")
- a dozen / one dozen          → qty=12, unit = "pieces"
- quintal / quintal            → quantity × 100, unit = "kg"      (e.g. "1 quintal sugar" → qty=100, unit="kg")
- paav / paao / quarter kg     → quantity × 0.25, unit = "kg"    (e.g. "2 paav paneer" → qty=0.5, unit="kg")
- aadha kilo / half kg / 1/2 kg→ 0.5 kg, unit = "kg"
- litre / liter / L            → unit = "litres"
- gram / grams / g             → unit = "grams"
- kg / kilo / kilogram         → unit = "kg"
- packet / pack / pkt          → unit = "packets"
- bottle / botol               → unit = "bottles"
- piece / pcs / nag            → unit = "pieces"
- loaf / loaves                → unit = "loaves"
Quantity like "4 dazan" means 4×12=48 pieces. Fill qty=48, unit="pieces".
Quantity "1 quintal" means qty=100, unit="kg". 

═══════════════════════════════════════════
MULTI-ITEM EXTRACTION (critical):
═══════════════════════════════════════════
For ADD_ITEM and REMOVE_ITEM: extract EVERY item into the `items` array.
Examples:
- "Add tomato ketchup, almond milk and water" → 3 entries
- "I need eggs and bread" → 2 entries
- "10 kg moong dal, 20 kg rice, 50 kg sugar" → 3 entries
- "4 kg chicken, 2 kg mutton, chicken masala, mutton masala, dhaniya, laal mirch, kaali mirch, 2 kg chawal, 5 kg aata"
  → 9 distinct entries:
    1. chicken (qty: 4, unit: "kg", cat: "Other")
    2. mutton (qty: 2, unit: "kg", cat: "Other")
    3. chicken masala (qty: 1, unit: null, cat: "Pantry")
    4. mutton masala (qty: 1, unit: null, cat: "Pantry")
    5. coriander (or dhaniya) (qty: 1, unit: null, cat: "Produce")
    6. red chili (or laal mirch) (qty: 1, unit: null, cat: "Pantry")
    7. black pepper (or kaali mirch) (qty: 1, unit: null, cat: "Pantry")
    8. rice (qty: 2, unit: "kg", cat: "Pantry")
    9. wheat flour (or aata) (qty: 5, unit: "kg", cat: "Pantry")

═══════════════════════════════════════════
HINDI TRANSLATION TABLE (examples):
═══════════════════════════════════════════
aam=mango, doodh=milk, chawal=rice, aata=wheat flour, dal=lentils,
moong dal=green lentils, chini=sugar, namak=salt, tel=oil, sabzi=vegetables,
pyaz=onion, aalu=potato, tamatar=tomato, lassan=garlic, adrak=ginger,
makhan=butter, paneer=cottage cheese, dahi=yogurt, ghee=clarified butter,
chai=tea, pani=water, anda=egg, bread=bread, biscuit=biscuit, maida=refined flour,
chicken=chicken, mutton=mutton, dhaniya=coriander, laal mirch=red chili, kaali mirch=black pepper,
haldi=turmeric, jeera=cumin, garam masala=garam masala

═══════════════════════════════════════════
CATEGORY INFERENCE (per item):
═══════════════════════════════════════════
Dairy:     milk, cheese, yogurt, butter, cream, eggs, paneer, dahi, ghee
Produce:   fruits, vegetables, herbs, mango, apple, orange, watermelon, onion, tomato, potato, coriander, dhaniya, ginger, garlic
Beverages: water, juice, soda, tea, coffee, energy drinks, chai, pani
Snacks:    chips, crackers, cookies, candy, nuts, popcorn, biscuit, namkeen
Pantry:    bread, pasta, rice, flour, aata, oil, sauce, ketchup, dal, sugar, salt, spices, masala, mirch, chicken masala, mutton masala, black pepper, red chili
Other:     chicken, mutton, meat, personal care, soap, cleaning, household, medicine

Set filter_criteria to null when not applicable. Use null for undetermined scalar fields."""


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

async def process_transcript(transcript: str) -> NLPResult:
    """
    Extract intent and entities from a voice transcript.
    Multi-Key Groq pool → Multi-Key Gemini pool → UNKNOWN on total failure.
    """
    # 1. Try Groq key pool
    groq_keys = GROQ_API_KEYS or ([GROQ_API_KEY] if GROQ_API_KEY else [])
    for k in groq_keys:
        try:
            return await _process_with_groq(transcript, k)
        except Exception as exc:
            logger.warning("NLP: Groq key failed (%s). Trying next key/fallback.", exc)

    # 2. Try Gemini key pool
    gemini_keys = GEMINI_API_KEYS or ([GEMINI_API_KEY] if GEMINI_API_KEY else [])
    for k in gemini_keys:
        try:
            return await _process_with_gemini(transcript, k)
        except Exception as exc:
            logger.warning("NLP: Gemini key failed (%s). Trying next Gemini key.", exc)

    logger.error("NLP: All Groq and Gemini keys exhausted. Returning UNKNOWN.")
    return NLPResult(intent=Intent.UNKNOWN)


# ─────────────────────────────────────────────────────────────────────────────
#  Provider implementations
# ─────────────────────────────────────────────────────────────────────────────

async def _process_with_groq(transcript: str, api_key: str) -> NLPResult:
    client = AsyncGroq(api_key=api_key)
    last_exc = None
    for model_name in GROQ_CHAT_MODELS:
        try:
            response = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": transcript},
                ],
                response_format={"type": "json_object"},
                temperature=0.05,
                max_tokens=1024,
            )
            raw: str = response.choices[0].message.content or "{}"
            logger.debug("NLP (Groq:%s) raw: %s", model_name, raw)
            return _parse(raw)
        except Exception as exc:
            logger.warning("NLP (Groq:%s) failed (%s). Trying next model in cascade.", model_name, exc)
            last_exc = exc
    raise last_exc or RuntimeError("All Groq models failed")


async def _process_with_gemini(transcript: str, api_key: str) -> NLPResult:
    client = genai.Client(api_key=api_key)
    prompt = f"{_SYSTEM_PROMPT}\n\nUser transcript: {transcript}"
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
                        temperature=0.05,
                    ),
                ),
            )
            raw: str = response.text or "{}"
            logger.debug("NLP (Gemini:%s) raw: %s", model_name, raw)
            return _parse(raw)
        except Exception as exc:
            logger.warning("NLP (Gemini:%s) failed (%s). Trying next Gemini model.", model_name, exc)
            last_exc = exc
    raise last_exc or RuntimeError("All Gemini models failed")


# ─────────────────────────────────────────────────────────────────────────────
#  JSON parser — tolerates partial / malformed LLM output
# ─────────────────────────────────────────────────────────────────────────────

def _parse(raw: str) -> NLPResult:
    try:
        data: dict = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("NLP: JSON decode failed — '%s'", raw)
        return NLPResult(intent=Intent.UNKNOWN)

    # Coerce intent
    try:
        intent = Intent(data.get("intent", "UNKNOWN"))
    except ValueError:
        intent = Intent.UNKNOWN

    # Coerce scalar category
    category: Optional[Category] = None
    cat_str: Optional[str] = data.get("category")
    if cat_str:
        try:
            category = Category(cat_str)
        except ValueError:
            category = None

    # Coerce filter_criteria
    filter_criteria: Optional[FilterCriteria] = None
    fc: Optional[dict] = data.get("filter_criteria")
    if isinstance(fc, dict):
        filter_criteria = FilterCriteria(
            brand=fc.get("brand"),
            max_price=fc.get("max_price"),
            min_price=fc.get("min_price"),
            tags=fc.get("tags") or [],
        )

    # Coerce multi-item `items` array
    items: list[ItemEntity] = []
    raw_items = data.get("items") or []
    if isinstance(raw_items, list):
        for entry in raw_items:
            if not isinstance(entry, dict):
                continue
            name = entry.get("item_name") or entry.get("name")
            if not name:
                continue
            try:
                item_cat = Category(entry.get("category") or "Other")
            except ValueError:
                item_cat = Category.OTHER
            raw_q = entry.get("quantity")
            qty = float(raw_q) if raw_q is not None else None
            items.append(ItemEntity(
                item_name=str(name).lower().strip(),
                quantity=qty,
                unit=entry.get("unit") or None,
                category=item_cat,
            ))

    # Coerce `remove_items` array (for simultaneous add and remove commands)
    remove_items: list[ItemEntity] = []
    raw_remove = data.get("remove_items") or []
    if isinstance(raw_remove, list):
        for entry in raw_remove:
            if not isinstance(entry, dict):
                continue
            name = entry.get("item_name") or entry.get("name")
            if not name:
                continue
            try:
                item_cat = Category(entry.get("category") or "Other")
            except ValueError:
                item_cat = Category.OTHER
            raw_q = entry.get("quantity")
            qty = float(raw_q) if raw_q is not None else None
            remove_items.append(ItemEntity(
                item_name=str(name).lower().strip(),
                quantity=qty,
                unit=entry.get("unit") or None,
                category=item_cat,
            ))

    # Coerce `search_queries` array (for multi-search and compound search queries)
    search_queries: list[SearchQuery] = []
    raw_sq = data.get("search_queries") or []
    if isinstance(raw_sq, list):
        for entry in raw_sq:
            if not isinstance(entry, dict):
                continue
            name = entry.get("item_name") or entry.get("name")
            if not name and not entry.get("brand") and not entry.get("tags"):
                continue
            search_queries.append(SearchQuery(
                item_name=str(name).lower().strip() if name else None,
                brand=entry.get("brand"),
                max_price=float(entry["max_price"]) if entry.get("max_price") is not None else None,
                min_price=float(entry["min_price"]) if entry.get("min_price") is not None else None,
                tags=entry.get("tags") or [],
            ))

    # If no search_queries but SEARCH_FILTER intent or filter_criteria present, synthesize from primary
    if not search_queries and (intent == Intent.SEARCH_FILTER or filter_criteria):
        primary_search = data.get("item_name")
        if primary_search or filter_criteria:
            search_queries.append(SearchQuery(
                item_name=str(primary_search).lower().strip() if primary_search else None,
                brand=filter_criteria.brand if filter_criteria else None,
                max_price=filter_criteria.max_price if filter_criteria else None,
                min_price=filter_criteria.min_price if filter_criteria else None,
                tags=filter_criteria.tags if filter_criteria else [],
            ))

    # For ADD/REMOVE without items array, synthesize from scalar fields or remove_items
    if intent == Intent.REMOVE_ITEM and not items and remove_items:
        items = list(remove_items)
    elif not items and intent in (Intent.ADD_ITEM, Intent.REMOVE_ITEM):
        scalar_name = data.get("item_name")
        if scalar_name:
            raw_q = data.get("quantity")
            items.append(ItemEntity(
                item_name=str(scalar_name).lower().strip(),
                quantity=float(raw_q) if raw_q is not None else (1.0 if intent == Intent.ADD_ITEM else None),
                unit=data.get("unit") or None,
                category=category or Category.OTHER,
            ))

    # Primary item_name
    primary_name = data.get("item_name")
    if not primary_name and items:
        primary_name = items[0].item_name
    elif not primary_name and search_queries:
        primary_name = search_queries[0].item_name

    return NLPResult(
        intent=intent,
        items=items,
        remove_items=remove_items,
        search_queries=search_queries,
        item_name=primary_name,
        quantity=data.get("quantity"),
        unit=data.get("unit"),
        category=category,
        filter_criteria=filter_criteria,
    )
