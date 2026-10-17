"""data/history.json yönetimi: yayınlanan postlar ve dedup verisi."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import DATA_DIR
from app.models import HistoryEntry

log = logging.getLogger("tekno-pusula.history")

HISTORY_FILE = DATA_DIR / "history.json"


def load_history() -> list[HistoryEntry]:
    """Tüm geçmişi okur. Dosya yoksa boş liste döner."""
    if not HISTORY_FILE.exists():
        return []
    try:
        raw = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        log.error("history.json okunamadı: %s", exc)
        return []
    return [HistoryEntry.model_validate(item) for item in raw]


def save_history(entries: list[HistoryEntry]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = [e.model_dump() for e in entries]
    HISTORY_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def append_entry(entry: HistoryEntry) -> list[HistoryEntry]:
    """Yeni kayıt ekler (aynı id varsa günceller)."""
    entries = load_history()
    entries = [e for e in entries if e.id != entry.id]
    entries.append(entry)
    save_history(entries)
    return entries


def entries_for_day(date_label: str) -> list[HistoryEntry]:
    """Belirli günün kayıtları (aynı gün aynı şirket limiti için)."""
    return [e for e in load_history() if e.date == date_label]


def slot_already_done(date_label: str, slot: str) -> bool:
    """Aynı slot için zaten post üretildi mi? (idempotent çalıştırma)"""
    return any(
        e.date == date_label and e.slot == slot for e in load_history()
    )


def recent_entries(days: int = 14) -> list[HistoryEntry]:
    """Son N günün kayıtları (kurtarma turu için)."""
    from datetime import datetime, timedelta

    from app.common import now_istanbul

    cutoff = now_istanbul() - timedelta(days=days)
    out = []
    for e in load_history():
        try:
            created = datetime.fromisoformat(e.created_at)
            if created >= cutoff:
                out.append(e)
        except (ValueError, TypeError):
            out.append(e)  # tarih yoksa dahil et (güvenli taraf)
    return out