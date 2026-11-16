"""Cheap workflow preflight, before installing Chromium and all dependencies."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.scheduling import due_slots, needs_recovery

if __name__ == "__main__":
    schedule = yaml.safe_load((ROOT / "config/schedule.yaml").read_text())
    history = json.loads((ROOT / "data/history.json").read_text())
    skipped = ROOT / "data/skipped_slots.json"
    if skipped.exists():
        history += json.loads(skipped.read_text())
    now = datetime.now(ZoneInfo(schedule["timezone"]))
    due = due_slots(schedule, history, now)
    should_run = bool(due) or needs_recovery(history, now) or os.environ.get("DRY_RUN") == "true"
    print(f"Bekleyen güncel slot: {due}")
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a") as stream:
            stream.write(f"due={'true' if should_run else 'false'}\n")
            stream.write(f"date={datetime.now(ZoneInfo(schedule['timezone'])).date().isoformat()}\n")
