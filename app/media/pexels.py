"""Pexels API — genel/temsili görseller (ücretsiz)."""
from __future__ import annotations

import logging

from app.common import http_get
from app.config import settings
from app.models import ImageCandidate

log = logging.getLogger("tekno-pusula.pexels")

PEXELS_URL = "https://api.pexels.com/v1/search"


def search_images(
    query: str,
    *,
    min_width: int = 1000,
    per_page: int = 5,
    orientation: str = "portrait",
) -> list[ImageCandidate]:
    """Pexels'ta görsel arar; minimum genişlik altındakileri eler."""
    api_key = settings().pexels_api_key
    if not api_key:
        log.warning("PEXELS_API_KEY tanımlı değil, Pexels atlanıyor")
        return []
    from urllib.parse import urlencode

    params = {
        "query": query,
        "per_page": per_page,
        "orientation": orientation,
    }
    resp = http_get(
        f"{PEXELS_URL}?{urlencode(params)}",
        headers={"Authorization": api_key},
        retries=2,
    )
    if resp is None or resp.status_code != 200:
        log.warning("Pexels araması başarısız: %s", resp.status_code if resp else "none")
        return []
    try:
        photos = resp.json().get("photos", [])
    except ValueError:
        return []

    out: list[ImageCandidate] = []
    for photo in photos:
        width = photo.get("width", 0)
        if width < min_width:
            continue
        out.append(
            ImageCandidate(
                source="pexels",
                url=photo.get("src", {}).get("large2x")
                or photo.get("src", {}).get("large", ""),
                width=width,
                height=photo.get("height", 0),
                license=f"Pexels License — {photo.get('photographer', '')}",
                author=photo.get("photographer", ""),
                credit_url=photo.get("url", ""),
                alt_text=photo.get("alt", "") or query,
            )
        )
    return out