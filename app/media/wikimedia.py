"""Wikimedia Commons / Wikipedia API — gerçek kişilerin fotoğrafları."""
from __future__ import annotations

import logging
import urllib.parse

from app.common import http_get
from app.models import ImageCandidate

log = logging.getLogger("tekno-pusula.wikimedia")

WIKI_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

HEADERS = {"User-Agent": "TeknoPusula/1.0 (news-verification bot)"}


def person_image(person_name: str) -> ImageCandidate | None:
    """Kişinin Wikipedia sayfasındaki ana görseli döndürür.

    Lisans ve yazar bilgisi credit alanlarına yazılır (credits.json'a kaydedilir).
    """
    # 1. Wikipedia sayfa görseli (pageimages)
    params = {
        "action": "query",
        "format": "json",
        "prop": "pageimages|pageterms",
        "piprop": "original",
        "titles": person_name,
        "redirects": "1",
    }
    resp = http_get(
        WIKI_API + "?" + urllib.parse.urlencode(params), headers=HEADERS
    )
    if resp is None or resp.status_code != 200:
        return None
    data = resp.json()
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        original = page.get("original", {})
        source_url = original.get("source", "")
        if not source_url:
            continue
        width = original.get("width", 0)
        if width and width < 1000:
            log.debug("Wikipedia görseli çok küçük: %s (%s px)", person_name, width)
            continue
        # Lisans bilgisi Commons'tan çekilmeye çalışılır (best-effort)
        license_info = _commons_license(source_url)
        return ImageCandidate(
            source="wikimedia",
            url=source_url,
            width=original.get("width", 0),
            height=original.get("height", 0),
            license=license_info.get("license", "Wikipedia/Commons"),
            author=license_info.get("author", ""),
            credit_url=f"https://en.wikipedia.org/wiki/{urllib.parse.quote(person_name)}",
            alt_text=person_name,
        )
    return None


def _commons_license(file_url: str) -> dict[str, str]:
    """Dosya adından Commons lisans bilgisini çeker (best-effort)."""
    filename = file_url.rsplit("/", 1)[-1]
    params = {
        "action": "query",
        "format": "json",
        "prop": "imageinfo",
        "iiprop": "extmetadata",
        "titles": f"File:{urllib.parse.unquote(filename)}",
    }
    resp = http_get(COMMONS_API + "?" + urllib.parse.urlencode(params), headers=HEADERS)
    if resp is None or resp.status_code != 200:
        return {}
    try:
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            meta = page.get("imageinfo", [{}])[0].get("extmetadata", {})
            license_short = meta.get("LicenseShortName", {}).get("value", "")
            artist = meta.get("Artist", {}).get("value", "")
            # HTML temizle
            import re

            artist = re.sub(r"<[^>]+>", "", artist).strip()
            return {"license": license_short, "author": artist}
    except (KeyError, IndexError, ValueError):
        pass
    return {}


def search_commons(query: str, *, min_width: int = 1000) -> ImageCandidate | None:
    """Commons'ta genel görsel araması (yedek kaynak)."""
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrlimit": "5",
        "gsrnamespace": "6",
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
    }
    resp = http_get(COMMONS_API + "?" + urllib.parse.urlencode(params), headers=HEADERS)
    if resp is None or resp.status_code != 200:
        return None
    try:
        pages = resp.json().get("query", {}).get("pages", {})
    except ValueError:
        return None
    for page in pages.values():
        info = page.get("imageinfo", [{}])[0]
        width = info.get("width", 0)
        if width < min_width:
            continue
        meta = info.get("extmetadata", {})
        license_short = meta.get("LicenseShortName", {}).get("value", "")
        artist = meta.get("Artist", {}).get("value", "")
        import re

        artist = re.sub(r"<[^>]+>", "", artist).strip()
        return ImageCandidate(
            source="wikimedia",
            url=info.get("url", ""),
            width=width,
            height=info.get("height", 0),
            license=license_short,
            author=artist,
            credit_url=info.get("descriptionurl", ""),
            alt_text=query,
        )
    return None