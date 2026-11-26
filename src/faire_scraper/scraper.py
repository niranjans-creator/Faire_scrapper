"""Main scrape loop: retries, backoff, block detection, resumable via SQLite."""
import hashlib
import json
import logging
import os
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout

from .browser import BlockedError, check_blocked, dom_hints, expand_product_sections, extract_blobs
from .extractor import build_product
from .storage import Store
from .utils import jitter_sleep

log = logging.getLogger(__name__)


def save_raw_snapshot(page, blobs, url: str) -> None:
    """Persist the page and embedded state so parsers can be fixed offline."""
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()
    raw_dir = Path(os.environ.get("FAIRE_DATA_DIR", "data")) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{key}.html").write_text(page.content(), encoding="utf-8")
    (raw_dir / f"{key}.json").write_text(
        json.dumps({"url": url, "blobs": blobs}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def wait_if_paused() -> None:
    control = Path(os.environ.get("FAIRE_DATA_DIR", "data")) / "scraper.control"
    while control.exists() and control.read_text(encoding="utf-8").strip() == "paused":
        log.info("Scrape paused; waiting for resume")
        time.sleep(1)


def scrape_pending(page, store: Store, delay_min: float, delay_max: float,
                   max_retries: int = 2, limit: int = 0, retry_failed: bool = False,
                   refresh_done: bool = False) -> None:
    run_id = store.begin_run(retry_failed=retry_failed, include_done=refresh_done)
    urls = store.pending(retry_failed=retry_failed, include_done=refresh_done, run_id=run_id)
    if limit:
        urls = urls[:limit]
    log.info("Run %s: %d URLs to scrape", run_id, len(urls))

    for i, url in enumerate(urls, 1):
        wait_if_paused()
        for attempt in range(1, max_retries + 2):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_selector("h1", timeout=15000)
                check_blocked(page)
                expand_product_sections(page)
                blobs = extract_blobs(page)
                save_raw_snapshot(page, blobs, url)
                product = build_product(blobs, url, dom_hints(page))
                if not product.product_name:
                    raise ValueError("no product name found (page layout changed or not logged in?)")
                store.mark_done(product)
                missing = product.missing_fields()
                log.info("[%d/%d] %s%s", i, len(urls), product.product_name,
                         f"  (missing: {', '.join(missing)})" if missing else "")
                break
            except BlockedError:
                raise  # never hammer a site that is challenging us
            except (PWTimeout, ValueError, Exception) as e:  # noqa: BLE001
                log.warning("[%d/%d] attempt %d failed for %s: %s", i, len(urls), attempt, url, e)
                if attempt > max_retries:
                    store.mark_failed(url, str(e))
                else:
                    # Keep retries polite, but avoid the old 5/10 second pause.
                    time.sleep(3 * attempt)  # linear backoff
        jitter_sleep(delay_min, delay_max)
