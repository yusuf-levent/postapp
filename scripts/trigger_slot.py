"""Yedek slot tetikleyici (GitHub Actions cron gecikmelerine karşı).

Her 15 dakikada bir çalışır:
- Aktif slot saatlerindeysek (09:00, 12:00, 15:00, 18:00, 21:00 İstanbul)
- Ve o slot için GitHub'daki data/history.json içinde henüz 6/6 yayınlanmış kayıt yoksa
- Ve şu anda çalışan/bekleyen bir post workflow'u yoksa
GitHub API üzerinden post.yml workflow_dispatch tetikler.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import requests

REPO = "yusuf-levent/postapp"
SLOTS = ["09:00", "12:00", "15:00", "18:00", "21:00"]


def get_github_token() -> str:
    out = subprocess.check_output(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        timeout=10,
    )
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return ""


def main() -> int:
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    today = now.strftime("%Y-%m-%d")

    # Şu anki saate en yakın slotu bul (yalnızca slot saatinden 0..75 dk sonrası için tetikle)
    active_slot = None
    for s in SLOTS:
        hh, mm = map(int, s.split(":"))
        slot_dt = datetime.combine(now.date(), time(hh, mm), tzinfo=now.tzinfo)
        diff_minutes = (now - slot_dt).total_seconds() / 60.0
        if 0 <= diff_minutes <= 75:
            active_slot = s
            break

    if not active_slot:
        return 0

    token = get_github_token()
    if not token:
        return 0
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    # 1) Şu anda çalışan bir post workflow'u var mı?
    r_runs = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/workflows/post.yml/runs?per_page=5",
        headers=headers,
        timeout=15,
    )
    if r_runs.status_code == 200:
        for run in r_runs.json().get("workflow_runs", []):
            if run.get("status") in ("in_progress", "queued", "waiting"):
                return 0

    # 2) Bu slot için history.json'da tamamlanmış post var mı?
    r_hist = requests.get(
        f"https://raw.githubusercontent.com/{REPO}/main/data/history.json",
        headers={"Cache-Control": "no-cache"},
        timeout=15,
    )
    if r_hist.status_code == 200:
        posts = r_hist.json().get("posts", [])
        for p in posts:
            if p.get("date") == today and p.get("slot") == active_slot:
                statuses = p.get("status_per_platform", [])
                if statuses and all(st.get("state") == "published" for st in statuses):
                    return 0

    # 3) Tetikle!
    requests.post(
        f"https://api.github.com/repos/{REPO}/actions/workflows/post.yml/dispatches",
        headers=headers,
        json={"ref": "main", "inputs": {"dry_run": "false", "force_type": "auto"}},
        timeout=15,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
