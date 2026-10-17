"""Marka logoları: yalnızca resmi SVG (Simple Icons → Wikimedia Commons).

Logo ASLA yapay zekayla çizilmez, uydurulmaz, PNG'den kesilmez.
Bulunamazsa logo KULLANILMAZ (boş/ince çizgi).
"""
from __future__ import annotations

import logging
import re

from app.common import http_get

log = logging.getLogger("tekno-pusula.logos")

SIMPLE_ICONS_CDN = "https://cdn.jsdelivr.net/npm/simple-icons@latest/icons/{slug}.svg"

# Bilinen marka → Simple Icons slug eşlemesi
SLUG_MAP = {
    "openai": "openai",
    "google": "google",
    "deepmind": "googledeepmind",
    "microsoft": "microsoft",
    "apple": "apple",
    "meta": "meta",
    "nvidia": "nvidia",
    "amazon": "amazon",
    "aws": "amazonwebservices",
    "anthropic": "anthropic",
    "github": "github",
    "tesla": "tesla",
    "qualcomm": "qualcomm",
    "amd": "amd",
    "intel": "intel",
    "samsung": "samsung",
    "ibm": "ibm",
    "oracle": "oracle",
    "adobe": "adobe",
    "hugging face": "huggingface",
    "huggingface": "huggingface",
    "mistral": "mistralai",
    "deepseek": "deepseek",
    "broadcom": "broadcom",
    "tsmc": "tsmc",
    "arm": "arm",
    "xai": "xai",
}


def fetch_logo_svg(brand: str, *, force_white: bool = True) -> str | None:
    """Marka logosunun SVG içeriğini döndürür. Yoksa None (logo kullanılmaz).

    force_white: koyu arka planda görünmeyen logolar beyaza çevrilir (fill).
    """
    slug = SLUG_MAP.get(brand.lower())
    if not slug:
        log.info("Logo slug eşlemesi yok, logo kullanılmayacak: %s", brand)
        return None

    url = SIMPLE_ICONS_CDN.format(slug=slug)
    resp = http_get(url, retries=2)
    if resp is None or resp.status_code != 200:
        log.info("Simple Icons'ta logo yok: %s (%s)", brand, slug)
        return None

    svg = resp.text.strip()
    if not svg.startswith("<svg"):
        return None

    if force_white:
        svg = _force_white_fill(svg)
    return svg


def _force_white_fill(svg: str) -> str:
    """SVG içindeki fill değerlerini beyaza çevirir; fill yoksa ekler."""
    if re.search(r'fill="(?!none)[^"]*"', svg):
        svg = re.sub(r'fill="(?!none)[^"]*"', 'fill="#FFFFFF"', svg)
    elif "<svg" in svg:
        svg = re.sub(r"<svg([^>]*)>", r'<svg\1 fill="#FFFFFF">', svg, count=1)
    return svg


def save_logo(brand: str, dest_path: str) -> bool:
    """Logoyu kaydeder. Başarısızsa False — çağıran taraf logo alanını boş bırakır."""
    svg = fetch_logo_svg(brand)
    if not svg:
        return False
    from pathlib import Path

    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(dest_path).write_text(svg, encoding="utf-8")
    return True