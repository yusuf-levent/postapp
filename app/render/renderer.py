"""HTML şablonları → PNG render (Playwright/Chromium).

Boyutlar: 1080×1350 (4:5) + TikTok için 1080×1920 (9:16) varyantı.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from app.config import brand_config
from app.render import fit as fit_mod
from app.render.turkish import tr_upper

log = logging.getLogger("tekno-pusula.renderer")

TEMPLATE_DIR = Path(__file__).parent / "templates"


class RenderError(RuntimeError):
    pass


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env


def _file_to_data_uri(path_or_url: str, default_mime: str = "image/png") -> str:
    """file:/// veya yerel dosya yolunu base64 data URI'ye çevirir (Playwright file:// kısıtını aşar)."""
    import base64
    from urllib.parse import unquote

    if not path_or_url:
        return ""
    if path_or_url.startswith("data:") or path_or_url.startswith("http"):
        return path_or_url
    raw = path_or_url
    if raw.startswith("file:///"):
        raw = unquote(raw[len("file:///") :])
    elif raw.startswith("file://"):
        raw = unquote(raw[len("file://") :])
    p = Path(raw)
    if not p.is_file():
        return path_or_url
    ext = p.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
        ".ttf": "font/ttf",
    }.get(ext, default_mime)
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _highlight_title(title: str, words: list[str], color: str) -> str:
    """Başlıktaki vurgulanacak kelimeleri renkli span ile sarar (sarı + cyan dönüşümlü)."""
    from markupsafe import Markup, escape

    html = str(escape(tr_upper(title)))
    primary = "hl-yellow" if color == "yellow" else "hl-cyan"
    secondary = "hl-cyan" if primary == "hl-yellow" else "hl-yellow"
    for idx, word in enumerate(words):
        w = str(escape(tr_upper(word)))
        if not w:
            continue
        cls = primary if idx % 2 == 0 else secondary
        html = html.replace(w, f'<span class="{cls}">{w}</span>', 1)
    return Markup(html)


def _highlight_heading(heading: str) -> str:
    """İç slayt başlıklarında ilk anlamlı kelimeleri sarı ve cyan ile vurgular."""
    from markupsafe import Markup, escape

    parts = [p for p in tr_upper(heading).strip().split() if p]
    if not parts:
        return Markup("")
    out: list[str] = []
    for i, word in enumerate(parts):
        esc = str(escape(word))
        if i == 0:
            out.append(f'<span class="hl-yellow">{esc}</span>')
        elif i == 1 and len(parts) >= 3:
            out.append(f'<span class="hl-cyan">{esc}</span>')
        else:
            out.append(esc)
    return Markup(" ".join(out))


_FONT_DATA_CACHE: dict[str, str] = {}


def _font_data_uri(filename: str, fonts_dir: Path | None = None) -> str:
    from app.render.fonts import ASSETS_FONTS

    base = fonts_dir or ASSETS_FONTS
    target = base / filename
    key = str(target)
    if key not in _FONT_DATA_CACHE:
        if target.is_file():
            _FONT_DATA_CACHE[key] = _file_to_data_uri(str(target), "font/ttf")
        else:
            _FONT_DATA_CACHE[key] = f"file:///{str(target).replace(chr(92), '/')}"
    return _FONT_DATA_CACHE[key]


def _css(fonts_dir: Path | None = None) -> str:
    from app.render.templates.styles import CSS

    brand = brand_config()
    from jinja2 import Template

    return Template(CSS).render(
        font_bebas=_font_data_uri("BebasNeue-Regular.ttf", fonts_dir),
        font_montserrat=_font_data_uri("Montserrat-ExtraBold.ttf", fonts_dir),
        font_inter=_font_data_uri("Inter-Regular.ttf", fonts_dir),
        width=brand["canvas"]["width"],
        height=brand["canvas"]["height"],
        cover_title_px=96,
        heading_px=52,
        stat_px=126,
    )


def build_html(
    template_name: str, context: dict[str, Any], *, css: str | None = None
) -> str:
    env = _env()
    tmpl = env.get_template(template_name)
    ctx = {"css": css or _css(), **context}
    return tmpl.render(**ctx)


def render_slide_html(deck: dict[str, Any], page_index: int) -> str:
    """Slayt numarasına göre uygun şablonu seçip tam HTML belgesi üretir.

    <html lang="tr"> kullanılır (Türkçe büyük harf davranışı için zorunlu).
    """
    brand = brand_config()
    handle = brand["handle"]
    dots = brand["progress_dots"]
    bg_raw = deck.get("bg_image", "")
    bg_uri = _file_to_data_uri(bg_raw) if bg_raw else ""
    base_ctx = {
        "handle": handle,
        "progress_dots": dots,
        "page_index": page_index,
        "page_total": brand["slide_count"],
        "bg_image": bg_uri,
    }

    if page_index == 1:
        cover = deck["cover"]
        fragment = build_html(
            "cover.html",
            {
                **base_ctx,
                "source_tags": [tr_upper(t) for t in cover["source_tags"]],
                "logo_svg": deck.get("logo_svg", ""),
                "category_label": tr_upper(cover["category_label"]),
                "title_html": _highlight_title(
                    cover["title"],
                    cover.get("highlight_words", []),
                    cover.get("highlight_color", "yellow"),
                ),
                "subtitle": tr_upper(cover["subtitle"]),
            },
        )
    elif page_index == 3:
        stat = deck["stat"]
        fragment = build_html(
            "stat.html",
            {
                **base_ctx,
                "accent": "yellow",
                "tag_label": tr_upper(deck.get("tag_label_3", "ÖNE ÇIKAN RAKAM")),
                "big_stat": stat["big_stat"],
                "stat_caption": tr_upper(stat["stat_caption"]),
                "stat_quote": stat["stat_quote"],
            },
        )
    elif page_index == 6:
        cta = deck["cta"]
        fragment = build_html(
            "cta.html",
            {
                **base_ctx,
                "accent": "cyan",
                "tag_label": tr_upper(deck.get("tag_label_6", "ETKİLEŞİM")),
                "question": cta["question"],
                "reminder_line": cta.get(
                    "reminder_line", "Düşüncelerini yorumlarda paylaşmayı unutma! 💬"
                ),
            },
        )
    else:
        # İç slaytlar: 2 = context, 4 = details, 5 = impact
        section_key = {2: "context", 4: "details", 5: "impact"}[page_index]
        accent = "cyan" if page_index in (2, 4) else "yellow"
        section = deck[section_key]
        cards = []
        for i, card in enumerate(section["cards"], start=1):
            cards.append(
                {
                    "badge": f"{i:02d}",
                    "title": card["card_title"],
                    "body": card["card_body"],
                }
            )
        raw_heading = section["heading"]
        fragment = build_html(
            "content.html",
            {
                **base_ctx,
                "accent": accent,
                "tag_label": tr_upper(deck.get(f"tag_label_{page_index}", "")),
                "heading": tr_upper(raw_heading),
                "heading_html": _highlight_heading(raw_heading),
                "cards": cards,
            },
        )

    # Tam belge sarmalayıcı: <html lang="tr"> zorunlu
    css_text = _css()
    return (
        "<!DOCTYPE html>\n"
        '<html lang="tr">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<style>\n{css_text}\n</style>\n"
        "</head>\n"
        f"<body>\n{fragment}\n</body>\n"
        "</html>"
    )


async def render_png(
    html: str,
    dest: Path,
    *,
    width: int = 1080,
    height: int = 1350,
    fonts_dir: Path | None = None,
    shorten_cb: Any = None,
) -> bool:
    """HTML'i PNG'ye çevirir. Taşma varsa font küçültür, olmazsa shorten_cb çağırır.

    shorten_cb(html, overflow) -> str  (yeniden render için yeni HTML)
    """
    from playwright.async_api import async_playwright

    dest.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(
            viewport={"width": width, "height": height}, device_scale_factor=1
        )
        await page.set_content(html, wait_until="networkidle")
        await page.evaluate("document.fonts.ready")

        # Taşma kontrolü + font küçültme
        ok, overflow = await fit_mod.fit_page(page)
        if not ok and shorten_cb is not None:
            log.warning("Taşma devam ediyor, metin kısaltılıyor: %s", overflow)
            new_html = shorten_cb(html, overflow)
            await page.set_content(new_html, wait_until="networkidle")
            await page.evaluate("document.fonts.ready")
            ok, overflow = await fit_mod.fit_page(page)
            if not ok:
                raise RenderError(
                    f"Taşma giderilemedi ({len(overflow)} kutu): {overflow[:3]}"
                )
        elif not ok:
            raise RenderError(f"Taşma giderilemedi: {overflow[:3]}")

        await page.screenshot(path=str(dest), type="png")
        await browser.close()
    return True


def render_deck(
    deck: dict[str, Any],
    out_dir: Path,
    *,
    fonts_dir: Path | None = None,
    with_9x16: bool = True,
) -> dict[str, list[Path]]:
    """6 slaytı hem 4:5 hem 9:16 olarak render eder.

    9:16 varyantı: aynı içerik dikeyde ortalanır, üst/alt boşluklar arka plan
    görseliyle doldurulur (koyu gradient).
    """
    import asyncio

    results: dict[str, list[Path]] = {"slides": [], "slides_9x16": []}
    slides_dir = out_dir / "slides"
    slides_dir.mkdir(parents=True, exist_ok=True)

    brand = brand_config()
    w45 = brand["canvas"]["width"]
    h45 = brand["canvas"]["height"]
    w916 = brand["canvas"]["width_9x16"]
    h916 = brand["canvas"]["height_9x16"]

    async def _render_all() -> None:
        for i in range(1, 7):
            html = render_slide_html(deck, i)
            dest = slides_dir / f"slide-{i}.png"
            await render_png(
                html, dest, width=w45, height=h45, fonts_dir=fonts_dir
            )
            results["slides"].append(dest)

            if with_9x16:
                # 9:16: 4:5 içeriği dikeyde ortala, üst/alt siyah dolgu
                dest916_dir = out_dir / "slides_9x16"
                dest916_dir.mkdir(parents=True, exist_ok=True)
                dest916 = dest916_dir / f"slide-{i}.png"
                await render_png_9x16(
                    html, dest916, w45, h45, w916, h916, fonts_dir=fonts_dir
                )
                results["slides_9x16"].append(dest916)

    asyncio.run(_render_all())
    return results


async def render_png_9x16(
    html: str,
    dest: Path,
    w45: int,
    h45: int,
    w916: int,
    h916: int,
    *,
    fonts_dir: Path | None = None,
) -> bool:
    """4:5 içeriği 1080×1920 tuvalde dikeyde ortalar, üst/alt dolgu yapar."""
    import re

    from playwright.async_api import async_playwright

    dest.parent.mkdir(parents=True, exist_ok=True)
    font_base = (
        f"file:///{str(fonts_dir).replace(chr(92), '/')}"
        if fonts_dir
        else "file:///assets/fonts"
    )
    html = html.replace("file:///assets/fonts", font_base)

    # Tam belgeden stili ve gövdeyi ayır (iç içe <html> olmasın)
    styles = "\n".join(re.findall(r"<style>(.*?)</style>", html, re.DOTALL))
    m = re.search(r"<body>(.*)</body>", html, re.DOTALL)
    body = m.group(1) if m else html

    wrapper = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><style>
  html,body {{ margin:0; padding:0; width:{w916}px; height:{h916}px; background:#07090d; overflow:hidden; }}
  .stage {{ position:relative; width:{w916}px; height:{h916}px; overflow:hidden; background:#07090d; }}
  .stage .content {{
    position:absolute; top:{(h916 - h45) // 2}px; left:{(w916 - w45) // 2}px;
    width:{w45}px; height:{h45}px; overflow:hidden;
    box-shadow: 0 0 120px rgba(0,0,0,0.8);
  }}
{styles}
</style></head><body>
  <div class="stage">
    <div class="content">{body}</div>
  </div>
</body></html>"""

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(
            viewport={"width": w916, "height": h916}, device_scale_factor=1
        )
        await page.set_content(wrapper, wait_until="networkidle")
        await page.evaluate("document.fonts.ready")
        await page.screenshot(path=str(dest), type="png")
        await browser.close()
    return True