import argparse
import logging
from pathlib import Path

from playwright.sync_api import sync_playwright

from .browser import BlockedError, open_context
from .collector import collect_links
from .scraper import scrape_pending
from .storage import Store
from .utils import normalize_url, setup_logging

log = logging.getLogger("faire_scraper")


def cmd_login(a):
    with sync_playwright() as p:
        ctx = open_context(p, a.profile, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.faire.com/")
        input("Log in (and solve any challenge) in the browser, then press Enter here... ")
        ctx.close()
    log.info("Session saved in %s", a.profile)


def cmd_collect(a):
    store = Store(a.db)
    with sync_playwright() as p:
        ctx = open_context(p, a.profile, headless=a.headless)
        page = ctx.new_page()
        try:
            links = collect_links(page, a.page, max_scrolls=a.scrolls)
        except BlockedError as e:
            log.error(str(e))
            return
        finally:
            ctx.close()
    added = store.add_urls(links)
    log.info("Found %d links, %d new queued. DB: %s", len(links), added, a.db)


def cmd_add(a):
    urls = [normalize_url(u) for u in Path(a.file).read_text().splitlines()
            if u.strip() and not u.startswith("#")]
    store = Store(a.db)
    log.info("Queued %d new URLs (of %d)", store.add_urls(urls), len(urls))


def cmd_scrape(a):
    store = Store(a.db)
    with sync_playwright() as p:
        ctx = open_context(p, a.profile, headless=a.headless)
        page = ctx.new_page()
        try:
            scrape_pending(page, store, a.delay_min, a.delay_max,
                           max_retries=a.retries, limit=a.limit,
                           retry_failed=a.retry_failed, refresh_done=a.refresh)
        except BlockedError as e:
            log.error(str(e))
        except KeyboardInterrupt:
            log.info("Interrupted; progress is saved. Re-run to resume.")
        finally:
            ctx.close()
    log.info("Status: %s", store.stats())


def cmd_export(a):
    store = Store(a.db)
    run_id = "" if a.all_runs else store.latest_run_id()
    if run_id and not a.all_runs:
        if a.format == "csv" and a.csv == "data/products.csv":
            a.csv = f"data/products-{run_id}.csv"
        elif a.format == "jsonl" and a.out == "data/products.jsonl":
            a.out = f"data/products-{run_id}.jsonl"
        elif a.format == "xlsx" and a.xlsx == "data/products.xlsx":
            a.xlsx = f"data/products-{run_id}.xlsx"
    if a.format == "csv":
        n = store.export_csv(a.csv, run_id)
    elif a.format == "jsonl":
        n = store.export_jsonl(a.out, run_id)
    else:
        n = store.export_xlsx(a.xlsx, run_id)
    log.info("Exported %d products", n)


def cmd_status(a):
    print(Store(a.db).stats())


def main():
    ap = argparse.ArgumentParser(prog="faire_scraper")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--db", default="data/faire.db")
    ap.add_argument("--profile", default="faire_profile")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("login", help="Log in once; session is saved").set_defaults(fn=cmd_login)

    c = sub.add_parser("collect", help="Queue product URLs from a brand/category page")
    c.add_argument("page")
    c.add_argument("--scrolls", type=int, default=40)
    c.add_argument("--headless", action="store_true")
    c.set_defaults(fn=cmd_collect)

    ad = sub.add_parser("add", help="Queue product URLs from a text file")
    ad.add_argument("file")
    ad.set_defaults(fn=cmd_add)

    s = sub.add_parser("scrape", help="Scrape all queued URLs")
    s.add_argument("--delay-min", type=float, default=2.0,
                   help="Minimum pause between product pages (default: 2s)")
    s.add_argument("--delay-max", type=float, default=5.0,
                   help="Maximum pause between product pages (default: 5s)")
    s.add_argument("--retries", type=int, default=2)
    s.add_argument("--limit", type=int, default=0, help="Max URLs this run (0 = all)")
    s.add_argument("--retry-failed", action="store_true")
    s.add_argument("--refresh", action="store_true",
                   help="Re-scrape completed URLs to refresh extracted fields")
    s.add_argument("--headless", action="store_true")
    s.set_defaults(fn=cmd_scrape)

    e = sub.add_parser("export", help="Export results")
    e.add_argument("--format", choices=["csv", "jsonl", "xlsx"], default="csv")
    e.add_argument("--csv", default="data/products.csv")
    e.add_argument("--out", default="data/products.jsonl")
    e.add_argument("--xlsx", default="data/products.xlsx")
    e.add_argument("--all-runs", action="store_true", help="Include products from every scrape batch")
    e.set_defaults(fn=cmd_export)

    sub.add_parser("status").set_defaults(fn=cmd_status)

    a = ap.parse_args()
    setup_logging(a.verbose)
    a.fn(a)
