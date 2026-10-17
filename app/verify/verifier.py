"""İddia bazlı doğrulama (Aşama 3-4): iki tur, alıntı doğrulama, karar kuralları."""
from __future__ import annotations

import logging
import random

from rapidfuzz import fuzz

from app.common import normalize_text
from app.config import schedule_config
from app.llm import prompts
from app.llm.gemini import GeminiClient
from app.models import Claim, ClaimVerification, ClaimVerificationList, Evidence

log = logging.getLogger("tekno-pusula.verifier")


def verify_claims_round(
    llm: GeminiClient,
    claims: list[Claim],
    source_texts: dict[str, str],
    *,
    round_number: int,
) -> list[ClaimVerification]:
    """Tek tur iddia doğrulama. İkinci turda iddia sırası karıştırılır."""
    ordered = list(claims)
    if round_number == 2:
        random.shuffle(ordered)

    sources_block = "\n\n".join(
        f"=== KAYNAK: {url} ===\n{text[:8000]}" for url, text in source_texts.items()
    )
    claims_block = "\n".join(f"{i+1}. {c.claim}" for i, c in enumerate(ordered))

    if round_number == 1:
        system, template = prompts.VERIFICATION_SYSTEM, prompts.VERIFICATION_PROMPT
    else:
        system, template = (
            prompts.VERIFICATION_ROUND2_SYSTEM,
            prompts.VERIFICATION_ROUND2_PROMPT,
        )

    prompt = template.format(sources_block=sources_block, claims_block=claims_block)
    result = llm.generate_structured(
        prompt,
        ClaimVerificationList,
        system=system,
        label=f"verify-round{round_number}",
    )
    return list(result.items)


def quote_in_source(quote: str, source_texts: dict[str, str]) -> bool:
    """Alıntı gerçekten kaynak metinde geçiyor mu? (normalize fuzzy ≥ 90)"""
    if not quote.strip():
        return False
    threshold = schedule_config()["verification"]["quote_match_threshold"]
    norm_quote = normalize_text(quote)
    if not norm_quote:
        return False
    for text in source_texts.values():
        norm_text = normalize_text(text)
        if not norm_text:
            continue
        # Hızlı yol: birebir içerme
        if norm_quote in norm_text:
            return True
        # Pencere içinde fuzzy eşleşme
        words = norm_text.split()
        qwords = norm_quote.split()
        if not qwords:
            continue
        window = len(qwords) + 6
        for i in range(0, max(1, len(words) - window + 1)):
            chunk = " ".join(words[i : i + window])
            if fuzz.ratio(norm_quote, chunk) >= threshold:
                return True
    return False


def validate_evidence(
    round1: list[ClaimVerification],
    round2: list[ClaimVerification],
    source_texts: dict[str, str],
) -> list[ClaimVerification]:
    """İki turu birleştirir ve alıntıları koda doğrulatır.

    Kurallar:
    - İki turun sonucu farklıysa iddia `not_found` sayılır.
    - quote değerinin gerçekten kaynak metinde geçtiği kodla kontrol edilir;
      uydurma alıntı varsa o kanıt geçersizdir.
    """
    by_claim_round2 = {_norm_claim(v.claim): v for v in round2}
    final: list[ClaimVerification] = []

    for v1 in round1:
        key = _norm_claim(v1.claim)
        v2 = by_claim_round2.get(key)
        if v2 is None or v1.verdict != v2.verdict:
            # Tur farkı → not_found (en muhafazakar sonuç)
            final.append(
                ClaimVerification(claim=v1.claim, verdict="not_found", evidence=[])
            )
            continue

        verdict = v1.verdict
        evidence: list[Evidence] = []
        if verdict == "supported":
            # Her iki turun kanıtlarını birleştir, alıntıları doğrula
            seen: set[str] = set()
            for ev in list(v1.evidence) + list(v2.evidence):
                if ev.quote in seen:
                    continue
                seen.add(ev.quote)
                if quote_in_source(ev.quote, source_texts):
                    evidence.append(ev)
                else:
                    log.warning("Uydurma alıntı tespit edildi, kanıt iptal: %r", ev.quote[:80])
            if not evidence:
                verdict = "not_found"
        final.append(ClaimVerification(claim=v1.claim, verdict=verdict, evidence=evidence))

    return final


def decide(
    verifications: list[ClaimVerification],
) -> tuple[bool, list[ClaimVerification], str]:
    """Karar kuralları: haber yayınlanmalı mı?

    - `contradicted` tek bir iddia varsa → reddet
    - `not_found` iddialar metinden çıkarılır; ana iddia not_found ise → reddet
    - En az 2 bağımsız kaynak şartı ayrıca crosscheck aşamasında uygulanır
    """
    for v in verifications:
        if v.verdict == "contradicted":
            return False, [], f"çelişkili iddia: {v.claim}"

    usable = [v for v in verifications if v.verdict == "supported"]

    # Ana iddia kontrolü: ilk iddia "ana" kabul edilir
    if verifications and verifications[0].verdict != "supported":
        return False, [], "ana iddia doğrulanamadı (not_found)"

    if not usable:
        return False, [], "hiçbir iddia doğrulanamadı"

    return True, usable, ""


def _norm_claim(text: str) -> str:
    return normalize_text(text)[:120]