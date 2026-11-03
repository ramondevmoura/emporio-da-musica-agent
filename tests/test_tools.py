from datetime import date

import pytest

from emporio import tools
from emporio.data import get_store_data
from emporio.tools import (
    build_tool_schemas,
    find_orders,
    get_product_details,
    quote_purchase,
    run_tool,
    search_products,
)


@pytest.fixture(scope="module")
def data():
    return get_store_data()


def names(result):
    return [r["name"] for r in result["results"]]


def test_search_is_typo_and_accent_tolerant(data):
    assert names(search_products(data, query="takamine gd 20")) == [
        "Takamine GD20 Dreadnought Natural"
    ]
    assert "Yamaha C40 Nylon Natural" in names(search_products(data, query="violao yamaha"))
    assert names(search_products(data, query="guitara gibson"))


def test_search_violoes_up_to_1000_only_available(data):
    r = search_products(data, category="Violões", max_price=1000, only_available=True)
    assert r["total_found"] == 12
    assert "Giannini GF-3D Dreadnought Sunburst" not in names(r)  # out of stock
    assert "Shelby SN-7C 7 Cordas Nylon Natural" not in names(r)  # discontinued


def test_search_out_of_catalog(data):
    r = search_products(data, query="saxofone")
    assert r["total_found"] == 0
    assert "apenas instrumentos" in r["note"]


def test_unavailable_product_suggests_alternatives(data):
    gf3d = next(p for p in data.products.values() if p.name.startswith("Giannini GF-3D"))
    details = get_product_details(data, gf3d.id)
    assert details["availability"] == "esgotado no momento"
    alts = details["available_alternatives"]
    assert alts and all(a["availability"] == "disponível" for a in alts)


def test_quote_rejects_quantity_above_stock(data):
    assert "error" in quote_purchase(data, [{"product_id": 95, "quantity": 99}], True)


def test_orders_require_matching_contact(data):
    assert find_orders(data, "naoexiste@x.com")["found"] is False
    # order 1 belongs to customer 3, not to customer 1
    assert find_orders(data, "(67) 99812-3456", order_id=1)["found"] is False


def test_orders_found_by_phone_in_any_format(data):
    for contact in ["(67) 99812-3456", "67998123456", "99812-3456"]:
        r = find_orders(data, contact)
        assert r["found"] and r["customer_first_name"] == "Lucas"


def test_return_window_computed_from_delivery(data):
    # Order 8 (customer 2) shipped with estimated delivery 2026-02-28
    customer = data.customers[2]
    order8 = find_orders(data, customer.email, order_id=8, today=date(2026, 3, 3))["orders"][0]
    assert order8["status"] == "enviado (a caminho)"

    order7_owner = data.customers[data.orders[7].customer_id]
    r = find_orders(data, order7_owner.email, order_id=7, today=date(2026, 2, 20))
    windows = r["orders"][0]["return_and_warranty"]
    assert windows["days_since_delivery"] == 3
    assert windows["regret_return_7_days"] is True


def test_escalation_returns_protocol(data, tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "HANDOFF_LOG", tmp_path / "h.jsonl")
    r = run_tool(
        data, "escalate_to_human", {"reason": "complaint", "summary": "x", "customer_contact": None}
    )
    assert r["protocol"].startswith("EM-")
    assert (tmp_path / "h.jsonl").exists()


def test_run_tool_never_raises(data):
    assert "error" in run_tool(data, "get_product_details", {"product_id": "abc"})
    assert "error" in run_tool(data, "nope", {})


def test_schemas_are_strict(data):
    for schema in build_tool_schemas(data):
        assert schema["strict"] is True
        params = schema["parameters"]
        assert params["additionalProperties"] is False
        assert set(params.get("required", [])) == set(params["properties"])


def test_search_reports_unavailable_exact_match(data):
    r = search_products(data, query="Giannini GF-3D", only_available=True)
    assert "Giannini GF-3D Dreadnought Sunburst" not in names(r)
    assert any("esgotado" in m for m in r["matching_but_unavailable"])


def test_duplicate_email_reveals_nothing_until_disambiguated(data):
    # Two customer records share bruno.martins@jmail.com (data quirk)
    r = find_orders(data, "bruno.martins@jmail.com")
    assert r["found"] is False and r["needs_more_info"] is True
    assert "Bruno" not in str(r)
    # The order number or the phone narrows it down to one record
    by_order = find_orders(data, "bruno.martins@jmail.com", order_id=10)
    assert by_order["found"] and by_order["orders"][0]["order_id"] == 10
    assert find_orders(data, "(67) 98543-2109")["found"] is True


def test_stuck_orders_are_flagged(data):
    today = date(2026, 11, 2)
    ana = data.customers[2].email  # order 8: shipped, ETA 28/02/2026
    shipped = find_orders(data, ana, order_id=8, today=today)["orders"][0]
    assert shipped["attention"].startswith("ATRASADO")

    owner13 = data.customers[data.orders[13].customer_id].email  # pending since March
    assert "Pagamento pendente" in find_orders(data, owner13, 13, today)["orders"][0]["attention"]

    # Before the ETA nothing is flagged
    on_time = find_orders(data, ana, order_id=8, today=date(2026, 2, 20))["orders"][0]
    assert "attention" not in on_time
