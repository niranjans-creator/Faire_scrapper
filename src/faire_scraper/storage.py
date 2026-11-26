"""SQLite store: tracks status per URL (resumable) and holds scraped results."""
import csv
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Iterable, List

from .models import CSV_FIELDS, Product

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    url TEXT PRIMARY KEY,
    run_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | done | failed
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    data TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(products)")}
        if "run_id" not in columns:
            self.db.execute("ALTER TABLE products ADD COLUMN run_id TEXT")
            self.db.commit()
        if not self.db.execute("SELECT 1 FROM runs LIMIT 1").fetchone():
            if self.db.execute("SELECT 1 FROM products WHERE status='done' LIMIT 1").fetchone():
                legacy_id = "legacy"
                self.db.execute("INSERT INTO runs(run_id) VALUES (?)", (legacy_id,))
                self.db.execute("UPDATE products SET run_id=? WHERE status='done' AND run_id IS NULL", (legacy_id,))
                self.db.commit()

    def add_urls(self, urls: Iterable[str]) -> int:
        n = 0
        for u in urls:
            cur = self.db.execute("INSERT OR IGNORE INTO products(url) VALUES (?)", (u,))
            n += cur.rowcount
        self.db.commit()
        return n

    def pending(self, retry_failed: bool = False, max_attempts: int = 3,
                include_done: bool = False, run_id: str = "") -> List[str]:
        conditions = ["p.status='pending'"]
        if retry_failed:
            conditions.append(f"(p.status='failed' AND p.attempts < {int(max_attempts)})")
        if include_done:
            conditions.append("p.status='done'")
        where = " OR ".join(conditions)
        params = []
        if run_id:
            where = f"({where}) AND p.run_id=?"
            params.append(run_id)
        query = f"SELECT p.url FROM products AS p WHERE {where} ORDER BY p.rowid"
        return [r[0] for r in self.db.execute(query, params)]

    def begin_run(self, retry_failed: bool = False, include_done: bool = False,
                  max_attempts: int = 3) -> str:
        """Assign the currently eligible queue to a new isolated scrape batch."""
        run_id = uuid.uuid4().hex[:12]
        conditions = ["status='pending'"]
        if retry_failed:
            conditions.append(f"status='failed' AND attempts < {int(max_attempts)}")
        if include_done:
            conditions.append("status='done'")
        where = " OR ".join(conditions)
        self.db.execute("INSERT INTO runs(run_id) VALUES (?)", (run_id,))
        self.db.execute(f"UPDATE products SET run_id=? WHERE {where}", (run_id,))
        self.db.commit()
        return run_id

    def latest_run_id(self) -> str:
        row = self.db.execute("SELECT run_id FROM runs ORDER BY started_at DESC, rowid DESC LIMIT 1").fetchone()
        return row[0] if row else ""

    def mark_done(self, p: Product) -> None:
        self.db.execute(
            "UPDATE products SET status='done', error=NULL, data=?, attempts=attempts+1, "
            "updated_at=CURRENT_TIMESTAMP WHERE url=?",
            (json.dumps(p.to_dict(), ensure_ascii=False), p.product_url),
        )
        self.db.commit()

    def mark_failed(self, url: str, error: str) -> None:
        self.db.execute(
            "UPDATE products SET status='failed', error=?, attempts=attempts+1, "
            "updated_at=CURRENT_TIMESTAMP WHERE url=?",
            (error[:500], url),
        )
        self.db.commit()

    def stats(self) -> dict:
        rows = self.db.execute("SELECT status, COUNT(*) FROM products GROUP BY status").fetchall()
        return dict(rows)

    def results(self, run_id: str = "") -> List[dict]:
        q = "SELECT data FROM products WHERE status='done'"
        params = []
        if run_id:
            q += " AND run_id=?"
            params.append(run_id)
        q += " ORDER BY rowid"
        return [json.loads(r[0]) for r in self.db.execute(q, params)]

    def queue(self) -> List[dict]:
        """Return queue rows for the local dashboard."""
        rows = self.db.execute(
            "SELECT url, status, error FROM products ORDER BY rowid"
        ).fetchall()
        return [{"url": url, "status": status, "error": error} for url, status, error in rows]

    def export_csv(self, path: str, run_id: str = "") -> int:
        rows = self.results(run_id)
        count = 0
        with open(path, "w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel reads UTF-8
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            w.writeheader()
            for r in rows:
                product = Product.from_dict(r)
                for row in product.to_rows():
                    w.writerow(row)
                    count += 1
        return count

    def export_jsonl(self, path: str, run_id: str = "") -> int:
        rows = self.results(run_id)
        count = 0
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                product = Product.from_dict(r)
                for row in product.to_rows():
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    count += 1
        return count

    def export_xlsx(self, path: str, run_id: str = "") -> int:
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Products"
        sheet.append(CSV_FIELDS)
        count = 0
        for raw in self.results(run_id):
            for row in Product.from_dict(raw).to_rows():
                sheet.append([row.get(field) for field in CSV_FIELDS])
                count += 1
        workbook.save(path)
        return count

    def close(self) -> None:
        self.db.close()
