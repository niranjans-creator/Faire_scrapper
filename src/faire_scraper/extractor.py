"""
Pure parsing logic (no browser) so it can be unit-tested offline.

Faire's page structure is not documented and changes over time. Extraction
therefore searches embedded JSON (Next.js state, JSON-LD, window state) for
likely key names. If a column comes back empty on real pages, inspect one page
in DevTools and add the real key names to KEYS below.
"""
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable, List, Optional

from .models import Product, Variant
from .utils import parse_int, parse_price

KEYS = {
    "name": ["name", "title", "product_name", "productName"],
    "brand": ["brand_name", "brandName", "brand"],
    "images": ["images", "image", "image_urls", "imageUrls", "product_images"],
    "sku": ["sku", "SKU", "sku_id", "skuId"],
    "wholesale_cents": ["wholesale_price_cents", "wholesalePriceCents"],
    "wholesale": ["wholesale_price", "wholesalePrice"],
    "msrp_cents": ["retail_price_cents", "retailPriceCents", "msrp_cents", "msrpCents"],
    "msrp": ["retail_price", "retailPrice", "msrp"],
    "item_quantity": ["item_quantity", "itemQuantity", "quantity", "itemCount", "unitsPerItem"],
    "weight": ["weight", "weight_unit_value", "product_weight", "productWeight"],
    "dimensions": ["dimensions", "measurements", "product_dimensions"],
    "details": ["details", "description", "product_description", "productDescription", "longDescription"],
    "country_of_origin": ["country_of_origin", "countryOfOrigin", "country_of_origin_name"],
    "ingredients": ["ingredients", "ingredient_list", "active_ingredients", "productIngredients"],
    "min_order_qty": ["min_order_quantity", "minOrderQuantity", "per_style_min_order_quantity"],
    "availability": ["availability", "availability_status", "availabilityStatus", "orderable"],
    "category": ["category", "category_name", "categoryName", "taxonomy", "breadcrumbs"],
}

EMPTY = (None, "", [], {})


def walk(obj: Any) -> Iterable:
    """Yield (key, value) for every dict entry in a nested structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from walk(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk(item)


def find_first(blobs: List[Any], candidates: List[str]) -> Any:
    """Honour candidate priority: try each key name across all blobs in order."""
    for cand in candidates:
        for blob in blobs:
            for k, v in walk(blob):
                if k == cand and v not in EMPTY:
                    return v
    return None


def _name_of(v: Any) -> Optional[str]:
    if isinstance(v, dict):
        return v.get("name") or v.get("title")
    if isinstance(v, str):
        return v
    return None


def flatten_images(v: Any) -> List[str]:
    out: List[str] = []
    if isinstance(v, str):
        out.append(v)
    elif isinstance(v, list):
        for i in v:
            out.extend(flatten_images(i))
    elif isinstance(v, dict):
        u = v.get("url") or v.get("src") or v.get("image_url") or v.get("imageUrl")
        if u:
            out.append(u)
    return list(dict.fromkeys(u for u in out if isinstance(u, str) and u.startswith("http")))


def category_text(v: Any) -> Optional[str]:
    if isinstance(v, list):
        names = [_name_of(i) for i in v]
        names = [n for n in names if n]
        return " > ".join(names) if names else None
    return _name_of(v)


def scalar_text(v: Any) -> Optional[str]:
    if v in EMPTY:
        return None
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def price_from(blobs, cents_keys, plain_keys) -> Optional[float]:
    cents = parse_price(find_first(blobs, cents_keys))
    if cents is not None:
        return round(cents / 100, 2)
    return parse_price(find_first(blobs, plain_keys))


def variants_from(blobs: List[Any], hints: dict, default_min_qty: Optional[int]) -> List[Variant]:
    """Build one Variant per visible size/option, preferring structured data."""
    variants: List[Variant] = []
    for item in hints.get("variants", []):
        variants.append(Variant(
            size_or_variant=item.get("size_or_variant"),
            sku=item.get("sku"),
            wholesale_price=item.get("wholesale_price"),
            msrp=item.get("msrp"),
            price_per_size=item.get("price_per_size"),
            case_pack_qty=item.get("case_pack_qty"),
            item_quantity=item.get("item_quantity"),
            min_order_qty=item.get("min_order_qty", default_min_qty),
            availability=item.get("availability"),
        ))
    if variants:
        return variants
    options = find_first(blobs, ["options", "variants", "product_options"])
    if isinstance(options, list):
        for option in options:
            if not isinstance(option, dict):
                continue
            label = (option.get("size") or option.get("name") or option.get("title")
                     or option.get("display_name"))
            if label:
                variants.append(Variant(
                    size_or_variant=scalar_text(label),
                    sku=scalar_text(option.get("sku") or option.get("skuId")),
                    wholesale_price=price_from([option], KEYS["wholesale_cents"], KEYS["wholesale"]),
                    msrp=price_from([option], KEYS["msrp_cents"], KEYS["msrp"]),
                    min_order_qty=parse_int(find_first([option], KEYS["min_order_qty"])) or default_min_qty,
                    item_quantity=parse_int(option.get("item_quantity") or option.get("itemQuantity")),
                ))
    return variants


def build_product(blobs: List[Any], url: str, dom_hints: Optional[dict] = None) -> Product:
    """dom_hints: optional fallbacks scraped from visible page text."""
    h = dom_hints or {}
    images = flatten_images(find_first(blobs, KEYS["images"])) or h.get("images", [])
    wholesale = price_from(blobs, KEYS["wholesale_cents"], KEYS["wholesale"])
    msrp = price_from(blobs, KEYS["msrp_cents"], KEYS["msrp"])
    min_order_qty = parse_int(find_first(blobs, KEYS["min_order_qty"]) or h.get("min_order_qty"))
    variants = variants_from(blobs, h, min_order_qty)
    return Product(
        product_url=url,
        product_name=_name_of(find_first(blobs, KEYS["name"])) or h.get("name"),
        brand_name=_name_of(find_first(blobs, KEYS["brand"])) or h.get("brand"),
        product_images=images,
        sku=scalar_text(find_first(blobs, KEYS["sku"])),
        wholesale_price=wholesale if wholesale is not None else parse_price(h.get("wholesale_price")),
        msrp=msrp if msrp is not None else parse_price(h.get("msrp")),
        item_quantity=parse_int(find_first(blobs, KEYS["item_quantity"]) or h.get("item_quantity")),
        weight=scalar_text(find_first(blobs, KEYS["weight"])) or h.get("weight"),
        dimensions=scalar_text(find_first(blobs, KEYS["dimensions"])) or h.get("dimensions"),
        details=scalar_text(find_first(blobs, KEYS["details"])) or h.get("details"),
        category=category_text(find_first(blobs, KEYS["category"])) or h.get("category"),
        country_of_origin=scalar_text(find_first(blobs, KEYS["country_of_origin"])) or h.get("country_of_origin"),
        ingredients=scalar_text(find_first(blobs, KEYS["ingredients"])) or h.get("ingredients"),
        description=scalar_text(find_first(blobs, KEYS["details"])) or h.get("description"),
        variants=variants,
        scraped_at=datetime.now(timezone.utc).isoformat(),
    )
