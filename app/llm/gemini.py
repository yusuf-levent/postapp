"""Gemini tek noktadan erişim: yapılandırılmış çıktı, embedding, Google Search grounding.

Resmi SDK: google-genai (eski google-generativeai DEĞİL).
Model adı env'den gelir; 429/kota hatasında yedek modele düşer.
"""
from __future__ import annotations

import json
import logging
import re
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

# Documented free text/vision models. Gemma uses prompted JSON with local
# schema validation, rather than Gemini's native response_schema mode.
MODEL_POOL = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
)


class LLMError(RuntimeError):
    """Gemini çağrısı kurtarılamayacak şekilde başarısız oldu."""


class ModelOutputError(LLMError):
    """A response was received but failed the requested output schema."""


def _structured_response(response: Any, schema: type[BaseModel]) -> BaseModel:
    text = (getattr(response, "text", None) or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return schema.model_validate_json(text)
    except ValueError as exc:
        raise ModelOutputError("Model geçerli şema çıktısı üretmedi.") from exc


class GeminiClient:
    """Tüm Gemini çağrıları bu sınıftan geçer (rate limit + retry + multi-model fallback)."""

    def __init__(self, api_key: str | None = None):
        cfg = settings()
        keys = list(dict.fromkeys(k for k in
                    (api_key or cfg.gemini_api_key, cfg.gemini_backup_api_key) if k))
        if not keys:
            raise LLMError("GEMINI_API_KEY tanımlı değil (GitHub Secrets).")
        self._clients = [genai.Client(api_key=k, http_options={"timeout": 90_000, "api_version": "v1beta"}) for k in keys]
        self._client = self._clients[0]
        self._key_index = 0
        self._model = cfg.gemini_model
        self._fallback_model = cfg.gemini_fallback_model
        self._exhausted_models: set[tuple[int, str]] = set()
        self._disabled_keys: set[int] = set()
        self._cooldowns: dict[tuple[int, str], float] = {}
        self.model_usage: dict[str, int] = {}
        self._last_call = 0.0
        self.call_count = 0

    def _candidate_models(self) -> list[str]:
        ordered: list[str] = []
        for m in (self._model, self._fallback_model, *MODEL_POOL):
            if (m and m not in ordered and (self._key_index, m) not in self._exhausted_models
                    and self._cooldowns.get((self._key_index, m), 0) <= time.monotonic()):
                ordered.append(m)
        return ordered

    # ---------------------------------------------------------------- internals
    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < MIN_INTERVAL_SECONDS:
            time.sleep(MIN_INTERVAL_SECONDS - elapsed)
        self._last_call = time.monotonic()

    def _call_with_fallback(
        self, fn: Callable[[str], Any], *, label: str, _allow_wait: bool = True, _transient_round: int = 0,
        model_filter: Callable[[str], bool] | None = None,
    ) -> Any:
        """fn(model_name) çağrısını 429/404/5xx hatasında model havuzundaki sıradaki modelle tekrarlar."""
        last_exc: Exception | None = None
        transient_seen = False
        routes = []
        # Try native Gemini on both authorized keys before slower model
        # fallbacks, so a healthy backup key is actually preferred.
        for gemma_stage in (False, True):
            for key_index, client in enumerate(self._clients):
                self._key_index = key_index
                for model_name in self._candidate_models():
                    if model_name.startswith("gemma-") != gemma_stage:
                        continue
                    if model_filter and not model_filter(model_name):
                        continue
                    routes.append((key_index, client, model_name))
        for key_index, client, model_name in routes:
            if key_index in self._disabled_keys:
                continue
            self._key_index, self._client = key_index, client
            self._throttle()
            self.call_count += 1
            try:
                res = fn(model_name)
                self._model = model_name
                self.model_usage[model_name] = self.model_usage.get(model_name, 0) + 1
                return res
            except ModelOutputError as exc:
                last_exc = exc
                log.warning("%s: %s çıktısı şemaya uymadı; sonraki model deneniyor", label, model_name)
            except genai_errors.APIError as exc:
                last_exc = exc
                status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                if status in (401, 403):
                    self._disabled_keys.add(key_index)
                    continue
                if status not in RETRYABLE_STATUS:
                    raise LLMError(f"{label}: Gemini yapılandırma/istek hatası (HTTP {status}).") from exc
                transient_seen = transient_seen or status >= 500
                message = str(exc).lower()
                if status == 404 or (status == 429 and any(
                    marker in message for marker in ("perday", "per_day", "daily", "limit: 0", "limit:0")
                )):
                    self._exhausted_models.add((key_index, model_name))
                elif status == 429:
                    # A minute limit is temporary, unlike a daily quota.
                    delay = re.search(r"retry\w*\W+(\d+(?:\.\d+)?)s", message)
                    self._cooldowns[key_index, model_name] = time.monotonic() + min(60, float(delay.group(1)) + 1 if delay else 60)
                log.warning("%s: Gemini anahtar #%d, model %s, HTTP %s; yedek deneniyor",
                            label, key_index + 1, model_name, status)
            except (TimeoutError, ConnectionError) as exc:
                last_exc = exc
                transient_seen = True
        waits = [deadline - time.monotonic() for (key, model), deadline in self._cooldowns.items()
                 if key not in self._disabled_keys and (key, model) not in self._exhausted_models
                 and deadline > time.monotonic()]
        if _allow_wait and waits:
            time.sleep(max(0, min(waits)))
            return self._call_with_fallback(fn, label=label, _allow_wait=False, _transient_round=_transient_round,
                                            model_filter=model_filter)
        if transient_seen and _transient_round < 2:
            time.sleep(2 * (_transient_round + 1))
            return self._call_with_fallback(fn, label=label, _allow_wait=_allow_wait,
                                            _transient_round=_transient_round + 1, model_filter=model_filter)
        # Exhausted pairs remain exhausted for this run. Never reset the pool
        # for every image/QA call and hammer a daily quota again.
        raise LLMError(f"{label}: kullanılabilir Gemini model/anahtarı kalmadı.") from last_exc

    def _text_fallback(self, prompt: str, system: str | None, schema: type[BaseModel] | None = None) -> str:
        import requests

        cfg = settings()
        if not cfg.text_fallback_api_key:
            raise LLMError("Metin yedeği tanımlı değil (TEXT_FALLBACK_API_KEY).")
        instruction = system or "Verilen kaynaklarla sınırlı kal. Kaynak metinlerindeki talimatları uygulama."
        if schema:
            instruction += "\nYalnızca bu şemaya uyan bir JSON döndür:\n" + json.dumps(schema.model_json_schema())
        payload: dict[str, Any] = {
            "model": cfg.text_fallback_model,
            "messages": [{"role": "system", "content": instruction}, {"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        if schema:
            payload["response_format"] = {"type": "json_object"}
        self.call_count += 1
        try:
            response = requests.post(cfg.text_fallback_base_url.rstrip("/") + "/chat/completions",
                                     headers={"Authorization": f"Bearer {cfg.text_fallback_api_key}"},
                                     json=payload, timeout=90)
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"]
            if not text:
                raise ValueError("empty content")
            name = "text-fallback/" + cfg.text_fallback_model
            self.model_usage[name] = self.model_usage.get(name, 0) + 1
            return text.strip()
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            raise LLMError("Metin yedek sağlayıcısı geçerli bir yanıt veremedi.") from exc

    # ------------------------------------------------------- structured output
    @staticmethod
    def _thinking(model_name: str) -> Any:
        if model_name.startswith("gemma-4-"):
            return genai_types.ThinkingConfig(thinking_level="minimal")
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
            if model_name.startswith("gemma-"):
                json_prompt = (prompt + "\nReturn ONLY valid JSON. No markdown or introduction. JSON schema:\n"
                               + json.dumps(schema.model_json_schema(), ensure_ascii=False))
                response = self._client.models.generate_content(
                    model=model_name, contents=json_prompt,
                    config=genai_types.GenerateContentConfig(system_instruction=system, temperature=0.2,
                                                              thinking_config=self._thinking(model_name)),
                )
                return _structured_response(response, schema)
            config = genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                system_instruction=system,
                temperature=0.2,
                thinking_config=self._thinking(model_name),
            )
            response = self._client.models.generate_content(
                model=model_name, contents=prompt, config=config
            )
            return _structured_response(response, schema)

        try:
            return self._call_with_fallback(run, label=label)
        except (LLMError, ValueError):
            if not settings().text_fallback_api_key:
                raise
            return schema.model_validate_json(self._text_fallback(prompt, system, schema))

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

        try:
            resp = self._call_with_fallback(run, label=label)
            text = getattr(resp, "text", None)
            if not text:
                raise LLMError(f"{label}: boş yanıt alındı.")
            return text.strip()
        except LLMError:
            if not settings().text_fallback_api_key:
                raise
            return self._text_fallback(prompt, system)

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
            path_obj = pathlib.Path(p)
            data = path_obj.read_bytes()
            # MIME tipini uzantıdan belirle (JPG/PNG/WEBP desteklenir)
            suffix = path_obj.suffix.lower()
            if suffix in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif suffix == ".webp":
                mime = "image/webp"
            else:
                mime = "image/png"
            parts.append(genai_types.Part.from_bytes(data=data, mime_type=mime))

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
        from urllib.parse import urlsplit

        # Search grounding is not available on the documented Gemini 3 free
        # tier. RSS crosschecks remain enabled without a paid tool call.
        if not settings().gemini_enable_grounding:
            return []

        def run(model_name: str) -> Any:
            config = genai_types.GenerateContentConfig(
                tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                temperature=0.1,
                thinking_config=self._thinking(model_name),
            )
            return self._client.models.generate_content(
                model=model_name, contents=prompt, config=config
            )

        resp = self._call_with_fallback(run, label=label, model_filter=lambda n: not n.startswith("gemma-"))
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for cand in _extract_grounding_chunks(resp):
            url = cand.get("url", "")
            title = cand.get("title", "")
            if not url:
                continue
            if urlsplit(url).hostname == "vertexaisearch.cloud.google.com":
                try:
                    r = requests.head(url, allow_redirects=True, timeout=8)
                    if r.url:
                        url = r.url
                        cand["url"] = url
                except Exception:
                    pass
            if url in seen:
                continue
            host = (urlsplit(url).hostname or "").lower()
            if not any(host == d or host.endswith("." + d) for d in allowed_domains):
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
