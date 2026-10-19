"""Garantili slot tetikleyici (GitHub Actions cron gecikmelerine karşı).

Her 15 dakikada bir çalışır:
- Bugünün saati gelmiş (09:00, 12:00, 15:00, 18:00, 21:00 İstanbul <= şu an) slotlarından
  herhangi biri GitHub'daki data/history.json içinde henüz 6/6 yayınlanmamışsa
- Ve şu anda çalışan (in_progress) bir publish workflow'u yoksa
GitHub Contents API üzerinden `data/slot_trigger.txt` dosyasını güncelleyerek
anında `push` webhook tetiklemesi başlatır (GitHub'da 1 saniye içinde başlar).
"""
from __future__ import annotations

import base64
import shutil
import subprocess
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import requests

REPO = "yusuf-levent/postapp"
SLOTS = ["09:00", "12:00", "15:00", "18:00", "21:00"]
GIT_EXE = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"


def get_github_token() -> str:
    out = subprocess.check_output(
        [GIT_EXE, "credential", "fill"],
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
    now_hm = now.strftime("%H:%M")

    due_slots = [s for s in SLOTS if s <= now_hm]
    if not due_slots:
        return 0

    token = get_github_token()
    if not token:
        return 0
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    # 1) Şu anda aktif çalışan (in_progress) bir publish.yml workflow'u var mı?
    r_runs = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/workflows/publish.yml/runs?per_page=5",
        headers=headers,
        timeout=15,
    )
    if r_runs.status_code == 200:
        for run in r_runs.json().get("workflow_runs", []):
            if run.get("status") == "in_progress":
                return 0

    # 2) Bugünün saati gelmiş tüm slotları 6/6 tamamlanmış mı?
    r_hist = requests.get(
        f"https://raw.githubusercontent.com/{REPO}/main/data/history.json",
        headers={"Cache-Control": "no-cache"},
        timeout=15,
    )
    missing_slots: list[str] = []
    if r_hist.status_code == 200:
        raw = r_hist.json()
        posts = raw if isinstance(raw, list) else raw.get("posts", [])
        done_today = set()
        for p in posts:
            if p.get("date") == today:
                statuses = p.get("status_per_platform", [])
                if statuses and all(st.get("state") == "published" for st in statuses):
                    done_today.add(p.get("slot"))
        missing_slots = [s for s in due_slots if s not in done_today]
    else:
        missing_slots = due_slots

    if not missing_slots:
        return 0

    # 3) data/slot_trigger.txt dosyasını GitHub API ile güncelle -> push webhook 1 sn'de başlar!
    url = f"https://api.github.com/repos/{REPO}/contents/data/slot_trigger.txt"
    r_file = requests.get(url, headers=headers, timeout=15)
    sha = r_file.json().get("sha") if r_file.status_code == 200 else None
    content = f"{today} {','.join(missing_slots)} triggered at {datetime.now(timezone.utc).isoformat()}\n"
    payload = {
        "message": f"⚡ trigger: {today} {','.join(missing_slots)}",
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha
    requests.put(url, headers=headers, json=payload, timeout=15)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
