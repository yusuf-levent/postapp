"""Makale metni çekme (trafilatura) ve yayın tarihi çıkarma."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

import trafilatura
from dateutil import parser as dateparser

from app.common import http_get
from app.models import Candidate

log = logging.getLogger("tekno-pusula.article")

PREFERRED_DATE_META = (
    "article:published_time",
    "og:published_time",
    "datePublished",
    "date",
    "pubdate",
)


def extract_text(url: str) -> tuple[str, datetime | None]:
    """Makale metnini ve yayın tarihini döndürür.

    Yayın tarihi öncelikle makale sayfasından (meta/JSON-LD) doğrulanır;
    bulunamazsa RSS tarihi kullanılır (çağrıyan taraf).
    """
    resp = http_get(url)
    if resp is None or resp.status_code != 200:
        log.warning("Makale çekilemedi: %s", url)
        return "", None
    html = resp.text
    text = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
    pub = extract_date(html)
    return text.strip(), pub


def extract_date(html: str) -> datetime | None:
    """HTML içinden yayın tarihini çıkarır: meta etiketleri → JSON-LD → time tag."""
    # 1. meta property/content
    for meta_name in PREFERRED_DATE_META:
        pattern = (
            r'<meta[^>]+(?:property|name|itemprop)=["\']'
            + re.escape(meta_name)
            + r'["\'][^>]+content=["\']([^"\']+)["\']'
        )
        m = re.search(pattern, html, re.IGNORECASE)
        if not m:
            pattern_rev = (
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name|itemprop)=["\']'
                + re.escape(meta_name)
                + r'["\']'
            )
            m = re.search(pattern_rev, html, re.IGNORECASE)
        if m:
            dt = _parse_dt(m.group(1))
            if dt:
                return dt

    # 2. JSON-LD datePublished
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        dt = _find_datepublished(data)
        if dt:
            return dt

    # 3. <time datetime="...">
    m = re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if m:
        return _parse_dt(m.group(1))
    return None


def _find_datepublished(data: object) -> datetime | None:
    if isinstance(data, dict):
        for key in ("datePublished", "dateCreated", "uploadDate"):
            if key in data:
                dt = _parse_dt(str(data[key]))
                if dt:
                    return dt
        for value in data.values():
            dt = _find_datepublished(value)
            if dt:
                return dt
    elif isinstance(data, list):
        for item in data:
            dt = _find_datepublished(item)
            if dt:
                return dt
    return None


def _parse_dt(raw: str) -> datetime | None:
    try:
        dt = dateparser.parse(raw)
    except (ValueError, OverflowError):
        return None
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def enrich_candidate(candidate: Candidate) -> Candidate:
    """Adayın makale metnini çeker, tarihi doğrular, tarih bulunamazsa adayı düşürür.

    Dönüş: güncellenmiş aday ya da None (tarih yoksa).
    """
    text, pub = extract_text(candidate.url)
    if text:
        candidate.summary = text[:4000]
        candidate.raw["full_text"] = text
    if pub is not None:
        candidate.published = pub
    if candidate.published is None:
        log.info("Tarih bulunamadı, aday atlanıyor: %s", candidate.url)
        return None  # type: ignore[return-value]
    return candidate