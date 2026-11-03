"""Deterministic reply used when the LLM is unavailable (outage, timeout, rate limit...).

It needs no API call: the customer still gets the store's channels, the opening hours and
whether the store is open right now, so the conversation (and the sale) is not lost.
"""

from __future__ import annotations

from datetime import datetime

from emporio import store_info
from emporio.store_hours import store_status


def status_line(now: datetime | None = None) -> str:
    status = store_status(now)
    if status["is_open"]:
        return f"🟢 Agora a loja está aberta, até as {status['closes_at']}."
    reason = f" ({status['holiday_today']})" if status.get("holiday_today") else ""
    return f"🔴 Agora a loja está fechada{reason}. Voltamos {status['next_opening']}."


def contact_block() -> str:
    return (
        f"💬 WhatsApp: {store_info.WHATSAPP}\n"
        f"📞 Telefone: {store_info.PHONE}\n"
        f"✉️ E-mail: {store_info.EMAIL}\n"
        f"📍 {store_info.ADDRESS}\n"
        f"🕐 {store_info.HOURS}"
    )


def fallback_message(now: datetime | None = None) -> str:
    return (
        f"Obrigada pelo seu contato com a {store_info.STORE_NAME}! 🎸\n\n"
        "Meu atendimento automático está com instabilidade agora e não consigo consultar "
        "preços, estoque ou pedidos. Mas a nossa equipe pode te ajudar:\n\n"
        f"{contact_block()}\n\n"
        f"{status_line(now)}\n\n"
        "Se preferir, tente me escrever de novo daqui a alguns minutos."
    )
