"""Opening hours (policy §2) with Brazilian national holidays, in Campo Grande's timezone.

The agent uses this to answer "are you open now?" correctly. It also uses it so that an
invitation to visit the store always points to a time when the store is actually open.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Campo_Grande")

# weekday() -> (open, close); Sunday closed
HOURS: dict[int, tuple[time, time]] = {
    **{d: (time(9), time(18)) for d in range(5)},  # Mon-Fri
    5: (time(9), time(13)),  # Saturday
}

WEEKDAYS_PT = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _easter(year: int) -> date:
    """Anonymous Gregorian algorithm (Meeus/Jones/Butcher)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    day = (h + l_ - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def national_holidays(year: int) -> dict[date, str]:
    easter = _easter(year)
    return {
        date(year, 1, 1): "Confraternização Universal",
        easter - timedelta(days=48): "Carnaval",
        easter - timedelta(days=47): "Carnaval",
        easter - timedelta(days=2): "Sexta-feira Santa",
        date(year, 4, 21): "Tiradentes",
        date(year, 5, 1): "Dia do Trabalho",
        easter + timedelta(days=60): "Corpus Christi",
        date(year, 9, 7): "Independência do Brasil",
        date(year, 10, 12): "Nossa Senhora Aparecida",
        date(year, 11, 2): "Finados",
        date(year, 11, 15): "Proclamação da República",
        date(year, 11, 20): "Dia da Consciência Negra",
        date(year, 12, 25): "Natal",
    }


def hours_for(day: date) -> tuple[time, time] | None:
    if day in national_holidays(day.year):
        return None
    return HOURS.get(day.weekday())


def now_local() -> datetime:
    return datetime.now(TZ)


def store_status(now: datetime | None = None) -> dict:
    """Is the store open right now, and when does it next open/close?"""
    now = (now or now_local()).astimezone(TZ)
    today = now.date()
    holiday = national_holidays(today.year).get(today)
    today_hours = hours_for(today)

    status = {
        "now": f"{WEEKDAYS_PT[now.weekday()]}, {now:%d/%m/%Y %H:%M}",
        "holiday_today": holiday,
    }
    if today_hours and today_hours[0] <= now.time() < today_hours[1]:
        status["is_open"] = True
        status["closes_at"] = today_hours[1].strftime("%H:%M")
        return status

    status["is_open"] = False
    # Next opening: later today, or the next day that has opening hours
    if today_hours and now.time() < today_hours[0]:
        status["next_opening"] = f"hoje às {today_hours[0]:%H:%M}"
        return status
    for offset in range(1, 10):
        day = today + timedelta(days=offset)
        h = hours_for(day)
        if h:
            label = "amanhã" if offset == 1 else f"{WEEKDAYS_PT[day.weekday()]} ({day:%d/%m})"
            status["next_opening"] = f"{label} às {h[0]:%H:%M}"
            break
    return status
