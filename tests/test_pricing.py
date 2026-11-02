import pytest

from emporio.data import Product, Promotion
from emporio.pricing import fmt_brl, max_installments, quote_cart, quote_product


def make_product(price: float, pid: int = 1) -> Product:
    return Product(pid, "Teste", 5, price, "", 3, "active")


def promo(pct: float, pid: int = 1) -> Promotion:
    return Promotion(1, pid, pct, "Black Friday", True)


def test_fmt_brl():
    assert fmt_brl(2199) == "R$ 2.199,00"
    assert fmt_brl(599.9) == "R$ 599,90"
    assert fmt_brl(11499) == "R$ 11.499,00"


@pytest.mark.parametrize(
    "amount, expected",
    [
        (2199, 12),  # 12 x 183.25 >= 100
        (700, 7),  # 7 x 100 >= 100
        (699, 6),  # 7x would be 99.86 < 100 -> fall back to 6x (min 80)
        (300, 3),  # 4x would be 75 < 80 -> 3x (min 50)
        (159.9, 3),
        (120, 2),
        (80, 1),
    ],
)
def test_max_installments_respects_policy_minimums(amount, expected):
    assert max_installments(amount) == expected


def test_pix_discount_without_promotion():
    q = quote_product(make_product(2199), None)
    assert q.final_price == 2199
    assert q.pix_price == pytest.approx(2089.05)
    assert q.max_installments == 12


def test_pix_does_not_stack_with_promotion():
    q = quote_product(make_product(1000), promo(10))
    assert q.final_price == 900
    assert q.pix_price is None
    d = q.to_dict()
    assert "não se aplica" in d["pix"]
    assert d["promotion"] == "Black Friday: 10% OFF"
    assert d["list_price"] == "R$ 1.000,00"  # original price is always shown (§6.2)


def test_cart_local_shipping_and_mixed_payment():
    cheap = quote_cart([(make_product(300), None, 1)], local_delivery=True)
    assert cheap["shipping"] == "R$ 35,00"
    assert cheap["can_mix_payment_methods"] is False

    big = quote_cart([(make_product(1500), None, 2)], local_delivery=True)
    assert big["shipping"] == "grátis"
    assert big["can_mix_payment_methods"] is True
    assert big["pix_total"] == "R$ 2.850,00"


def test_cart_pix_only_on_non_promo_items():
    lines = [(make_product(1000, 1), promo(10, 1), 1), (make_product(1000, 2), None, 1)]
    q = quote_cart(lines, local_delivery=False)
    assert q["subtotal"] == "R$ 1.900,00"
    assert q["pix_total"] == "R$ 1.850,00"  # 900 (promo, no PIX) + 950
    assert q["total_with_shipping_card"] is None
