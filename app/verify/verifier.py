"""İddia bazlı doğrulama (Aşama 3-4): iki tur, alıntı doğrulama, karar kuralları."""
from __future__ import annotations

import logging
import random
import re

from rapidfuzz import fuzz

from app.common import normalize_text, source_identity
from app.config import schedule_config
from app.llm import prompts
from app.llm.gemini import GeminiClient
from app.models import Claim, ClaimVerification, ClaimVerificationList, Evidence
from app.select.dedup import normalize_url

log = logging.getLogger("tekno-pusula.verifier")

_INVALID_QUOTES = {"not_found", "not found", "none", "null", "n/a", "yok", ""}


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
    claims_block = "\n".join(f"{i+1}. {'[ANA İDDİA] ' if c.is_main else ''}{c.claim}" for i, c in enumerate(ordered))

    if round_number == 1:
        system, template = prompts.VERIFICATION_SYSTEM, prompts.VERIFICATION_PROMPT
    else:
        system, template = (
            prompts.VERIFICATION_ROUND2_SYSTEM,
            prompts.VERIFICATION_ROUND2_PROMPT,
        )

    prompt = template.format(sources_block=sources_block, claims_block=claims_block)
    unique_domains = {source_identity(u) for u in source_texts if u}
    if len(unique_domains) >= 2:
        prompt += (
            "\nBirden fazla kaynak verildi. Her iddia için destekleyen TÜM kaynaklardan "
            "(özellikle [ANA İDDİA] için farklı kaynak alan adlarından) ayrı birebir alıntılar ekle. "
            "Bir kaynakta destek yoksa o kaynak için kanıt ekleme; asla 'not_found' gibi sahte alıntı yazma. "
            "claim alanına [ANA İDDİA] önekini koyma, yalnızca iddianın metnini yaz."
        )
    else:
        prompt += (
            "\nHer desteklenen iddia için kaynak metinden birebir alıntı ver; "
            "destek yoksa verdict='not_found' ve evidence=[] döndür. "
            "claim alanına [ANA İDDİA] önekini koyma, yalnızca iddianın metnini yaz."
        )
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


def _resolve_source(ev_url: str, source_texts: dict[str, str], norm_map: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    """Evidence URL'sini orijinal kaynak anahtarına ve metnine çözümler."""
    if ev_url in source_texts:
        return ev_url, source_texts[ev_url]
    if ev_url:
        hit = norm_map.get(normalize_url(ev_url))
        if hit is not None:
            return hit
    return None


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
    norm_sources = {normalize_url(u): (u, txt) for u, txt in source_texts.items()}
    final: list[ClaimVerification] = []

    for v1 in round1:
        key = _norm_claim(v1.claim)
        v2 = by_claim_round2.get(key)
        if v2 is None and key:
            # Küçük noktalama/önek farklarında yüksek eşikle round2 karşılığını bul
            best_score = 0.0
            for k2, cand_v2 in by_claim_round2.items():
                score = fuzz.ratio(key, k2)
                if score >= 92 and score > best_score:
                    best_score = score
                    v2 = cand_v2
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
            seen: set[tuple[str, str]] = set()
            for ev in list(v1.evidence) + list(v2.evidence):
                q_clean = (ev.quote or "").strip()
                if q_clean.lower() in _INVALID_QUOTES:
                    continue
                resolved = _resolve_source(ev.url, source_texts, norm_sources)
                if resolved is not None:
                    canon_url, src_text = resolved
                    if (canon_url, q_clean) in seen:
                        continue
                    seen.add((canon_url, q_clean))
                    if quote_in_source(q_clean, {canon_url: src_text}):
                        evidence.append(Evidence(url=canon_url, quote=q_clean))
                        continue
                log.warning("Uydurma alıntı tespit edildi, kanıt iptal: %r", q_clean[:80])
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
    cleaned = re.sub(r"^\s*(?:\d+\.\s*)?(?:\[?ANA\s+[İI]DD[İI]A\]?\s*:?\s*)", "", text, flags=re.IGNORECASE)
    return normalize_text(cleaned)[:120]
