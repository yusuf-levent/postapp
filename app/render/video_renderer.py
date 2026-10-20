"""9:16 Reels & TikTok video üretici (1080×1920 MP4).

Üst pencerede internetten indirilen gerçek ve doğrulanmış video kendi doğal akışıyla oynar,
alt kısımda ise haberin başlığı + somut bilgi maddeleri (rakamlar, gerçek detaylar) yer alır.
Video bulunamazsa veya doğrulanamazsa None döner ve sistem otomatik olarak
Instagram/TikTok'a 6'lı görsel slayt paylaşır.
"""
from __future__ import annotations

import asyncio
import html as _html
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

MIN_REEL_DURATION = 8.0
MAX_REEL_DURATION = 45.0
DEFAULT_REEL_DURATION = 15.0


def render_reel_video(
    deck: dict[str, Any],
    source_video: Path,
    post_dir: Path,
    *,
    fonts_dir: Path | None = None,
    music_info: dict[str, Any] | None = None,
) -> Path | None:
    """Gerçek video + alt kısımda somut haber özeti/maddeleri + müzik ile 1080×1920 MP4 üretir.

    Ses mantığı (hibrit):
    - Orijinal videoda ses akışı VARSA → %100 orijinal ses kullanılır (müzik eklenmez)
    - Orijinal videoda ses YOKSA → music_info ile gelen telifsiz müzik kullanılır
    - Müzik de yoksa → sessiz video (sessiz Reels normaldir, kullanıcı kendi müziğini ekler)
    """
    if not source_video or not source_video.exists():
        log.warning("Kaynak video bulunamadı, Reels/TikTok videosu üretilmiyor (6'lı slayt paylaşılacak).")
        return None
    if not shutil.which("ffmpeg"):
        log.warning("Sistemde ffmpeg kurulu değil, Reels/TikTok videosu üretilmiyor (6'lı slayt paylaşılacak).")
        source_video.unlink(missing_ok=True)
        return None

    video_dir = post_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    overlay_png = video_dir / "overlay.png"
    out_mp4 = video_dir / "reel.mp4"

    try:
        asyncio.run(_render_single_overlay(deck, overlay_png, fonts_dir=fonts_dir))
    except Exception as exc:
        log.warning("Video tekli yazı katmanı render hatası: %s", exc)
        overlay_png.unlink(missing_ok=True)
        source_video.unlink(missing_ok=True)
        return None

    natural_dur = _get_video_duration(source_video)
    target_duration = max(MIN_REEL_DURATION, min(MAX_REEL_DURATION, natural_dur))

    has_audio = _video_has_audio(source_video)

    # Ses mantığı: orijinal ses varsa %100 kullan, yoksa telifsiz müzik, o da yoksa sessiz
    music_wav = None
    if not has_audio and music_info and music_info.get("path"):
        music_path = Path(music_info["path"])
        if music_path.exists():
            music_wav = video_dir / "music.wav"
            # Müziği video süresine göre loop + kırp
            mcmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1",
                "-t", f"{target_duration:.2f}",
                "-i", str(music_path.resolve()),
                "-ac", "2", "-ar", "44100",
                "-b:a", "128k",
                str(music_wav.resolve()),
            ]
            mp = subprocess.run(mcmd, capture_output=True, text=True, timeout=60)
            if mp.returncode != 0:
                log.warning("Müzik dönüştürme başarısız: %s", mp.stderr[-300:])
                music_wav.unlink(missing_ok=True)
                music_wav = None

    filter_complex = (
        "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
        "boxblur=24:2,eq=brightness=-0.45[bg];"
        "[0:v]scale=1080:940:force_original_aspect_ratio=increase,crop=1080:940[topvid];"
        "[bg][topvid]overlay=0:0[base];"
        "[base][1:v]overlay=0:0:format=auto,format=yuv420p[vout]"
    )

    if has_audio:
        # Orijinal ses %100 kullanılır (müzik eklenmez)
        audio_filter = ";[0:a]aresample=44100[aout]"
        full_filter = filter_complex + audio_filter
        audio_map = "[aout]"
    elif music_wav:
        # Müzik %100 (orijinal ses yoksa)
        audio_filter = ";[2:a]aresample=44100,volume=0.85[aout]"
        full_filter = filter_complex + audio_filter
        audio_map = "[aout]"
    else:
        # Sessiz video (kullanıcı kendi müziğini ekler)
        full_filter = filter_complex
        audio_map = "2:a"

    cmd = [
        "ffmpeg",
        "-y",
        "-stream_loop", "-1",
        "-t", f"{target_duration:.2f}",
        "-i", str(source_video.resolve()),
        "-loop", "1",
        "-t", f"{target_duration:.2f}",
        "-i", str(overlay_png.resolve()),
    ]
    if music_wav:
        cmd += ["-i", str(music_wav.resolve())]

    if music_wav and not has_audio:
        # Sessiz video + müzik ekle
        cmd += ["-shortest"]
        audio_map = "[aout]"
        output_codec = ["-c:a", "aac", "-b:a", "128k"]
    elif has_audio:
        # Orijinal ses kullan
        output_codec = ["-c:a", "aac", "-b:a", "128k"]
    else:
        # Tamamen sessiz (audio stream yok)
        audio_map = ""
        output_codec = []

    cmd += [
        "-filter_complex", full_filter,
        "-map", "[vout]",
    ]
    if audio_map:
        cmd += ["-map", audio_map]
    cmd += [
        "-t", f"{target_duration:.2f}",
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
    ]
    cmd += output_codec
    cmd += [
        "-movflags", "+faststart",
        str(out_mp4.resolve()),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    overlay_png.unlink(missing_ok=True)
    if music_wav:
        music_wav.unlink(missing_ok=True)
    source_video.unlink(missing_ok=True)

    if proc.returncode != 0 or not out_mp4.exists() or out_mp4.stat().st_size < 50_000:
        log.warning("FFmpeg video üretimi başarısız (rc=%s): %s", proc.returncode, proc.stderr[-500:])
        out_mp4.unlink(missing_ok=True)
        return None

    log.info(
        "Reels/TikTok videosu üretildi: %s (%.1f sn, %.1f MB)",
        out_mp4.name,
        target_duration,
        out_mp4.stat().st_size / (1024 * 1024),
    )
    return out_mp4


def render_slideshow_reel(
    slide_images: list[Path],
    deck: dict[str, Any],
    post_dir: Path,
    *,
    fonts_dir: Path | None = None,
    music_info: dict[str, Any] | None = None,
    per_slide_seconds: float = 3.0,
) -> Path | None:
    """Gerçek video bulunamazsa 6 slayt görselini hareketli (zoom + fade) 1080×1920 Reel'e çevirir.

    Her slayt hafifçe zoom yapar (Ken Burns) ve bir sonrakine fade ile geçer.
    Müzik verilmişse video süresine göre loop edilir; yoksa sessiz bırakılır.
    """
    if not slide_images:
        return None
    if not shutil.which("ffmpeg"):
        log.warning("Sistemde ffmpeg kurulu değil, slideshow reel üretilemiyor.")
        return None

    video_dir = post_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    out_mp4 = video_dir / "reel.mp4"

    n = len(slide_images)
    target_duration = max(8.0, min(45.0, per_slide_seconds * n))
    per_slide = target_duration / n

    # Zoom + fade filtre zinciri
    inputs = []
    filter_parts = []
    for i, img in enumerate(slide_images):
        inputs += ["-loop", "1", "-t", f"{per_slide:.2f}", "-i", str(img.resolve())]
        # Her slayt: ölçekle + hafif zoom + kenar yumuşatma + fade in/out
        filter_parts.append(
            f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,"
            f"zoompan=z='1.0+0.08*on/{int(30*per_slide)}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={int(30*per_slide)}:s=1080x1920:fps=30,"
            f"fade=t=in:st=0:d=0.3,fade=t=out:st={max(0,per_slide-0.3):.2f}:d=0.3[v{i}]"
        )

    # Birleştir
    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vout]")
    full_filter = ";".join(filter_parts)

    music_wav = None
    if music_info and music_info.get("path"):
        music_path = Path(music_info["path"])
        if music_path.exists():
            music_wav = video_dir / "music.wav"
            mcmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1",
                "-t", f"{target_duration:.2f}",
                "-i", str(music_path.resolve()),
                "-ac", "2", "-ar", "44100",
                "-b:a", "128k",
                str(music_wav.resolve()),
            ]
            mp = subprocess.run(mcmd, capture_output=True, text=True, timeout=60)
            if mp.returncode != 0:
                music_wav.unlink(missing_ok=True)
                music_wav = None

    cmd = ["ffmpeg", "-y"] + inputs
    if music_wav:
        cmd += ["-i", str(music_wav.resolve())]
        filter_parts.append("[{}]aresample=44100[aout]".format(n))
        full_filter = ";".join(filter_parts)
        cmd += ["-filter_complex", full_filter, "-map", "[vout]", "-map", "[aout]"]
    else:
        cmd += ["-filter_complex", full_filter, "-map", "[vout]"]

    cmd += [
        "-t", f"{target_duration:.2f}",
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
    ]
    if music_wav:
        cmd += ["-c:a", "aac", "-b:a", "128k"]
    cmd += ["-movflags", "+faststart", str(out_mp4.resolve())]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if music_wav:
        music_wav.unlink(missing_ok=True)

    if proc.returncode != 0 or not out_mp4.exists() or out_mp4.stat().st_size < 30_000:
        log.warning("Slideshow reel üretimi başarısız (rc=%s): %s", proc.returncode, proc.stderr[-400:])
        out_mp4.unlink(missing_ok=True)
        return None

    log.info("Slideshow Reels/TikTok videosu üretildi: %s (%.1f sn)", out_mp4.name, target_duration)
    return out_mp4


def _extract_fact_bullets(deck: dict[str, Any]) -> list[str]:
    """Slayt destesindeki doğrulanmış kartlardan en somut 3 bilgi maddesini çıkarır."""
    bullets: list[str] = []

    stat = deck.get("stat") or {}
    big_stat = str(stat.get("big_stat") or "").strip()
    stat_cap = str(stat.get("stat_caption") or "").strip()
    if big_stat and big_stat != "💡" and stat_cap:
        bullets.append(f"<strong>{_html.escape(big_stat)}:</strong> {_html.escape(stat_cap)}")

    for section_key in ("context", "details", "impact"):
        sec = deck.get(section_key) or {}
        for card in sec.get("cards") or []:
            ctitle = str(card.get("title") or "").strip()
            cbody = str(card.get("body") or "").strip()
            if ctitle and cbody:
                bullets.append(f"<strong>{_html.escape(ctitle)}:</strong> {_html.escape(cbody)}")
            elif cbody:
                bullets.append(_html.escape(cbody))
            if len(bullets) >= 3:
                return bullets[:3]
    return bullets[:3]


async def _render_single_overlay(
    deck: dict[str, Any],
    dest_png: Path,
    *,
    fonts_dir: Path | None = None,
) -> Path:
    """Üst kısmı şeffaf (gerçek videonun görüneceği), alt kısmında başlık + 3 somut haber maddesi olan 1080×1920 PNG üretir."""
    from playwright.async_api import async_playwright

    brand = brand_config()
    w916 = brand["canvas"]["width_9x16"]
    h916 = brand["canvas"]["height_9x16"]
    accent = brand.get("colors", {}).get("accent_yellow", "#FFE000")
    handle = _html.escape(brand.get("handle", "@tekno_pusula"))

    d = dict(deck)
    d["bg_image"] = ""
    raw_html = render_slide_html(d, 1)
    styles = "\n".join(re.findall(r"<style>(.*?)</style>", raw_html, re.DOTALL))

    cover = deck.get("cover", {}) or {}
    category = _html.escape(str(cover.get("category_tag") or "TEKNOLOJİ GÜNDEMİ").upper())
    title_raw = str(cover.get("title") or "")
    highlight_words = cover.get("highlight_words") or []
    sources = deck.get("source_names") or []
    source_label = _html.escape(" · ".join(sources[:2])) if sources else "Tekno Pusula"

    title_html = _html.escape(title_raw)
    for hw in highlight_words:
        hw_esc = _html.escape(str(hw).strip())
        if hw_esc:
            pattern = re.compile(re.escape(hw_esc), re.IGNORECASE)
            title_html = pattern.sub(
                lambda m: f'<span class="hl">{m.group(0)}</span>', title_html, count=1
            )

    bullets = _extract_fact_bullets(deck)
    bullets_html = "\n".join(
        f'<div class="fact-item"><span class="fact-dot">▸</span><span class="fact-text">{b}</span></div>'
        for b in bullets
    )

    overlay_html = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><style>
{styles}
html, body {{
  width: {w916}px !important;
  height: {h916}px !important;
  margin: 0;
  padding: 0;
  background: transparent !important;
  overflow: hidden;
}}
.reel-frame {{
  position: relative;
  width: {w916}px;
  height: {h916}px;
  background: linear-gradient(
    to bottom,
    rgba(7,9,13,0.45) 0px,
    rgba(7,9,13,0.0) 140px,
    rgba(7,9,13,0.0) 780px,
    rgba(7,9,13,0.94) 930px,
    #07090d 990px,
    #07090d 1920px
  );
  box-sizing: border-box;
}}
.top-pill {{
  position: absolute;
  top: 52px;
  left: 56px;
  padding: 10px 22px;
  border-radius: 999px;
  background: rgba(12, 16, 23, 0.80);
  border: 1px solid rgba(255, 255, 255, 0.16);
  color: #f5f7fa;
  font-family: 'Inter', sans-serif;
  font-size: 22px;
  font-weight: 600;
}}
.caption-panel {{
  position: absolute;
  left: 56px;
  right: 56px;
  top: 940px;
  bottom: 64px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
}}
.cat-badge {{
  display: inline-flex;
  align-self: flex-start;
  align-items: center;
  gap: 10px;
  padding: 8px 20px;
  border-radius: 999px;
  background: rgba(255, 224, 0, 0.14);
  border: 1.5px solid {accent};
  color: {accent};
  font-family: 'JetBrains Mono', monospace;
  font-size: 19px;
  font-weight: 700;
  letter-spacing: 1.2px;
  margin-bottom: 18px;
}}
.reel-title {{
  font-family: 'Montserrat', sans-serif;
  font-weight: 800;
  font-size: 46px;
  line-height: 1.15;
  color: #ffffff;
  margin: 0 0 22px 0;
  letter-spacing: -0.5px;
}}
.reel-title .hl {{
  color: {accent};
}}
.facts-box {{
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-bottom: 22px;
}}
.fact-item {{
  display: flex;
  align-items: flex-start;
  gap: 14px;
  background: rgba(255, 255, 255, 0.05);
  border-left: 4px solid {accent};
  border-radius: 10px;
  padding: 14px 18px;
}}
.fact-dot {{
  color: {accent};
  font-size: 24px;
  line-height: 1.3;
  font-weight: 700;
}}
.fact-text {{
  font-family: 'Inter', sans-serif;
  font-weight: 400;
  font-size: 24px;
  line-height: 1.36;
  color: #e2e8f0;
}}
.fact-text strong {{
  color: #ffffff;
  font-weight: 700;
}}
.reel-footer {{
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.12);
  color: #8b95a5;
  font-family: 'Inter', sans-serif;
  font-size: 20px;
  font-weight: 500;
}}
</style></head><body>
  <div class="reel-frame">
    <div class="top-pill">{handle}</div>
    <div class="caption-panel">
      <div class="cat-badge">● {category}</div>
      <h1 class="reel-title">{title_html}</h1>
      <div class="facts-box">
        {bullets_html}
      </div>
      <div class="reel-footer">
        <span>Kaynak: {source_label}</span>
        <span>{handle}</span>
      </div>
    </div>
  </div>
</body></html>"""

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(
            viewport={"width": w916, "height": h916}, device_scale_factor=1
        )
        await page.set_content(overlay_html, wait_until="networkidle")
        await page.evaluate("document.fonts.ready")
        await page.screenshot(path=str(dest_png), type="png", omit_background=True)
        await browser.close()
    return dest_png


def _get_video_duration(video_path: Path) -> float:
    """ffprobe ile kaynak videonun gerçek süresini (saniye) döndürür."""
    if not shutil.which("ffprobe"):
        return DEFAULT_REEL_DURATION
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path.resolve()),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        val = float((proc.stdout or "").strip())
        if val > 0:
            return val
    except Exception:
        pass
    return DEFAULT_REEL_DURATION


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


def _generate_silence_audio(dest: Path, *, duration: float = 15.0, sample_rate: int = 44100) -> None:
    """Video süresince sessiz bir WAV üretir (ffmpeg için boş ses akışı)."""
    total_samples = int(duration * sample_rate)
    buf = bytearray(total_samples * 2)  # 16-bit mono, tamamen sessiz
    with wave.open(str(dest), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(buf))
