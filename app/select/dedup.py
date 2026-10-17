"""Tekrar önleme (dedup): URL, başlık benzerliği, embedding, entity/event."""
from __future__ import annotations

import logging
from datetime import timedelta

from rapidfuzz import fuzz

from app.common import normalize_text, now_istanbul, to_istanbul
from app.config import schedule_config
from app.llm.gemini import cosine_similarity
from app.models import Candidate, HistoryEntry

log = logging.getLogger("tekno-pusula.dedup")


def normalize_url(url: str) -> str:
    """URL normalize: utm_* parametreleri, www, sondaki / temizlenir."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url.strip().lower())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.startswith("utm_") and k not in ("ref", "source", "fbclid", "gclid")
    ]
    netloc = parts.netloc.removeprefix("www.")
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, netloc, path, urlencode(query), ""))


def title_similarity(a: str, b: str) -> float:
    """Normalize başlık benzerliği (token_set_ratio, 0-100)."""
    return fuzz.token_set_ratio(normalize_text(a), normalize_text(b))


def is_duplicate(
    candidate: Candidate,
    history: list[HistoryEntry],
    *,
    today_posts: list[HistoryEntry] | None = None,
) -> tuple[bool, str]:
    """Aday reddedilmeli mi? (sebep, reddedildi_mi)"""
    cfg = schedule_config()["dedup"]
    title_threshold = cfg["title_similarity_threshold"]
    emb_threshold = cfg["embedding_similarity_threshold"]
    news_window = cfg["news_event_window_days"]
    edu_window = cfg["edu_topic_window_days"]
    max_per_entity = schedule_config().get("max_posts_per_entity_per_day", 2)

    cand_url = normalize_url(candidate.url)
    cand_norm_title = normalize_text(candidate.title)
    is_edu = candidate.event_type == "edu_topic" or candidate.source_kind == "official"

    for entry in history:
        # 1. Aynı canonical URL
        if entry.canonical_url and normalize_url(entry.canonical_url) == cand_url:
            return True, f"aynı canonical URL: {entry.canonical_url}"

        # 2. Başlık benzerliği
        sim = title_similarity(candidate.title, entry.original_title or entry.title_tr)
        if sim >= title_threshold:
            return True, f"başlık benzerliği %{sim:.0f} (eşik {title_threshold})"

        # 3. Aynı ana olay: embedding kosinüs ya da entity + event_type
        try:
            entry_dt = to_istanbul(_parse_dt(entry.created_at) or now_istanbul())
        except Exception:
            entry_dt = now_istanbul()
        age_days = (now_istanbul() - entry_dt).days
        window = edu_window if is_edu else news_window
        if age_days <= window:
            if candidate.embedding and entry.embedding:
                cos = cosine_similarity(candidate.embedding, entry.embedding)
                if cos >= emb_threshold:
                    return True, f"embedding benzerliği {cos:.2f} (eşik {emb_threshold})"
            if (
                candidate.entities
                and entry.entities
                and set(candidate.entities) & set(entry.entities)
                and candidate.event_type
                and candidate.event_type == entry.event_type
            ):
                return True, (
                    f"aynı olay: entity {set(candidate.entities) & set(entry.entities)} "
                    f"+ event_type {candidate.event_type}"
                )

    # 4. Aynı gün aynı şirket hakkında en fazla N post
    if today_posts:
        for entity in candidate.entities:
            count = sum(1 for e in today_posts if entity in e.entities)
            if count >= max_per_entity:
                return True, f"günlük entity limiti: {entity} ({count}/{max_per_entity})"
            for e in today_posts:
                if entity in e.entities and (
                    not candidate.entities
                    or not (set(candidate.entities) & set(e.entities))
                ):
                    continue

    return False, ""


def _parse_dt(raw: str):
    from dateutil import parser as dateparser

    if not raw:
        return None
    try:
        return dateparser.parse(raw)
    except (ValueError, OverflowError):
        return None