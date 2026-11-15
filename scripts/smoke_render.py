"""Offline browser + FFmpeg integration check. No keys or publishing calls."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.media.video_probe import probe_video
from app.render.fonts import ensure_fonts
from app.render.sample import render_sample, sample_deck
from app.render.video_renderer import render_reel_video

if __name__ == "__main__":
    out = render_sample() / "video-smoke"
    out.mkdir(parents=True, exist_ok=True)
    source = out / "source.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=960x540:rate=30", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
                    "-t", "9", "-c:v", "libx264", "-threads", "2", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
                   check=True, timeout=60)
    deck = sample_deck()
    deck["source_names"] = ["TEST — YAYINLANMAZ"]
    reel = render_reel_video(deck, source, out, fonts_dir=ensure_fonts())
    assert reel is not None, "MP4 production failed"
    info = probe_video(reel)
    assert (info["width"], info["height"]) == (1080, 1920)
    assert info["codec"] == "h264" and info["pixel_format"] == "yuv420p"
    assert info["has_audio"] and 8.9 <= info["duration"] <= 9.2
    print("OK: 12 PNG + 1080x1920 H.264/AAC MP4, 9 seconds; no publishing calls.")
