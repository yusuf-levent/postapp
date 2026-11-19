"""İddia çıkarımı (Aşama 1) ve çapraz kaynak arama (Aşama 2)."""
from __future__ import annotations

import logging
import re

from rapidfuzz import fuzz

from app.config import sources_config
from app.common import normalize_text, source_identity
from app.llm import prompts
from app.llm.gemini import GeminiClient
from app.models import Candidate, Claim, ClaimList, CrosscheckInfo

log = logging.getLogger("tekno-pusula.claims")

MAX_CLAIMS = 8

_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "into", "over",
    "after", "before", "about", "more", "most", "just", "will", "would",
    "could", "should", "have", "has", "had", "been", "being", "were", "was",
    "are", "not", "but", "its", "their", "your", "our", "his", "her", "they",
    "them", "who", "what", "when", "where", "why", "how", "now", "new", "all",
    "any", "can", "may", "out", "off", "own", "says", "said", "gets", "get",
    "make", "makes", "made", "available", "announces", "announced", "launches",
    "launched", "releases", "released", "lets", "let", "here", "first",
    "world", "year", "years", "best", "good", "next", "one", "two", "day",
    "days", "tech", "technology", "company", "companies", "report", "reports",
    "reported", "feature", "features", "update", "updates", "mode", "using",
    "used", "use", "way", "ways", "still", "even", "than", "also", "back",
    "into", "onto", "only", "much", "many", "very", "like", "time", "today",
}

_GENERIC_ENTITIES = {
    "ai", "artificial intelligence", "tech", "technology", "app", "software",
    "data", "cloud", "internet", "company", "companies", "startup", "users",
    "model", "models", "system", "platform", "service",
}


def _meaningful_tokens(text: str) -> set[str]:
    norm = normalize_text(text)
    return {
        tok for tok in norm.split()
        if (len(tok) >= 3 or tok.isdigit()) and tok not in _STOPWORDS
    }


def _entity_in_text(entity: str, norm_text: str) -> bool:
    norm_ent = normalize_text(entity)
    if not norm_ent or norm_ent in _GENERIC_ENTITIES or len(norm_ent) < 3:
        return False
    return bool(re.search(r"\b" + re.escape(norm_ent) + r"\b", norm_text))


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

    Stopword'ler ayıklanarak yalnızca anlamlı başlık/varlık örtüşmesi olan
    farklı domain adayları puanlanır ve en güçlü eşleşmeler önce döndürülür.
    """
    sel_domain = source_identity(selected.url)
    sel_tokens = _meaningful_tokens(selected.title)
    sel_summary_tokens = _meaningful_tokens(f"{selected.title} {selected.summary[:400]}")

    raw_entities = list(dict.fromkeys([*info.entities, *selected.entities]))
    target_entities = [
        e.strip() for e in raw_entities
        if normalize_text(e) not in _GENERIC_ENTITIES and len(normalize_text(e)) >= 3
    ]

    scored_matches: list[tuple[float, str, dict[str, str]]] = []

    for cand in all_candidates:
        if cand.url == selected.url:
            continue
        domain = source_identity(cand.url)
        if not domain or domain == sel_domain:
            continue

        cand_tokens = _meaningful_tokens(cand.title)
        shared_title = sel_tokens & cand_tokens
        clean_sim = (
            fuzz.token_set_ratio(" ".join(sorted(sel_tokens)), " ".join(sorted(cand_tokens)))
            if sel_tokens and cand_tokens
            else 0.0
        )

        cand_title_norm = normalize_text(cand.title)
        cand_haystack_norm = normalize_text(f"{cand.title} {cand.summary[:600]}")
        ent_hits_title = sum(1 for ent in target_entities if _entity_in_text(ent, cand_title_norm))
        ent_hits_all = sum(1 for ent in target_entities if _entity_in_text(ent, cand_haystack_norm))

        cand_summary_tokens = _meaningful_tokens(f"{cand.title} {cand.summary[:400]}")
        shared_summary = sel_summary_tokens & cand_summary_tokens

        strong_title = len(shared_title) >= 2 and clean_sim >= 45
        very_high_title = len(shared_title) >= 1 and clean_sim >= 65
        strong_entity = ent_hits_all >= 2 and (
            len(shared_title) >= 1 or ent_hits_title >= 1 or len(shared_summary) >= 4
        )
        if not (strong_title or very_high_title or strong_entity):
            continue

        match_score = (
            len(shared_title) * 30.0
            + clean_sim * 0.5
            + ent_hits_title * 20.0
            + ent_hits_all * 10.0
            + min(len(shared_summary), 8) * 3.0
        )
        scored_matches.append((
            match_score,
            domain,
            {"url": cand.url, "title": cand.title, "source": cand.source_name},
        ))

    scored_matches.sort(key=lambda item: item[0], reverse=True)
    out: list[dict[str, str]] = []
    seen_domains: set[str] = {sel_domain} if sel_domain else set()
    for _, domain, item in scored_matches:
        if domain in seen_domains:
            continue
        seen_domains.add(domain)
        out.append(item)
        if len(out) >= max_sources:
            break
    return out
