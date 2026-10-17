"""Gemini tek noktadan erişim: yapılandırılmış çıktı, embedding, Google Search grounding.

Resmi SDK: google-genai (eski google-generativeai DEĞİL).
Model adı env'den gelir; 429/kota hatasında yedek modele düşer.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel

from app.config import settings

log = logging.getLogger("tekno-pusula.gemini")

# Ücretsiz katman için istekler arası minimum bekleme (saniye)
MIN_INTERVAL_SECONDS = 2.0

RETRYABLE_STATUS = {404, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """Gemini çağrısı kurtarılamayacak şekilde başarısız oldu."""


class GeminiClient:
    """Tüm Gemini çağrıları bu sınıftan geçer (rate limit + retry + fallback)."""

    def __init__(self, api_key: str | None = None):
        cfg = settings()
        key = api_key or cfg.gemini_api_key
        if not key:
            raise LLMError("GEMINI_API_KEY tanımlı değil (GitHub Secrets).")
        self._client = genai.Client(api_key=key)
        self._model = cfg.gemini_model
        self._fallback_model = cfg.gemini_fallback_model
        self._last_call = 0.0
        self.call_count = 0

    # ---------------------------------------------------------------- internals
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < MIN_INTERVAL_SECONDS:
            time.sleep(MIN_INTERVAL_SECONDS - elapsed)
        self._last_call = time.monotonic()

    def _call_with_fallback(
        self, fn: Callable[[str], Any], *, label: str
    ) -> Any:
        """fn(model_name) çağrısını 429/5xx hatasında backoff ile tekrarlar."""
        last_exc: Exception | None = None
        for attempt in range(3):
            self._throttle()
            self.call_count += 1
            try:
                return fn(self._model)
            except genai_errors.APIError as exc:
                last_exc = exc
                status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                if status not in RETRYABLE_STATUS:
                    raise
                if status in (429, 500, 502, 503, 504) and attempt < 2:
                    wait = 12 * (attempt + 1)
                    log.warning(
                        "%s: model %s geçici hata (%s), %ds beklenip tekrar denenecek (%d/3)",
                        label, self._model, status, wait, attempt + 1,
                    )
                    time.sleep(wait)
                    continue
                if self._fallback_model and self._fallback_model != self._model:
                    log.warning(
                        "%s: model %s hata (%s), yedek %s deneniyor",
                        label, self._model, status, self._fallback_model,
                    )
                    time.sleep(5)
                    self._throttle()
                    self.call_count += 1
                    return fn(self._fallback_model)
                raise
        if last_exc:
            raise last_exc

    # ------------------------------------------------------- structured output
    @staticmethod
    def _thinking(model_name: str) -> Any:
        if "3." in model_name and hasattr(genai_types, "ThinkingConfig"):
            try:
                return genai_types.ThinkingConfig(thinking_level="low")
            except Exception:
                return None
        return None

    def generate_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        *,
        system: str | None = None,
        label: str = "structured",
    ) -> BaseModel:
        """response_schema ile yapılandırılmış JSON çıktısı üretir."""

        def run(model_name: str) -> Any:
            config = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                system_instruction=system,
                temperature=0.2,
                thinking_config=self._thinking(model_name),
            )
            return self._client.models.generate_content(
                model=model_name, contents=prompt, config=config
            )

        resp = self._call_with_fallback(run, label=label)
        text = getattr(resp, "text", None)
        if not text:
            raise LLMError(f"{label}: boş yanıt alındı.")
        data = json.loads(text)
        return schema.model_validate(data)

    def generate_structured_list(
        self,
        prompt: str,
        item_schema: type[BaseModel],
        *,
        wrapper: type[BaseModel] | None = None,
        system: str | None = None,
        label: str = "structured-list",
    ) -> list[BaseModel]:
        """Bir liste üretir. wrapper verilirse {items: [...]} sarmalayıcı kullanılır."""
        if wrapper is not None:
            result = self.generate_structured(prompt, wrapper, system=system, label=label)
            return list(getattr(result, "items"))
        # Pydantic v2: doğrudan liste şeması için RootModel sarmalayıcısı kullan
        from pydantic import RootModel

        class _ListModel(RootModel[list[item_schema]]):  # type: ignore[valid-type]
            pass

        result = self.generate_structured(prompt, _ListModel, system=system, label=label)
        return list(result.root)

    def generate_text(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.5,
        label: str = "text",
    ) -> str:
        def run(model_name: str) -> Any:
            config = genai_types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                thinking_config=self._thinking(model_name),
            )
            return self._client.models.generate_content(
                model=model_name, contents=prompt, config=config
            )

        resp = self._call_with_fallback(run, label=label)
        text = getattr(resp, "text", None)
        if not text:
            raise LLMError(f"{label}: boş yanıt alındı.")
        return text.strip()

    # ------------------------------------------------------------- multimodal
    def analyze_images(
        self,
        prompt: str,
        image_paths: list[str],
        *,
        system: str | None = None,
        label: str = "vision",
    ) -> str:
        """Görselleri Gemini'ye gösterip metinsel değerlendirme alır."""
        import pathlib

        parts: list[Any] = [prompt]
        for p in image_paths:
            data = pathlib.Path(p).read_bytes()
            parts.append(genai_types.Part.from_bytes(data=data, mime_type="image/png"))

        def run(model_name: str) -> Any:
            config = genai_types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.1,
                thinking_config=self._thinking(model_name),
            )
            return self._client.models.generate_content(
                model=model_name, contents=parts, config=config
            )

        resp = self._call_with_fallback(run, label=label)
        return (getattr(resp, "text", "") or "").strip()

    # -------------------------------------------------------------- grounding
    def search_grounded(
        self, prompt: str, *, allowed_domains: list[str], label: str = "grounding"
    ) -> list[dict[str, str]]:
        """Google Search grounding ile kaynak arar.

        Dönüş: [{"url": ..., "title": ...}, ...] — yalnızca allowed_domains
        içindeki domainler kabul edilir (whitelist dışı sonuçlar atılır).
        """
        import requests

        def run(model_name: str) -> Any:
            config = genai_types.GenerateContentConfig(
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                temperature=0.1,
                thinking_config=self._thinking(model_name),
            )
            return self._client.models.generate_content(
                model=model_name, contents=prompt, config=config
            )

        resp = self._call_with_fallback(run, label=label)
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for cand in _extract_grounding_chunks(resp):
            url = cand.get("url", "")
            title = cand.get("title", "")
            if not url:
                continue
            combined = f"{url} {title}".lower()
            if "vertexaisearch.cloud.google.com" in url.lower() and any(
                d in combined for d in allowed_domains
            ):
                try:
                    r = requests.head(url, allow_redirects=True, timeout=8)
                    if r.url:
                        url = r.url
                        cand["url"] = url
                        combined = f"{url} {title}".lower()
                except Exception:
                    pass
            if url in seen:
                continue
            if not any(d in combined for d in allowed_domains):
                continue
            seen.add(url)
            results.append(cand)
        return results

    # -------------------------------------------------------------- embeddings
    def embed(self, text: str, *, label: str = "embed") -> list[float]:
        """Gemini embedding döndürür (dedup kosinüs benzerliği için)."""

        def run(model_name: str) -> Any:
            return self._client.models.embed_content(
                model="gemini-embedding-001",
                contents=text,
                config=genai_types.EmbedContentConfig(
                    output_dimensionality=768, task_type="RETRIEVAL_DOCUMENT"
                ),
            )

        try:
            resp = self._call_with_fallback(run, label=label)
        except genai_errors.APIError as exc:
            log.warning("embedding alınamadı (%s), embedding'siz devam", exc)
            return []
        embeddings = getattr(resp, "embeddings", None)
        if not embeddings:
            return []
        return list(embeddings[0].values)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _extract_grounding_chunks(resp: Any) -> list[dict[str, str]]:
    """Grounding metadata içinden kaynak URL'lerini çıkarır."""
    out: list[dict[str, str]] = []
    meta = None
    for cand in getattr(resp, "candidates", None) or []:
        meta = getattr(cand, "grounding_metadata", None)
        if meta:
            break
    if not meta:
        return out
    for chunk in getattr(meta, "grounding_chunks", None) or []:
        web = getattr(chunk, "web", None)
        if web:
            out.append(
                {
                    "url": getattr(web, "uri", "") or "",
                    "title": getattr(web, "title", "") or "",
                }
            )
    return out