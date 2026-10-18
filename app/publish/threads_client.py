"""Threads Graph API istemcisi (graph.threads.net).

Kaynak: https://developers.facebook.com/documentation/threads/posts (doğrulandı)
- Görsel post: 2 adım (container → publish).
- Carousel: çocuk containerlar → carousel container → publish (en fazla 20, min 2).
- Metin limiti 500 karakter (emoji = UTF-8 byte).
- Publish öncesi container durumu FINISHED olana kadar poll edilir.
- Long-lived token 60 gün geçerlidir; yenileme refresh_access_token ile yapılır.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

from app.config import settings
from app.publish.retry import PermanentError, TransientError, raise_for_status

log = logging.getLogger("tekno-pusula.threads")

GRAPH_BASE = "https://graph.threads.net/v1.0"
REFRESH_URL = "https://graph.threads.net/refresh_access_token"

MAX_CAROUSEL = 20
MIN_CAROUSEL = 2
CHAR_LIMIT = 500  # emojiler UTF-8 byte sayılır

CONTAINER_POLL_INTERVAL = 5
CONTAINER_POLL_MAX = 24  # toplam ~2 dakika

TOKEN_STATE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "token_state.json"


def threads_char_length(text: str) -> int:
    """Threads karakter sayımı: emoji UTF-8 byte olarak sayılır."""
    return len(text.encode("utf-8"))


class ThreadsClient:
    """Threads Graph API adapter'ı."""

    def __init__(
        self,
        access_token: str | None = None,
        user_id: str | None = None,
    ):
        cfg = settings()
        # Açık parametre ("" dahil) verilmişse onu kullan; yoksa env'den oku
        self._token = access_token if access_token is not None else cfg.threads_access_token
        self._user_id = user_id if user_id is not None else cfg.threads_user_id
        if not self._token or not self._user_id:
            raise PermanentError("THREADS_ACCESS_TOKEN / THREADS_USER_ID tanımlı değil.")
        self._session = requests.Session()

    # ------------------------------------------------------------------ core
    def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
    ) -> dict:
        params = dict(params or {})
        params["access_token"] = self._token
        resp = self._session.request(
            method,
            url,
            params=params,
            data=data,
            timeout=30,
            headers={"User-Agent": "TeknoPusula/1.0"},
        )
        if resp.status_code == 401:
            raise PermanentError("Threads token geçersiz/süresi dolmuş (401).")
        if resp.status_code == 429:
            raise TransientError("Threads rate limit (429).")
        if resp.status_code == 400 and (
            "4279004" in resp.text or "Invalid Carousel Children" in resp.text
        ):
            raise TransientError(f"Threads çocuk container henüz hazır değil (400): {resp.text[:250]}")
        raise_for_status(resp.status_code, resp.text)
        try:
            return resp.json()
        except ValueError:
            raise TransientError(f"Threads geçersiz JSON: {resp.text[:200]}")

    # ------------------------------------------------------------- publishing
    def publish_carousel(
        self, image_urls: list[str], text: str
    ) -> dict[str, str]:
        """Carousel akışı: çocuklar → carousel container → publish.

        Kurallar (resmi doküman):
        1. Her görsel için POST /{user-id}/threads (is_carousel_item=true)
        2. media_type=CAROUSEL, children=... ile ana container
        3. Container FINISHED olana kadar poll → POST /{user-id}/threads_publish
        """
        if threads_char_length(text) > CHAR_LIMIT:
            raise PermanentError(
                f"Threads metni {threads_char_length(text)} byte, sınır {CHAR_LIMIT}."
            )
        if not image_urls:
            return self.publish_text(text)
        if len(image_urls) < MIN_CAROUSEL:
            # Tek görsel → normal görsel postu
            return self.publish_image(image_urls[0], text)
        if len(image_urls) > MAX_CAROUSEL:
            image_urls = image_urls[:MAX_CAROUSEL]

        children: list[str] = []
        for url in image_urls:
            child_id = self._create_container(
                {
                    "media_type": "IMAGE",
                    "image_url": url,
                    "is_carousel_item": "true",
                }
            )
            children.append(child_id)
            log.info("Carousel çocuk container: %s", child_id)

        time.sleep(1.5)
        main_id = self._create_container(
            {
                "media_type": "CAROUSEL",
                "children": ",".join(children),
                "text": text,
            }
        )
        self._wait_container(main_id)
        return self._publish(main_id)

    def publish_image(self, image_url: str, text: str) -> dict[str, str]:
        """Tek görsel post: container → bekle → publish."""
        if threads_char_length(text) > CHAR_LIMIT:
            raise PermanentError(
                f"Threads metni {threads_char_length(text)} byte, sınır {CHAR_LIMIT}."
            )
        container_id = self._create_container(
            {"media_type": "IMAGE", "image_url": image_url, "text": text}
        )
        self._wait_container(container_id)
        return self._publish(container_id)

    def publish_text(self, text: str) -> dict[str, str]:
        """Metin postu."""
        if threads_char_length(text) > CHAR_LIMIT:
            raise PermanentError(
                f"Threads metni {threads_char_length(text)} byte, sınır {CHAR_LIMIT}."
            )
        container_id = self._create_container(
            {"media_type": "TEXT", "text": text}
        )
        self._wait_container(container_id)
        return self._publish(container_id)

    def _create_container(self, fields: dict[str, str]) -> str:
        data = self._request(
            "POST", f"{GRAPH_BASE}/{self._user_id}/threads", data=fields
        )
        container_id = data.get("id", "")
        if not container_id:
            raise TransientError(f"Threads container ID yok: {data}")
        return container_id

    def _wait_container(self, container_id: str) -> None:
        """Container durumu FINISHED olana kadar poll eder (resmi öneri)."""
        for attempt in range(CONTAINER_POLL_MAX):
            data = self._request(
                "GET",
                f"{GRAPH_BASE}/{container_id}",
                params={"fields": "status"},
            )
            status = data.get("status", "")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED", "PUBLISHED"):
                raise TransientError(
                    f"Threads container {status}: {container_id} — {data}"
                )
            time.sleep(CONTAINER_POLL_INTERVAL)
        raise TransientError(
            f"Threads container {container_id} {CONTAINER_POLL_MAX} denemede FINISHED olmadı."
        )

    def _publish(self, container_id: str) -> dict[str, str]:
        data = self._request(
            "POST",
            f"{GRAPH_BASE}/{self._user_id}/threads_publish",
            data={"creation_id": container_id},
        )
        media_id = data.get("id", "")
        if not media_id:
            raise TransientError(f"Threads publish media ID yok: {data}")
        permalink = self.get_permalink(media_id)
        log.info("Threads paylaşıldı: %s → %s", media_id, permalink)
        return {"id": media_id, "permalink": permalink}

    def get_permalink(self, media_id: str) -> str:
        """Yayın sonrası permalink'i kaydeder."""
        try:
            data = self._request(
                "GET", f"{GRAPH_BASE}/{media_id}", params={"fields": "permalink"}
            )
            return data.get("permalink", "")
        except (PermanentError, TransientError) as exc:
            log.warning("Permalink alınamadı: %s", exc)
            return ""


# ------------------------------------------------------------ token yenileme
def load_token_state() -> dict:
    """data/token_state.json — yalnızca son yenileme TARİHİ tutulur, token DEĞİL."""
    if TOKEN_STATE_FILE.exists():
        try:
            return json.loads(TOKEN_STATE_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def save_token_state(state: dict) -> None:
    TOKEN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def maybe_refresh_token(
    *, dry_run: bool = False, force: bool = False
) -> dict[str, str]:
    """Long-lived token 60 gün geçerlidir; 40 günü geçtiyse yeniler.

    Yeni token GitHub REST API ile repo secret'ına yazılır (GH_PAT + PyNaCl
    sealed box). token_state.json'a yalnızca tarih yazılır.
    """
    from datetime import datetime, timezone

    state = load_token_state()
    last_refresh = state.get("last_refresh", "")
    if last_refresh and not force:
        try:
            last = datetime.fromisoformat(last_refresh)
            age_days = (datetime.now(timezone.utc) - last).days
            if age_days < 40:
                log.info("Token yenileme gerekmiyor (%d gün önce yenilendi)", age_days)
                return {"status": "skipped", "age_days": str(age_days)}
        except ValueError:
            pass

    token = settings().threads_access_token
    if not token:
        raise PermanentError("THREADS_ACCESS_TOKEN tanımlı değil.")

    if dry_run:
        return {"status": "dry_run", "action": "refresh"}

    # Resmi yenileme uç noktası (Threads dokümantasyonu)
    resp = requests.get(
        REFRESH_URL,
        params={
            "grant_type": "th_refresh_token",
            "access_token": token,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise TransientError(f"Token yenileme başarısız: HTTP {resp.status_code}")
    data = resp.json()
    new_token = data.get("access_token", "")
    if not new_token:
        raise TransientError(f"Yeni token yok: {data}")

    # Yeni token'ı GitHub secret'ına yaz
    updated = update_github_secret("THREADS_ACCESS_TOKEN", new_token)
    state["last_refresh"] = datetime.now(timezone.utc).isoformat()
    state["last_refresh_result"] = "secret_updated" if updated else "secret_update_failed"
    save_token_state(state)
    log.info("Threads token yenilendi (secret güncellendi: %s)", updated)
    return {
        "status": "refreshed",
        "secret_updated": str(updated),
    }


def update_github_secret(name: str, value: str) -> bool:
    """GitHub REST API ile repo secret'ını günceller.

    Şifreleme: PyNaCl sealed box ile GitHub'ın public key'i kullanılır.
    GH_PAT secret'ı gerekli (GITHUB_TOKEN repo secret yazma iznine sahip değildir).
    """
    import base64

    import requests as req
    from nacl import encoding, public

    cfg = settings()
    if not cfg.gh_pat or not cfg.github_repository:
        log.error("GH_PAT veya GITHUB_REPOSITORY tanımlı değil, secret güncellenemedi.")
        return False

    repo = cfg.github_repository
    headers = {
        "Authorization": f"Bearer {cfg.gh_pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # 1. Repo public key'ini al
    r = req.get(f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
                headers=headers, timeout=30)
    if r.status_code != 200:
        log.error("GitHub public key alınamadı: HTTP %s", r.status_code)
        return False
    key_id = r.json()["key_id"]
    key_b64 = r.json()["key"]

    # 2. Sealed box ile şifrele
    public_key = public.PublicKey(key_b64, encoding.Base64Encoder())
    box = public.SealedBox(public_key)
    encrypted = box.encrypt(value.encode("utf-8"))
    encrypted_b64 = base64.b64encode(encrypted).decode("utf-8")

    # 3. Secret'ı güncelle
    r = req.put(
        f"https://api.github.com/repos/{repo}/actions/secrets/{name}",
        headers=headers,
        json={"encrypted_value": encrypted_b64, "key_id": key_id},
        timeout=30,
    )
    if r.status_code in (201, 204):
        return True
    log.error("Secret güncellenemedi: HTTP %s — %s", r.status_code, r.text[:200])
    return False