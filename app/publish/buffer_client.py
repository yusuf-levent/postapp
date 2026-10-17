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
    email
    organizations {
      id
      name
      channels {
        id
        service
        displayName
        externalLink
        isDisconnected
        isLocked
      }
    }
  }
}
"""

QUERY_POST = """
query Post($id: PostId!) {
  post(id: $id) {
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
        return data.get("account", {})

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

        meta: dict[str, Any] = {}
        service = PLATFORM_SERVICE_KEY.get(platform, "")
        if service == "instagram":
            meta["instagram"] = {"shouldShareToFeed": True, "type": "post"}
        elif service == "tiktok":
            meta["tiktok"] = {}

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

        data = self._post(MUTATION_CREATE_POST, {"input": input_obj})
        payload = data.get("createPost") or {}
        typename = payload.get("__typename", "")

        if typename == "PostActionSuccess":
            post = payload.get("post", {})
            post_id = post.get("id", "")
            status = post.get("status", "")
            ext_link = post.get("externalLink", "")
            log.info("Buffer post oluşturuldu: %s (%s)", post_id, status)
            if status == "error":
                raise TransientError(f"Buffer gönderim hatası ({post_id}): {status}")
            if post_id and share_now and status != "sent":
                polled = self._poll_post_status(post_id)
                if polled:
                    status = polled.get("status") or status
                    ext_link = polled.get("externalLink") or ext_link
                    err = (polled.get("error") or {}).get("message")
                    if status == "error" or err:
                        raise TransientError(f"Buffer gönderim hatası ({post_id}): {err or status}")
            return {
                "id": post_id,
                "status": status,
                "externalLink": ext_link,
            }

        message = payload.get("message", f"bilinmeyen Buffer hatası: {typename}")
        if typename in ("UnauthorizedError", "LimitReachedError"):
            raise PermanentError(f"Buffer {typename}: {message}")
        raise TransientError(f"Buffer {typename}: {message}")

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
        data = self._post(QUERY_POST, {"id": post_id})
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
            {"image": {"url": u, "metadata": {"altText": ""}}}
            for u in (root_images or [])[:4]
        ]
        thread_items: list[dict[str, Any]] = [
            {"text": root_text, "assets": root_assets}
        ]
        for reply in replies:
            assets = [
                {"image": {"url": u, "metadata": {"altText": ""}}}
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
        data = self._post(MUTATION_CREATE_POST, {"input": input_obj})
        payload = data.get("createPost") or {}
        if payload.get("__typename") == "PostActionSuccess":
            post = payload.get("post", {})
            return {
                "id": post.get("id", ""),
                "status": post.get("status", ""),
                "externalLink": post.get("externalLink", ""),
            }
        message = payload.get("message", "")
        raise TransientError(f"Buffer thread hatası: {message}")


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
        client = BufferClient(token)
        info = client.account_info()
        for org in info.get("organizations", []):
            for ch in org.get("channels", []):
                out.append(
                    {
                        "account": account,
                        "organization": org.get("name", ""),
                        "organization_id": org.get("id", ""),
                        "channel_id": ch.get("id", ""),
                        "service": ch.get("service", ""),
                        "name": ch.get("displayName", ""),
                        "url": ch.get("externalLink", ""),
                        "disconnected": str(ch.get("isDisconnected", False)),
                    }
                )
    return out