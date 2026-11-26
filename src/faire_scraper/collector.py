"""Collect product URLs from a brand / category / search results page (infinite scroll)."""
import logging
from typing import List

from .browser import check_blocked
from .utils import jitter_sleep, normalize_url

log = logging.getLogger(__name__)

_JS = "els => els.map(e => e.href)"


def collect_links(page, listing_url: str, max_scrolls: int = 40, patience: int = 3) -> List[str]:
    """Scroll until no new product links appear for `patience` consecutive scrolls."""
    page.goto(listing_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    check_blocked(page)

    seen: dict = {}  # ordered set
    stale = 0
    for i in range(max_scrolls):
        count_before = len(seen)
        for h in page.eval_on_selector_all("a[href*='/product/']", _JS):
            seen.setdefault(normalize_url(h), None)
        stale = stale + 1 if len(seen) == count_before else 0
        log.info("scroll %d: %d product links", i + 1, len(seen))
        if stale >= patience:
            break
        page.mouse.wheel(0, 5000)
        jitter_sleep(1.5, 3.0)
    return list(seen)
