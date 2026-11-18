"""Yayınlama orkestrasyonu: Buffer + Threads, durum doğrulama, kurtarma.

Durum makinesi: pending → submitted → published | failed.
Her platform için ayrı durum tutulur. Buffer istek limiti sonraki çalışma için
yeniden deneme zamanı kaydeder. Buffer kimliği bulunan gönderi yalnızca sorgulanır.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.config import platforms_config
from app.models import PlatformStatus
from app.publish.buffer_client import client_for_account
from app.publish.retry import (
    RECOVERY_MAX_ATTEMPTS, PermanentError, RateLimitError, TransientError, with_retry,
)
from app.publish.threads_client import ThreadsClient, maybe_refresh_token
from app.scheduling import platform_recovery_due

log = logging.getLogger("tekno-pusula.publisher")


class PublisherError(RuntimeError):
    pass


def wait_for_public_urls(urls: list[str], *, timeout: int = 120) -> bool:
    """Görsel/video URL'leri herkese açık olana kadar bekle (exponential backoff).

    Commit + push sonrası raw.githubusercontent.com propagasyonu için.
    200 + image/png veya video/mp4 dönene kadar bekle.
    """
    from app.common import http_get

    deadline = time.time() + timeout
    backoff = 3
    while time.time() < deadline:
        all_ok = True
        for url in urls:
            if not url:
                continue
            resp = http_get(url, retries=1, timeout=15)
            ctype = (resp.headers.get("Content-Type", "") if resp is not None else "").lower()
            valid_type = (
                "image" in ctype
                or "video" in ctype
                or "octet-stream" in ctype
                or url.lower().endswith(".mp4")
            )
            if resp is None or resp.status_code != 200 or not valid_type:
                all_ok = False
                break
        if all_ok:
            return True
        time.sleep(min(backoff, 30))
        backoff *= 2
    return False


def publish_platform(
    platform: str,
    *,
    caption: str,
    image_urls: list[str],
    video_url: str = "",
    channel_id: str = "",
    account: str = "A",
    status: PlatformStatus | None = None,
    thread_replies: list[dict] | None = None,
    before_submit: Callable[[], None] | None = None,
) -> PlatformStatus:
    """Tek platforma paylaşım yapar (retry + idempotent)."""
    st = status or PlatformStatus(platform=platform)
    if st.state == "published":
        log.info("%s zaten yayınlanmış, atlanıyor (idempotent)", platform)
        return st
    if st.retry_at > time.time():
        return st

    # An accepted Buffer ID must only be queried, never submitted a second time.
    if st.external_id and platform != "threads":
        try:
            value = client_for_account(account).get_post_status(st.external_id)
            _apply_result(st, value)
        except RateLimitError as exc:
            _defer_buffer_retry(st, exc.retry_at, str(exc))
        except Exception as exc:
            log.warning("%s durum sorgusu başarısız: %s", platform, type(exc).__name__)
        return st
    if st.state == "submitted":
        return st  # unknown result without an ID needs manual reconciliation
    if platform != "threads" and not channel_id:
        st.state, st.last_error = "failed", "Buffer kanal kimliği tanımlı değil."
        return st

    def _do() -> dict:
        if platform == "threads":
            client = ThreadsClient()
            if thread_replies:
                # Threads carousel: tüm görseller tek post'ta
                return client.publish_carousel(image_urls, caption)
            return client.publish_carousel(image_urls[:10], caption)

        client = client_for_account(account)
        max_images = platforms_config().platforms[platform].max_images

        # Instagram Reels & TikTok: gerçek video (reel.mp4) varsa videolu paylaş
        if platform in ("instagram", "tiktok") and video_url:
            return client.create_video_post(
                channel_id=channel_id,
                text=caption,
                video_url=video_url,
                share_now=True,
                platform=platform,
                fallback_image_urls=image_urls[:max_images],
            )

        # X: 4 görsel üst sınırı; 5-6. görseller yanıt tweetine (thread)
        if platform == "x" and len(image_urls) > 4 and thread_replies:
            return client.create_thread(
                channel_id=channel_id,
                root_text=caption,
                replies=thread_replies,
                root_images=image_urls[:4],
            )
        return client.create_post(
            channel_id=channel_id,
            text=caption,
            image_urls=image_urls[:max_images],
            share_now=True,
            platform=platform,
        )

    st.attempts += 1
    st.state = "submitted"
    if before_submit:
        before_submit()  # durable journal BEFORE the external side effect
    result = with_retry(_do, max_attempts=3, label=f"publish:{platform}")
    if result.ok:
        value = result.value or {}
        _apply_result(st, value)
    elif result.retry_at:
        st.attempts -= 1
        st.state = "pending"
        _defer_buffer_retry(st, result.retry_at, result.error)
    elif result.ambiguous:
        # İstek gönderildi ama sonuç doğrulanamadı (timeout vb.).
        # Post PAYLAŞILMIŞ OLABİLİR → `submitted` olarak bırakılır.
        # Kurtarma turu bu durumu TEKRAR DENEMEZ (çift paylaşım engeli).
        st.state = "submitted"
        st.last_error = f"belirsiz sonuç (post gönderilmiş olabilir): {result.error}"
        log.error(
            "%s paylaşımının sonucu doğrulanamadı: %s — TEKRAR GÖNDERİLMEDİ (çift paylaşım engeli). "
            "Manuel kontrol gerekli.", platform, result.error,
        )
    else:
        st.state = "failed"
        st.last_error = result.error
        log.error("%s paylaşımı başarısız: %s", platform, result.error)
    return st


def _defer_buffer_retry(st: PlatformStatus, retry_at: int, error: str) -> None:
    st.retry_at, st.last_error = retry_at, error
    log.warning("%s Buffer yeniden deneme zamanı: %s", st.platform,
                datetime.fromtimestamp(retry_at, timezone.utc).isoformat())


def _apply_result(st: PlatformStatus, value: dict) -> None:
    st.external_id = str(value.get("id") or st.external_id or "")
    st.permalink = str(value.get("permalink") or value.get("externalLink") or st.permalink or "")
    remote = str(value.get("status") or "").lower()
    st.remote_status = remote
    error = value.get("error") or {}
    message = error.get("message", "") if isinstance(error, dict) else str(error)
    if st.external_id and (remote == "sent" or st.platform == "threads"):
        st.state, st.last_error = "published", ""
        st.retry_at = 0
    elif remote == "error":
        st.state, st.last_error = "failed", message or "Buffer gönderimi hata ile tamamlandı."
        st.retry_at = 0
    else:
        st.state = "submitted"
        st.last_error = message or f"Buffer yayını henüz doğrulanmadı ({remote or 'bilinmiyor'})."
        # Keep an existing retry timestamp until we have a terminal result.
        if retry_at := value.get("retry_at"):
            _defer_buffer_retry(st, retry_at, value.get("retry_error") or st.last_error)


def publish_all(
    post_dir: Path,
    *,
    captions: dict[str, str],
    image_urls: list[str],
    image_urls_9x16: list[str] | None = None,
    video_url: str = "",
    channel_map: dict[str, tuple[str, str]],  # platform → (account, channel_id)
    thread_replies: list[dict] | None = None,
    dry_run: bool = False,
    checkpoint: Callable[[], None] | None = None,
) -> dict[str, PlatformStatus]:
    """Tüm platformlara paylaşım yapar. status.json + history.json güncellenir.

    channel_map: {"instagram": ("A", "channel_id"), ...}
    """
    platforms = platforms_config().platforms
    statuses: dict[str, PlatformStatus] = {}

    if dry_run:
        for name in platforms:
            statuses[name] = PlatformStatus(platform=name, state="pending")
        _write_status(post_dir, statuses, dry_run=True)
        return statuses

    # Threads token durumu kontrolü (40 günü geçtiyse yenile)
    try:
        refresh_info = maybe_refresh_token()
        log.info("Threads token kontrolü: %s", refresh_info)
    except (PermanentError, TransientError) as exc:
        log.warning("Threads token yenileme atlandı: %s", exc)

    # Görsellerin ve videonun herkese açık URL'lerinin yayılmasını bekle
    check_urls = list(dict.fromkeys([*(image_urls or []), *(image_urls_9x16 or [])]))
    if video_url:
        check_urls.append(video_url)
    if check_urls:
        if not wait_for_public_urls(check_urls):
            raise PublisherError("Medya URL'leri erişilebilir değil; paylaşım başlatılmadı.")

    existing_map: dict[str, PlatformStatus] = {}
    status_file = post_dir / "status.json"
    if status_file.exists():
        try:
            raw_st = json.loads(status_file.read_text(encoding="utf-8")).get("platforms", {})
            for k, v in raw_st.items():
                if isinstance(v, dict):
                    existing_map[k] = PlatformStatus.model_validate(v)
        except Exception:
            pass

    statuses = {name: existing_map.get(name) or PlatformStatus(platform=name)
                for name in platforms if name in captions}

    def save_status() -> None:
        _write_status(post_dir, statuses, dry_run=False)
        if checkpoint:
            checkpoint()

    for name, rules in platforms.items():
        if name not in captions:
            continue
        # Idempotent: daha önce published ise tekrar gönderme (çift paylaşım engeli)
        prev = statuses.get(name)
        if prev and prev.state == "published":
            log.info("%s zaten yayınlanmış (idempotent), atlanıyor", name)
            statuses[name] = prev
            continue
        account, channel_id = channel_map.get(name, ("A", ""))
        plat_urls = (
            image_urls_9x16
            if (rules.use_9x16 and image_urls_9x16)
            else image_urls
        )
        status = publish_platform(
            name,
            caption=captions[name],
            image_urls=plat_urls,
            video_url=video_url if name in ("instagram", "tiktok") else "",
            channel_id=channel_id,
            account=account,
            status=prev,
            thread_replies=thread_replies,
            before_submit=save_status,
        )
        statuses[name] = status
        save_status()

    _write_status(post_dir, statuses, dry_run=False)
    return statuses


def recover_failed(
    post_dir: Path,
    *,
    captions: dict[str, str],
    image_urls: list[str],
    image_urls_9x16: list[str] | None = None,
    video_url: str = "",
    channel_map: dict[str, tuple[str, str]],
    history_statuses: list[PlatformStatus],
    thread_replies: list[dict] | None = None,
    max_total_attempts: int = RECOVERY_MAX_ATTEMPTS,
    recent: bool = True,
    dry_run: bool = False,
    checkpoint: Callable[[], None] | None = None,
) -> dict[str, PlatformStatus]:
    """Zamanı gelen gönderimleri yeniden dener, kabul edilenleri sorgular."""
    if dry_run:
        return {st.platform: st for st in history_statuses}
    platforms = platforms_config().platforms
    latest = {s.platform: s for s in history_statuses}
    status_file = post_dir / "status.json"
    if status_file.exists():
        saved = json.loads(status_file.read_text(encoding="utf-8")).get("platforms", {})
        latest.update({k: PlatformStatus.model_validate(v) for k, v in saved.items()})
    now = datetime.now(timezone.utc)
    due = [
        st for st in latest.values()
        if st.platform in captions and platform_recovery_due(
            st.model_dump(), now, recent=recent, max_attempts=max_total_attempts,
        )
    ]
    if any(not st.external_id for st in due):
        urls = list(dict.fromkeys([*image_urls, *(image_urls_9x16 or []), *([video_url] if video_url else [])]))
        if urls and not wait_for_public_urls(urls):
            raise PublisherError("Kurtarma için medya URL'leri erişilebilir değil; yeni gönderim başlatılmadı.")

    def save_status() -> None:
        _write_status(post_dir, latest, dry_run=False)
        if checkpoint:
            checkpoint()

    for st in due:
        account, channel_id = channel_map.get(st.platform, ("A", ""))
        rules = platforms.get(st.platform)
        plat_urls = (
            image_urls_9x16
            if (rules and rules.use_9x16 and image_urls_9x16)
            else image_urls
        )
        new_status = publish_platform(
            st.platform,
            caption=captions[st.platform],
            image_urls=plat_urls,
            video_url=video_url if st.platform in ("instagram", "tiktok") else "",
            channel_id=channel_id,
            account=account,
            status=st,
            thread_replies=thread_replies,
            before_submit=save_status,
        )
        latest[st.platform] = new_status
        save_status()

    return latest


def _write_status(
    post_dir: Path, statuses: dict[str, PlatformStatus], *, dry_run: bool
) -> None:
    """status.json: platform paylaşım durumları + linkler."""
    data = {
        "dry_run": dry_run,
        "platforms": {
            name: st.model_dump() for name, st in statuses.items()
        },
    }
    (post_dir / "status.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
