"""Google Fonts indirme: fontlar repoya assets/fonts altına kaydedilir.

Fontlar GitHub Actions'ta her çalıştırmada tekrar indirilmez; repoda tutulur.
Bu betik repo kurulumunda bir kez çalıştırılır (veya CI cache'inden gelir).
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.common import http_get

log = logging.getLogger("tekno-pusula.fonts")

ASSETS_FONTS = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"

# Google Fonts API CSS → gerçek TTF URL'leri
FONT_SOURCES = {
    "BebasNeue-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf",
    "Montserrat-Bold.ttf": "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf",
    "Montserrat-ExtraBold.ttf": "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf",
    "Montserrat-Black.ttf": "https://github.com/google/fonts/raw/main/ofl/montserrat/Montserrat%5Bwght%5D.ttf",
    "Inter-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf",
    "Inter-SemiBold.ttf": "https://github.com/google/fonts/raw/main/ofl/inter/Inter%5Bopsz%2Cwght%5D.ttf",
}


def ensure_fonts(target_dir: Path | None = None, *, force: bool = False) -> Path:
    """Fontları indirir (varsa atlar). Font dizinini döndürür."""
    target = target_dir or ASSETS_FONTS
    target.mkdir(parents=True, exist_ok=True)

    for filename, url in FONT_SOURCES.items():
        dest = target / filename
        if dest.exists() and not force and dest.stat().st_size > 10000:
            continue
        log.info("Font indiriliyor: %s", filename)
        resp = http_get(url, retries=3, timeout=60)
        if resp is None or resp.status_code != 200:
            log.warning("Font indirilemedi: %s", filename)
            continue
        dest.write_bytes(resp.content)

    return target


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = ensure_fonts(force=True)
    print(f"Fontlar hazır: {path}")