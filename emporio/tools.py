"""Tools the agent can call: plain functions over StoreData plus their JSON schemas.

Design rules:
- Tools return facts that are ready to show the customer (prices already in "R$ 1.234,56", a
  single availability label, return windows already computed), so the LLM never does math
  or date arithmetic.
- Order lookups require the customer's phone or e-mail (LGPD, policy §9): an order number
  alone is never enough to reveal someone's purchase.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from emporio.data import DATA_DIR, Product, StoreData, digits_only, normalize_text
from emporio.pricing import fmt_brl, quote_cart, quote_product
from emporio.store_hours import now_local, store_status

MAX_RESULTS = 8
MATCH_THRESHOLD = 70
REGRET_DAYS = 7
DEFECT_EXCHANGE_DAYS = 30
LEGAL_WARRANTY_DAYS = 90
HANDOFF_LOG = DATA_DIR / "handoffs.jsonl"

AVAILABILITY_PT = {
    "in_stock": "disponível",
    "out_of_stock": "esgotado no momento",
    "coming_soon": "em breve (ainda não está à venda)",
    "discontinued": "descontinuado (saiu do catálogo)",
}
ORDER_STATUS_PT = {
    "pending": "aguardando confirmação do pagamento",
    "confirmed": "pagamento confirmado, em separação",
    "shipped": "enviado (a caminho)",
    "delivered": "entregue",
    "cancelled": "cancelado",
}
PAYMENT_PT = {"pix": "PIX", "debit": "cartão de débito", "boleto": "boleto"}


def _payment_label(method: str) -> str:
    if method.startswith("credit_"):
        return f"cartão de crédito em {method.removeprefix('credit_')}"
    return PAYMENT_PT.get(method, method)


def _product_summary(data: StoreData, p: Product) -> dict[str, Any]:
    quote = quote_product(p, data.active_promotion(p.id))
    return {
        "product_id": p.id,
        "name": p.name,
        "category": data.category_name(p.category_id),
        "availability": AVAILABILITY_PT[p.availability],
        "units_in_stock": p.stock if p.availability == "in_stock" else 0,
        **quote.to_dict(),
    }


def _final_price(data: StoreData, p: Product) -> float:
    return quote_product(p, data.active_promotion(p.id)).final_price


STOPWORDS = {"de", "da", "do", "das", "dos", "para", "pra", "com", "um", "uma", "o", "a", "e"}


def _match_score(data: StoreData, p: Product, query: str) -> tuple[float, bool]:
    """Typo-tolerant token matching.

    Every query word is compared with every word of the product's name, category and
    description, so 'violao yamaha' matches 'Yamaha C40' in the category 'Violões'.
    Returns (average score of matched words, whether every word matched).
    """
    q_tokens = [t for t in normalize_text(query).split() if t not in STOPWORDS]
    if not q_tokens:
        return 0.0, False
    name = normalize_text(p.name)
    hay_tokens = set(
        normalize_text(f"{p.name} {data.category_name(p.category_id)} {p.description}").split()
    )
    # 'gd 20' vs 'gd20': compare the query without spaces against the name without spaces
    if fuzz.partial_ratio("".join(q_tokens), name.replace(" ", "")) >= 95 and len(q_tokens) > 1:
        return 100.0, True

    scores = []
    for qt in q_tokens:
        best = max(
            100.0 if (len(qt) >= 3 and ht.startswith(qt)) else fuzz.ratio(qt, ht)
            for ht in hay_tokens
        )
        if best >= MATCH_THRESHOLD:
            # words found in the product name weigh more than words in the description
            best += 10 if any(fuzz.ratio(qt, nt) >= MATCH_THRESHOLD for nt in name.split()) else 0
            scores.append(best)
    if not scores:
        return 0.0, False
    return sum(scores) / len(q_tokens), len(scores) == len(q_tokens)


# --------------------------------------------------------------------------- tools


def search_products(
    data: StoreData,
    query: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    only_available: bool = False,
) -> dict:
    products = list(data.products.values())
    if category:
        cat = normalize_text(category)
        products = [p for p in products if normalize_text(data.category_name(p.category_id)) == cat]
    if max_price is not None:
        products = [p for p in products if _final_price(data, p) <= max_price]
    if min_price is not None:
        products = [p for p in products if _final_price(data, p) >= min_price]
    if only_available:
        products = [p for p in products if p.availability == "in_stock"]

    note = None
    if query:
        exact, partial = [], []
        for p in products:
            score, all_matched = _match_score(data, p, query)
            if all_matched:
                exact.append((score, p))
            elif score > 0:
                partial.append((score, p))
        if exact:
            ranked = exact
        else:
            ranked = partial
            if partial:
                note = "Nenhum produto com todos os termos buscados; estes são os mais próximos."
        ranked.sort(key=lambda sp: (-sp[0], sp[1].price))
        products = [p for _, p in ranked]
    else:
        # Browsing: hide discontinued items and show cheapest first
        products = sorted(
            (p for p in products if p.availability != "discontinued"),
            key=lambda p: _final_price(data, p),
        )

    results = [_product_summary(data, p) for p in products[:MAX_RESULTS]]
    out: dict[str, Any] = {"total_found": len(products), "results": results}
    if note:
        out["note"] = note
    if not results:
        out["note"] = (
            "Nenhum produto encontrado com esses critérios. A loja vende apenas instrumentos "
            "musicais (sem acessórios)."
        )
    return out


def get_product_details(data: StoreData, product_id: int) -> dict:
    p = data.products.get(product_id)
    if not p:
        return {"error": f"Produto {product_id} não encontrado."}
    out = _product_summary(data, p)
    out["description"] = p.description
    out["specs"] = p.specs
    if p.availability != "in_stock":
        # Policy §7.3: always offer similar alternatives that are actually available
        price = _final_price(data, p)
        similar = [
            q
            for q in data.products.values()
            if q.category_id == p.category_id and q.id != p.id and q.availability == "in_stock"
        ]
        similar.sort(key=lambda q: abs(_final_price(data, q) - price))
        out["available_alternatives"] = [_product_summary(data, q) for q in similar[:3]]
    return out


def quote_purchase(
    data: StoreData, items: list[dict], delivery_in_campo_grande: bool | None = None
) -> dict:
    lines = []
    for item in items:
        p = data.products.get(int(item["product_id"]))
        if not p:
            return {"error": f"Produto {item['product_id']} não encontrado."}
        if p.availability != "in_stock":
            return {"error": f"{p.name} está {AVAILABILITY_PT[p.availability]}."}
        qty = max(1, int(item.get("quantity") or 1))
        if qty > p.stock:
            return {"error": f"Só temos {p.stock} unidade(s) de {p.name} em estoque."}
        lines.append((p, data.active_promotion(p.id), qty))
    quote = quote_cart(lines, local_delivery=bool(delivery_in_campo_grande))
    if delivery_in_campo_grande is None:
        quote["shipping"] = (
            "Retirada na loja: grátis. Entrega em Campo Grande: grátis acima de R$ 500,00 "
            "(senão R$ 35,00). Outras cidades: cotação pelo CEP."
        )
        quote["total_with_shipping_card"] = None
    quote["items"] = [f"{qty}x {p.name}" for p, _, qty in lines]
    return quote


def _find_customer(data: StoreData, contact: str):
    contact = contact.strip().lower()
    if "@" in contact:
        return next((c for c in data.customers.values() if c.email == contact), None)
    digits = digits_only(contact)
    if len(digits) < 8:
        return None
    # Compare the last 8 digits so "(67) 99812-3456", "67998123456" and "99812-3456" all match
    return next(
        (c for c in data.customers.values() if digits_only(c.phone)[-8:] == digits[-8:]), None
    )


def _return_windows(order, today: date) -> dict:
    """Pre-compute policy §4 and §8 deadlines so the LLM only has to explain them."""
    if order.status != "delivered":
        return {"note": "Prazos de troca/devolução contam a partir do recebimento do produto."}
    # Assumption (README): the actual delivery date is not in the data; we use estimated_delivery
    received = order.estimated_delivery or order.order_date
    since_delivery = (today - received).days
    since_purchase = (today - order.order_date).days
    return {
        "received_on": received.strftime("%d/%m/%Y"),
        "days_since_delivery": since_delivery,
        "regret_return_7_days": since_delivery <= REGRET_DAYS,
        "defect_exchange_30_days": since_purchase <= DEFECT_EXCHANGE_DAYS,
        "legal_warranty_90_days": since_delivery <= LEGAL_WARRANTY_DAYS,
        "after_that": "garantia do fabricante (6 meses a 2 anos); a loja pode intermediar",
    }


def find_orders(
    data: StoreData, contact: str, order_id: int | None = None, today: date | None = None
) -> dict:
    today = today or now_local().date()
    customer = _find_customer(data, contact)
    not_found = {
        "found": False,
        "message": "Não encontrei pedidos com esses dados. Peça para o cliente conferir o "
        "telefone ou e-mail usado na compra.",
    }
    if not customer:
        return not_found
    orders = [o for o in data.orders.values() if o.customer_id == customer.id]
    if order_id is not None:
        orders = [o for o in orders if o.id == order_id]  # never reveal other customers' orders
    if not orders:
        return not_found
    orders.sort(key=lambda o: o.order_date, reverse=True)

    result = []
    for o in orders:
        entry = {
            "order_id": o.id,
            "date": o.order_date.strftime("%d/%m/%Y"),
            "status": ORDER_STATUS_PT[o.status],
            "items": [
                f"{it.quantity}x {data.products[it.product_id].name}"
                for it in o.items
                if it.product_id in data.products
            ],
            "total_paid": fmt_brl(o.total),
            "payment": _payment_label(o.payment_method),
        }
        if o.tracking_code:
            entry["tracking_code"] = o.tracking_code
        if o.estimated_delivery:
            label = "entregue em" if o.status == "delivered" else "previsão de entrega"
            entry[label] = o.estimated_delivery.strftime("%d/%m/%Y")
        if o.notes:
            entry["notes"] = o.notes
        entry["return_and_warranty"] = _return_windows(o, today)
        result.append(entry)
    return {
        "found": True,
        "customer_first_name": customer.name.split()[0],
        "customer_city": customer.city,
        "today": today.strftime("%d/%m/%Y"),
        "orders": result,
    }


def get_store_status(data: StoreData) -> dict:
    return store_status()


def escalate_to_human(
    data: StoreData, reason: str, summary: str, customer_contact: str | None = None
) -> dict:
    protocol = f"EM-{datetime.now():%y%m%d}-{uuid.uuid4().hex[:4].upper()}"
    record = {
        "protocol": protocol,
        "created_at": now_local().isoformat(),
        "reason": reason,
        "summary": summary,
        "customer_contact": customer_contact,
    }
    try:
        with Path(HANDOFF_LOG).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # read-only deploys: the protocol is still returned to the customer
    return {
        "protocol": protocol,
        "return_time": "até 24 horas úteis",
        "contact_channels": "WhatsApp (67) 3321-4500 ou telefone (67) 3341-4444",
    }


# --------------------------------------------------------------------------- schemas


def _nullable(type_: str, description: str, **extra) -> dict:
    return {"type": [type_, "null"], "description": description, **extra}


def build_tool_schemas(data: StoreData) -> list[dict]:
    categories = sorted(c.name for c in data.categories.values())
    return [
        {
            "type": "function",
            "name": "search_products",
            "description": (
                "Search the instrument catalog by name/brand/type, category and price range. "
                "Use for any question about which products exist, prices or availability. "
                "Prices are final (promotions already applied)."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": _nullable(
                        "string", "Free text: model, brand or type, e.g. 'Takamine GD20'."
                    ),
                    "category": {
                        "type": ["string", "null"],
                        "enum": [*categories, None],
                        "description": "Category filter.",
                    },
                    "max_price": _nullable("number", "Maximum price in BRL."),
                    "min_price": _nullable("number", "Minimum price in BRL."),
                    "only_available": {
                        "type": "boolean",
                        "description": "True to return only items in stock.",
                    },
                },
                "required": ["query", "category", "max_price", "min_price", "only_available"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_product_details",
            "description": (
                "Full details of one product: description, specs, price, payment conditions "
                "and, if unavailable, similar alternatives that are in stock."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "integer"}},
                "required": ["product_id"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "quote_purchase",
            "description": (
                "Total price for one or more products with every payment option (PIX, card "
                "installments, debit/boleto) and shipping."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_id": {"type": "integer"},
                                "quantity": {"type": "integer"},
                            },
                            "required": ["product_id", "quantity"],
                            "additionalProperties": False,
                        },
                    },
                    "delivery_in_campo_grande": _nullable(
                        "boolean",
                        "True if delivery is in Campo Grande, false for other cities, "
                        "null if unknown or pickup in store.",
                    ),
                },
                "required": ["items", "delivery_in_campo_grande"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "find_orders",
            "description": (
                "Look up a customer's orders (status, items, tracking, delivery date and "
                "return/warranty deadlines). Requires the phone or e-mail used in the purchase."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "contact": {
                        "type": "string",
                        "description": "Customer phone number or e-mail used in the purchase.",
                    },
                    "order_id": _nullable("integer", "Order number, if the customer knows it."),
                },
                "required": ["contact", "order_id"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "get_store_status",
            "description": (
                "Current date/time in Campo Grande, whether the store is open now, and the "
                "next opening time (considers holidays)."
            ),
            "strict": True,
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "type": "function",
            "name": "escalate_to_human",
            "description": (
                "Register a complaint or a request that needs a human (refunds, returns, "
                "damaged products, special quotes) and get a protocol number."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "enum": ["complaint", "return_or_exchange", "shipping_quote", "other"],
                    },
                    "summary": {"type": "string", "description": "Short summary for the team."},
                    "customer_contact": _nullable("string", "Customer phone or e-mail."),
                },
                "required": ["reason", "summary", "customer_contact"],
                "additionalProperties": False,
            },
        },
    ]


TOOL_FUNCTIONS: dict[str, Callable[..., dict]] = {
    "search_products": search_products,
    "get_product_details": get_product_details,
    "quote_purchase": quote_purchase,
    "find_orders": find_orders,
    "get_store_status": get_store_status,
    "escalate_to_human": escalate_to_human,
}


def run_tool(data: StoreData, name: str, arguments: dict) -> dict:
    func = TOOL_FUNCTIONS.get(name)
    if not func:
        return {"error": f"Unknown tool {name}"}
    try:
        return func(data, **arguments)
    except Exception as exc:  # a tool error must never crash the chat
        return {"error": f"{type(exc).__name__}: {exc}"}
