from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

CSV_FIELDS = [
    "product_url", "product_name", "brand_name", "category", "size_or_variant",
    "sku", "wholesale_price", "msrp", "price_per_size", "case_pack_qty",
    "item_quantity", "min_order_qty", "availability", "country_of_origin", "weight", "dimensions",
    "ingredients", "description", "image_urls", "missing_fields", "scraped_at",
]


@dataclass
class Variant:
    size_or_variant: Optional[str] = None
    sku: Optional[str] = None
    wholesale_price: Optional[float] = None
    msrp: Optional[float] = None
    price_per_size: Optional[float] = None
    case_pack_qty: Optional[int] = None
    item_quantity: Optional[int] = None
    min_order_qty: Optional[int] = None
    availability: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Product:
    product_url: str
    product_name: Optional[str] = None
    brand_name: Optional[str] = None
    product_images: List[str] = field(default_factory=list)
    sku: Optional[str] = None
    wholesale_price: Optional[float] = None
    msrp: Optional[float] = None
    item_quantity: Optional[int] = None
    weight: Optional[str] = None
    dimensions: Optional[str] = None
    details: Optional[str] = None
    category: Optional[str] = None
    country_of_origin: Optional[str] = None
    ingredients: Optional[str] = None
    description: Optional[str] = None
    variants: List[Variant] = field(default_factory=list)
    scraped_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Product":
        values = {k: data.get(k) for k in cls.__dataclass_fields__ if k in data}
        if "ingredients" not in values and data.get("materials"):
            values["ingredients"] = data["materials"]
        values["variants"] = [Variant(**v) if isinstance(v, dict) else v
                              for v in values.get("variants", [])]
        return cls(**values)

    def to_csv_row(self) -> dict:
        rows = self.to_rows()
        return rows[0] if rows else {k: None for k in CSV_FIELDS}

    def to_rows(self) -> List[dict]:
        variants = self.variants or [Variant(
            sku=self.sku,
            wholesale_price=self.wholesale_price,
            msrp=self.msrp,
            price_per_size=self.wholesale_price,
            case_pack_qty=None,
            item_quantity=self.item_quantity,
            min_order_qty=None,
        )]
        missing = "|".join(self.missing_fields())
        rows = []
        for variant in variants:
            row = {
                "product_url": self.product_url,
                "product_name": self.product_name,
                "brand_name": self.brand_name,
                "category": self.category,
                "size_or_variant": variant.size_or_variant,
                "sku": variant.sku or self.sku,
                "wholesale_price": variant.wholesale_price,
                "msrp": variant.msrp,
                "price_per_size": variant.price_per_size or variant.wholesale_price,
                "case_pack_qty": variant.case_pack_qty,
                "item_quantity": variant.item_quantity or self.item_quantity,
                "min_order_qty": variant.min_order_qty,
                "availability": variant.availability,
                "country_of_origin": self.country_of_origin,
                "weight": self.weight,
                "dimensions": self.dimensions,
                "ingredients": self.ingredients,
                "description": self.description or self.details,
                "image_urls": "|".join(self.product_images),
                "missing_fields": missing,
                "scraped_at": self.scraped_at,
            }
            rows.append({k: row.get(k) for k in CSV_FIELDS})
        return rows

    def missing_fields(self) -> List[str]:
        d = self.to_dict()
        required = {
            "product_name": self.product_name,
            "brand_name": self.brand_name,
            "category": self.category,
            "weight": self.weight,
            "dimensions": self.dimensions,
            "description": self.description or self.details,
        }
        missing = [k for k, value in required.items() if value in (None, "", [])]
        if not self.variants:
            missing.append("size_or_variant")
        return missing
