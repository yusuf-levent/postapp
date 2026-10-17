"""RSS toplama (whitelist kaynaklar) ve tarih filtreleme."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import feedparser
from dateutil import parser as dateparser

from app.collect.dates import within_lookback
from app.common import http_get
from app.config import Source, sources_config
from app.models import Candidate

log = logging.getLogger("tekno-pusula.rss")


def parse_feed_date(entry: dict) -> datetime | None:
    """RSS girişinden yayın tarihini çıkarır; yoksa None."""
    for key in ("published_parsed", "updated_parsed"):
        struct = entry.get(key)
        if struct:
            return datetime(*struct[:6], tzinfo=timezone.utc)
    for key in ("published", "updated"):
        raw = entry.get(key)
        if raw:
            try:
                dt = dateparser.parse(raw)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except (ValueError, OverflowError):
                continue
    return None


def fetch_source(source: Source, *, max_items: int = 30) -> list[Candidate]:
    """Tek bir kaynaktan haber adaylarını toplar."""
    resp = http_get(source.url)
    if resp is None or resp.status_code != 200:
        log.warning("RSS alınamadı: %s (status=%s)", source.name,
                    resp.status_code if resp else "none")
        return []
    feed = feedparser.parse(resp.content)
    candidates: list[Candidate] = []
    for entry in feed.entries[:max_items]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        published = parse_feed_date(entry)
        candidates.append(
            Candidate(
                title=title,
                url=link,
                summary=_strip_html(summary)[:600],
                published=published,
                source_name=source.name,
                source_kind="official" if source in sources_config().official else "news",
            )
        )
    return candidates


def collect_all(
    *, max_days: int = 7, include_official: bool = False
) -> list[Candidate]:
    """Tüm whitelist kaynaklarından, tarih penceresi içindeki adayları toplar.

    Tarih önceliği (bugün → dün → ...) seçim aşamasında uygulanır; burada yalnızca
    7 gün sınırı uygulanır. Tarihi bulunamayan haberler ATLANIR.
    """
    cfg = sources_config()
    sources = cfg.all_feeds if include_official else cfg.news
    all_candidates: list[Candidate] = []
    for source in sources:
        try:
            items = fetch_source(source)
        except Exception as exc:  # kaynak başına hata izole edilir
            log.warning("RSS hatası %s: %s", source.name, exc)
            continue
        for cand in items:
            if cand.published is None:
                log.debug("Tarihsiz haber atlandı: %s", cand.url)
                continue
            if within_lookback(cand.published, max_days):
                all_candidates.append(cand)
    log.info("Toplanan aday: %d", len(all_candidates))
    return all_candidates


def _strip_html(text: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()