from datetime import date, datetime

from emporio.store_hours import TZ, national_holidays, store_status


def at(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=TZ)


def test_easter_based_holidays():
    h = national_holidays(2026)
    assert h[date(2026, 4, 3)] == "Sexta-feira Santa"  # Easter 2026 = Apr 5
    assert h[date(2026, 2, 17)] == "Carnaval"


def test_open_on_weekday_afternoon():
    s = store_status(at(2026, 11, 3, 15))  # Tuesday
    assert s["is_open"] is True
    assert s["closes_at"] == "18:00"


def test_closed_on_holiday_points_to_next_day():
    s = store_status(at(2026, 11, 2, 10))  # Monday, Finados
    assert s["is_open"] is False
    assert s["holiday_today"] == "Finados"
    assert s["next_opening"] == "amanhã às 09:00"


def test_saturday_closes_at_13():
    assert store_status(at(2026, 11, 7, 12))["is_open"] is True
    s = store_status(at(2026, 11, 7, 14))
    assert s["is_open"] is False
    assert s["next_opening"] == "segunda (09/11) às 09:00"  # Sunday closed


def test_before_opening_today():
    s = store_status(at(2026, 11, 3, 7, 30))
    assert s["next_opening"] == "hoje às 09:00"
