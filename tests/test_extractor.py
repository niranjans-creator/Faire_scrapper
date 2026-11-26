import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from faire_scraper.extractor import build_product  # noqa: E402
from faire_scraper.models import Product  # noqa: E402
from faire_scraper.storage import Store  # noqa: E402
from faire_scraper.utils import normalize_url, parse_int, parse_price  # noqa: E402

NEXT_DATA = {
    "props": {"pageProps": {"product": {
        "name": "Soy Candle - Lavender",
        "brand": {"name": "Hearth & Co"},
        "images": [{"url": "https://cdn.faire.com/a.jpg"}, {"url": "https://cdn.faire.com/b.jpg"},
                   {"url": "https://cdn.faire.com/a.jpg"}],
        "options": [{"name": "8 oz", "sku": "HC-LAV-8", "wholesale_price_cents": 1200,
                     "retail_price_cents": 2400, "itemQuantity": 1}],
        "weight": "10 oz",
        "dimensions": {"length": 3, "width": 3, "height": 4, "unit": "in"},
        "description": "A calming lavender candle.",
        "itemQuantity": 1,
        "category": [{"name": "Home"}, {"name": "Candles"}],
    }}}
}


class TestExtractor(unittest.TestCase):
    def test_full_product(self):
        p = build_product([NEXT_DATA], "https://www.faire.com/product/p_1")
        self.assertEqual(p.product_name, "Soy Candle - Lavender")
        self.assertEqual(p.brand_name, "Hearth & Co")
        self.assertEqual(p.product_images, ["https://cdn.faire.com/a.jpg", "https://cdn.faire.com/b.jpg"])
        self.assertEqual(p.sku, "HC-LAV-8")
        self.assertEqual(p.wholesale_price, 12.0)
        self.assertEqual(p.msrp, 24.0)
        self.assertEqual(p.item_quantity, 1)
        self.assertEqual(p.details, "A calming lavender candle.")
        self.assertEqual(len(p.variants), 1)
        self.assertEqual(p.variants[0].size_or_variant, "8 oz")
        self.assertEqual(p.category, "Home > Candles")
        self.assertIn("length", p.dimensions)
        self.assertEqual(p.missing_fields(), [])

    def test_dom_fallback(self):
        p = build_product([{}], "u", {"name": "X", "wholesale_price": "5.50", "msrp": "11", "item_quantity": "12", "description": "Details", "variants": [{"size_or_variant": "One size", "item_quantity": 12}]})
        self.assertEqual((p.product_name, p.wholesale_price, p.msrp, p.item_quantity), ("X", 5.5, 11.0, 12))
        self.assertEqual(p.to_rows()[0]["item_quantity"], 12)

    def test_zero_price_not_dropped(self):
        p = build_product([{"wholesale_price_cents": 0}], "u")
        self.assertEqual(p.wholesale_price, 0.0)


class TestUtils(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_price("$1,299.50"), 1299.5)
        self.assertIsNone(parse_price("n/a"))
        self.assertEqual(parse_int("Case of 24"), 24)

    def test_normalize(self):
        self.assertEqual(normalize_url("https://www.faire.com/product/p_1/?x=1#a"),
                         "https://www.faire.com/product/p_1")


class TestStore(unittest.TestCase):
    def test_flow_and_export(self):
        with tempfile.TemporaryDirectory() as d:
            s = Store(os.path.join(d, "t.db"))
            self.assertEqual(s.add_urls(["u1", "u2", "u1"]), 2)
            s.mark_done(Product(product_url="u1", product_name="A", product_images=["i1", "i2"]))
            s.mark_failed("u2", "boom")
            self.assertEqual(s.pending(), [])
            self.assertEqual(s.pending(retry_failed=True), ["u2"])
            self.assertEqual(s.stats(), {"done": 1, "failed": 1})
            csv_path = os.path.join(d, "o.csv")
            self.assertEqual(s.export_csv(csv_path), 1)
            with open(csv_path, encoding="utf-8-sig") as fh:
                self.assertIn("i1|i2", fh.read())


if __name__ == "__main__":
    unittest.main()
