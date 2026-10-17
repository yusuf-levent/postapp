"""Slot ve tarih hesaplama (Europe/Istanbul, cron gecikmelerine dayanıklı)."""
from __future__ import annotations

from datetime import datetime, time, timedelta

from app.common import now_istanbul, to_istanbul


def nearest_slot(
    now: datetime | None = None, schedule: list[dict] | None = None
) -> str:
    """Çalışma anındaki İstanbul saatine en yakın slot'u "HH:MM" olarak döndürür.

    Cron gecikmelerinde (örn. 09:07 yerine 09:23 başladıysa) hâlâ 09:00 slotu
    bulunur: slot saatine en yakın olan, ancak slot saatinden en fazla 90 dakika
    sonraki başlangıçlar o slota atanır.
    """
    from app.config import schedule_config

    sched = schedule or schedule_config()["slots"]
    current = to_istanbul(now or now_istanbul())
    slot_times = [(s["time"], _parse_hhmm(s["time"])) for s in sched]

    best: str | None = None
    best_delta = timedelta(hours=99)
    # Dünkü slotlar da adaydır (gece yarısı sonrası manuel çalıştırmalar için)
    for day_offset in (-1, 0):
        for label, stime in slot_times:
            slot_dt = datetime.combine(
                current.date(), stime, tzinfo=current.tzinfo
            ) + timedelta(days=day_offset)
            delta = abs(current - slot_dt)
            if delta < best_delta:
                best = label
                best_delta = delta
    if best is None:
        # Tüm slotlar 90 dakikadan eski (örn. gece yarısı sonrası) → son slot
        best = slot_times[-1][0]
    return best


def slot_type(
    slot: str, schedule: list[dict] | None = None, force_type: str = "auto"
) -> str:
    """Slotun içerik tipini döndürür: news | edu."""
    from app.config import schedule_config

    if force_type in ("news", "edu"):
        return force_type
    sched = schedule or schedule_config()["slots"]
    for s in sched:
        if s["time"] == slot:
            return s.get("type", "news")
    return "news"


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def today_label(offset_days: int = 0) -> str:
    """YYYY-MM-DD (İstanbul)."""
    d = now_istanbul() + timedelta(days=offset_days)
    return d.strftime("%Y-%m-%d")


def within_lookback(published: datetime | None, max_days: int = 7) -> bool:
    """Yayın tarihi bugün mü, en fazla max_days geriye kadar mı?"""
    if published is None:
        return False
    pub = to_istanbul(published)
    now = now_istanbul()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    earliest = start_of_today - timedelta(days=max_days - 1)
    return earliest <= pub <= now + timedelta(hours=1)


def day_offset_of(published: datetime) -> int:
    """Haberin bugünden kaç gün önce olduğunu döndürür (0 = bugün)."""
    pub = to_istanbul(published).replace(hour=0, minute=0, second=0, microsecond=0)
    today = now_istanbul().replace(hour=0, minute=0, second=0, microsecond=0)
    return (today - pub).days