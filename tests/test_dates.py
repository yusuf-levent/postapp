"""Tarih filtresi (7 gün sınırı) ve slot hesaplama testleri."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.collect.dates import (
    day_offset_of,
    nearest_slot,
    slot_type,
    within_lookback,
)
from app.common import ISTANBUL


def test_within_lookback_today():
    now = datetime.now(ISTANBUL)
    assert within_lookback(now, max_days=7)


def test_within_lookback_seven_days_ago():
    d = datetime.now(ISTANBUL) - timedelta(days=6)
    assert within_lookback(d, max_days=7)


def test_outside_lookback_rejected():
    d = datetime.now(ISTANBUL) - timedelta(days=8)
    assert not within_lookback(d, max_days=7)


def test_none_rejected():
    assert not within_lookback(None, max_days=7)


def test_future_rejected():
    d = datetime.now(ISTANBUL) + timedelta(days=2)
    assert not within_lookback(d, max_days=7)


def test_day_offset():
    d = datetime.now(ISTANBUL) - timedelta(days=3)
    assert day_offset_of(d) == 3


def test_nearest_slot_morning():
    # 09:05 İstanbul → 09:00 slotu
    d = datetime(2026, 10, 15, 9, 5, tzinfo=ISTANBUL)
    assert nearest_slot(d) == "09:00"


def test_nearest_slot_cron_delay():
    # 09:23 (cron gecikmesi) → hâlâ 09:00 slotu (90 dk tolerans)
    d = datetime(2026, 10, 15, 9, 23, tzinfo=ISTANBUL)
    assert nearest_slot(d) == "09:00"


def test_nearest_slot_evening():
    d = datetime(2026, 10, 15, 21, 12, tzinfo=ISTANBUL)
    assert nearest_slot(d) == "21:00"


def test_nearest_slot_late_night():
    # Gece yarısı sonrası → son slot (21:00)
    d = datetime(2026, 10, 16, 0, 30, tzinfo=ISTANBUL)
    assert nearest_slot(d) == "21:00"


def test_slot_type_1800_is_edu():
    assert slot_type("18:00") == "edu"


def test_slot_type_0900_is_news():
    assert slot_type("09:00") == "news"


def test_slot_type_force():
    assert slot_type("09:00", force_type="edu") == "edu"