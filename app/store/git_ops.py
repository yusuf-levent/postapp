"""Git işlemleri: commit + push, çakışmada pull --rebase + tekrar dene (3 kez).

Commit yazarı: github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.config import REPO_ROOT

log = logging.getLogger("tekno-pusula.git")

BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args, cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8"
    )
    if check and result.returncode != 0:
        log.error("git hatası: %s\n%s", " ".join(args), result.stderr[:500])
    return result


def commit_paths(message: str, paths: list[str | Path]) -> bool:
    """Değişiklikleri commit eder. Değişiklik yoksa True döner (sessizce)."""
    for p in paths:
        _run(["git", "add", "-A", str(p)], check=False)

    status = _run(["git", "status", "--porcelain"], check=False)
    if not status.stdout.strip():
        log.info("Commit edilecek değişiklik yok.")
        return True

    env_args = ["git", "-c", f"user.name={BOT_NAME}", "-c", f"user.email={BOT_EMAIL}"]
    commit = _run(
        [*env_args, "commit", "-m", message], check=False
    )
    if commit.returncode != 0:
        log.error("commit başarısız: %s", commit.stderr[:300])
        return False
    log.info("Commit: %s", message)
    return True


def push_with_rebase(*, max_retries: int = 3) -> bool:
    """Push eder; çakışmada pull --rebase + tekrar dener (3 kez)."""
    for attempt in range(1, max_retries + 1):
        push = _run(["git", "push"], check=False)
        if push.returncode == 0:
            return True
        log.warning("push başarısız (deneme %d/%d): %s", attempt, max_retries, push.stderr[:200])
        _run(["git", "pull", "--rebase"], check=False)
    log.error("push %s denemede başarısız.", max_retries)
    return False


def commit_and_push(message: str, paths: list[str | Path]) -> bool:
    """Commit + push (rebase retry dahil)."""
    if not commit_paths(message, paths):
        return False
    return push_with_rebase()