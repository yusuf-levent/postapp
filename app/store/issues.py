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
    # GITHUB_TOKEN (github-actions[bot]) tercih edilir; böylece @repo-sahibi
    # etiketlendiğinde GitHub otomatik bildirim e-postası gönderir.
    return {
        "Authorization": f"Bearer {cfg.github_token or cfg.gh_pat}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _repo_owner() -> str:
    cfg = settings()
    if cfg.github_repository and "/" in cfg.github_repository:
        return cfg.github_repository.split("/", 1)[0]
    return ""


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

    owner = _repo_owner()
    mention = f"@{owner}\n\n" if owner else ""
    title = f"{ISSUE_PREFIX} {platform} – {date}"
    body = (
        f"{mention}## Paylaşım hatası\n\n"
        f"- **Platform:** {platform}\n"
        f"- **Tarih:** {date}\n"
        f"- **Hata:**\n\n```\n{error_detail[:2000]}\n```\n\n"
        f"Bu issue, kalıcı bir paylaşım hatası nedeniyle otomatik açıldı.\n"
        f"Sorun çözüldüğünde manuel olarak kapatın veya bir sonraki başarılı "
        f"paylaşımda otomatik kapanacaktır.\n"
    )
    payload: dict = {"title": title, "body": body}
    if owner:
        payload["assignees"] = [owner]
    resp = requests.post(
        f"{API}/repos/{cfg.github_repository}/issues",
        headers=_headers(),
        json=payload,
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


def notify_post_published(
    *,
    date_label: str,
    slot: str,
    ptype: str,
    title_tr: str,
    statuses: dict,
    image_urls: list[str],
    caption_preview: str = "",
    source_urls: list[str] | None = None,
) -> int | None:
    """Her post paylaşıldığında bildirim gönderir (GitHub Issue e-posta bildirimi + opsiyonel SMTP).

    github-actions[bot] üzerinden @repo_owner etiketlenerek Issue açıldığı için
    GitHub, kullanıcının kayıtlı e-posta adresine otomatik olarak post özetini ve
    slayt görsellerini içeren bir e-posta gönderir.
    """
    import os
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    published_count = sum(1 for s in statuses.values() if getattr(s, "state", "") == "published")
    total_count = len(statuses)
    owner = _repo_owner()
    mention = f"@{owner} " if owner else ""

    status_lines = []
    for name, st in statuses.items():
        state = getattr(st, "state", "pending")
        icon = "✅" if state == "published" else ("❌" if state == "failed" else "⏳")
        link = getattr(st, "permalink", "") or ""
        ext_id = getattr(st, "external_id", "") or ""
        err = getattr(st, "last_error", "") or ""
        detail = f"[Gönderi Linki]({link})" if link else (f"ID: `{ext_id}`" if ext_id else (err[:80] if err else state))
        status_lines.append(f"| **{name.upper()}** | {icon} `{state}` | {detail} |")

    slides_md = "\n".join(
        f"### Slayt {i}\n![Slayt {i}]({u})" for i, u in enumerate(image_urls, start=1)
    )
    sources_md = "\n".join(f"- {u}" for u in (source_urls or []) if u) or "- (Eğitim / Hap Bilgi)"

    subject = f"📬 Post Paylaşıldı ({published_count}/{total_count}): {date_label} {slot} – {title_tr[:60]}"
    body = (
        f"{mention}Yeni sosyal medya gönderisi otomatik olarak hazırlandı ve paylaşıldı!\n\n"
        f"## 📌 Gönderi Özeti\n"
        f"- **Tarih / Saat:** `{date_label} {slot}` (İstanbul)\n"
        f"- **Tür:** `{ptype.upper()}`\n"
        f"- **Başlık:** **{title_tr}**\n"
        f"- **Paylaşım Durumu:** **{published_count} / {total_count} platform başarılı**\n\n"
        f"## 🌐 Platform Durumları\n"
        f"| Platform | Durum | Detay |\n"
        f"|---|---|---|\n"
        + "\n".join(status_lines)
        + "\n\n"
        + (f"## 📝 Açıklama Önizlemesi\n```text\n{caption_preview[:1000]}\n```\n\n" if caption_preview else "")
        + f"## 🔗 Kaynaklar\n{sources_md}\n\n"
        + (f"## 🖼️ Üretilen Slaytlar\n{slides_md}\n" if image_urls else "")
    )

    # 1) Opsiyonel doğrudan SMTP e-posta (SMTP_USER, SMTP_PASS, NOTIFY_EMAIL tanımlıysa)
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASS", "").strip()
    notify_email = os.environ.get("NOTIFY_EMAIL", "").strip() or smtp_user
    if smtp_user and smtp_pass and notify_email:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_user
            msg["To"] = notify_email
            msg.attach(MIMEText(body, "plain", "utf-8"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as server:
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, [notify_email], msg.as_string())
            log.info("SMTP e-posta bildirimi gönderildi: %s", notify_email)
        except Exception as exc:
            log.warning("SMTP e-posta gönderilemedi: %s", exc)

    # 2) GitHub Issue bildirimi (GitHub otomatik olarak repo sahibine e-posta atar)
    cfg = settings()
    if not cfg.github_repository or not (cfg.github_token or cfg.gh_pat):
        return None
    try:
        payload: dict = {"title": subject, "body": body}
        if owner:
            payload["assignees"] = [owner]
        resp = requests.post(
            f"{API}/repos/{cfg.github_repository}/issues",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        if resp.status_code == 201:
            num = resp.json().get("number")
            log.info("Paylaşım bildirim issue'su açıldı (e-posta tetiklendi): #%s", num)
            # Bildirim e-postası tetiklendikten sonra issue listesi kirlenmesin diye kapat
            requests.patch(
                f"{API}/repos/{cfg.github_repository}/issues/{num}",
                headers=_headers(),
                json={"state": "closed"},
                timeout=30,
            )
            return num
        log.warning("Paylaşım bildirim issue'su açılamadı: HTTP %s", resp.status_code)
    except Exception as exc:
        log.warning("Paylaşım bildirim hatası: %s", exc)
    return None