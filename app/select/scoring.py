"""Aday puanlama: önem × güncellik × görsel potansiyeli × kaynak sayısı."""
from __future__ import annotations

import re
from datetime import datetime

from app.collect.dates import day_offset_of
from app.models import Candidate

# Büyük şirket/etki sinyalleri
BIG_ENTITIES = (
    "openai", "google", "deepmind", "microsoft", "apple", "meta", "nvidia",
    "amazon", "aws", "anthropic", "github", "tesla", "qualcomm", "amd", "intel",
    "samsung", "huawei", "ibm", "oracle", "adobe", "hugging face", "mistral",
    "xai", "deepseek", "broadcom", "tsmc", "arm",
)

BREAKING_MARKERS = (
    "launches", "unveils", "announces", "releases", "raises", "acquires",
    "partnership", "breakthrough", "record", "first", "new model", "chip",
    "gpu", "benchmark", "security flaw", "vulnerability", "update",
    "duyurdu", "tanıttı", "çıkardı",
)

NUMBER_RE = re.compile(r"%?\d[\d.,]*\s*(?:billion|million|milyar|milyon|%|x|GB|TB|MHz|GHz)?",
                       re.IGNORECASE)


def _importance(candidate: Candidate) -> float:
    text = f"{candidate.title} {candidate.summary}".lower()
    score = 1.0
    if any(e in text for e in BIG_ENTITIES):
        score += 1.5
    if any(m in text for m in BREAKING_MARKERS):
        score += 1.0
    if NUMBER_RE.search(text):
        score += 0.5
    return score


def _freshness(candidate: Candidate) -> float:
    if candidate.published is None:
        return 0.0
    offset = day_offset_of(candidate.published)
    # 0 gün = 1.0, her gün %15 düşer
    return max(0.1, 1.0 - 0.15 * offset)


def _visual_potential(candidate: Candidate) -> float:
    text = f"{candidate.title} {candidate.summary}".lower()
    visual_markers = (
        "robot", "chip", "gpu", "device", "phone", "laptop", "satellite",
        "car", "drone", "factory", "lab", "data center", "processor", "screen",
        "gadget", "wearable", "rocket", "quantum",
    )
    return 1.5 if any(m in text for m in visual_markers) else 1.0


def _source_count(candidate: Candidate, source_index: dict[str, list[str]]) -> float:
    """Aynı olayın kaç farklı kaynakta göründüğü (URL dışı başlık eşleşmesiyle)."""
    key = candidate.title.lower()[:40]
    urls = source_index.get(key, [])
    unique = len(set(urls))
    return 1.0 + 0.4 * min(unique, 4)


_STOPWORDS = {
    "about", "after", "again", "against", "apple", "before", "being", "between",
    "could", "Every", "every", "first", "found", "their", "there", "these",
    "those", "through", "under", "until", "where", "which", "while", "world",
    "would", "years",
}


def _keywords(title: str) -> set[str]:
    words = re.findall(r"[a-zA-Z0-9]{4,}", title.lower())
    return {w for w in words if w not in _STOPWORDS}


def score_candidates(
    candidates: list[Candidate],
    *,
    source_index: dict[str, list[str]] | None = None,
) -> list[Candidate]:
    """Adayları puanlar ve azalan sırada döndürür. Tarih önceliği puanın parçasıdır.

    source_index: başlık öneki → [kaynak URL'leri] (çapraz kaynak sayısı için).
    """
    idx = source_index or {}
    kw_map = {id(c): _keywords(c.title) for c in candidates}
    dom_map = {
        id(c): (c.url.split("/")[2] if "//" in c.url else c.source_name)
        for c in candidates
    }
    for cand in candidates:
        my_kw = kw_map[id(cand)]
        my_dom = dom_map[id(cand)]
        corroborating_domains: set[str] = set()
        if my_kw:
            for other in candidates:
                other_dom = dom_map[id(other)]
                if other_dom == my_dom:
                    continue
                if len(my_kw & kw_map[id(other)]) >= 2:
                    corroborating_domains.add(other_dom)
        cross_bonus = 2.5 if corroborating_domains else 1.0
        cand.score = (
            _importance(cand)
            * _freshness(cand)
            * _visual_potential(cand)
            * _source_count(cand, idx)
            * cross_bonus
        )
    candidates.sort(
        key=lambda c: (
            c.published or datetime.min,  # tarih önceliği: bugün → dün → ...
            c.score,
        ),
        reverse=True,
    )
    return candidates


def build_source_index(candidates: list[Candidate]) -> dict[str, list[str]]:
    """Başlık öneki → URL listesi (çapraz kaynak sayımı için)."""
    index: dict[str, list[str]] = {}
    for cand in candidates:
        key = cand.title.lower()[:40]
        index.setdefault(key, []).append(cand.url)
    return index