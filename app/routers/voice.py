"""
Voice Shopping Assistant — API route handlers.

Routes (all prefixed /api/v1):
  POST   /voice-command          — Full pipeline: STT → NLP → cart → suggestions → filter
  GET    /cart                   — Current in-memory shopping list
  DELETE /cart                   — Clear the entire shopping list
  DELETE /cart/{item_name}       — Silently remove one item (no transcript banner)
  GET    /suggestions            — Startup / on-demand personalised suggestions
"""
import logging
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, File, Form, UploadFile, HTTPException

from app.data.mock_db import (
    MOCK_PRODUCT_CATALOG,
    add_item,
    clear_cart,
    get_cart,
    modify_item,
    remove_item,
)
from app.models import (
    CartItem,
    CartResponse,
    Category,
    ClearCartResponse,
    DirectAddItemRequest,
    DirectModifyQtyRequest,
    FilterCriteria,
    Intent,
    NLPResult,
    ProductResult,
    RemoveItemResponse,
    SearchQuery,
    SuggestionResult,
    VoiceCommandResponse,
)
from app.services.catalog_search import search_products, sort_by_price_relevance
from app.services.nlp_engine import process_transcript
from app.services.stt import transcribe
from app.services.suggestions import generate_suggestions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Voice Shopping Assistant"])


# ─────────────────────────────────────────────────────────────────────────────
#  POST /api/v1/voice-command
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/voice-command",
    response_model=VoiceCommandResponse,
    summary="Process a voice command",
    description=(
        "Accepts a live audio file (multipart/form-data) **or** a plain-text "
        "`transcript_override` for testing. Runs the full pipeline: "
        "STT → NLP entity extraction → cart management → smart suggestions → search/filter."
    ),
)
async def voice_command(
    audio: Optional[UploadFile] = File(
        None,
        description="Recorded audio blob from the browser (webm / wav / mp3 / m4a).",
    ),
    transcript_override: Optional[str] = Form(
        None,
        description="Direct text input for testing — bypasses Whisper STT.",
    ),
) -> VoiceCommandResponse:

    # ── 1. Speech-to-Text ────────────────────────────────────────────────────
    if transcript_override and transcript_override.strip():
        transcript: str = transcript_override.strip()
        logger.info("voice_command | transcript_override used: %r", transcript)
    elif audio is not None:
        audio_bytes: bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio payload received.")
        logger.info("voice_command | audio received: %d bytes, filename=%r, content_type=%r", len(audio_bytes), audio.filename, audio.content_type)
        transcript = await transcribe(
            audio=audio_bytes,
            filename=audio.filename or "recording.webm",
            content_type=audio.content_type or "audio/webm",
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either an audio file or a transcript_override field.",
        )

    if not transcript or not transcript.strip():
        logger.info("voice_command | empty or inaudible transcript received.")
        return VoiceCommandResponse(
            transcript="",
            intent=Intent.UNKNOWN,
            message="No speech detected. Please tap the microphone and speak clearly.",
            cart=get_cart(),
            suggestions=await generate_suggestions(None, get_cart()),
            search_results=None,
        )

    # ── 2. NLP Entity & Intent Extraction ────────────────────────────────────
    nlp: NLPResult = await process_transcript(transcript)
    logger.info(
        "voice_command | transcript=%r | intent=%s | items=%d | search_queries=%d | item=%s",
        transcript, nlp.intent, len(nlp.items), len(nlp.search_queries), nlp.item_name,
    )

    # ── 3. Cart / list management (multi-item aware) ─────────────────────────
    message: str = _apply_intent(nlp)

    # ── 4. Smart suggestions (cart-aware) ──────────────────────────────────
    suggestions: SuggestionResult = await generate_suggestions(nlp.item_name, get_cart())

    # ── 5. Search / filter (two-layer & multi-query aware) ───────────────────
    search_results = None
    queries_to_run = list(nlp.search_queries)
    if not queries_to_run and (nlp.intent == Intent.SEARCH_FILTER or nlp.filter_criteria or (nlp.item_name and not nlp.items)):
        if nlp.item_name or nlp.filter_criteria:
            queries_to_run.append(SearchQuery(
                item_name=nlp.item_name,
                brand=nlp.filter_criteria.brand if nlp.filter_criteria else None,
                max_price=nlp.filter_criteria.max_price if nlp.filter_criteria else None,
                min_price=nlp.filter_criteria.min_price if nlp.filter_criteria else None,
                tags=nlp.filter_criteria.tags if nlp.filter_criteria else [],
            ))

    if queries_to_run:
        raw_products: list[ProductResult] = []
        for sq in queries_to_run:
            fc = FilterCriteria(
                brand=sq.brand,
                max_price=sq.max_price,
                min_price=sq.min_price,
                tags=sq.tags,
            )
            res = await search_products(sq.item_name, fc)
            raw_products.extend(res)

        # De-duplicate products by (name, brand)
        seen_keys = set()
        deduped: list[ProductResult] = []
        for prod in raw_products:
            key = (prod.name.lower().strip(), (prod.brand or "").lower().strip())
            if key not in seen_keys:
                seen_keys.add(key)
                deduped.append(prod)
        
        # Sort price-wise (closest to target price first)
        primary_fc = nlp.filter_criteria
        if not primary_fc and queries_to_run:
            first_q = queries_to_run[0]
            primary_fc = FilterCriteria(max_price=first_q.max_price, min_price=first_q.min_price)
        search_results = sort_by_price_relevance(deduped, primary_fc)

    return VoiceCommandResponse(
        transcript=transcript,
        intent=nlp.intent,
        message=message,
        cart=get_cart(),
        suggestions=suggestions,
        search_results=search_results,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  GET /api/v1/cart
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/cart",
    response_model=CartResponse,
    summary="Get the current shopping list",
    description="Returns the full in-memory shopping list with the total item count.",
)
async def get_cart_state() -> CartResponse:
    cart = get_cart()
    return CartResponse(cart=cart, total_items=len(cart))


# ─────────────────────────────────────────────────────────────────────────────
#  POST /api/v1/cart/items  — direct addition for UI buttons (zero LLM overhead)
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/cart/items",
    response_model=CartResponse,
    summary="Directly add or increment a cart item",
    description="Adds an item to the in-memory cart instantly without consuming LLM API tokens.",
)
async def direct_add_item(req: DirectAddItemRequest) -> CartResponse:
    item = CartItem(
        item_name=req.item_name,
        quantity=req.quantity or 1.0,
        unit=req.unit,
        category=req.category or Category.OTHER,
        price_estimate=req.price_estimate,
    )
    add_item(item)
    cart = get_cart()
    return CartResponse(cart=cart, total_items=len(cart))


# ─────────────────────────────────────────────────────────────────────────────
#  PATCH /api/v1/cart/items/{item_name}  — direct quantity modify for UI buttons
# ─────────────────────────────────────────────────────────────────────────────

@router.patch(
    "/cart/items/{item_name}",
    response_model=CartResponse,
    summary="Directly modify quantity of a cart item",
    description="Adjusts or sets quantity directly in-memory without consuming LLM API tokens.",
)
async def direct_modify_qty(item_name: str, req: DirectModifyQtyRequest) -> CartResponse:
    name = unquote(item_name).strip()
    if req.quantity is not None:
        if req.quantity <= 0:
            remove_item(name)
        else:
            modify_item(name, quantity=req.quantity)
    elif req.delta is not None:
        cart = get_cart()
        target = next((c for c in cart if c.item_name.lower() == name.lower()), None)
        if target:
            new_q = float(target.quantity) + req.delta
            if new_q <= 0:
                remove_item(name)
            else:
                modify_item(name, quantity=new_q)
    cart = get_cart()
    return CartResponse(cart=cart, total_items=len(cart))


# ─────────────────────────────────────────────────────────────────────────────
#  DELETE /api/v1/cart/{item_name}  — silent per-item removal for UI buttons
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/cart/{item_name}",
    response_model=RemoveItemResponse,
    summary="Silently remove a single item",
    description=(
        "Removes one item by name. Designed for UI remove buttons — "
        "returns the updated cart WITHOUT triggering a transcript banner."
    ),
)
async def remove_cart_item(item_name: str) -> RemoveItemResponse:
    name = unquote(item_name).strip()
    remove_item(name)          # returns False if not found — that's fine, just silently sync
    cart = get_cart()
    return RemoveItemResponse(success=True, cart=cart, total_items=len(cart))


# ─────────────────────────────────────────────────────────────────────────────
#  DELETE /api/v1/cart  — clear entire list
# ─────────────────────────────────────────────────────────────────────────────

@router.delete(
    "/cart",
    response_model=ClearCartResponse,
    summary="Clear the shopping list",
    description="Removes every item from the in-memory shopping list.",
)
async def clear_cart_state() -> ClearCartResponse:
    clear_cart()
    return ClearCartResponse(message="Shopping list cleared successfully.", cart=[])


# ─────────────────────────────────────────────────────────────────────────────
#  GET /api/v1/suggestions
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/suggestions",
    response_model=SuggestionResult,
    summary="Get startup suggestions",
    description=(
        "Returns personalised suggestions without any audio input: "
        "historical restock items, seasonal picks, and common substitutes. "
        "Designed to pre-populate the UI on first load."
    ),
)
async def get_suggestions() -> SuggestionResult:
    return await generate_suggestions(item_name=None, cart_items=get_cart())


# ─────────────────────────────────────────────────────────────────────────────
#  GET /api/v1/catalog
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/catalog",
    response_model=list[ProductResult],
    summary="Get all store products",
    description="Returns the full store inventory and FMCG product catalog grouped by categories.",
)
async def get_store_catalog() -> list[ProductResult]:
    return MOCK_PRODUCT_CATALOG


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helper — applies NLP intent to in-memory cart (multi-item aware)
# ─────────────────────────────────────────────────────────────────────────────

def _apply_intent(nlp: NLPResult) -> str:
    """Mutate the in-memory cart and return a user-facing message."""

    # ── ADD_ITEM (with optional simultaneous removals) ────────────────────────
    if nlp.intent == Intent.ADD_ITEM:
        # 1. Execute any simultaneous removals
        simul_removed: list[str] = []
        if nlp.remove_items:
            for rem_entity in nlp.remove_items:
                explicit_qty = rem_entity.quantity
                found = remove_item(rem_entity.item_name, explicit_qty, unit=rem_entity.unit)
                if found:
                    if explicit_qty:
                        simul_removed.append(f"Reduced: {_fmt_qty(explicit_qty, rem_entity.unit)} {rem_entity.item_name}")
                    else:
                        simul_removed.append(f"Removed: {rem_entity.item_name}")

        # 2. Execute additions
        added_labels: list[str] = []
        for entity in nlp.items:
            cart_item = CartItem(
                item_name=entity.item_name,
                quantity=entity.quantity or 1.0,
                unit=entity.unit,
                category=entity.category,
            )
            result = add_item(cart_item)
            qty_str = _fmt_qty(result.quantity, result.unit)
            added_labels.append(f"{qty_str} {result.item_name}")

        if not added_labels and not simul_removed:
            return "I couldn't identify any items to add. Please say something like 'Add 2 litres of milk'."

        msg_parts: list[str] = []
        if added_labels:
            if len(added_labels) == 1:
                msg_parts.append(f"✅ Added {added_labels[0]} to your list.")
            else:
                msg_parts.append(f"✅ Added {len(added_labels)} items: {', '.join(added_labels)}.")
        if simul_removed:
            msg_parts.extend(simul_removed)
        if nlp.search_queries:
            sq_names = [f"{sq.item_name or 'products'}{f' (<${sq.max_price:.2f})' if sq.max_price is not None else ''}" for sq in nlp.search_queries]
            msg_parts.append(f"🔍 Searching for: {', '.join(sq_names)}")
        return " · ".join(msg_parts) or "Done."

    # ── REMOVE_ITEM ──────────────────────────────────────────────────────────
    if nlp.intent == Intent.REMOVE_ITEM:
        clear_keywords = {"all", "everything", "all items", "cart", "shopping list", "sab", "pura", "puri", "pura cart", "puri cart", "empty", "clear"}
        target_entities = nlp.items or nlp.remove_items

        # Check if user specifically requested clearing all items
        target_names = {e.item_name.lower().strip() for e in target_entities if e.item_name}
        if nlp.item_name:
            target_names.add(nlp.item_name.lower().strip())

        if target_names and target_names.issubset(clear_keywords):
            clear_cart()
            return "🗑️ Cleared your entire shopping list."

        if not target_entities:
            return "I couldn't identify any items to remove. Please say 'Remove milk' for example."

        removed: list[str] = []
        reduced: list[str] = []
        not_found: list[str] = []
        for entity in target_entities:
            explicit_qty = entity.quantity  # None = full remove; float = partial reduction
            found = remove_item(entity.item_name, explicit_qty, unit=entity.unit)
            if found:
                if explicit_qty:
                    reduced.append(f"{_fmt_qty(explicit_qty, entity.unit)} {entity.item_name}")
                else:
                    removed.append(entity.item_name)
            else:
                not_found.append(entity.item_name)

        parts: list[str] = []
        if removed:
            parts.append(f"Removed: {', '.join(removed)}")
        if reduced:
            parts.append(f"Reduced: {', '.join(reduced)}")
        if not_found:
            parts.append(f"Not found: {', '.join(not_found)}")
        return " · ".join(parts) or "Nothing was removed."

    # ── MODIFY_QUANTITY ──────────────────────────────────────────────────────
    if nlp.intent == Intent.MODIFY_QUANTITY:
        name = nlp.item_name or (nlp.items[0].item_name if nlp.items else None)
        qty  = nlp.quantity  or (nlp.items[0].quantity  if nlp.items else None)
        unit = nlp.unit or (nlp.items[0].unit if nlp.items else None)
        cat  = nlp.category or (nlp.items[0].category if nlp.items else Category.OTHER)
        if not name or qty is None:
            return "Please specify both the item name and the new quantity."
        result = modify_item(name, qty, unit=unit)
        if result:
            return f"✅ Updated '{name}' to {_fmt_qty(result.quantity, result.unit)}."
        # Item not in cart — upsert (add it)
        new_item = CartItem(item_name=name, quantity=qty, unit=unit, category=cat)
        add_item(new_item)
        return f"✅ Added '{name}' ({_fmt_qty(qty, unit)}) to your list."

    # ── SEARCH_FILTER ─────────────────────────────────────────────────────────
    if nlp.intent == Intent.SEARCH_FILTER:
        if nlp.search_queries and len(nlp.search_queries) > 1:
            q_strs = []
            for sq in nlp.search_queries:
                p = [sq.item_name or "items"]
                if sq.max_price is not None: p.append(f"under ${sq.max_price:.2f}")
                if sq.min_price is not None: p.append(f"above ${sq.min_price:.2f}")
                if sq.brand: p.append(f"brand: {sq.brand}")
                if sq.tags: p.append(f"tags: {', '.join(sq.tags)}")
                q_strs.append(" ".join(p))
            return f"🔍 Searching for {' · '.join(q_strs)}."

        parts = [nlp.item_name or "items"]
        fc = nlp.filter_criteria
        if fc:
            if fc.brand:          parts.append(f"brand: {fc.brand}")
            if fc.max_price is not None: parts.append(f"under ${fc.max_price:.2f}")
            if fc.min_price is not None: parts.append(f"above ${fc.min_price:.2f}")
            if fc.tags:           parts.append(f"tags: {', '.join(fc.tags)}")
        return f"🔍 Searching for {' | '.join(parts)}."

    # ── GET_SUGGESTIONS ───────────────────────────────────────────────────────
    if nlp.intent == Intent.GET_SUGGESTIONS:
        return "✨ Here are your personalised shopping suggestions."

    return "I didn't understand that command. Please try again with a clearer phrase."


def _fmt_qty(quantity: float, unit: Optional[str]) -> str:
    qty_str = str(int(quantity)) if quantity == int(quantity) else str(quantity)
    return f"{qty_str} {unit}" if unit else qty_str
