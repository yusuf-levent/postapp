"""Inspect actual media streams before and after encoding."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def probe_video(path: Path) -> dict:
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                                 "-of", "json", str(path)], capture_output=True, text=True, timeout=20)
        if result.returncode:
            return {}
        data = json.loads(result.stdout)
        streams = data.get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        return {"duration": float((data.get("format") or {}).get("duration") or 0),
                "width": int(video.get("width") or 0), "height": int(video.get("height") or 0),
                "has_audio": any(s.get("codec_type") == "audio" for s in streams),
                "codec": video.get("codec_name", ""), "pixel_format": video.get("pix_fmt", "")}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}
