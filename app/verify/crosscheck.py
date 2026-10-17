"""İddia çıkarımı (Aşama 1) ve çapraz kaynak arama (Aşama 2)."""
from __future__ import annotations

import logging

from app.config import sources_config
from app.llm import prompts
from app.llm.gemini import GeminiClient
from app.models import Candidate, Claim, ClaimList, CrosscheckInfo

log = logging.getLogger("tekno-pusula.claims")

MAX_CLAIMS = 8


def extract_claims(llm: GeminiClient, article_text: str) -> list[Claim]:
    """Makale metninden doğrulanabilir somut iddiaları çıkarır."""
    prompt = prompts.CLAIM_EXTRACTION_PROMPT.format(
        article=article_text[:12000], max_claims=MAX_CLAIMS
    )
    result = llm.generate_structured(
        prompt, ClaimList, system=prompts.CLAIM_EXTRACTION_SYSTEM, label="claims"
    )
    claims = list(result.items)
    if claims:
        claims[0].is_main = True
    return claims


def crosscheck_query(llm: GeminiClient, candidate: Candidate) -> CrosscheckInfo:
    """Haber için arama sorgusu + entity listesi üretir."""
    prompt = prompts.CROSSCHECK_QUERY_PROMPT.format(
        title=candidate.title, summary=candidate.summary[:1500]
    )
    return llm.generate_structured(
        prompt, CrosscheckInfo, system=prompts.CLAIM_EXTRACTION_SYSTEM, label="crosscheck"
    )


def find_corroborating_sources(
    llm: GeminiClient,
    candidate: Candidate,
    info: CrosscheckInfo,
    *,
    max_sources: int = 3,
) -> list[dict[str, str]]:
    """Haberi doğrulayacak ek kaynakları bulur.

    Önce diğer whitelist RSS'lerinde başlık/entity eşleşmesi aranır (kodla),
    yetmezse Gemini Google Search grounding kullanılır. Grounding sonuçlarından
    yalnızca whitelist veya resmi kaynak domainleri kabul edilir.
    """
    cfg = sources_config()
    found: list[dict[str, str]] = []

    # 1. Grounding ile whitelist/official domainlerde ara
    query = (
        f"{info.search_query or candidate.title} "
        f"({candidate.source_name} OR {' OR '.join(info.entities[:3])})"
    )
    try:
        results = llm.search_grounded(
            f"Find news articles about: {query}",
            allowed_domains=cfg.allowed_domains,
            label="grounding",
        )
    except Exception as exc:
        log.warning("Grounding hatası: %s", exc)
        results = []

    # Adayın kendi URL'si hariç tutulur
    candidate_norm = candidate.url.rstrip("/")
    for r in results:
        if r["url"].rstrip("/") == candidate_norm:
            continue
        r["kind"] = "grounding"
        found.append(r)
        if len(found) >= max_sources:
            break

    # 2. Aynı olayın diğer whitelist kaynaklarında görülmesi (RSS düzeyinde)
    #    Bu, orkestratörde collect_all sonuçlarıyla yapılır; burada grounding
    #    sonuçlarına ek olarak entity eşleşmeli RSS haberleri de eklenir.
    return found


def corroborating_from_rss(
    all_candidates: list[Candidate],
    selected: Candidate,
    info: CrosscheckInfo,
    *,
    max_sources: int = 3,
) -> list[dict[str, str]]:
    """Toplanmış RSS adayları içinden aynı olayı doğrulayan diğer kaynakları bulur.

    Bağımsız kaynak sayımı için: biri diğerini kaynak gösterip aynen aktarmıyorsa
    (farklı domain + benzer başlık) bağımsız sayılır.
    """
    from app.select.dedup import title_similarity

    out: list[dict[str, str]] = []
    seen_domains: set[str] = set()
    for cand in all_candidates:
        if cand.url == selected.url:
            continue
        domain = cand.url.split("/")[2] if "//" in cand.url else ""
        if domain in seen_domains:
            continue
        # Başlık benzerliği VEYA entity kesişimi
        sim = title_similarity(cand.title, selected.title)
        entity_hit = bool(set(cand.entities) & set(info.entities))
        if sim >= 60 or entity_hit:
            seen_domains.add(domain)
            out.append(
                {"url": cand.url, "title": cand.title, "source": cand.source_name}
            )
            if len(out) >= max_sources:
                break
    return out