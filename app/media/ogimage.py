"""Kaynak makalenin og:image görselini çekme."""
from __future__ import annotations

import logging
import re

from app.common import http_get
from app.config import settings
from app.models import ImageCandidate

log = logging.getLogger("tekno-pusula.ogimage")


def og_image(article_url: str, *, min_width: int = 1000) -> ImageCandidate | None:
    """Makale sayfasından og:image URL'sini çıkarır.

    Resmi şirket basın görseli sayılır; lisans/kaynak makale olarak yazılır.
    """
    resp = http_get(article_url)
    if resp is None or resp.status_code != 200:
        return None
    html = resp.text
    m = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            html,
            re.IGNORECASE,
        )
    if not m:
        return None
    image_url = m.group(1).strip()
    if image_url.startswith("//"):
        image_url = "https:" + image_url

    # Genişlik meta'sı varsa kontrol et
    width = 0
    wm = re.search(
        r'<meta[^>]+property=["\']og:image:width["\'][^>]+content=["\'](\d+)["\']',
        html,
        re.IGNORECASE,
    )
    if wm:
        width = int(wm.group(1))
        if width < min_width:
            log.debug("og:image çok dar: %s px", width)
            return None

    return ImageCandidate(
        source="ogimage",
        url=image_url,
        width=width,
        license="Kaynak makale görseli",
        author="",
        credit_url=article_url,
        alt_text="",
    )


def download_image(url: str, dest_path: str) -> tuple[bool, int, int]:
    """Görseli indirir. Dönüş: (başarılı, genişlik, yükseklik)."""
    resp = http_get(url, retries=2)
    if resp is None or resp.status_code != 200:
        return False, 0, 0
    from pathlib import Path

    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(dest_path).write_bytes(resp.content)
    try:
        from PIL import Image

        with Image.open(dest_path) as img:
            return True, img.width, img.height
    except Exception:
        return False, 0, 0