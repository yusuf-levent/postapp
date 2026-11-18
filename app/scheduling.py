"""Slot decisions shared by the workflow preflight and the pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.publish.retry import RECOVERY_MAX_ATTEMPTS


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


def within_recovery_window(created_at: str, now: datetime) -> bool:
    try:
        return datetime.fromisoformat(created_at) >= now - timedelta(days=2)
    except (ValueError, TypeError):
        return False


def platform_recovery_due(
    status: dict,
    now: datetime,
    *,
    recent: bool,
    max_attempts: int = RECOVERY_MAX_ATTEMPTS,
) -> bool:
    retry_at = status.get("retry_at", 0)
    if retry_at:
        if retry_at > now.timestamp():
            return False
    elif not recent:
        return False
    if status.get("external_id"):
        return status.get("state") == "submitted"
    return status.get("state") in ("pending", "failed") and status.get("attempts", 0) < max_attempts


def needs_recovery(history: list[dict], now: datetime) -> bool:
    for entry in history:
        recent = within_recovery_window(entry.get("created_at", ""), now)
        if any(platform_recovery_due(status, now, recent=recent)
               for status in entry.get("status_per_platform", [])):
            return True
    return False
