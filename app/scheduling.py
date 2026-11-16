"""Slot decisions shared by the workflow preflight and the pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta


def due_slots(schedule: dict, history: list[dict], now: datetime) -> list[str]:
    """One fresh slot per run; never publish a burst of stale catch-up posts."""
    done = {h["slot"] for h in history if h.get("date") == now.date().isoformat()}
    window = timedelta(minutes=schedule.get("max_catchup_minutes", 90))
    eligible = []
    for item in schedule.get("slots", []):
        hm = item["time"]
        hour, minute = map(int, hm.split(":"))
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if hm not in done and timedelta(0) <= now - scheduled <= window:
            eligible.append(hm)
    return sorted(eligible, reverse=True)[:1]


def needs_recovery(history: list[dict], now: datetime) -> bool:
    for entry in history:
        try:
            if datetime.fromisoformat(entry.get("created_at", "")) < now - timedelta(days=2):
                continue
        except (ValueError, TypeError):
            continue
        for status in entry.get("status_per_platform", []):
            if status.get("state") == "submitted" and status.get("external_id"):
                return True
            if (status.get("state") in ("pending", "failed") and not status.get("external_id")
                    and status.get("attempts", 0) < 5):
                return True
    return False
