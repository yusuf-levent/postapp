"""Retry yardımcıları: exponential backoff + idempotent durum makinesi.

Geçici hatalar (5xx, 429, timeout) tekrar denenir (30s, 2dk, 5dk).
Kalıcı hatalar (401, 400 validation) loglanıp `failed` işaretlenir.
`published` olan platforma ASLA tekrar gönderilmez.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

log = logging.getLogger("tekno-pusula.retry")

T = TypeVar("T")

BACKOFF_SECONDS = [30, 120, 300]
MAX_ATTEMPTS = 3
RECOVERY_MAX_ATTEMPTS = 5  # kurtarma turlarında toplam sınır

# HTTP kodları
TRANSIENT_CODES = {408, 425, 429, 500, 502, 503, 504}
PERMANENT_CODES = {400, 401, 403, 404, 422}


class PermanentError(RuntimeError):
    """Tekrar denenmemesi gereken hata."""


class TransientError(RuntimeError):
    """Tekrar denenebilir hata."""


class AmbiguousError(RuntimeError):
    """İstek GÖNDERİLDİ ama sonuç BELLİ DEĞİL (timeout/connection reset).

    Post sunucuda kaydedilmiş olabilir. Bu hata tekrar DENENMEZ;
    durum "submitted" olarak bırakılır ve manuel kontrol gerekir.
    """


@dataclass
class RetryResult:
    ok: bool
    value: Any = None
    error: str = ""
    attempts: int = 0
    permanent: bool = False
    ambiguous: bool = False  # istek gönderildi, sonuç belli değil (tekrar denenmez)


def classify_status(status: int) -> str:
    """HTTP koduna göre 'transient' | 'permanent' | 'ok'."""
    if status in PERMANENT_CODES:
        return "permanent"
    if status in TRANSIENT_CODES:
        return "transient"
    return "ok"


def with_retry(
    fn: Callable[[], T],
    *,
    max_attempts: int = MAX_ATTEMPTS,
    sleep_fn: Callable[[float], None] = time.sleep,
    label: str = "op",
) -> RetryResult:
    """fn'i exponential backoff ile dener. kalıcı hatada hemen durur."""
    attempt = 0
    last_error = ""
    while attempt < max_attempts:
        attempt += 1
        try:
            value = fn()
            return RetryResult(ok=True, value=value, attempts=attempt)
        except PermanentError as exc:
            log.error("%s kalıcı hata (deneme %d): %s", label, attempt, exc)
            return RetryResult(
                ok=False, error=str(exc), attempts=attempt, permanent=True
            )
        except AmbiguousError as exc:
            # İstek gönderildi ama sonuç belli değil → ASLA tekrar gönderme.
            log.error("%s belirsiz sonuç (deneme %d): %s — tekrar denenmiyor (çift paylaşım engeli)",
                      label, attempt, exc)
            return RetryResult(ok=False, error=str(exc), attempts=attempt, ambiguous=True)
        except (TimeoutError, ConnectionError) as exc:
            # Timeout/connection reset: istek sunucuya GİTMİŞ olabilir.
            # Yeni istek göndermek çift paylaşım yapar → tekrar DENENMEZ.
            log.error("%s ağ hatası (deneme %d): %s — istek gönderilmiş olabilir, tekrar denenmiyor",
                      label, attempt, exc)
            return RetryResult(ok=False, error=str(exc), attempts=attempt, ambiguous=True)
        except TransientError as exc:
            last_error = str(exc)
            if attempt < max_attempts:
                wait = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
                log.warning(
                    "%s geçici hata (deneme %d/%d): %s — %ds bekleniyor",
                    label, attempt, max_attempts, exc, wait,
                )
                sleep_fn(wait)
        except Exception as exc:  # bilinmeyen hata: güvenli taraf ambiguous
            last_error = str(exc)
            log.error("%s bilinmeyen hata (deneme %d): %s — tekrar denenmiyor (çift paylaşım engeli)",
                      label, attempt, exc)
            return RetryResult(ok=False, error=str(exc), attempts=attempt, ambiguous=True)
    return RetryResult(ok=False, error=last_error, attempts=attempt)


def raise_for_status(status: int, body: str = "") -> None:
    """HTTP kodunu kalıcı/geçici hataya çevirir."""
    kind = classify_status(status)
    if kind == "permanent":
        raise PermanentError(f"HTTP {status}: {body[:300]}")
    if kind == "transient":
        raise TransientError(f"HTTP {status}: {body[:300]}")
    if status >= 400:
        raise TransientError(f"HTTP {status}: {body[:300]}")