import logging
import random
import re
import time
from urllib.parse import urlsplit, urlunsplit


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )


def jitter_sleep(lo: float, hi: float) -> None:
    time.sleep(random.uniform(lo, hi))


def normalize_url(url: str) -> str:
    """Strip query/fragment so the same product isn't scraped twice."""
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme or "https", p.netloc or "www.faire.com", p.path.rstrip("/"), "", ""))


def parse_price(value):
    """Accepts 12, '12.50', '$1,299.00' -> float; returns None if not parseable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"\d[\d,]*\.?\d*", str(value))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def parse_int(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    m = re.search(r"\d+", str(value))
    return int(m.group(0)) if m else None
