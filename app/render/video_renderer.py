"""Real footage with timed, readable news captions for Reels and TikTok."""
from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.config import brand_config
from app.media.video_probe import probe_video

log = logging.getLogger("tekno-pusula.video_renderer")
MIN_REEL_DURATION = 8.0
MAX_REEL_DURATION = 22.0


@dataclass
class ReelScene:
    label: str
    heading: str
    body: str


def build_storyboard(deck: dict[str, Any]) -> list[ReelScene]:
    """Reuse verified slide copy; no new claims or extra LLM calls."""
    cover = deck.get("cover") or {}
    scenes = [ReelScene("NE OLDU?", str(cover.get("title") or ""),
                        str(cover.get("subtitle") or ""))]
    for key, label in (("context", "BİLMEN GEREKEN"), ("details", "DETAY"), ("impact", "NEDEN ÖNEMLİ?")):
        cards = (deck.get(key) or {}).get("cards") or []
        for card in cards:
            # The real schema is card_title/card_body. Reading title/body
            # silently dropped almost all facts in the previous renderer.
            heading = str(card.get("card_title") or card.get("title") or "").strip()
            body = str(card.get("card_body") or card.get("body") or "").strip()
            if body:
                scenes.append(ReelScene(label, heading, body))
                break
    return scenes[:4]


def overlay_html(scene: ReelScene, *, index: int, total: int, sources: list[str], fonts_dir: Path | None,
                 illustrative: bool = False) -> str:
    font_css = ""
    if fonts_dir:
        for family, name in (("Inter", "Inter-Regular.ttf"), ("Montserrat", "Montserrat-Bold.ttf")):
            font = fonts_dir / name
            if font.exists():
                encoded = base64.b64encode(font.read_bytes()).decode()
                font_css += f"@font-face{{font-family:'{family}';src:url(data:font/ttf;base64,{encoded})}}"
    handle = html.escape(brand_config().get("handle", "@tekno_pusula"))
    source = html.escape(" · ".join(sources[:2]) or "Tekno Pusula")
    return f"""<!DOCTYPE html><html lang="tr"><meta charset="utf-8"><style>
{font_css}
*{{box-sizing:border-box}}html,body{{width:1080px;height:1920px;margin:0;background:transparent}}
body{{font-family:Inter,sans-serif;color:#fff}}
.shade{{position:absolute;inset:0;background:linear-gradient(transparent 58%,rgba(7,9,13,.86) 67%,#07090d 80%)}}
.brand{{position:absolute;top:160px;left:64px;font-size:27px;background:#07090dcc;padding:15px 22px;border-radius:12px}}
.footage{{position:absolute;top:176px;right:180px;font-size:20px;color:#d9e0e7;background:#07090dcc;padding:8px 12px;border-radius:8px}}
.footage:empty{{display:none}}
.panel{{position:absolute;left:64px;right:180px;top:1250px;height:360px;display:flex;flex-direction:column}}
.label{{color:#ffe000;font-size:20px;letter-spacing:2px;margin-bottom:14px}}
h1{{font-family:Montserrat,Inter,sans-serif;font-size:{54 if index == 0 else 44}px;line-height:1.14;margin:0 0 16px;overflow-wrap:anywhere}}
.body{{font-size:32px;line-height:1.32;margin:0;overflow-wrap:anywhere}}
.footer{{position:absolute;top:1630px;left:64px;right:180px;color:#a9b4c2;font-size:21px;display:flex;justify-content:space-between;gap:20px}}
.source{{max-width:690px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.progress{{position:absolute;left:64px;right:180px;top:1690px;height:5px;background:#ffffff28}}
.progress span{{display:block;height:100%;background:#ffe000;width:{100 * (index + 1) / total}%}}
</style><body><div class="shade"></div><div class="brand">{handle}</div>
<div class="footage">{'Temsili görüntü' if illustrative else ''}</div>
<section class="panel"><div class="label">{html.escape(scene.label)}</div>
<h1>{html.escape(scene.heading)}</h1><p class="body">{html.escape(scene.body)}</p></section>
<div class="footer"><span class="source">Kaynak: {source}</span><span>{index + 1:02d} / {total:02d}</span></div>
<div class="progress"><span></span></div></body></html>"""


async def _render_overlays(scenes: list[ReelScene], video_dir: Path, sources: list[str], fonts_dir: Path | None,
                           *, illustrative: bool = False) -> list[Path]:
    from playwright.async_api import async_playwright

    outputs = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
        for index, scene in enumerate(scenes):
            await page.set_content(overlay_html(scene, index=index, total=len(scenes), sources=sources,
                                               fonts_dir=fonts_dir, illustrative=illustrative))
            await page.evaluate("document.fonts.ready")
            fits = await page.evaluate("""() => {
              const panel = document.querySelector('.panel');
              for (let i=0; i<20 && panel.scrollHeight>panel.clientHeight; i++) {
                for (const el of panel.querySelectorAll('h1,.body')) {
                  const size=parseFloat(getComputedStyle(el).fontSize);
                  if(size<=28) return false;
                  el.style.fontSize=(size-2)+'px';
                }
              }
              return panel.scrollHeight<=panel.clientHeight;
            }""")
            if not fits:
                raise ValueError("Video metni güvenli alana sığmıyor.")
            dest = video_dir / f"overlay-{index + 1}.png"
            await page.screenshot(path=str(dest), omit_background=True)
            outputs.append(dest)
        await browser.close()
    return outputs


def render_reel_video(
    deck: dict[str, Any],
    source_video: Path,
    post_dir: Path,
    *,
    fonts_dir: Path | None = None,
    music_info: dict[str, Any] | None = None,
) -> Path | None:
    if not source_video or not source_video.exists() or not shutil.which("ffmpeg"):
        return None
    info = probe_video(source_video)
    src_duration = float(info.get("duration") or 0)
    if src_duration < MIN_REEL_DURATION:
        log.info("Video çok kısa veya çözümlenemedi; karusel kullanılacak.")
        return None
    scenes = build_storyboard(deck)
    if len(scenes) < 3 or not scenes[0].heading:
        log.info("Video için yeterli doğrulanmış bilgi yok; karusel kullanılacak.")
        return None

    illustrative = bool(deck.get("video_illustrative"))
    has_orig_audio = bool(info.get("has_audio")) and not illustrative

    music = Path(music_info["path"]) if music_info and music_info.get("path") else None
    if not (music and music.exists()) or has_orig_audio:
        music = None

    # Reels/TikTok için ideal 14-22 saniyelik dinamik tempo
    duration = min(MAX_REEL_DURATION, src_duration)
    hook = min(3.5, duration / len(scenes))
    scene_duration = (duration - hook) / (len(scenes) - 1)
    bounds = [0.0, hook] + [hook + scene_duration * n for n in range(1, len(scenes))]

    video_dir = post_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    overlays = asyncio.run(_render_overlays(
        scenes, video_dir, deck.get("source_names") or [], fonts_dir, illustrative=illustrative,
    ))

    cmd = ["ffmpeg", "-y", "-filter_complex_threads", "2", "-i", str(source_video.resolve())]
    for overlay in overlays:
        cmd += ["-loop", "1", "-i", str(overlay.resolve())]

    music_idx: int | None = None
    if music is not None:
        # Şarkı uzunsa yavaş intro yerine ritmin oturduğu 10. saniyeden başla
        music_dur = float((music_info or {}).get("duration") or 0)
        if not music_dur:
            music_dur = float(probe_video(music).get("duration") or 0)
        start_offset = 10.0 if music_dur > duration + 15.0 else 0.0
        cmd += ["-stream_loop", "-1"]
        if start_offset > 0:
            cmd += ["-ss", f"{start_offset:.1f}"]
        cmd += ["-i", str(music.resolve())]
        music_idx = len(overlays) + 1

    src_w, src_h = int(info.get("width") or 0), int(info.get("height") or 0)
    if src_h > src_w > 0:
        # Dikey (portrait) HD kaynak: tam ekran 1080x1920 keskin görüntü
        filters = [
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[base]",
        ]
    else:
        # Yatay (landscape) HD kaynak: bulanık arka plan + büyük keskin orta çerçeve
        filters = [
            "[0:v]split=2[bgsrc][fgsrc]",
            "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:2,eq=brightness=-0.4[bg]",
            "[fgsrc]scale=1320:1180:force_original_aspect_ratio=decrease,crop=w='min(iw,1080)':h=ih[fg]",
            "[bg][fg]overlay=x=(W-w)/2:y=150+(1180-h)/2[base]",
        ]

    current = "base"
    for i in range(len(overlays)):
        output = f"scene{i}"
        filters.append(f"[{current}][{i+1}:v]overlay=0:0:enable='gte(t,{bounds[i]:.3f})*lt(t,{bounds[i+1]:.3f})'[{output}]")
        current = output

    fade_start = max(0.0, duration - 1.2)
    has_final_audio = False
    if has_orig_audio:
        filters.append(f"[0:a]loudnorm=I=-15:TP=-1.5:LRA=11,afade=t=out:st={fade_start:.2f}:d=1.2[aout]")
        has_final_audio = True
    elif music_idx is not None:
        filters.append(
            f"[{music_idx}:a]silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.1,"
            f"loudnorm=I=-15:TP=-1.5:LRA=10,afade=t=in:st=0:d=0.5,afade=t=out:st={fade_start:.2f}:d=1.2[aout]"
        )
        has_final_audio = True

    out = video_dir / "reel.mp4"
    cmd += ["-filter_complex", ";".join(filters), "-map", f"[{current}]", "-t", f"{duration:.3f}",
            "-r", "30", "-c:v", "libx264", "-threads", "2", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p"]
    if has_final_audio:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-ar", "48000", "-b:a", "160k"]
    cmd += ["-movflags", "+faststart", str(out.resolve())]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0 or not out.exists():
        log.warning("Video render başarısız: %s", proc.stderr[-800:])
        out.unlink(missing_ok=True)
        return None
    rendered = probe_video(out)
    if (rendered.get("width"), rendered.get("height")) != (1080, 1920) or rendered.get("duration", 0) < 7.8:
        out.unlink(missing_ok=True)
        return None
    (video_dir / "storyboard.json").write_text(json.dumps({
        "duration": duration, "scenes": [asdict(s) for s in scenes],
        "bounds": bounds, "probe": rendered,
        "music": bool(music_idx is not None),
        "orig_audio": bool(has_orig_audio),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    source_video.unlink(missing_ok=True)
    if music is not None:
        music.unlink(missing_ok=True)
    return out
