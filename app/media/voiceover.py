"""Doğrulanmış haber içeriği için doğal Türkçe Reels/TikTok seslendirmesi (edge-tts).

Kurallar:
- Slayt kart başlıklarını ("Erişime Açıldı.", "Gerçek Zamanlı Kontrol." vb.) mekanik
  şekilde okumaz; doğrulanmış iddialardan kulakla dinlenmeye uygun akıcı, kısa (18-26s)
  bir Türkçe haber spikeri senaryosu üretir.
- Üretilen senaryodaki tüm sayısal değerlerin doğrulanmış metinde geçtiği kodla kontrol
  edilir (halüsinasyon engeli).
- Her sahne ayrı klip olarak sentezlenir ve sahne geçiş sınırları konuşmaya birebir
  senkronize edilir.
- Ağ/servis hatasında None döner; pipeline'ı asla çökertmez.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.media.video_probe import probe_video

log = logging.getLogger("tekno-pusula.voiceover")

DEFAULT_VOICE = "tr-TR-AhmetNeural"
DEFAULT_RATE = "+6%"
SCENE_PAUSE_SECONDS = 0.14
MAX_VOICEOVER_DURATION = 38.0


class ReelNarration(BaseModel):
    lines: list[str] = Field(default_factory=list)


def clean_speech_text(text: str) -> str:
    """Metni doğal Türkçe seslendirme için temizler (URL, hashtag, emoji ayıklanır)."""
    text = re.sub(r"https?://\S+", "", text or "")
    text = re.sub(r"#\w+", "", text)
    text = re.sub(r"[^\w\s.,!?;:%'\"’\-–—/()+çÇğĞıİöÖşŞüÜ]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def scene_script(scene: Any, *, index: int) -> str:
    """Fallback konuşma metni: 2-4. sahnelerde kart başlığını atlayıp yalnızca gövdeyi okur."""
    heading = clean_speech_text(getattr(scene, "heading", "") or "")
    body = clean_speech_text(getattr(scene, "body", "") or "")
    if index == 0:
        # Açılışta başlık + kısa alt metin doğal akışta
        if heading and body and body.casefold() != heading.casefold():
            h = heading if heading.endswith((".", "!", "?")) else f"{heading}."
            b = body if body.endswith((".", "!", "?")) else f"{body}."
            return f"{h} {b}".strip()
        return heading or body
    # 2, 3, 4. sahnelerde "Erişime Açıldı." gibi slayt kart başlıklarını okuma!
    chosen = body or heading
    if chosen and not chosen.endswith((".", "!", "?")):
        chosen += "."
    return chosen


def _numbers_grounded(lines: list[str], allowed_corpus: str) -> bool:
    """Konuşma metnindeki her sayının doğrulanmış kaynaklarda geçmesini zorunlu kılar."""
    corpus_low = allowed_corpus.lower()
    corpus_tokens = set(re.findall(r"%?\d[\d.,]*", corpus_low))
    for line in lines:
        for num in re.findall(r"%?\d[\d.,]*", line.lower()):
            tok = num.rstrip(".,")
            if tok and tok not in corpus_tokens and tok not in corpus_low:
                log.warning("Seslendirme senaryosunda doğrulanmamış sayı tespit edildi: %r", num)
                return False
    return True


def build_narration_lines(
    scenes: list[Any],
    *,
    llm: Any = None,
    verified_claims: list[str] | None = None,
) -> list[str]:
    """4 sahnelik doğal Türkçe Reels/TikTok spiker metni üretir (halüsinasyon kontrollü)."""
    fallback = [scene_script(s, index=i) for i, s in enumerate(scenes)]
    if llm is None or not scenes:
        return fallback

    scenes_text = "\n".join(
        f"Sahne {i + 1} ({getattr(s, 'label', '')}): Başlık='{getattr(s, 'heading', '')}' | İçerik='{getattr(s, 'body', '')}'"
        for i, s in enumerate(scenes)
    )
    claims_block = "\n".join(verified_claims or [])[:4000]
    prompt = (
        f"Aşağıdaki doğrulanmış teknoloji haberi için {len(scenes)} sahnelik, kulakla dinlenmeye uygun "
        "DOĞAL ve AKICI bir Türkçe Reels/TikTok spiker konuşma metni yaz.\n\n"
        f"--- SAHNELER ---\n{scenes_text}\n\n"
        + (f"--- DOĞRULANMIŞ KAYNAK İDDİALARI ---\n{claims_block}\n\n" if claims_block else "")
        + "KESİN KURALLAR:\n"
        f"- Tam olarak {len(scenes)} cümle üret (lines dizisinde {len(scenes)} eleman; her sahneye 1 kısa cümle).\n"
        "- ASLA slayt kart başlığı okur gibi konuşma! ('Erişime Açıldı. Genie 4...', 'Gerçek Zamanlı Kontrol. Klavye...' KESİNLİKLE YASAK).\n"
        "- Bir teknoloji içerik üreticisinin kameraya akıcı, samimi ve enerjik anlatımı gibi tek parça aksın.\n"
        "- 1. cümle: Güçlü, merak uyandıran açılış (10-14 kelime).\n"
        "- 2. ve 3. cümleler: Birbirine doğal bağlaçlarla bağlanan somut detaylar (her biri 10-15 kelime).\n"
        "- Son cümle: Kısa etki + izleyiciye doğal bir soru (10-15 kelime).\n"
        "- Toplamda 45-62 kelimeyi geçme (toplam süre 18-25 saniye olmalı).\n"
        "- YALNIZCA yukarıdaki doğrulanmış bilgilerdeki rakam, isim ve olguları kullan; yeni hiçbir sayı veya bilgi EKLEME.\n"
        "- Emoji, hashtag, URL veya madde işareti koyma."
    )
    try:
        res = llm.generate_structured(
            prompt,
            ReelNarration,
            system="Sen akıcı, abartısız ve güvenilir bir Türkçe teknoloji video spikerisin. Sadece verilen doğrulanmış olguları konuşma diline çevirirsin.",
            label="reel-narration",
        )
        lines = [clean_speech_text(x) for x in (res.lines or []) if clean_speech_text(x)]
        if len(lines) != len(scenes):
            log.warning("Seslendirme satır sayısı uyuşmadı (%d != %d), yedek metin kullanılacak.", len(lines), len(scenes))
            return fallback
        corpus = scenes_text + "\n" + claims_block
        if not _numbers_grounded(lines, corpus):
            return fallback
        return lines
    except Exception as exc:
        log.warning("Doğal seslendirme senaryosu üretilemedi, yedek metne geçiliyor: %s", exc)
        return fallback


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
    """Sahne ses kliplerini kısa doğal nefes boşluğuyla tek MP3'te birleştirir."""
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
    llm: Any = None,
    verified_claims: list[str] | None = None,
    voice: str = DEFAULT_VOICE,
    rate: str = DEFAULT_RATE,
) -> dict[str, Any] | None:
    """Storyboard sahneleri için doğal, senkron Türkçe seslendirme üretir.

    Dönüş: {"path": Path, "duration": float, "bounds": list[float], "voice": str, "lines": list[str]} veya None.
    """
    if not scenes or not shutil.which("ffmpeg"):
        return None
    scripts = build_narration_lines(scenes, llm=llm, verified_claims=verified_claims)
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
        if total_est > MAX_VOICEOVER_DURATION and rate == DEFAULT_RATE:
            for c in clips:
                c.unlink(missing_ok=True)
            clips = asyncio.run(_synthesize_clips(scripts, video_dir, voice=voice, rate="+16%"))
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
            "lines": scripts,
        }
    except Exception as exc:
        log.warning("Türkçe seslendirme üretilemedi, yedek sese geçilecek: %s", exc)
        return None
    finally:
        for clip in clips:
            clip.unlink(missing_ok=True)
