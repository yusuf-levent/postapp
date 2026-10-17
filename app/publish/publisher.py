"""Yayınlama orkestrasyonu: Buffer + Threads, durum doğrulama, kurtarma.

Durum makinesi: pending → submitted → published | failed.
Her platform için ayrı durum tutulur. `published` olan platforma asla tekrar
gönderilmez (idempotent). Son 24 saatteki failed/pending platformlar yeniden denenir.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import platforms_config, settings
from app.models import PlatformStatus
from app.publish.buffer_client import BufferClient, client_for_account
from app.publish.retry import PermanentError, TransientError, with_retry
from app.publish.threads_client import ThreadsClient, maybe_refresh_token

log = logging.getLogger("tekno-pusula.publisher")


class PublisherError(RuntimeError):
    pass


def wait_for_public_urls(urls: list[str], *, timeout: int = 120) -> bool:
    """Görsel URL'leri herkese açık olana kadar bekle (exponential backoff).

    Commit + push sonrası raw.githubusercontent.com propagasyonu için.
    200 + image/png dönene kadar bekle.
    """
    import time

    from app.common import http_get

    deadline = time.time() + timeout
    backoff = 3
    while time.time() < deadline:
        all_ok = True
        for url in urls:
            resp = http_get(url, retries=1, timeout=15)
            ctype = resp.headers.get("Content-Type", "") if resp is not None else ""
            if resp is None or resp.status_code != 200 or "image" not in ctype:
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
    channel_id: str = "",
    account: str = "A",
    status: PlatformStatus | None = None,
    thread_replies: list[dict] | None = None,
) -> PlatformStatus:
    """Tek platforma paylaşım yapar (retry + idempotent)."""
    st = status or PlatformStatus(platform=platform)
    if st.state == "published":
        log.info("%s zaten yayınlanmış, atlanıyor (idempotent)", platform)
        return st

    def _do() -> dict:
        if platform == "threads":
            client = ThreadsClient()
            if thread_replies:
                # Threads carousel: tüm görseller tek post'ta
                return client.publish_carousel(image_urls, caption)
            return client.publish_carousel(image_urls[:10], caption)

        client = client_for_account(account)
        # X: 4 görsel üst sınırı; 5-6. görseller yanıt tweetine (thread)
        if platform == "x" and len(image_urls) > 4 and thread_replies:
            return client.create_thread(
                channel_id=channel_id,
                root_text=caption,
                replies=thread_replies,
                root_images=image_urls[:4],
            )
        max_images = platforms_config().platforms[platform].max_images
        return client.create_post(
            channel_id=channel_id,
            text=caption,
            image_urls=image_urls[:max_images],
            share_now=True,
            platform=platform,
        )

    st.attempts += 1
    st.state = "submitted"
    result = with_retry(_do, max_attempts=3, label=f"publish:{platform}")
    if result.ok:
        value = result.value or {}
        st.external_id = str(value.get("id") or "")
        st.permalink = str(value.get("permalink") or value.get("externalLink") or "")
        st.state = "published"
        st.last_error = ""
    else:
        st.state = "failed"
        st.last_error = result.error
        log.error("%s paylaşımı başarısız: %s", platform, result.error)
    return st


def publish_all(
    post_dir: Path,
    *,
    captions: dict[str, str],
    image_urls: list[str],
    image_urls_9x16: list[str] | None = None,
    channel_map: dict[str, tuple[str, str]],  # platform → (account, channel_id)
    thread_replies: list[dict] | None = None,
    dry_run: bool = False,
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

    # Görsellerin herkese açık URL'lerinin yayılmasını bekle
    if image_urls:
        if not wait_for_public_urls(image_urls):
            log.warning("Görsel URL'leri zamanında herkese açılmadı, devam ediliyor")

    for name, rules in platforms.items():
        if name not in captions:
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
            channel_id=channel_id,
            account=account,
            thread_replies=thread_replies,
        )
        statuses[name] = status

    _write_status(post_dir, statuses, dry_run=False)
    return statuses


def recover_failed(
    post_dir: Path,
    *,
    captions: dict[str, str],
    image_urls: list[str],
    image_urls_9x16: list[str] | None = None,
    channel_map: dict[str, tuple[str, str]],
    history_statuses: list[PlatformStatus],
    thread_replies: list[dict] | None = None,
    max_total_attempts: int = 5,
    dry_run: bool = False,
) -> dict[str, PlatformStatus]:
    """Son 24 saatteki failed/pending platformları yeniden dener.

    Idempotent: `published` olan platform ASLA tekrar gönderilmez.
    Toplam deneme sınırı: 5.
    """
    recovered: dict[str, PlatformStatus] = {}
    if dry_run:
        for st in history_statuses:
            recovered[st.platform] = st
        return recovered
    platforms = platforms_config().platforms
    for st in history_statuses:
        if st.state == "published":
            recovered[st.platform] = st
            continue
        if st.attempts >= max_total_attempts:
            log.warning(
                "%s için deneme sınırı doldu (%d), atlanıyor",
                st.platform, st.attempts,
            )
            recovered[st.platform] = st
            continue
        if st.platform not in captions:
            continue
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
            channel_id=channel_id,
            account=account,
            status=st,
            thread_replies=thread_replies,
        )
        recovered[st.platform] = new_status

    _write_status(post_dir, recovered, dry_run=False)
    return recovered


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