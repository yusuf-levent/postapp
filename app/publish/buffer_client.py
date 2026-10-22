"""Buffer GraphQL API istemcisi (api.buffer.com).

Kaynak: https://developers.buffer.com/reference.md (2026-10 doğrulandı).
- Auth: `Authorization: Bearer <API_KEY>` her istekte.
- createPost(input: CreatePostInput!): PostActionPayload!
  - channelId, text, assets: [AssetInput!], mode: ShareMode ("shareNow"),
    schedulingType: SchedulingType ("automatic"), metadata: PostInputMetaData
- PostStatus: draft | error | needs_approval | scheduled | sending | sent
- Rate limit: 100/15dk, 250/24sa (free) — RateLimit başlıklarına bakılır.

Eski REST v1 (api.bufferapp.com/1) KULLANILMAZ.
API değişirse yalnızca bu dosya değişir (adapter).
"""
from __future__ import annotations

import logging
from typing import Any

import requests

from app.config import platforms_config, settings
from app.publish.retry import PermanentError, TransientError, raise_for_status

log = logging.getLogger("tekno-pusula.buffer")

API_URL = "https://api.buffer.com"

# Hesap → platform → secret adı eşlemesi (config/platforms.yaml'dan)
ACCOUNT_TOKEN_ENV = {
    "A": "buffer_access_token_a",
    "B": "buffer_access_token_b",
}

PLATFORM_SERVICE_KEY = {
    "instagram": "instagram",
    "tiktok": "tiktok",
    "x": "twitter",       # Buffer şemasında X = twitter
    "facebook": "facebook",
    "linkedin": "linkedin",
    "threads": "threads",
}

MUTATION_CREATE_POST = """
mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess {
      post {
        id
        status
        dueAt
        externalLink
        channelService
      }
    }
    ... on NotFoundError { message }
    ... on UnauthorizedError { message }
    ... on UnexpectedError { message }
    ... on RestProxyError { message }
    ... on LimitReachedError { message }
    ... on InvalidInputError { message }
  }
}
"""

QUERY_ACCOUNT = """
query Account {
  account {
    id
    organizations {
      id
      name
    }
  }
}
"""

QUERY_CHANNELS = """
query Channels($input: ChannelsInput!) {
  channels(input: $input) {
    id
    name
    service
    displayName
    externalLink
    isDisconnected
    isLocked
  }
}
"""

QUERY_POST = """
query Post($input: PostInput!) {
  post(input: $input) {
    id
    status
    externalLink
    dueAt
    error { message }
  }
}
"""


class BufferClient:
    """Buffer GraphQL API adapter'ı. Tüm çağrılar bu sınıftan geçer."""

    def __init__(self, access_token: str | None = None):
        token = access_token or settings().buffer_access_token_a
        if not token:
            raise PermanentError("Buffer API anahtarı tanımlı değil.")
        self._token = token
        self._session = requests.Session()
        self._last_rate_remaining: int | None = None

    # ------------------------------------------------------------------ core
    def _post(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self._session.post(
            API_URL,
            json={"query": query, "variables": variables or {}},
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        self._read_rate_limit(resp)

        if resp.status_code == 401:
            raise PermanentError("Buffer API anahtarı geçersiz (401).")
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "60")
            raise TransientError(f"Buffer rate limit (429), bekleme: {retry_after}s")
        raise_for_status(resp.status_code, resp.text)

        data = resp.json()
        if "errors" in data:
            msg = "; ".join(e.get("message", "") for e in data["errors"])
            code = data["errors"][0].get("extensions", {}).get("code", "")
            if code == "RATE_LIMIT_EXCEEDED":
                raise TransientError(f"Buffer rate limit: {msg}")
            if "unauthorized" in msg.lower() or code == "UNAUTHORIZED":
                raise PermanentError(f"Buffer yetkilendirme hatası: {msg}")
            raise PermanentError(f"Buffer GraphQL hatası: {msg}")
        return data.get("data", {})

    def _read_rate_limit(self, resp: requests.Response) -> None:
        """RateLimit başlıklarını okur; kalan istek azsa uyarır."""
        raw = resp.headers.get("RateLimit") or resp.headers.get("ratelimit")
        if not raw:
            return
        import re

        for policy in re.split(r",\s*(?=\")", raw):
            m = re.search(r"r=(\d+)", policy)
            w = re.search(r"w=(\d+)", policy)
            if m and w and w.group(1) == "900":  # 15 dk penceresi
                self._last_rate_remaining = int(m.group(1))
                if self._last_rate_remaining < 10:
                    log.warning(
                        "Buffer rate limit yaklaşıyor: %s istek kaldı (15dk)",
                        self._last_rate_remaining,
                    )

    # ------------------------------------------------------------ operations
    def account_info(self) -> dict[str, Any]:
        """Hesap + organizasyon + kanal listesi (tools workflow'u için)."""
        data = self._post(QUERY_ACCOUNT)
        acc = dict(data.get("account") or {})
        orgs: list[dict[str, Any]] = []
        for org in acc.get("organizations") or []:
            org_copy = dict(org)
            org_id = org_copy.get("id", "")
            if org_id and "channels" not in org_copy:
                ch_data = self._post(QUERY_CHANNELS, {"input": {"organizationId": org_id}})
                org_copy["channels"] = ch_data.get("channels") or []
            orgs.append(org_copy)
        acc["organizations"] = orgs
        return acc

    def create_post(
        self,
        *,
        channel_id: str,
        text: str,
        image_urls: list[str],
        share_now: bool = True,
        platform: str = "",
        alt_texts: list[str] | None = None,
    ) -> dict[str, Any]:
        """Gönderiyi oluşturur ve anında paylaşır (mode=shareNow).

        Dönüş: {"id": ..., "status": ..., "externalLink": ...}
        """
        assets: list[dict[str, Any]] = []
        for i, url in enumerate(image_urls):
            asset: dict[str, Any] = {"image": {"url": url}}
            alt = (alt_texts or [])[i] if i < len(alt_texts or []) else ""
            if alt:
                asset["image"]["metadata"] = {"altText": alt}
            assets.append({"image": asset["image"]})

        service = PLATFORM_SERVICE_KEY.get(platform, "")
        meta_candidates: list[dict[str, Any]] = [{}]
        if service == "instagram":
            meta_candidates = [
                {"instagram": {"shouldShareToFeed": True, "type": "post"}},
                {},
            ]
        elif service == "facebook":
            meta_candidates = [
                {"facebook": {"type": "post"}},
                {},
            ]
        elif service == "tiktok":
            first_line = (text.split("\n")[0] if text else "").strip()[:80]
            meta_candidates = [
                {"tiktok": {"title": first_line}} if first_line else {"tiktok": {}},
                {},
            ]

        payload: dict[str, Any] = {}
        typename = ""
        last_err: Exception | None = None
        for meta in meta_candidates:
            input_obj: dict[str, Any] = {
                "channelId": channel_id,
                "text": text,
                "assets": assets,
                "mode": "shareNow" if share_now else "addToQueue",
                "schedulingType": "automatic",
                "source": "tekno-pusula",
            }
            if meta:
                input_obj["metadata"] = meta
            try:
                data = self._post(MUTATION_CREATE_POST, {"input": input_obj})
                payload = data.get("createPost") or {}
                typename = payload.get("__typename", "")
                if typename == "InvalidInputError" and len(meta_candidates) > 1:
                    log.warning("Buffer metadata denemesi (%s) InvalidInputError döndü: %s", meta, payload.get("message"))
                    continue
                last_err = None
                break
            except PermanentError as exc:
                last_err = exc
                if "GraphQL hatası" in str(exc) and len(meta_candidates) > 1:
                    log.warning("Buffer metadata denemesi (%s) şema hatası döndü: %s", meta, exc)
                    continue
                raise
        if last_err is not None:
            raise last_err

        if typename == "PostActionSuccess":
            post = payload.get("post", {})
            post_id = post.get("id", "")
            status = post.get("status", "")
            ext_link = post.get("externalLink", "")
            log.info("Buffer post oluşturuldu: %s (%s)", post_id, status)
            # ÖNEMLİ: PostActionSuccess = post Buffer'a KAYDEDİLDİ.
            # Buradan sonra exception fırlatmak, retry mekanizmasının AYNI postu
            # tekrar göndermesine neden olur (çift paylaşım). Bu yüzden status
            # "error" olsa bile exception YOK — durum kaydedilir ve dönülür.
            if status == "error":
                log.error(
                    "Buffer post kaydedildi ama gönderim hatası (%s). "
                    "Tekrar GÖNDERİLMEZ (çift paylaşım engeli).", post_id,
                )
            if post_id and share_now and status not in ("sent", "error"):
                polled = self._poll_post_status(post_id)
                if polled:
                    status = polled.get("status") or status
                    ext_link = polled.get("externalLink") or ext_link
                    err = (polled.get("error") or {}).get("message")
                    if err:
                        log.error("Buffer gönderim hatası (%s): %s", post_id, err)
            return {
                "id": post_id,
                "status": status,
                "externalLink": ext_link,
            }

        message = payload.get("message", f"bilinmeyen Buffer hatası: {typename}")
        if typename in ("UnauthorizedError", "LimitReachedError"):
            raise PermanentError(f"Buffer {typename}: {message}")
        raise TransientError(f"Buffer {typename}: {message}")

    def create_video_post(
        self,
        *,
        channel_id: str,
        text: str,
        video_url: str,
        share_now: bool = True,
        platform: str = "",
        fallback_image_urls: list[str] | None = None,
        fallback_images: list[str] | None = None,
    ) -> dict[str, Any]:
        """Instagram Reels veya TikTok için 9:16 video gönderisi oluşturur ve paylaşır."""
        fallback_list = fallback_image_urls or fallback_images or []
        service = PLATFORM_SERVICE_KEY.get(platform, "")
        meta_candidates: list[dict[str, Any]] = [{}]
        if service == "instagram":
            meta_candidates = [
                {"instagram": {"shouldShareToFeed": True, "type": "reel"}},
                {"instagram": {"shouldShareToFeed": True, "type": "post"}},
                {},
            ]
        elif service == "tiktok":
            meta_candidates = [
                {"tiktok": {"isAiGenerated": False}},
                {},
            ]

        assets = [{"video": {"url": video_url}}]
        for meta in meta_candidates:
            input_obj: dict[str, Any] = {
                "channelId": channel_id,
                "text": text,
                "assets": assets,
                "mode": "shareNow" if share_now else "addToQueue",
                "schedulingType": "automatic",
                "source": "tekno-pusula",
            }
            if meta:
                input_obj["metadata"] = meta
            try:
                data = self._post(MUTATION_CREATE_POST, {"input": input_obj})
                payload = data.get("createPost") or {}
                typename = payload.get("__typename", "")
                if typename == "PostActionSuccess":
                    # PostActionSuccess = video post Buffer'a KAYDEDİLDİ.
                    # Buradan sonra BAŞKA meta denemesi veya fallback YAPILMAZ.
                    post = payload.get("post", {})
                    post_id = post.get("id", "")
                    status = post.get("status", "")
                    ext_link = post.get("externalLink", "")
                    log.info("Buffer video post oluşturuldu (%s): %s (%s)", platform, post_id, status)
                    if post_id and share_now and status not in ("sent", "error"):
                        polled = self._poll_post_status(post_id)
                        if polled:
                            status = polled.get("status") or status
                            ext_link = polled.get("externalLink") or ext_link
                            err = (polled.get("error") or {}).get("message")
                            if err:
                                log.error("Buffer video gönderim hatası (%s): %s", post_id, err)
                    return {
                        "id": post_id,
                        "status": status,
                        "externalLink": ext_link,
                    }
                # Yalnızca post HİÇ kaydedilmediyse sonraki meta denenir.
                if typename == "InvalidInputError":
                    log.warning("Buffer video metadata denemesi (%s) InvalidInputError: %s", meta, payload.get("message"))
                    continue
                # Diğer hatalarda post kaydedilmiş olabilir → tekrar deneme YOK.
                log.error("Buffer video denemesi (%s, %s) sonuç: %s — tekrar denenmiyor.", platform, meta, typename or payload.get("message"))
                break
            except Exception as exc:
                log.warning("Buffer video denemesi (%s, %s) hata verdi: %s", platform, meta, exc)
                # Ağ hatası vb.: post kaydedilmiş olabilir → fallback'e GEÇME,
                # tekrar deneme YOK (çift paylaşım engeli).
                return {
                    "id": "",
                    "status": "unknown",
                    "externalLink": "",
                }

        # Yalnızca hiçbir deneme post kaydetmediyse fallback'e geç.
        # (PostActionSuccess alan herhangi bir deneme yukarıda döndü.)
        if fallback_list:
            log.info("%s için video paylaşımı yerine 6'lı slayt yedek paylaşımına geçiliyor (video hiç kaydedilmedi).", platform)
            return self.create_post(
                channel_id=channel_id,
                text=text,
                image_urls=fallback_list,
                share_now=share_now,
                platform=platform,
            )
        raise TransientError(f"Buffer video post oluşturulamadı ({platform})")

    def _poll_post_status(self, post_id: str, *, max_polls: int = 4, delay: float = 3.0) -> dict[str, Any]:
        """Gönderim sonrası post durumunu poll eder (sent/error kontrolü)."""
        import time

        last: dict[str, Any] = {}
        for _ in range(max_polls):
            try:
                last = self.get_post_status(post_id)
            except Exception as exc:
                log.debug("Buffer status poll uyarısı (%s): %s", post_id, exc)
                return last
            st = (last or {}).get("status", "")
            if st in ("sent", "error", "scheduled", "needs_approval"):
                return last
            time.sleep(delay)
        return last

    def get_post_status(self, post_id: str) -> dict[str, Any]:
        """Gönderi durumunu sorgular (sent/error doğrulaması için)."""
        data = self._post(QUERY_POST, {"input": {"id": post_id}})
        return data.get("post", {})

    def create_thread(
        self,
        *,
        channel_id: str,
        root_text: str,
        replies: list[dict[str, Any]],
        root_images: list[str] | None = None,
    ) -> dict[str, Any]:
        """X thread: kök tweet (ilk 4 görsel) + yanıt tweetleri (5-6. görseller)."""
        root_assets = [
            {"image": {"url": u}}
            for u in (root_images or [])[:4]
        ]
        thread_items: list[dict[str, Any]] = [
            {"text": root_text, "assets": root_assets}
        ]
        for reply in replies:
            assets = [
                {"image": {"url": u}}
                for u in reply.get("images", [])
            ]
            thread_items.append({"text": reply["text"], "assets": assets})

        input_obj = {
            "channelId": channel_id,
            "text": root_text,
            "assets": root_assets,
            "mode": "shareNow",
            "schedulingType": "automatic",
            "source": "tekno-pusula",
            "metadata": {"twitter": {"thread": thread_items}},
        }
        try:
            data = self._post(MUTATION_CREATE_POST, {"input": input_obj})
            payload = data.get("createPost") or {}
            if payload.get("__typename") == "PostActionSuccess":
                # Thread KAYDEDİLDİ → fallback YAPMA (çift paylaşım engeli).
                post = payload.get("post", {})
                return {
                    "id": post.get("id", ""),
                    "status": post.get("status", ""),
                    "externalLink": post.get("externalLink", ""),
                }
            message = payload.get("message", "")
            # Thread HİÇ kaydedilmedi (InvalidInputError vb.) → fallback güvenli.
            if payload.get("__typename") == "InvalidInputError":
                log.warning("Buffer X thread reddedildi (%s), 4 görselli tek post olarak paylaşılıyor.", message)
                return self.create_post(
                    channel_id=channel_id,
                    text=root_text,
                    image_urls=(root_images or [])[:4],
                    share_now=True,
                    platform="x",
                )
            log.error("Buffer X thread sonucu belirsiz (%s) — fallback yapılmıyor, tekrar denenmiyor.", payload.get("__typename") or message)
            return {"id": "", "status": "unknown", "externalLink": ""}
        except PermanentError as exc:
            # Kalıcı hata: thread kesin kaydedilmedi → fallback güvenli.
            log.warning("Buffer X thread kalıcı hata (%s), 4 görselli tek post olarak paylaşılıyor.", exc)
            return self.create_post(
                channel_id=channel_id,
                text=root_text,
                image_urls=(root_images or [])[:4],
                share_now=True,
                platform="x",
            )
        except Exception as exc:
            # Ağ timeout / geçici hata: thread KAYDEDİLMİŞ OLABİLİR.
            # Fallback YAPMA, tekrar deneme YOK (çift paylaşım engeli).
            log.error("Buffer X thread hatası (%s) — thread kaydedilmiş olabilir, fallback yapılmıyor.", exc)
            return {"id": "", "status": "unknown", "externalLink": ""}


def client_for_account(account: str) -> BufferClient:
    """config/platforms.yaml'daki hesap haritasına göre token seçer."""
    cfg = settings()
    if account == "A":
        return BufferClient(cfg.buffer_access_token_a)
    return BufferClient(cfg.buffer_access_token_b)


def list_profiles() -> list[dict[str, str]]:
    """Yardımcı araç: tüm kanalları listeler (token loglanmaz)."""
    cfg = settings()
    out: list[dict[str, str]] = []
    for account in ("A", "B"):
        token = cfg.buffer_access_token_a if account == "A" else cfg.buffer_access_token_b
        if not token:
            continue
        try:
            client = BufferClient(token)
            info = client.account_info()
        except Exception as exc:
            log.warning("Buffer hesap %s sorgulanamadı: %s", account, exc)
            continue
        for org in info.get("organizations", []):
            for ch in org.get("channels", []):
                out.append(
                    {
                        "account": account,
                        "organization": org.get("name", ""),
                        "organization_id": org.get("id", ""),
                        "channel_id": ch.get("id", ""),
                        "service": ch.get("service", ""),
                        "name": ch.get("displayName") or ch.get("name", ""),
                        "url": ch.get("externalLink", ""),
                        "disconnected": str(ch.get("isDisconnected", False)),
                    }
                )
    return out