"""GitHub Issue yönetimi: kalıcı paylaşım hatalarında otomatik issue açma.

Aynı hata için yinelenen issue AÇILMAZ. Sorun çözülünce issue otomatik kapanır.
"""
from __future__ import annotations

import logging

import requests

from app.config import settings

log = logging.getLogger("tekno-pusula.issues")

API = "https://api.github.com"
ISSUE_PREFIX = "❌ Paylaşım hatası:"


def _headers() -> dict[str, str]:
    cfg = settings()
    return {
        "Authorization": f"Bearer {cfg.gh_pat or cfg.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def find_existing_issue(platform: str, date: str) -> int | None:
    """Aynı platform+tarih için açık issue var mı? (yinelenen issue önleme)"""
    cfg = settings()
    if not cfg.github_repository:
        return None
    title_filter = f"{ISSUE_PREFIX} {platform}"
    resp = requests.get(
        f"{API}/repos/{cfg.github_repository}/issues",
        headers=_headers(),
        params={"state": "open", "per_page": 50},
        timeout=30,
    )
    if resp.status_code != 200:
        log.warning("Issue listesi alınamadı: HTTP %s", resp.status_code)
        return None
    for issue in resp.json():
        title = issue.get("title", "")
        if title.startswith(title_filter) and date in title:
            return issue.get("number")
    return None


def open_issue(platform: str, date: str, error_detail: str) -> int | None:
    """Paylaşım hatası için issue açar. Aynı hata için tekrar açılmaz."""
    cfg = settings()
    if not cfg.github_repository:
        log.error("GITHUB_REPOSITORY tanımlı değil, issue açılamadı.")
        return None

    existing = find_existing_issue(platform, date)
    if existing:
        log.info("Aynı hata için issue zaten açık: #%d", existing)
        return existing

    title = f"{ISSUE_PREFIX} {platform} – {date}"
    body = (
        f"## Paylaşım hatası\n\n"
        f"- **Platform:** {platform}\n"
        f"- **Tarih:** {date}\n"
        f"- **Hata:**\n\n```\n{error_detail[:2000]}\n```\n\n"
        f"Bu issue, kalıcı bir paylaşım hatası nedeniyle otomatik açıldı.\n"
        f"Sorun çözüldüğünde manuel olarak kapatın veya bir sonraki başarılı "
        f"paylaşımda otomatik kapanacaktır.\n"
    )
    resp = requests.post(
        f"{API}/repos/{cfg.github_repository}/issues",
        headers=_headers(),
        json={"title": title, "body": body},
        timeout=30,
    )
    if resp.status_code == 201:
        number = resp.json().get("number")
        log.info("Issue açıldı: #%d (%s)", number, title)
        return number
    log.error("Issue açılamadı: HTTP %s — %s", resp.status_code, resp.text[:200])
    return None


def close_issue(issue_number: int, comment: str = "Sorun çözüldü, otomatik kapatılıyor.") -> bool:
    """Sorun çözülünce issue'yu otomatik kapatır."""
    cfg = settings()
    if not cfg.github_repository:
        return False
    requests.post(
        f"{API}/repos/{cfg.github_repository}/issues/{issue_number}/comments",
        headers=_headers(),
        json={"body": comment},
        timeout=30,
    )
    resp = requests.patch(
        f"{API}/repos/{cfg.github_repository}/issues/{issue_number}",
        headers=_headers(),
        json={"state": "closed"},
        timeout=30,
    )
    return resp.status_code == 200


def close_resolved_issues(platform: str) -> None:
    """Başarılı paylaşımdan sonra o platforma ait açık issue'ları kapatır."""
    cfg = settings()
    if not cfg.github_repository:
        return
    resp = requests.get(
        f"{API}/repos/{cfg.github_repository}/issues",
        headers=_headers(),
        params={"state": "open", "per_page": 50},
        timeout=30,
    )
    if resp.status_code != 200:
        return
    for issue in resp.json():
        title = issue.get("title", "")
        if title.startswith(f"{ISSUE_PREFIX} {platform}"):
            close_issue(
                issue.get("number"),
                f"{platform} platformunda başarılı paylaşım yapıldı, otomatik kapatılıyor.",
            )