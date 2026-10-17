"""Platforma özel açıklama üretimi + karakter limiti doğrulaması."""
from __future__ import annotations

import logging

from app.config import platforms_config
from app.llm import prompts
from app.llm.gemini import GeminiClient
from app.models import Caption, Captions, CaptionsDoc

log = logging.getLogger("tekno-pusula.captions")

PLATFORM_KEYS = ("instagram", "tiktok", "x", "threads", "linkedin", "facebook")


class CaptionLimitError(ValueError):
    pass


def generate_captions(
    llm: GeminiClient,
    content_summary: str,
    source_names: list[str],
    *,
    max_retries: int = 2,
) -> Captions:
    """Her platform için açıklama üretir ve karakter limitlerini koda doğrular."""
    prompt = prompts.CAPTIONS_PROMPT.format(
        content=content_summary, source_names=", ".join(source_names)
    )
    captions = llm.generate_structured(
        prompt, Captions, system=prompts.CAPTIONS_SYSTEM, label="captions"
    )

    for key in PLATFORM_KEYS:
        cap = getattr(captions, key)
        cap.hashtags = [h.lstrip("#").strip() for h in cap.hashtags if h.lstrip("#").strip()]

    for attempt in range(max_retries + 1):
        over = _find_limit_violations(captions)
        if not over:
            return captions
        log.warning("Karakter limiti aşımları: %s", over)
        if attempt == max_retries:
            # Son çare: koda kısalt (hashtag'leri azalt, sonra kes)
            captions = _force_trim(captions, over)
            return captions
        captions = _request_shortening(llm, captions, over)
        for key in PLATFORM_KEYS:
            cap = getattr(captions, key)
            cap.hashtags = [h.lstrip("#").strip() for h in cap.hashtags if h.lstrip("#").strip()]
    return captions


def _effective_length(platform: str, text: str) -> int:
    """Platforma özel uzunluk: X'te URL 23 karakter sayılır, Threads'te emoji UTF-8 byte."""
    rules = platforms_config().platforms[platform]
    if platform == "x" and rules.url_length:
        import re

        urls = re.findall(r"https?://\S+", text)
        length = len(text)
        for u in urls:
            length += rules.url_length - len(u)
        return length
    if platform == "threads":
        return len(text.encode("utf-8"))
    return len(text)


def _find_limit_violations(captions: Captions) -> dict[str, int]:
    violations: dict[str, int] = {}
    for key in PLATFORM_KEYS:
        cap: Caption = getattr(captions, key)
        limit = platforms_config().platforms[key].limit
        length = _effective_length(key, cap.text)
        if length > limit:
            violations[key] = length
        hmin, hmax = platforms_config().platforms[key].hashtags
        if len(cap.hashtags) > hmax:
            violations[f"{key}.hashtags"] = len(cap.hashtags)
    return violations


def _request_shortening(
    llm: GeminiClient, captions: Captions, over: dict[str, int]
) -> Captions:
    prompt = (
        "Aşağıdaki sosyal medya açıklamalarında karakter/hashtag limiti aşımları var. "
        "Her açıklamayı KISALT ama tonu ve bilgiyi koru.\n\n"
        f"Aşımlar: {over}\n\n"
        f"Mevcut JSON:\n{captions.model_dump_json()}\n\n"
        "Limitler: " + _limits_summary()
    )
    return llm.generate_structured(
        prompt, Captions, system=prompts.CAPTIONS_SYSTEM, label="captions-shorten"
    )


def _force_trim(captions: Captions, over: dict[str, int]) -> Captions:
    """Gemini kısaltamazsa koda son çare kısaltma (hashtag azalt + kesme)."""
    import re

    for key in list(over.keys()):
        platform = key.split(".")[0]
        cap = getattr(captions, platform)
        rules = platforms_config().platforms[platform]
        # Önce hashtag'leri azalt
        if len(cap.hashtags) > rules.hashtags[1]:
            cap.hashtags = cap.hashtags[: rules.hashtags[1]]
        # Hâlâ aşıyorsa metni kes ve "..." ekle
        if _effective_length(platform, cap.text) > rules.limit:
            max_len = rules.limit - 3
            cap.text = cap.text[:max_len].rsplit(" ", 1)[0] + "…"
        setattr(captions, platform, cap)
    return captions


def _limits_summary() -> str:
    parts = []
    for key in PLATFORM_KEYS:
        r = platforms_config().platforms[key]
        parts.append(f"{key}: ≤{r.limit} karakter, hashtag {r.hashtags[0]}-{r.hashtags[1]}")
    return "; ".join(parts)


def to_doc(captions: Captions, source_names: list[str], title_tr: str, canonical_url: str) -> CaptionsDoc:
    return CaptionsDoc(
        captions=captions,
        source_names=source_names,
        title_tr=title_tr,
        canonical_url=canonical_url,
    )