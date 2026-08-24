"""
In-memory state management.

Provides:
  - Shopping list CRUD  (add, remove, modify, get, clear)
  - Mock user purchase history for suggestion context
  - Mock product catalog with catalog search / filter logic
"""
from typing import Dict, List, Optional

from app.models import CartItem, FilterCriteria, ProductResult


# ─────────────────────────────────────────────────────────────────────────────
#  In-memory shopping list  (keyed by normalised item name)
# ─────────────────────────────────────────────────────────────────────────────

_shopping_list: Dict[str, CartItem] = {}


# ─────────────────────────────────────────────────────────────────────────────
#  Mock user purchase history
# ─────────────────────────────────────────────────────────────────────────────

PURCHASE_HISTORY: List[str] = [
    "whole milk",
    "bread",
    "eggs",
    "orange juice",
    "greek yogurt",
    "chicken breast",
    "pasta",
    "olive oil",
    "tomatoes",
    "bananas",
    "cheddar cheese",
    "coffee",
    "oats",
    "spinach",
    "butter",
]


# ─────────────────────────────────────────────────────────────────────────────
#  Mock product catalog  (simulates a store inventory)
# ─────────────────────────────────────────────────────────────────────────────

MOCK_PRODUCT_CATALOG: List[ProductResult] = [
    # ── Fresh Fruits (Produce) ───────────────────────────────────────────────
    ProductResult(name="alphonso mango",         brand="Farm Fresh",     category="Produce",       price=1.19,  tags=["fruit", "fresh", "seasonal", "mango", "sweet"]),
    ProductResult(name="kesar mango",           brand="Gir Kesar",      category="Produce",       price=0.99,  tags=["fruit", "fresh", "seasonal", "mango"]),
    ProductResult(name="organic apples",        brand="Nature's Best",  category="Produce",       price=3.99,  tags=["organic", "fruit", "fresh", "apple"]),
    ProductResult(name="royal gala apples",     brand="Washington",     category="Produce",       price=2.49,  tags=["fruit", "fresh", "apple"]),
    ProductResult(name="banana",                 brand="Chiquita",       category="Produce",       price=0.29,  tags=["fruit", "fresh", "potassium"]),
    ProductResult(name="orange",                 brand="Valencia",       category="Produce",       price=0.49,  tags=["fruit", "citrus", "vitamin c"]),
    ProductResult(name="fresh strawberries",    brand="Driscoll's",     category="Produce",       price=3.49,  tags=["fruit", "berries", "fresh"]),
    ProductResult(name="watermelon",            brand="Local Orchard",  category="Produce",       price=2.99,  tags=["fruit", "summer", "hydration"]),
    ProductResult(name="pineapple",             brand="Dole",           category="Produce",       price=2.49,  tags=["fruit", "tropical", "fresh"]),
    ProductResult(name="papaya",                brand="Organic Harvest",category="Produce",       price=1.49,  tags=["fruit", "tropical", "digestive"]),
    ProductResult(name="green grapes",          brand="Sun World",      category="Produce",       price=2.29,  tags=["fruit", "seedless", "fresh"]),
    ProductResult(name="pomegranate",           brand="Ruby",           category="Produce",       price=1.89,  tags=["fruit", "antioxidant", "fresh"]),
    ProductResult(name="avocado",               brand="Hass",           category="Produce",       price=1.99,  tags=["fruit", "healthy fat", "organic"]),
    ProductResult(name="lemons pack",           brand="Sunkist",        category="Produce",       price=1.29,  tags=["citrus", "cooking", "vitamin c"]),
    ProductResult(name="frozen mixed berries",  brand="Wyman's",        category="Produce",       price=5.99,  tags=["fruit", "frozen", "antioxidant"]),

    # ── Fresh Vegetables (Produce) ──────────────────────────────────────────
    ProductResult(name="red tomatoes",          brand="Farm Fresh",     category="Produce",       price=0.89,  tags=["vegetable", "fresh", "cooking"]),
    ProductResult(name="yellow onions",         brand="Fresh Produce",  category="Produce",       price=0.69,  tags=["vegetable", "staple", "cooking"]),
    ProductResult(name="russet potatoes",       brand="Idaho",          category="Produce",       price=0.79,  tags=["vegetable", "staple", "carb"]),
    ProductResult(name="baby spinach",          brand="Earthbound Farm",category="Produce",       price=4.99,  tags=["organic", "vegetable", "leafy green"]),
    ProductResult(name="broccoli florets",      brand="Green Giant",    category="Produce",       price=1.99,  tags=["vegetable", "green", "healthy"]),
    ProductResult(name="fresh carrots",         brand="Bunny Luv",      category="Produce",       price=1.19,  tags=["vegetable", "crunchy", "vitamin a"]),
    ProductResult(name="english cucumber",      brand="Euro Fresh",     category="Produce",       price=0.99,  tags=["vegetable", "salad", "hydration"]),
    ProductResult(name="green capsicum",        brand="Local Farm",     category="Produce",       price=0.89,  tags=["vegetable", "bell pepper", "crunchy"]),
    ProductResult(name="cauliflower",           brand="Fresh Fields",   category="Produce",       price=1.49,  tags=["vegetable", "cruciferous", "cooking"]),
    ProductResult(name="fresh ginger",          brand="Spice Harvest",  category="Produce",       price=0.59,  tags=["root", "aromatic", "spices"]),
    ProductResult(name="fresh garlic",          brand="Spice Harvest",  category="Produce",       price=0.69,  tags=["allium", "aromatic", "cooking"]),
    ProductResult(name="green chilies",         brand="Desi Farms",     category="Produce",       price=0.39,  tags=["spicy", "chili", "cooking"]),
    ProductResult(name="fresh coriander",       brand="Desi Farms",     category="Produce",       price=0.49,  tags=["herbs", "fresh", "garnish"]),

    # ── Dairy & Plant Milks ──────────────────────────────────────────────────
    ProductResult(name="organic whole milk",     brand="Horizon Organic",category="Dairy",         price=4.99,  tags=["organic", "dairy", "fresh", "milk"]),
    ProductResult(name="whole milk",             brand="Amul",           category="Dairy",         price=2.49,  tags=["dairy", "fresh", "milk"]),
    ProductResult(name="toned milk",             brand="Mother Dairy",   category="Dairy",         price=1.99,  tags=["dairy", "low-fat", "milk"]),
    ProductResult(name="almond milk",            brand="Silk",           category="Dairy",         price=4.49,  tags=["dairy-free", "vegan", "milk"]),
    ProductResult(name="oat milk",               brand="Oatly",          category="Dairy",         price=5.99,  tags=["dairy-free", "vegan", "milk"]),
    ProductResult(name="greek yogurt",           brand="Chobani",        category="Dairy",         price=1.99,  tags=["dairy", "probiotic", "protein"]),
    ProductResult(name="fresh paneer",          brand="Amul",           category="Dairy",         price=2.29,  tags=["dairy", "cottage cheese", "protein"]),
    ProductResult(name="cheddar cheese",         brand="Kraft",          category="Dairy",         price=5.49,  tags=["dairy", "cheese"]),
    ProductResult(name="butter salted",          brand="Amul",           category="Dairy",         price=1.89,  tags=["dairy", "spread", "cooking"]),
    ProductResult(name="free-range eggs",        brand="Happy Egg",      category="Dairy",         price=4.99,  tags=["protein", "fresh", "free-range", "eggs"]),
    ProductResult(name="fresh dahi curd",        brand="Amul",           category="Dairy",         price=1.29,  tags=["dairy", "probiotic", "curd"]),

    # ── Bakery & Grains (Pantry) ─────────────────────────────────────────────
    ProductResult(name="whole wheat bread",      brand="Nature's Own",   category="Pantry",        price=3.79,  tags=["bread", "whole grain", "bakery"]),
    ProductResult(name="multigrain bread",       brand="Modern",         category="Pantry",        price=1.99,  tags=["bread", "multigrain", "bakery"]),
    ProductResult(name="whole wheat aata",       brand="Aashirvaad",     category="Pantry",        price=4.99,  tags=["flour", "staple", "wheat", "aata"]),
    ProductResult(name="basmati rice",           brand="India Gate",     category="Pantry",        price=6.49,  tags=["rice", "grain", "premium", "staple"]),
    ProductResult(name="brown rice",             brand="Lundberg",       category="Pantry",        price=4.29,  tags=["grain", "gluten-free", "healthy"]),
    ProductResult(name="rolled oats",            brand="Quaker",         category="Pantry",        price=2.99,  tags=["breakfast", "fiber", "oats"]),
    ProductResult(name="yellow moong dal",       brand="Tata Sampann",   category="Pantry",        price=2.49,  tags=["lentils", "protein", "dal"]),
    ProductResult(name="toor dal",               brand="Tata Sampann",   category="Pantry",        price=2.79,  tags=["lentils", "protein", "staple"]),
    ProductResult(name="pasta penne",            brand="Barilla",        category="Pantry",        price=1.49,  tags=["grain", "italian", "pasta"]),

    # ── Spices, Oils & Condiments (Pantry) ───────────────────────────────────
    ProductResult(name="extra virgin olive oil", brand="Kirkland",       category="Pantry",        price=12.99, tags=["cooking", "oil", "healthy fat"]),
    ProductResult(name="sunflower cooking oil",  brand="Fortune",        category="Pantry",        price=3.99,  tags=["cooking", "oil", "refined"]),
    ProductResult(name="turmeric powder",        brand="MDH",            category="Pantry",        price=0.99,  tags=["spices", "haldi", "immunity"]),
    ProductResult(name="red chili powder",       brand="Everest",        category="Pantry",        price=1.19,  tags=["spices", "chili", "hot"]),
    ProductResult(name="garam masala",           brand="Everest",        category="Pantry",        price=1.49,  tags=["spices", "aromatic", "blend"]),
    ProductResult(name="chicken masala",         brand="MDH",            category="Pantry",        price=1.29,  tags=["spices", "chicken", "blend"]),
    ProductResult(name="mutton masala",          brand="Everest",        category="Pantry",        price=1.39,  tags=["spices", "mutton", "blend"]),
    ProductResult(name="iodized table salt",     brand="Tata Salt",      category="Pantry",        price=0.49,  tags=["staple", "seasoning", "salt"]),
    ProductResult(name="refined white sugar",    brand="Madhur",         category="Pantry",        price=1.19,  tags=["staple", "sweetener", "sugar"]),
    ProductResult(name="tomato ketchup",         brand="Heinz",          category="Pantry",        price=2.49,  tags=["condiment", "sauce", "ketchup"]),
    ProductResult(name="pasta tomato sauce",     brand="Rao's",          category="Pantry",        price=8.49,  tags=["sauce", "italian", "canned"]),

    # ── Meat & Poultry ───────────────────────────────────────────────────────
    ProductResult(name="chicken breast boneless",brand="Pilgrim's",      category="Meat",          price=8.99,  tags=["protein", "fresh", "meat", "chicken"]),
    ProductResult(name="fresh whole chicken",    brand="Perdue",         category="Meat",          price=6.99,  tags=["meat", "poultry", "fresh"]),
    ProductResult(name="chicken curry cut",      brand="Fresh Farms",    category="Meat",          price=4.99,  tags=["meat", "chicken", "curry"]),
    ProductResult(name="mutton curry cut",       brand="Premium Meats",  category="Meat",          price=9.99,  tags=["meat", "mutton", "red meat"]),
    ProductResult(name="fresh salmon fillet",    brand="Ocean Catch",    category="Meat",          price=11.99, tags=["fish", "seafood", "omega-3"]),

    # ── Beverages ────────────────────────────────────────────────────────────
    ProductResult(name="orange juice",           brand="Tropicana",      category="Beverages",     price=4.29,  tags=["juice", "fruit", "fresh", "breakfast"]),
    ProductResult(name="dole mango juice 1l",    brand="Dole",           category="Beverages",     price=3.99,  tags=["juice", "mango", "fruit", "drink"]),
    ProductResult(name="tropicana mango juice 1l",brand="Tropicana",     category="Beverages",     price=4.49,  tags=["juice", "mango", "fruit"]),
    ProductResult(name="pure coconut water",     brand="Vita Coco",      category="Beverages",     price=3.99,  tags=["hydration", "natural", "electrolytes"]),
    ProductResult(name="instant coffee classic", brand="Nescafe",        category="Beverages",     price=7.99,  tags=["hot drink", "caffeine", "coffee"]),
    ProductResult(name="green tea pure",         brand="Lipton",         category="Beverages",     price=3.29,  tags=["tea", "healthy", "antioxidant"]),
    ProductResult(name="premium black tea",      brand="Tata Tea Gold",  category="Beverages",     price=4.49,  tags=["tea", "chai", "hot drink"]),
    ProductResult(name="sparkling mineral water",brand="Perrier",        category="Beverages",     price=2.19,  tags=["water", "sparkling", "refreshing"]),

    # ── Snacks & Confectionery ───────────────────────────────────────────────
    ProductResult(name="classic potato chips",   brand="Lay's",          category="Snacks",        price=1.49,  tags=["snack", "chips", "crunchy"]),
    ProductResult(name="masala munch snacks",    brand="Kurkure",        category="Snacks",        price=0.99,  tags=["snack", "spicy", "desi"]),
    ProductResult(name="nacho cheese chips",     brand="Doritos",        category="Snacks",        price=2.49,  tags=["snack", "chips", "cheese"]),
    ProductResult(name="bourbon chocolate biscuits",brand="Britannia",   category="Snacks",        price=1.19,  tags=["cookies", "chocolate", "sweet"]),
    ProductResult(name="roasted mixed nuts",     brand="Planters",       category="Snacks",        price=8.99,  tags=["snack", "protein", "healthy", "nuts"]),
    ProductResult(name="dark chocolate 70%",     brand="Lindt",          category="Snacks",        price=4.49,  tags=["snack", "chocolate", "antioxidant"]),

    # ── Personal Care & Household ────────────────────────────────────────────
    ProductResult(name="total toothpaste",       brand="Colgate",        category="Personal Care", price=3.49,  tags=["hygiene", "dental", "toothpaste"]),
    ProductResult(name="sensitive repair toothpaste",brand="Sensodyne",  category="Personal Care", price=6.99,  tags=["hygiene", "dental", "sensitive"]),
    ProductResult(name="beauty moisture bar soap",brand="Lux",           category="Personal Care", price=1.29,  tags=["soap", "skincare", "bath"]),
    ProductResult(name="antibacterial liquid handwash",brand="Dettol",   category="Personal Care", price=2.19,  tags=["hygiene", "handwash", "protection"]),
    ProductResult(name="anti-dandruff shampoo",  brand="Head & Shoulders",category="Personal Care",price=5.99,  tags=["haircare", "shampoo", "shower"]),
    ProductResult(name="dishwash liquid gel",    brand="Pril",           category="Personal Care", price=2.49,  tags=["cleaning", "kitchen", "household"]),
]


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalise(name: str) -> str:
    return name.strip().lower()


def _stem(word: str) -> str:
    """Normalize English plurals (apples -> apple, mangoes -> mango, berries -> berry)."""
    w = word.strip().lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("es") and len(w) > 4:
        if w.endswith(("ses", "xes", "zes", "ches", "shes", "toes", "goes")):
            return w[:-2]
        return w[:-1]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w


def _make_key(name: str, unit: Optional[str] = None) -> str:
    norm_name = _stem(_normalise(name))
    norm_unit = unit.strip().lower() if unit else ""
    # Standardize piece/count aliases to default key
    if norm_unit in ("", "piece", "pieces", "count", "nag", "unit", "units"):
        return norm_name
    return f"{norm_name}::{norm_unit}"


def _find_matching_keys(name: str, unit: Optional[str] = None) -> List[str]:
    """
    Find cart keys that match the given item name with exact, stem, or word-boundary priority.
    Prioritizes exact matches to prevent removing unintended items.
    """
    norm_name = _normalise(name)
    stemmed_query = _stem(norm_name)
    target_key = _make_key(name, unit) if unit else None

    # 1. Exact key match (e.g., exact unit + name)
    if target_key and target_key in _shopping_list:
        return [target_key]
    if norm_name in _shopping_list:
        return [norm_name]
    if stemmed_query in _shopping_list:
        return [stemmed_query]

    # 2. Key prefix match (e.g. "mango::kg" matching "mango")
    exact_prefix = [k for k in _shopping_list if k == stemmed_query or k.startswith(f"{stemmed_query}::")]
    if exact_prefix:
        return exact_prefix

    # 3. Stemmed match (e.g. "mangoes" matching "mango", "apples" matching "apple")
    stemmed_matches = []
    for k in _shopping_list:
        base_item = k.split("::")[0]
        if _stem(base_item) == stemmed_query:
            stemmed_matches.append(k)
    if stemmed_matches:
        return stemmed_matches

    # 4. Word boundary / substring match (e.g. "milk" matching "whole milk")
    # Only if exact/stem was not found
    word_matches = []
    for k in _shopping_list:
        base_item = k.split("::")[0]
        if norm_name in base_item or base_item in norm_name or stemmed_query in _stem(base_item):
            word_matches.append(k)
    return word_matches


# ─────────────────────────────────────────────────────────────────────────────
#  Shopping list CRUD
# ─────────────────────────────────────────────────────────────────────────────

def add_item(item: CartItem) -> CartItem:
    """
    Add an item to the cart.
    If the item already exists with the same unit (or stem), its quantity is accumulated.
    Different units (e.g. 10 pieces vs 1 kg) remain distinct entries.
    """
    key = _make_key(item.item_name, item.unit)
    if key in _shopping_list:
        existing = _shopping_list[key]
        existing.quantity = round(existing.quantity + (item.quantity or 1.0), 2)
        return existing
    _shopping_list[key] = item
    return item


def remove_item(item_name: str, qty: Optional[float] = None, unit: Optional[str] = None) -> bool:
    """
    Remove an item by name with exact-priority matching.
    - If `qty` is None  → remove the entry.
    - If `qty` is given → reduce quantity by that amount; delete only when qty ≤ 0.
    Returns True if the item was found and acted upon, False if not found.
    """
    keys_to_check = _find_matching_keys(item_name, unit)
    if not keys_to_check:
        return False

    key = keys_to_check[0]
    if qty is None:
        del _shopping_list[key]
        return True
    existing = _shopping_list[key]
    existing.quantity = round(existing.quantity - qty, 2)
    if existing.quantity <= 0:
        del _shopping_list[key]
    return True


def modify_item(item_name: str, quantity: float, unit: Optional[str] = None) -> Optional[CartItem]:
    """Update the quantity of an existing item with exact-priority matching."""
    keys_to_check = _find_matching_keys(item_name, unit)
    if keys_to_check:
        key = keys_to_check[0]
        _shopping_list[key].quantity = round(quantity, 2)
        if unit:
            _shopping_list[key].unit = unit
        return _shopping_list[key]
    return None


def get_cart() -> List[CartItem]:
    """Return the full shopping list as an ordered list."""
    return list(_shopping_list.values())


def clear_cart() -> None:
    """Remove all items from the shopping list."""
    _shopping_list.clear()


# ─────────────────────────────────────────────────────────────────────────────
#  Catalog search
# ─────────────────────────────────────────────────────────────────────────────

def search_catalog(
    item_name: Optional[str] = None,
    filter_criteria: Optional[FilterCriteria] = None,
) -> List[ProductResult]:
    """
    Filter the mock product catalog by name, brand, price range, and tags.
    All filters are applied cumulatively (AND logic).
    """
    results: List[ProductResult] = MOCK_PRODUCT_CATALOG.copy()

    if item_name:
        query = _normalise(item_name)
        results = [p for p in results if query in p.name.lower()]

    if filter_criteria:
        if filter_criteria.brand:
            brand_q = filter_criteria.brand.lower()
            results = [p for p in results if p.brand and brand_q in p.brand.lower()]

        if filter_criteria.max_price is not None:
            results = [p for p in results if p.price is not None and p.price <= filter_criteria.max_price]

        if filter_criteria.min_price is not None:
            results = [p for p in results if p.price is not None and p.price >= filter_criteria.min_price]

        if filter_criteria.tags:
            filter_tags = {t.lower() for t in filter_criteria.tags}
            results = [p for p in results if filter_tags.intersection({t.lower() for t in p.tags})]

    return results
