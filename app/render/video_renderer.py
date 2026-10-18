"""9:16 Reels & TikTok video üretici (1080×1920 MP4).

Üst pencerede internetten indirilen gerçek video akar, alt panelde ise Tekno Pusula
slayt kartları (1..6) 3.5 saniyede bir sırayla değişir. Arka planda telifsiz
ambient teknoloji/haber fon müziği (ve varsa videonun kendi sesi) yer alır.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any

from app.config import brand_config
from app.render.renderer import render_slide_html

log = logging.getLogger("tekno-pusula.video_renderer")

SLIDE_SECONDS = 3.5
SLIDE_COUNT = 6
TOTAL_DURATION = SLIDE_SECONDS * SLIDE_COUNT  # 21.0 saniye


def render_reel_video(
    deck: dict[str, Any],
    source_video: Path,
    post_dir: Path,
    *,
    fonts_dir: Path | None = None,
) -> Path | None:
    """Gerçek video + 6 slayt alt katmanı + ambient fon müziği ile 1080×1920 MP4 üretir."""
    if not source_video or not source_video.exists():
        log.warning("Kaynak video bulunamadı, Reels/TikTok videosu üretilmiyor.")
        return None
    if not shutil.which("ffmpeg"):
        log.warning("Sistemde ffmpeg kurulu değil, Reels/TikTok videosu üretilmiyor.")
        source_video.unlink(missing_ok=True)
        return None

    video_dir = post_dir / "video"
    overlays_dir = video_dir / "overlays"
    overlays_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = video_dir / "reel.mp4"

    try:
        overlay_paths = asyncio.run(_render_transparent_overlays(deck, overlays_dir, fonts_dir=fonts_dir))
    except Exception as exc:
        log.warning("Video overlay render hatası: %s", exc)
        shutil.rmtree(overlays_dir, ignore_errors=True)
        source_video.unlink(missing_ok=True)
        return None

    ambient_wav = video_dir / "ambient.wav"
    _generate_ambient_tech_beat(ambient_wav, duration=TOTAL_DURATION)

    # FFmpeg concat dosyası (her overlay 3.5 sn)
    concat_txt = overlays_dir / "overlays.txt"
    lines: list[str] = []
    for p in overlay_paths:
        lines.append(f"file '{p.name}'")
        lines.append(f"duration {SLIDE_SECONDS:.2f}")
    lines.append(f"file '{overlay_paths[-1].name}'")
    concat_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Kaynak videoda ses kanalı var mı kontrol et
    has_audio = _video_has_audio(source_video)

    filter_complex = (
        # 1) Üst alanda (1080x880) gerçek video net akar, alt alan (1080x1040) koyu/bulanık arka plan
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "boxblur=20:2,eq=brightness=-0.45[bg];"
        "[0:v]scale=1080:860:force_original_aspect_ratio=increase,crop=1080:860[topvid];"
        "[bg][topvid]overlay=0:0[base];"
        # 2) Şeffaf PNG slayt katmanlarını (1080x1920) üzerine bindir
        "[base][1:v]overlay=0:0:format=auto,format=yuv420p[vout]"
    )

    if has_audio:
        audio_filter = (
            ";[0:a]aresample=44100,volume=0.22[va];"
            "[2:a]aresample=44100,volume=0.85[ma];"
            "[va][ma]amix=inputs=2:duration=shortest:dropout_transition=2[aout]"
        )
        full_filter = filter_complex + audio_filter
        audio_map = "[aout]"
    else:
        full_filter = filter_complex
        audio_map = "2:a"

    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop", "-1",
        "-t", f"{TOTAL_DURATION:.2f}",
        "-i", str(source_video.resolve()),
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_txt.resolve()),
        "-i", str(ambient_wav.resolve()),
        "-filter_complex", full_filter,
        "-map", "[vout]",
        "-map", audio_map,
        "-t", f"{TOTAL_DURATION:.2f}",
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(out_mp4.resolve()),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    # Geçici dosyaları temizle (repoya sadece reel.mp4 girsin)
    shutil.rmtree(overlays_dir, ignore_errors=True)
    ambient_wav.unlink(missing_ok=True)
    source_video.unlink(missing_ok=True)

    if proc.returncode != 0 or not out_mp4.exists() or out_mp4.stat().st_size < 50_000:
        log.warning("FFmpeg video üretimi başarısız (rc=%s): %s", proc.returncode, proc.stderr[-500:])
        out_mp4.unlink(missing_ok=True)
        return None

    log.info("Reels/TikTok videosu üretildi: %s (%.1f MB)", out_mp4.name, out_mp4.stat().st_size / (1024 * 1024))
    return out_mp4


async def _render_transparent_overlays(
    deck: dict[str, Any],
    overlays_dir: Path,
    *,
    fonts_dir: Path | None = None,
) -> list[Path]:
    """6 slayt için üst yarısı şeffaf (videonun görüneceği), alt yarısı kartlı 1080×1920 PNG üretir."""
    from playwright.async_api import async_playwright

    brand = brand_config()
    w916 = brand["canvas"]["width_9x16"]
    h916 = brand["canvas"]["height_9x16"]
    out_paths: list[Path] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(
            viewport={"width": w916, "height": h916}, device_scale_factor=1
        )
        for i in range(1, SLIDE_COUNT + 1):
            d = dict(deck)
            d["bg_image"] = ""
            raw_html = render_slide_html(d, i)
            styles = "\n".join(re.findall(r"<style>(.*?)</style>", raw_html, re.DOTALL))
            m = re.search(r"<body>(.*)</body>", raw_html, re.DOTALL)
            body = m.group(1) if m else raw_html

            overlay_html = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><style>
{styles}
html, body {{
  width: {w916}px !important;
  height: {h916}px !important;
  background: transparent !important;
  overflow: hidden;
}}
.video-stage {{
  position: relative;
  width: {w916}px;
  height: {h916}px;
  background: linear-gradient(
    to bottom,
    rgba(7,9,13,0.55) 0px,
    rgba(7,9,13,0.0) 140px,
    rgba(7,9,13,0.0) 680px,
    rgba(7,9,13,0.88) 830px,
    #07090d 900px,
    #07090d 1920px
  );
  overflow: hidden;
}}
.video-stage .slide {{
  width: {w916}px !important;
  height: {h916}px !important;
  background: transparent !important;
}}
.video-stage .slide-bg {{
  display: none !important;
}}
/* Üst bar rozetleri videonun üst kısmında dursun */
.video-stage .handle-pill,
.video-stage .source-tags,
.video-stage .slide-tag,
.video-stage .page-counter {{
  top: 54px !important;
}}
/* Tüm slayt içeriklerini alt panele (830px - 1780px) hizala */
.video-stage .cover-center {{
  top: 850px !important;
  bottom: 140px !important;
}}
.video-stage .inner-content {{
  top: 850px !important;
  bottom: 140px !important;
}}
.video-stage .stat-wrap {{
  top: 930px !important;
}}
.video-stage .cta-wrap {{
  top: 860px !important;
  bottom: 140px !important;
}}
.video-stage .inner-heading {{
  font-size: 46px !important;
  margin-bottom: 24px !important;
}}
.video-stage .card {{
  padding: 24px 32px 26px 40px !important;
  margin-bottom: 18px !important;
}}
.video-stage .card-title {{
  font-size: 28px !important;
}}
.video-stage .card-body {{
  font-size: 22px !important;
}}
.video-stage .cover-bottom-bar {{
  bottom: 125px !important;
}}
.video-stage .cover-bottom-left,
.video-stage .progress,
.video-stage .inner-footer {{
  bottom: 48px !important;
}}
</style></head><body>
  <div class="video-stage">{body}</div>
</body></html>"""

            await page.set_content(overlay_html, wait_until="networkidle")
            await page.evaluate("document.fonts.ready")
            dest = overlays_dir / f"overlay-{i}.png"
            await page.screenshot(path=str(dest), type="png", omit_background=True)
            out_paths.append(dest)
        await browser.close()
    return out_paths


def _video_has_audio(video_path: Path) -> bool:
    """ffprobe ile kaynak videoda ses akışı olup olmadığını kontrol eder."""
    if not shutil.which("ffprobe"):
        return False
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                str(video_path.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return "audio" in (proc.stdout or "").lower()
    except Exception:
        return False


def _generate_ambient_tech_beat(dest: Path, *, duration: float = 21.0, sample_rate: int = 44100) -> None:
    """Telifsiz, yumuşak bir haber/teknoloji ambient fon müziği (WAV) üretir."""
    total_samples = int(duration * sample_rate)
    # A minor 9 ambient akor frekansları (A2, E3, G3, B3, C4)
    chord_freqs = (110.0, 164.81, 196.00, 246.94, 261.63)
    bpm = 112.0
    beat_period = 60.0 / bpm

    buf = bytearray(total_samples * 2)  # 16-bit mono
    for i in range(total_samples):
        t = i / sample_rate
        # Fade-in (ilk 0.8 sn) ve fade-out (son 1.5 sn)
        env = 1.0
        if t < 0.8:
            env = t / 0.8
        elif t > duration - 1.5:
            env = max(0.0, (duration - t) / 1.5)

        # Ambient pad
        pad = 0.0
        for idx, f in enumerate(chord_freqs):
            lfo = 0.7 + 0.3 * math.sin(2.0 * math.pi * (0.18 + idx * 0.05) * t)
            pad += math.sin(2.0 * math.pi * f * t) * lfo / len(chord_freqs)

        # Yumuşak ritmik bas nabzı (her vuruşta)
        beat_pos = (t % beat_period) / beat_period
        pulse_env = math.exp(-6.5 * beat_pos)
        pulse = math.sin(2.0 * math.pi * 55.0 * t) * pulse_env * 0.45

        # Slayt geçişlerinde (her 3.5 sn'de bir) hafif kristal bildirim tınısı
        slide_pos = t % SLIDE_SECONDS
        chime = 0.0
        if slide_pos < 0.45:
            chime_env = math.exp(-8.0 * slide_pos)
            chime = math.sin(2.0 * math.pi * 523.25 * t) * chime_env * 0.18

        sample = (pad * 0.42 + pulse + chime) * env
        clamped = max(-0.95, min(0.95, sample))
        struct.pack_into("<h", buf, i * 2, int(clamped * 14000))

    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(buf))
