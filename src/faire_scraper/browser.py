"""Playwright helpers: persistent logged-in profile, JSON extraction, block detection."""
import json
import logging
import re
from typing import Any, List

log = logging.getLogger(__name__)

BLOCK_MARKERS = [
    "captcha", "verify you are human", "access denied", "unusual traffic",
    "press & hold", "are you a robot", "request blocked",
]


class BlockedError(RuntimeError):
    """Raised when the site shows a challenge/block page. The run stops instead of retrying."""


class LoginRequired(RuntimeError):
    pass


def open_context(playwright, profile_dir: str, headless: bool):
    return playwright.chromium.launch_persistent_context(
        profile_dir, headless=headless, viewport={"width": 1366, "height": 900}
    )


def check_blocked(page) -> None:
    try:
        title = (page.title() or "").lower()
        body = page.inner_text("body", timeout=3000).lower()[:4000]
    except Exception:
        return
    text = title + " " + body
    if any(m in text for m in BLOCK_MARKERS):
        raise BlockedError(
            "Challenge/block page detected. Stopping. Solve it manually in a visible "
            "browser (run `login`), wait a while, and lower your request rate."
        )


def extract_blobs(page) -> List[Any]:
    """Collect embedded JSON: Next.js data, JSON-LD, generic JSON scripts, window state."""
    blobs: List[Any] = []
    for sel in ["script#__NEXT_DATA__", 'script[type="application/ld+json"]',
                'script[type="application/json"]']:
        for el in page.query_selector_all(sel):
            try:
                blobs.append(json.loads(el.inner_text()))
            except Exception:
                continue
    for var in ["__INITIAL_STATE__", "__APOLLO_STATE__", "__PRELOADED_STATE__", "__REDUX_STATE__"]:
        try:
            data = page.evaluate(f"window.{var} || null")
            if data:
                blobs.append(data)
        except Exception:
            pass
    return blobs


def expand_product_sections(page) -> None:
    """Open common collapsed PDP sections before the DOM fallback runs."""
    for label in ("Show more", "Product description", "Dimensions and weight", "Details"):
        try:
            locator = page.get_by_text(label, exact=True).first
            if locator.count() and locator.is_visible():
                locator.click(timeout=1000)
        except Exception:
            continue


def dom_hints(page) -> dict:
    """Fallbacks from visible text; used only when embedded JSON lacks a field."""
    h: dict = {}
    try:
        h["name"] = page.locator("h1").first.inner_text(timeout=2000).strip()
    except Exception:
        pass
    try:
        expand_product_sections(page)
        body = page.inner_text("body")
        def section(start: str, end: str) -> str:
            if start not in body:
                return ""
            value = body.split(start, 1)[1]
            return value.split(end, 1)[0].strip() if end in value else value.strip()

        m = re.search(r"(?:wholesale|your price)[^$\n]{0,40}\$\s?([\d,]+\.?\d*)", body, re.I)
        if m:
            h["wholesale_price"] = m.group(1)
        m = re.search(r"(?:msrp|retail)[^$\n]{0,40}\$\s?([\d,]+\.?\d*)", body, re.I)
        if m:
            h["msrp"] = m.group(1)
        h["item_quantity"] = re.search(r"(?:item quantity|quantity|count)\s*[:\n-]\s*(\d+)", body, re.I)
        if h["item_quantity"]:
            h["item_quantity"] = h["item_quantity"].group(1)
        h["weight"] = re.search(r"weight\s*[:\n-]\s*([^\n]+)", body, re.I)
        if h["weight"]:
            h["weight"] = h["weight"].group(1).strip()
        h["dimensions"] = re.search(r"dimensions?\s*[:\n-]\s*([^\n]+)", body, re.I)
        if h["dimensions"]:
            h["dimensions"] = h["dimensions"].group(1).strip()
        h["details"] = re.search(r"(?:details|description)\s*[:\n-]\s*([^\n]+)", body, re.I)
        if h["details"]:
            h["details"] = h["details"].group(1).strip()
        description = section("Product description", "Dimensions and weight")
        if description:
            h["description"] = description
        origin = re.search(r"Country of Origin:\s*([^\n]+)", body, re.I)
        if origin:
            h["country_of_origin"] = origin.group(1).strip()
        ingredients = section("Ingredients", "Shipping & policies")
        if ingredients:
            h["ingredients"] = ingredients
        min_qty = re.search(r"Min Qty\s+(\d+)", body, re.I)
        h["min_order_qty"] = min_qty.group(1) if min_qty else None
        h["availability"] = "available" if not re.search(r"(?:out of stock|sold out|unavailable)", body, re.I) else "unavailable"
        h["variants"] = []
        for quantity in page.locator('input[aria-label^="Quantity for size "]').all():
            label = quantity.get_attribute("aria-label") or ""
            size = re.sub(r"^Quantity for size\s+", "", label).strip()
            try:
                text = quantity.locator("xpath=../..").inner_text()
            except Exception:
                text = ""
            price = re.search(r"\$\s?([\d,]+(?:\.\d+)?)", text)
            msrp = re.search(r"(?:MSRP|retail)\s*\$\s?([\d,]+(?:\.\d+)?)", text, re.I)
            h["variants"].append({
                "size_or_variant": size,
                "wholesale_price": float(price.group(1).replace(",", "")) if price else None,
                "price_per_size": float(price.group(1).replace(",", "")) if price else None,
                "msrp": float(msrp.group(1).replace(",", "")) if msrp else None,
                "min_order_qty": int(h["min_order_qty"]) if h["min_order_qty"] else None,
                "availability": "available" if not quantity.is_disabled() else "unavailable",
            })
        try:
            breadcrumb = [text.strip() for text in page.locator('nav a').all_inner_texts() if text.strip()]
            if breadcrumb:
                h["category"] = " > ".join(breadcrumb)
        except Exception:
            pass
        try:
            brand_link = page.locator('a[href*="/brand/"]').first
            if brand_link.count():
                h["brand"] = brand_link.inner_text().strip()
        except Exception:
            pass
    except Exception:
        pass
    try:
        h["images"] = []
        for image in page.locator("main img").all():
            src = image.get_attribute("src") or ""
            alt = image.get_attribute("alt") or ""
            if src.startswith("http") and "faire" in src and "logo" not in src.lower() and alt:
                h["images"].append(src)
        h["images"] = list(dict.fromkeys(h["images"]))
    except Exception:
        pass
    return h
