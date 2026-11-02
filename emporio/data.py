"""Load and clean the store CSVs into typed, in-memory records.

The dataset is tiny (~150 rows in total), so everything is loaded once into plain
dataclasses. No database or dataframe library is needed, and the tools stay easy to test.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CSV_PREFIX = "desafio_tecnico_ai_eng - "


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    description: str


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    category_id: int
    price: float
    description: str
    stock: int
    status: str  # active | coming_soon | discontinued
    specs: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def availability(self) -> str:
        """A single availability label so the LLM never has to combine status and stock."""
        if self.status == "discontinued":
            return "discontinued"
        if self.status == "coming_soon":
            return "coming_soon"
        return "in_stock" if self.stock > 0 else "out_of_stock"


@dataclass(frozen=True)
class Promotion:
    id: int
    product_id: int
    discount_percent: float
    description: str
    is_active: bool


@dataclass(frozen=True)
class Customer:
    id: int
    name: str
    phone: str
    email: str
    city: str


@dataclass(frozen=True)
class OrderItem:
    product_id: int
    quantity: int


@dataclass(frozen=True)
class Order:
    id: int
    customer_id: int
    order_date: date
    status: str  # pending | confirmed | shipped | delivered | cancelled
    total: float
    payment_method: str
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None
    items: tuple[OrderItem, ...] = ()


@dataclass
class StoreData:
    categories: dict[int, Category]
    products: dict[int, Product]
    promotions: list[Promotion]
    customers: dict[int, Customer]
    orders: dict[int, Order]

    def active_promotion(self, product_id: int) -> Promotion | None:
        """Return the active promotion for a product (best discount wins if several)."""
        active = [p for p in self.promotions if p.product_id == product_id and p.is_active]
        return max(active, key=lambda p: p.discount_percent, default=None)

    def category_name(self, category_id: int) -> str:
        cat = self.categories.get(category_id)
        return cat.name if cat else "Desconhecida"


def normalize_text(text: str) -> str:
    """Lowercase and strip accents/punctuation, so 'Violão' matches 'violao'."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def digits_only(text: str) -> str:
    return re.sub(r"\D", "", text or "")


def _read_csv(table: str, data_dir: Path) -> list[dict[str, str]]:
    path = data_dir / f"{CSV_PREFIX}{table}.csv"
    with path.open(encoding="utf-8", newline="") as f:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def _parse_date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def _parse_specs(value: str) -> dict:
    try:
        return json.loads(value) if value else {}
    except json.JSONDecodeError:
        return {}


def load_store_data(data_dir: Path = DATA_DIR) -> StoreData:
    categories = {
        int(r["category_id"]): Category(int(r["category_id"]), r["name"], r["description"])
        for r in _read_csv("categories", data_dir)
    }
    products = {
        int(r["product_id"]): Product(
            id=int(r["product_id"]),
            name=r["name"],
            category_id=int(r["category_id"]),
            price=float(r["price_brl"]),
            description=r["description"],
            stock=int(r["stock_quantity"] or 0),
            status=r["status"],
            specs=_parse_specs(r["specs"]),
        )
        for r in _read_csv("products", data_dir)
    }
    promotions = [
        Promotion(
            id=int(r["promotion_id"]),
            product_id=int(r["product_id"]),
            discount_percent=float(r["discount_percent"]),
            description=r["description"],
            is_active=r["is_active"] == "1",
        )
        for r in _read_csv("promotions", data_dir)
    ]
    customers = {
        int(r["customer_id"]): Customer(
            int(r["customer_id"]), r["name"], r["phone"], r["email"].lower(), r["city"]
        )
        for r in _read_csv("customers", data_dir)
    }
    items_by_order: dict[int, list[OrderItem]] = {}
    for r in _read_csv("order_items", data_dir):
        items_by_order.setdefault(int(r["order_id"]), []).append(
            OrderItem(int(r["product_id"]), int(r["quantity"]))
        )
    orders = {
        int(r["order_id"]): Order(
            id=int(r["order_id"]),
            customer_id=int(r["customer_id"]),
            order_date=date.fromisoformat(r["order_date"]),
            status=r["status"],
            total=float(r["total_brl"]),
            payment_method=r["payment_method"],
            tracking_code=r["tracking_code"] or None,
            estimated_delivery=_parse_date(r["estimated_delivery"]),
            notes=r["notes"] or None,
            items=tuple(items_by_order.get(int(r["order_id"]), [])),
        )
        for r in _read_csv("orders", data_dir)
    }
    return StoreData(categories, products, promotions, customers, orders)


@lru_cache(maxsize=1)
def get_store_data() -> StoreData:
    return load_store_data()
