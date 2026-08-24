"""
Pydantic data models enforcing strict schema for:
  - LLM JSON extraction  (NLPResult, Intent, FilterCriteria)
  - Shopping list state  (CartItem, Category)
  - Smart suggestions    (SuggestionResult, SubstitutePair)
  - Search results       (ProductResult)
  - API responses        (VoiceCommandResponse, CartResponse, ClearCartResponse)
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
#  Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class Intent(str, Enum):
    """Six discrete user intents extracted by the NLP engine."""
    ADD_ITEM = "ADD_ITEM"
    REMOVE_ITEM = "REMOVE_ITEM"
    MODIFY_QUANTITY = "MODIFY_QUANTITY"
    SEARCH_FILTER = "SEARCH_FILTER"
    GET_SUGGESTIONS = "GET_SUGGESTIONS"
    UNKNOWN = "UNKNOWN"


class Category(str, Enum):
    """Automatic item categorisation labels."""
    DAIRY = "Dairy"
    PRODUCE = "Produce"
    SNACKS = "Snacks"
    BEVERAGES = "Beverages"
    PANTRY = "Pantry"
    OTHER = "Other"


# ─────────────────────────────────────────────────────────────────────────────
#  Core domain models
# ─────────────────────────────────────────────────────────────────────────────

class FilterCriteria(BaseModel):
    """Search/filter parameters extracted from a SEARCH_FILTER voice command."""
    brand: Optional[str] = None
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    tags: List[str] = Field(default_factory=list)  # e.g. ["organic", "vegan"]


class CartItem(BaseModel):
    """A single item in the shopping list with quantity, unit, and category."""
    item_name: str
    quantity: float = Field(default=1.0, gt=0, description="Must be positive")
    unit: Optional[str] = None           # e.g. "bottles", "kg", "pack", "dozen"
    category: Category = Category.OTHER
    price_estimate: Optional[float] = None


class ItemEntity(BaseModel):
    """A single item entity in a multi-item voice command."""
    item_name: str
    quantity: Optional[float] = Field(default=None, description="Explicit quantity if mentioned; None means unquantified (full removal or default 1 add)")
    unit: Optional[str] = None
    category: Category = Category.OTHER


class SearchQuery(BaseModel):
    """An individual search and filter query target."""
    item_name: Optional[str] = None
    brand: Optional[str] = None
    max_price: Optional[float] = None
    min_price: Optional[float] = None
    tags: List[str] = Field(default_factory=list)


class NLPResult(BaseModel):
    """
    Strict JSON extraction output from the LLM NLP engine.
    `items` carries items to ADD or primary items.
    `remove_items` carries items to REMOVE for simultaneous add/remove commands.
    `search_queries` carries one or more search/filter targets.
    `item_name` carries the primary item for SEARCH_FILTER/GET_SUGGESTIONS.
    """
    intent: Intent = Intent.UNKNOWN
    items: List[ItemEntity] = Field(default_factory=list)          # items to ADD
    remove_items: List[ItemEntity] = Field(default_factory=list)   # items to REMOVE
    search_queries: List[SearchQuery] = Field(default_factory=list) # multi-query search targets
    item_name: Optional[str] = None   # primary item for search/suggestions
    quantity: Optional[float] = None
    unit: Optional[str] = None
    category: Optional[Category] = None
    filter_criteria: Optional[FilterCriteria] = None


# ─────────────────────────────────────────────────────────────────────────────
#  Suggestion models
# ─────────────────────────────────────────────────────────────────────────────

class SubstitutePair(BaseModel):
    """A smart substitute suggestion with a human-readable reason."""
    original: str
    substitute: str
    reason: str


class SuggestionResult(BaseModel):
    """LLM-generated smart suggestions returned on every voice command."""
    historical_recommendations: List[str] = Field(default_factory=list)
    seasonal_recommendations: List[str] = Field(default_factory=list)
    substitutes: List[SubstitutePair] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
#  Search / catalog model
# ─────────────────────────────────────────────────────────────────────────────

class ProductResult(BaseModel):
    """A product entry from the mock catalog returned on SEARCH_FILTER intent."""
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    price: Optional[float] = None
    tags: List[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
#  API response envelopes
# ─────────────────────────────────────────────────────────────────────────────

class VoiceCommandResponse(BaseModel):
    """Full response envelope for POST /api/v1/voice-command."""
    transcript: str
    intent: Intent
    message: str
    cart: List[CartItem]
    suggestions: SuggestionResult
    search_results: Optional[List[ProductResult]] = None


class CartResponse(BaseModel):
    """Response for GET /api/v1/cart."""
    cart: List[CartItem]
    total_items: int


class ClearCartResponse(BaseModel):
    """Response for DELETE /api/v1/cart."""
    message: str
    cart: List[CartItem]


class RemoveItemResponse(BaseModel):
    """Response for DELETE /api/v1/cart/{item_name} — silent UI remove."""
    success: bool
    cart: List[CartItem]
    total_items: int


class DirectAddItemRequest(BaseModel):
    """Request schema for direct UI item addition without LLM overhead."""
    item_name: str
    quantity: float = Field(default=1.0, gt=0)
    unit: Optional[str] = None
    category: Optional[Category] = None
    price_estimate: Optional[float] = None


class DirectModifyQtyRequest(BaseModel):
    """Request schema for direct UI quantity increment/decrement/set."""
    delta: Optional[float] = None
    quantity: Optional[float] = None
