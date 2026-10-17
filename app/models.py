"""Paylaşılan Pydantic modelleri (yapılandırılmış Gemini çıktıları dahil)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ doğrulama
class Evidence(BaseModel):
    url: str = ""
    quote: str = ""


class Claim(BaseModel):
    claim: str
    is_main: bool = False


class ClaimVerification(BaseModel):
    claim: str
    verdict: Literal["supported", "contradicted", "not_found"]
    evidence: list[Evidence] = Field(default_factory=list)


class ClaimVerificationList(BaseModel):
    items: list[ClaimVerification] = Field(default_factory=list)


class ClaimList(BaseModel):
    items: list[Claim] = Field(default_factory=list)


class CrosscheckInfo(BaseModel):
    search_query: str = ""
    entities: list[str] = Field(default_factory=list)
    event_type: str = ""


# -------------------------------------------------------------------- içerik
class Card(BaseModel):
    card_title: str
    card_body: str


class SlideCover(BaseModel):
    category_label: str
    title: str
    highlight_words: list[str] = Field(default_factory=list)
    highlight_color: Literal["yellow", "cyan"] = "yellow"
    subtitle: str = ""
    source_tags: list[str] = Field(default_factory=list)


class SlideContext(BaseModel):
    heading: str
    cards: list[Card] = Field(default_factory=list)


class SlideStat(BaseModel):
    big_stat: str
    stat_caption: str
    stat_quote: str = ""


class SlideDetails(BaseModel):
    heading: str
    cards: list[Card] = Field(default_factory=list)


class SlideImpact(BaseModel):
    heading: str
    cards: list[Card] = Field(default_factory=list)


class SlideCTA(BaseModel):
    question: str
    reminder_line: str = "Düşüncelerini yorumlarda paylaşmayı unutma! 💬"


class SlideDeck(BaseModel):
    cover: SlideCover
    context: SlideContext
    stat: SlideStat
    details: SlideDetails
    impact: SlideImpact
    cta: SlideCTA

    def all_text(self) -> list[str]:
        out: list[str] = [
            self.cover.category_label,
            self.cover.title,
            self.cover.subtitle,
            *self.cover.source_tags,
            self.context.heading,
            self.stat.big_stat,
            self.stat.stat_caption,
            self.stat.stat_quote,
            self.details.heading,
            self.impact.heading,
            self.cta.question,
            self.cta.reminder_line,
        ]
        for cards in (
            self.context.cards,
            self.details.cards,
            self.impact.cards,
        ):
            for c in cards:
                out.append(c.card_title)
                out.append(c.card_body)
        return [t for t in out if t]


class EduSlide(BaseModel):
    """Eğitim slaytı: monospace kod/prompt kutusu içerebilir."""

    heading: str = ""
    cards: list[Card] = Field(default_factory=list)
    code_block: str = ""


class EduDeck(BaseModel):
    cover: SlideCover
    problem: EduSlide
    steps: list[EduSlide] = Field(default_factory=list)
    cta: SlideCTA


# ------------------------------------------------------------------ açıklamalar
class Caption(BaseModel):
    text: str
    hashtags: list[str] = Field(default_factory=list)


class Captions(BaseModel):
    instagram: Caption
    tiktok: Caption
    x: Caption
    threads: Caption
    linkedin: Caption
    facebook: Caption


class CaptionsDoc(BaseModel):
    captions: Captions
    source_names: list[str] = Field(default_factory=list)
    title_tr: str = ""
    canonical_url: str = ""


# ------------------------------------------------------------------- görseller
class ImageCandidate(BaseModel):
    source: str  # wikimedia | pexels | ogimage | abstract
    url: str = ""
    local_path: str = ""
    width: int = 0
    height: int = 0
    license: str = ""
    author: str = ""
    credit_url: str = ""
    relevance_ok: bool = True
    alt_text: str = ""


# ---------------------------------------------------------------------- kayıt
class PlatformStatus(BaseModel):
    platform: str
    state: Literal["pending", "submitted", "published", "failed"] = "pending"
    external_id: str = ""
    permalink: str = ""
    attempts: int = 0
    last_error: str = ""


class HistoryEntry(BaseModel):
    id: str
    date: str  # YYYY-MM-DD (İstanbul)
    slot: str  # HH:MM
    type: Literal["news", "edu"]
    title_tr: str = ""
    original_title: str = ""
    source_urls: list[str] = Field(default_factory=list)
    canonical_url: str = ""
    entities: list[str] = Field(default_factory=list)
    event_type: str = ""
    embedding: list[float] = Field(default_factory=list)
    status_per_platform: list[PlatformStatus] = Field(default_factory=list)
    created_at: str = ""
    verified_claims_count: int = 0


class Candidate(BaseModel):
    """Toplama aşamasından seçim aşamasına taşınan ham haber adayı."""

    title: str
    url: str
    summary: str = ""
    published: datetime | None = None
    source_name: str = ""
    source_kind: Literal["news", "official"] = "news"
    entities: list[str] = Field(default_factory=list)
    event_type: str = ""
    embedding: list[float] = Field(default_factory=list)
    score: float = 0.0
    raw: dict[str, Any] = Field(default_factory=dict)