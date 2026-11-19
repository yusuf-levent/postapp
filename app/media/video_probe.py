"""Inspect actual media streams before and after encoding."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _parse_fps(raw: str) -> float:
    if not raw or raw == "0/0":
        return 0.0
    if "/" in raw:
        num, den = raw.split("/", 1)
        try:
            d = float(den)
            return float(num) / d if d else 0.0
        except ValueError:
            return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def probe_video(path: Path) -> dict:
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                                 "-of", "json", str(path)], capture_output=True, text=True, timeout=20)
        if result.returncode:
            return {}
        data = json.loads(result.stdout)
        streams = data.get("streams") or []
        fmt = data.get("format") or {}
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        fps = _parse_fps(str(video.get("avg_frame_rate") or video.get("r_frame_rate") or ""))
        try:
            bit_rate = int(video.get("bit_rate") or fmt.get("bit_rate") or 0)
        except (TypeError, ValueError):
            bit_rate = 0
        return {"duration": float(fmt.get("duration") or 0),
                "width": int(video.get("width") or 0), "height": int(video.get("height") or 0),
                "has_audio": any(s.get("codec_type") == "audio" for s in streams),
                "codec": video.get("codec_name", ""), "pixel_format": video.get("pix_fmt", ""),
                "fps": round(fps, 2), "bit_rate": bit_rate}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}
