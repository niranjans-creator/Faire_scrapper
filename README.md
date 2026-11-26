# Faire Product Scraper

Collects product details from Faire product pages into SQLite, then exports to CSV, JSONL, or XLSX.

**Fields:** one row per visible size/variant with product name, brand, full breadcrumb category,
images, SKU, wholesale price, MSRP, price per size, case-pack/unit multiplier when listed,
item quantity, minimum order quantity, availability, country of origin, weight, dimensions,
ingredients, description, missing-field reasons, timestamp, and product URL.

## Before you use it

- **Check Faire's Terms of Service.** They restrict automated scraping. Only use this where
  you have the right to. If you are a brand collecting your own catalog, use Faire's official
  External API instead.
- Wholesale prices are only visible to **logged-in, approved retailers**. The scraper reuses
  *your* browser session; it does not bypass logins.
- If a CAPTCHA/block page appears the scraper **stops** rather than retrying. It has no
  stealth, fingerprint spoofing, or proxy rotation by design.

## Install

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Run all commands from the project root with `PYTHONPATH=src` (or `export PYTHONPATH=src`):

## Workflow

```bash
# 1. Log in once (a browser opens; session saved to ./faire_profile)
python -m faire_scraper login

# 2. Queue product URLs - either from a listing page...
python -m faire_scraper collect "https://www.faire.com/brand/<brand-slug>"
#    ...or from a file (one URL per line, '#' for comments)
python -m faire_scraper add urls.txt

# 3. Scrape (resumable; Ctrl+C is safe)
python -m faire_scraper scrape --limit 3          # test on 3 products first!
python -m faire_scraper scrape                     # then everything queued
python -m faire_scraper scrape --retry-failed      # retry failures later
python -m faire_scraper scrape --refresh           # re-scrape completed URLs after extractor updates

# 4. Export
python -m faire_scraper export                     # -> data/products.csv
python -m faire_scraper export --format jsonl      # -> data/products.jsonl
python -m faire_scraper export --format xlsx       # -> data/products.xlsx
python -m faire_scraper export --all-runs           # include every historical batch
python -m faire_scraper status
```

## Dashboard

Launch the local dashboard from the project root:

```bash
PYTHONPATH=src python -m faire_scraper.web
```

Then open <http://127.0.0.1:8765>. The dashboard uses the existing SQLite database,
so queued URLs, scrape status, product results, and CSV export stay in sync with the
CLI. You can paste URLs or upload a CSV with a `url`, `product_url`, or `link` column.
Log in once with the CLI before starting a scrape from the dashboard. If a run exits,
the dashboard records the child process output in `data/scraper.log`.

Every completed URL also writes `data/raw/<sha1>.html` and `data/raw/<sha1>.json`. These
snapshots make it possible to update the parser and re-test a page without visiting Faire again.
Each scrape invocation is isolated as its own batch. Dashboard exports contain only the latest
batch and are named with its run ID; use `--all-runs` for a combined historical export.

The dashboard is protected by an app password on first launch. Only a salted PBKDF2 hash is
stored in `dashboard-auth.json`; the Faire password is never requested or stored by this app.
Faire authentication still happens manually in the visible persistent browser session.

Useful flags: `--delay-min/--delay-max` (default 2-5 s between pages), `--retries`,
`--headless`, `-v`, global `--db` and `--profile` paths.

## Windows desktop application

On Windows PowerShell, run `.\build_windows.ps1`. The script creates a virtual environment,
installs Playwright, WebView2 support, and PyInstaller, then builds
`dist\FaireScraper\FaireScraper.exe`. Launching the executable opens the dashboard in a native
window. Database files, exports, logs, raw snapshots, and the persistent Faire browser profile
are stored under `%LOCALAPPDATA%\FaireScraper`.

Microsoft Edge WebView2 Runtime must be installed on the Windows machine. The first build also
installs the Chromium browser used by Playwright.

## IMPORTANT: calibrate on real pages

Faire's page structure isn't public and can change, and this project was written without
live access to the site. Extraction looks through embedded JSON (`__NEXT_DATA__`, JSON-LD,
window state) for likely key names, then falls back to visible text.

1. Run `scrape --limit 3` (without `--headless`) and check the log. It lists
   `missing:` fields per product.
2. In DevTools, open a product page, find `__NEXT_DATA__` (Elements/Network tab) and note the
   real key names for the missing fields.
3. Add them to the `KEYS` dict in `src/faire_scraper/extractor.py`.
4. Variant rows are assembled from structured `options`/`variants` data first, then visible
   quantity controls. If a field is not listed on the page it is reported in `missing_fields`.

## Layout

```
src/faire_scraper/
  cli.py        commands          browser.py   Playwright, block detection, JSON extraction
  collector.py  listing -> URLs   extractor.py parsing (pure, unit-tested)
  scraper.py    scrape loop       storage.py   SQLite state + CSV/JSONL export
  models.py     Product schema    utils.py     helpers
tests/          offline unit tests:  python -m unittest discover -s tests
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Prices empty | Not logged in / account not approved for wholesale, or key names differ (see calibration) |
| "Challenge/block page detected" | Run `login`, solve it manually, wait, then use longer delays |
| `no product name found` | Layout changed or page didn't load; run non-headless with `-v` |
