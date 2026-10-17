"""Slayt metinleri üretimi (yalnızca doğrulanmış iddialardan)."""
from __future__ import annotations

import logging
import re

from app.llm import prompts
from app.llm.gemini import GeminiClient
from app.models import ClaimVerification, EduDeck, SlideDeck

log = logging.getLogger("tekno-pusula.slides")

MAX_TITLE = 60
MAX_BODY = 280


class ContentValidationError(ValueError):
    """Üretilen metin doğrulanmış iddiaları aşıyor."""


def generate_slides(
    llm: GeminiClient,
    verifications: list[ClaimVerification],
    source_names: list[str],
) -> SlideDeck:
    """Doğrulanmış iddialardan 6 slaytlık içerik üretir + son kontrol yapar."""
    claims_text = "\n".join(
        f"- {v.claim}" for v in verifications if v.verdict == "supported"
    )
    prompt = prompts.SLIDES_PROMPT.format(
        claims=claims_text, source_names=", ".join(source_names)
    )
    deck = llm.generate_structured(
        prompt, SlideDeck, system=prompts.CONTENT_SYSTEM, label="slides"
    )

    # Sınır kontrolü
    violations = _check_limits(deck)
    if violations:
        log.warning("Slayt limit aşımları: %s — kısaltma isteniyor", violations)
        deck = _shorten(llm, deck, violations)

    # Doğrulanmış iddia dışı bilgi kontrolü
    if not _content_only_uses_verified(deck, verifications):
        log.warning("Doğrulanmamış bilgi tespit edildi — metin yeniden üretiliyor")
        prompt2 = (
            prompt
            + "\n\nÖNEMLİ: Önceki taslakta doğrulanmış iddialarda olmayan bilgiler vardı. "
            "Yalnızca aşağıdaki iddialardaki bilgileri kullan, hiçbir rakam/isim/tarih ekleme:\n"
            + claims_text
        )
        deck = llm.generate_structured(
            prompt2, SlideDeck, system=prompts.CONTENT_SYSTEM, label="slides-retry"
        )
        violations = _check_limits(deck)
        if violations:
            deck = _shorten(llm, deck, violations)

    return deck


def generate_edu_deck(llm: GeminiClient, claims_text: str, source_names: list[str]) -> EduDeck:
    """Eğitim postu yapısı: kapak, problem, adım adım ipuçları, CTA."""
    prompt = (
        "Aşağıdaki doğrulanmış bilgilerle 6 slaytlık EĞİTİM/BİLGİ postu üret.\n\n"
        f"--- DOĞRULANMIŞ BİLGİLER ---\n{claims_text}\n\n"
        f"--- KAYNAKLAR ---\n{', '.join(source_names)}\n\n"
        "JSON yapısı: cover (category_label, title, subtitle, source_tags), "
        "problem (heading + 2 kart), steps (3 slayt, her biri heading + 2-3 kart, "
        "gerekiyorsa code_block — örnek kod/prompt), cta (question, reminder_line).\n"
        "Adım adım, pratik ve uygulanabilir olsun. Doğrulanmamış bilgi ekleme."
    )
    return llm.generate_structured(
        prompt, EduDeck, system=prompts.CONTENT_SYSTEM, label="edu-slides"
    )


def _check_limits(deck: SlideDeck) -> list[str]:
    """Başlık ≤ 60, gövde ≤ 280 karakter kontrolü."""
    violations: list[str] = []
    if len(deck.cover.title) > MAX_TITLE:
        violations.append(f"cover.title: {len(deck.cover.title)}")
    for name, text in (
        ("cover.subtitle", deck.cover.subtitle),
        ("stat.stat_caption", deck.stat.stat_caption),
        ("stat.stat_quote", deck.stat.stat_quote),
        ("cta.question", deck.cta.question),
    ):
        if len(text) > MAX_BODY:
            violations.append(f"{name}: {len(text)}")
    for section_name, cards in (
        ("context", deck.context.cards),
        ("details", deck.details.cards),
        ("impact", deck.impact.cards),
    ):
        for i, card in enumerate(cards):
            if len(card.card_title) > 40:
                violations.append(f"{section_name}[{i}].card_title: {len(card.card_title)}")
            if len(card.card_body) > MAX_BODY:
                violations.append(f"{section_name}[{i}].card_body: {len(card.card_body)}")
    return violations


def _shorten(llm: GeminiClient, deck: SlideDeck, violations: list[str]) -> SlideDeck:
    """Limit aşan metinleri Gemini'ye kısalttırır (alt limitler korunur)."""
    problem_list = "\n".join(f"- {v}" for v in violations)
    prompt = (
        "Aşağıdaki slayt metinlerinde karakter limiti aşımları var. "
        "Metinleri anlamlı biçimde KISALT, hiçbir bilgi kaybı olmadan özleştir.\n\n"
        f"Aşımlar:\n{problem_list}\n\n"
        f"Mevcut JSON:\n{deck.model_dump_json()}\n\n"
        "Kurallar: cover.title ≤ 60 karakter, tüm gövde metinleri ≤ 280 karakter, "
        "card_title ≤ 40 karakter. Türkçe karakterler korunmalı."
    )
    try:
        return llm.generate_structured(
            prompt, SlideDeck, system=prompts.CONTENT_SYSTEM, label="slides-shorten"
        )
    except Exception as exc:
        log.error("Kısaltma başarısız, mevcut metin kullanılacak: %s", exc)
        return deck


def _content_only_uses_verified(
    deck: SlideDeck, verifications: list[ClaimVerification]
) -> bool:
    """Metinde doğrulanmış iddialarda olmayan sayı/isim var mı? (kodla kontrol)"""
    verified_text = " ".join(v.claim.lower() for v in verifications)
    verified_tokens = set(re.findall(r"[a-zçğıöşü0-9%.,]+", verified_text))

    for text in deck.all_text():
        # Metindeki sayısal değerler doğrulanmış iddialarda geçmeli
        for num in re.findall(r"%?\d[\d.,]*", text):
            token = num.lower().rstrip(".,")
            if token and token not in verified_tokens:
                # Rakam doğrulanmış metnin içinde geçiyor mu?
                if token not in verified_text:
                    log.warning("Doğrulanmamış rakam: %r (metin: %r)", num, text[:60])
                    return False
    return True