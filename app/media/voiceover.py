"""Doğrulanmış video sahneleri için Türkçe Neural seslendirme (edge-tts).

Kurallar:
- Yalnızca doğrulanmış ve QA'dan geçmiş storyboard metinlerini okur; yeni metin uydurmaz.
- Her sahne için ayrı klip üretir, sürelerini ölçer ve tam senkron sahne sınırları döndürür.
- Ağ/servis hatasında None döner; video üretimi müzikli veya sessiz devam eder.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.media.video_probe import probe_video

log = logging.getLogger("tekno-pusula.voiceover")

DEFAULT_VOICE = "tr-TR-AhmetNeural"
DEFAULT_RATE = "+10%"
SCENE_PAUSE_SECONDS = 0.25
MAX_VOICEOVER_DURATION = 28.0


def clean_speech_text(text: str) -> str:
    """Ekrandaki doğrulanmış metni doğal Türkçe okuma için temizler."""
    text = re.sub(r"https?://\S+", "", text or "")
    text = re.sub(r"#\w+", "", text)
    # Emoji ve özel sembolleri temizle, Türkçe harf/rakam/noktalamayı koru
    text = re.sub(r"[^\w\s.,!?;:%'\"’\-–—/()+çÇğĞıİöÖşŞüÜ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def scene_script(scene: Any, *, index: int) -> str:
    """Bir ReelScene için okunacak kısa, doğal cümleyi oluşturur."""
    heading = clean_speech_text(getattr(scene, "heading", "") or "")
    body = clean_speech_text(getattr(scene, "body", "") or "")
    parts = []
    if heading:
        parts.append(heading if heading.endswith((".", "!", "?")) else f"{heading}.")
    if body and body.casefold() != heading.casefold():
        parts.append(body if body.endswith((".", "!", "?")) else f"{body}.")
    return " ".join(parts).strip()


async def _synthesize_clips(
    scripts: list[str],
    out_dir: Path,
    *,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
) -> list[Path]:
    import edge_tts

    clips: list[Path] = []
    for idx, text in enumerate(scripts):
        clip = out_dir / f"vo-scene-{idx + 1}.mp3"
        comm = edge_tts.Communicate(text, voice=voice, rate=rate)
        await comm.save(str(clip))
        if not clip.exists() or clip.stat().st_size < 1000:
            raise RuntimeError(f"Boş TTS çıktısı (sahne {idx + 1})")
        clips.append(clip)
    return clips


def _concat_clips_with_pause(clips: list[Path], dest: Path, *, pause: float = SCENE_PAUSE_SECONDS) -> bool:
    """Sahne ses kliplerini aralarına kısa nefes boşluğu ekleyerek tek WAV/MP3'te birleştirir."""
    if not clips or not shutil.which("ffmpeg"):
        return False
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for clip in clips:
        cmd += ["-i", str(clip.resolve())]
    filter_parts = []
    inputs = []
    for i in range(len(clips)):
        pad = f"apad=pad_dur={pause:.2f}" if i < len(clips) - 1 else "anull"
        filter_parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,{pad}[a{i}]")
        inputs.append(f"[a{i}]")
    filter_parts.append(f"{''.join(inputs)}concat=n={len(clips)}:v=0:a=1[out]")
    cmd += [
        "-filter_complex", ";".join(filter_parts),
        "-map", "[out]",
        "-c:a", "libmp3lame", "-ar", "48000", "-b:a", "192k",
        str(dest.resolve()),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return proc.returncode == 0 and dest.exists() and dest.stat().st_size > 2000


def synthesize_storyboard_voiceover(
    scenes: list[Any],
    video_dir: Path,
    *,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
) -> dict[str, Any] | None:
    """Storyboard sahneleri için senkron Türkçe seslendirme üretir.

    Dönüş: {"path": Path, "duration": float, "bounds": list[float], "voice": str} veya None.
    """
    if not scenes or not shutil.which("ffmpeg"):
        return None
    scripts = [scene_script(s, index=i) for i, s in enumerate(scenes)]
    if any(not s for s in scripts):
        return None

    video_dir.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    try:
        clips = asyncio.run(_synthesize_clips(scripts, video_dir, voice=voice, rate=rate))
        durations: list[float] = []
        for clip in clips:
            dur = float(probe_video(clip).get("duration") or 0.0)
            if dur <= 0.3:
                raise RuntimeError("TTS klip süresi ölçülemedi")
            durations.append(dur)

        total_est = sum(durations) + SCENE_PAUSE_SECONDS * max(0, len(durations) - 1)
        # 28 saniyeyi çok aşıyorsa biraz daha seri okut
        if total_est > MAX_VOICEOVER_DURATION and rate == DEFAULT_RATE:
            for c in clips:
                c.unlink(missing_ok=True)
            clips = asyncio.run(_synthesize_clips(scripts, video_dir, voice=voice, rate="+20%"))
            durations = [float(probe_video(c).get("duration") or 0.0) for c in clips]
            if any(d <= 0.3 for d in durations):
                raise RuntimeError("Hızlı TTS klip süresi ölçülemedi")

        dest = video_dir / "voiceover.mp3"
        if not _concat_clips_with_pause(clips, dest):
            return None

        measured_total = float(probe_video(dest).get("duration") or 0.0)
        if measured_total < 4.0:
            dest.unlink(missing_ok=True)
            return None

        bounds = [0.0]
        cursor = 0.0
        for idx, dur in enumerate(durations):
            cursor += dur + (SCENE_PAUSE_SECONDS if idx < len(durations) - 1 else 0.0)
            bounds.append(round(cursor, 3))
        bounds[-1] = round(max(measured_total, bounds[-1]), 3)

        log.info("Türkçe seslendirme hazır (%s): %.1fs, %d sahne", voice, bounds[-1], len(scenes))
        return {
            "path": dest,
            "duration": bounds[-1],
            "bounds": bounds,
            "voice": voice,
        }
    except Exception as exc:
        log.warning("Türkçe seslendirme üretilemedi, sessiz/müzikli devam edilecek: %s", exc)
        return None
    finally:
        for clip in clips:
            clip.unlink(missing_ok=True)
