"""Deterministic pricing rules from the store policy (sections 3 and 6).

All money math lives here, never in the LLM:
- active promotions lower the list price;
- PIX gives 5% off the list price, but it does NOT stack with a promotion (§6.2);
- credit card: up to 12x interest-free, with a minimum installment that depends on the
  number of installments (§3.1);
- mixing payment methods is only allowed for purchases above R$ 2.000 (§3.1);
- shipping in the Campo Grande metro area is free above R$ 500, otherwise R$ 35 (§5.1).
"""

from __future__ import annotations

from dataclasses import dataclass

from emporio.data import Product, Promotion

PIX_DISCOUNT = 0.05
MAX_INSTALLMENTS = 12
MIXED_PAYMENT_THRESHOLD = 2000.0
FREE_SHIPPING_THRESHOLD = 500.0
LOCAL_SHIPPING_FEE = 35.0


def fmt_brl(value: float) -> str:
    """Format as Brazilian currency: 2199.0 -> 'R$ 2.199,00'."""
    s = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def min_installment_value(n: int) -> float:
    """Minimum value of each installment for an n-installment plan (§3.1)."""
    if n <= 3:
        return 50.0
    if n <= 6:
        return 80.0
    return 100.0


def max_installments(amount: float) -> int:
    """Largest number of interest-free installments allowed for this amount."""
    for n in range(MAX_INSTALLMENTS, 1, -1):
        if amount / n >= min_installment_value(n):
            return n
    return 1


@dataclass(frozen=True)
class PriceQuote:
    list_price: float
    final_price: float  # price after promotion (= list price when there is none)
    promotion_name: str | None
    promotion_percent: float | None
    pix_price: float | None  # None when a promotion applies (no stacking)
    max_installments: int
    installment_value: float

    def to_dict(self) -> dict:
        d = {
            "list_price": fmt_brl(self.list_price),
            "final_price": fmt_brl(self.final_price),
            "best_price": fmt_brl(self.pix_price if self.pix_price else self.final_price),
            "card": (
                f"até {self.max_installments}x de {fmt_brl(self.installment_value)} sem juros"
                if self.max_installments > 1
                else "à vista no cartão"
            ),
        }
        if self.promotion_name:
            d["promotion"] = f"{self.promotion_name}: {self.promotion_percent:g}% OFF"
            d["pix"] = "desconto PIX não se aplica (produto já em promoção)"
        else:
            d["pix"] = f"{fmt_brl(self.pix_price)} no PIX (5% de desconto)"
        return d


def quote_product(product: Product, promotion: Promotion | None) -> PriceQuote:
    list_price = product.price
    if promotion:
        final = round(list_price * (1 - promotion.discount_percent / 100), 2)
        pix = None
    else:
        final = list_price
        pix = round(list_price * (1 - PIX_DISCOUNT), 2)
    n = max_installments(final)
    return PriceQuote(
        list_price=list_price,
        final_price=final,
        promotion_name=promotion.description if promotion else None,
        promotion_percent=promotion.discount_percent if promotion else None,
        pix_price=pix,
        max_installments=n,
        installment_value=round(final / n, 2),
    )


def quote_cart(lines: list[tuple[Product, Promotion | None, int]], local_delivery: bool) -> dict:
    """Quote a cart of (product, promotion, quantity) lines, with every payment option."""
    subtotal = 0.0
    pix_total = 0.0
    for product, promo, qty in lines:
        q = quote_product(product, promo)
        subtotal += q.final_price * qty
        # PIX discount only applies to items that are not on promotion (§6.2)
        pix_total += (q.pix_price if q.pix_price is not None else q.final_price) * qty
    subtotal, pix_total = round(subtotal, 2), round(pix_total, 2)
    n = max_installments(subtotal)

    if local_delivery:
        shipping = 0.0 if subtotal > FREE_SHIPPING_THRESHOLD else LOCAL_SHIPPING_FEE
        shipping_info = "grátis" if shipping == 0 else fmt_brl(shipping)
    else:
        shipping = None
        shipping_info = "calculado pelo CEP (PAC, SEDEX ou Jadlog) - a equipe faz a cotação"

    return {
        "subtotal": fmt_brl(subtotal),
        "pix_total": fmt_brl(pix_total),
        "card": f"até {n}x de {fmt_brl(subtotal / n)} sem juros" if n > 1 else "à vista",
        "debit_or_boleto": fmt_brl(subtotal),
        "can_mix_payment_methods": subtotal > MIXED_PAYMENT_THRESHOLD,
        "shipping": shipping_info,
        "total_with_shipping_card": fmt_brl(subtotal + shipping) if shipping is not None else None,
    }
