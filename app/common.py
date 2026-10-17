"""Ortak yardımcılar: HTTP istemcisi, tarih/saat, loglama."""
from __future__ import annotations

import logging
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

import requests

ISTANBUL = ZoneInfo("Europe/Istanbul")

USER_AGENT = (
    "TeknoPusula/1.0 (+https://github.com/; automated news verification bot; "
    "contact: github-actions)"
)

_TRANS_TABLE = str.maketrans("çÇğĞıIİöÖşŞüÜ", "cCgGiIioOsSuU")


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    return logging.getLogger("tekno-pusula")


def now_istanbul() -> datetime:
    return datetime.now(ISTANBUL)


def istanbul_day(offset_days: int = 0) -> datetime:
    """Europe/Istanbul'a göre bugün (offset ile geriye/ileriye)."""
    base = now_istanbul().replace(hour=0, minute=0, second=0, microsecond=0)
    return base + timedelta(days=offset_days)


def to_istanbul(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ISTANBUL)


def normalize_text(text: str) -> str:
    """Küçük harfe çevir + Türkçe harfleri ASCII'ye indirge + noktalama temizle."""
    text = text.translate(_TRANS_TABLE).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def turkish_upper(text: str) -> str:
    """Türkçe kurallarına göre büyük harf: i → İ, ı → I (markalar korunur)."""
    from app.render.turkish import tr_upper

    return tr_upper(text)


def turkish_lower(text: str) -> str:
    """Türkçe kurallarına göre küçük harf: İ → i, I → ı."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def slugify(text: str, max_len: int = 48) -> str:
    norm = normalize_text(text)
    slug = re.sub(r"\s+", "-", norm).strip("-")
    return slug[:max_len].strip("-") or "post"


def http_get(
    url: str,
    *,
    timeout: int = 20,
    retries: int = 3,
    headers: dict[str, str] | None = None,
    session: requests.Session | None = None,
) -> requests.Response | None:
    """Retry'lı GET. Geçici hatalarda (5xx/429/timeout) exponential backoff."""
    sess = session or requests.Session()
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    backoff = 5
    for attempt in range(1, retries + 1):
        try:
            resp = sess.get(url, headers=hdrs, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                retry_after = resp.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else backoff
                time.sleep(wait)
                backoff *= 2
                continue
            return resp
        except requests.RequestException:
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
    return None


def http_post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
    retries: int = 3,
    session: requests.Session | None = None,
) -> requests.Response | None:
    sess = session or requests.Session()
    hdrs = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        **(headers or {}),
    }
    backoff = 5
    for attempt in range(1, retries + 1):
        try:
            resp = sess.post(url, json=payload, headers=hdrs, timeout=timeout)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                retry_after = resp.headers.get("Retry-After")
                wait = int(retry_after) if retry_after and retry_after.isdigit() else backoff
                time.sleep(wait)
                backoff *= 2
                continue
            return resp
        except requests.RequestException:
            if attempt < retries:
                time.sleep(backoff)
                backoff *= 2
    return None


def rate_limited(interval_seconds: float) -> Callable[..., Any]:
    """Basit istekler arası rate limiter decorator'ı (ücretsiz katman limitleri)."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        last: list[float] = [0.0]

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            elapsed = time.monotonic() - last[0]
            if elapsed < interval_seconds:
                time.sleep(interval_seconds - elapsed)
            last[0] = time.monotonic()
            return fn(*args, **kwargs)

        return wrapper

    return decorator