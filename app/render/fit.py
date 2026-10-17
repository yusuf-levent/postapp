"""Taşma kontrolü ve font küçültme (zorunlu kalite kontrolü).

Render ÖNCESİ Playwright ile her metin kutusunda taşma ölçülür:
scrollHeight > clientHeight veya scrollWidth > clientWidth.
Taşma varsa font boyutu kademeli küçültülür (alt limit var).
Hâlâ taşıyorsa Gemini'den metin kısaltması istenir.
Taşmış/kesik yazılı görsel ASLA yayınlanmaz.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("tekno-pusula.fit")

# Kademeli küçültme oranları
SHRINK_STEPS = [1.0, 0.92, 0.85, 0.78, 0.72, 0.66]

# Alt limitler (piksel)
MIN_COVER_TITLE_PX = 64
MIN_HEADING_PX = 32
MIN_BODY_PX = 18

MEASURE_JS = """
() => {
  const out = [];
  const nodes = document.querySelectorAll(
    '.cover-center, .inner-content, .cta-wrap, ' +
    '.cover-title, .cover-subtitle, .inner-heading, .card-title, .card-body, ' +
    '.big-stat, .stat-caption, .stat-quote, .cta-question, .cta-note, ' +
    '.cta-big, .cta-actions, .code-box, .category-label, .source-tag, .pill'
  );
  for (const el of nodes) {
    if (el.scrollHeight > el.clientHeight + 4 || el.scrollWidth > el.clientWidth + 4) {
      out.push({
        cls: el.className,
        text: (el.textContent || '').slice(0, 60),
        scrollH: el.scrollHeight,
        clientH: el.clientHeight,
        scrollW: el.scrollWidth,
        clientW: el.clientWidth
      });
    }
  }
  return out;
}
"""

SET_SCALE_JS = """
(scale) => {
  const targets = {
    'cover-title': 0, 'inner-heading': 1, 'card-title': 2,
    'card-body': 3, 'cta-question': 4
  };
  // Boyutları CSS değişkeni gibi yeniden hesapla
  document.querySelectorAll('.cover-title').forEach(e =>
    e.style.fontSize = (parseFloat(e.dataset.baseSize || getComputedStyle(e).fontSize) * scale) + 'px');
  return true;
}
"""


async def check_overflow(page: Any) -> list[dict[str, Any]]:
    """Açık sayfadaki tüm metin kutularında taşma olup olmadığını ölçer."""
    return await page.evaluate(MEASURE_JS)


async def fit_page(
    page: Any,
    *,
    min_scale: float = 0.66,
    base_sizes: dict[str, float] | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    """Taşma yoksa (True, []) döner. Font küçültme denenir; hâlâ taşma varsa
    (False, taşan_kutular) döner — çağıran taraf Gemini'den kısaltma ister.
    """
    # base font size'ları kaydet
    await page.evaluate(
        """
        () => {
          for (const el of document.querySelectorAll(
            '.cover-title, .inner-heading, .card-title, .card-body, .cta-question, .big-stat'
          )) {
            if (!el.dataset.baseSize) {
              el.dataset.baseSize = getComputedStyle(el).fontSize;
            }
          }
        }
        """
    )

    overflow = await check_overflow(page)
    if not overflow:
        return True, []

    scale = 1.0
    for step in SHRINK_STEPS[1:]:
        scale = step
        if scale < min_scale:
            break
        log.info("Taşma tespit edildi, fontlar %.0f%% küçültülüyor", scale * 100)
        await page.evaluate(
            """
            (scale) => {
              for (const el of document.querySelectorAll(
                '.cover-title, .inner-heading, .card-title, .card-body, ' +
                '.cta-question, .big-stat, .stat-caption, .stat-quote, .cta-big'
              )) {
                const base = parseFloat(el.dataset.baseSize || getComputedStyle(el).fontSize);
                el.style.fontSize = (base * scale) + 'px';
              }
            }
            """,
            scale,
        )
        overflow = await check_overflow(page)
        if not overflow:
            return True, []

    return False, overflow


def enforce_min_sizes(font_sizes: dict[str, float]) -> dict[str, float]:
    """Alt limitlerin altına inmeyi engeller."""
    mins = {
        "cover_title_px": MIN_COVER_TITLE_PX,
        "heading_px": MIN_HEADING_PX,
        "body_px": MIN_BODY_PX,
    }
    out = dict(font_sizes)
    for key, floor in mins.items():
        if key in out and out[key] < floor:
            out[key] = floor
    return out