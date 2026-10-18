"""Gerçek video toplama: haber makalesi gömülü videosu → Wikimedia Commons → Pexels Videos.

AI video üretimi KESİNLİKLE kullanılmaz; yalnızca internetten gerçek video indirilir.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlencode, urljoin

from app.common import http_get
from app.config import settings
from app.llm import prompts
from app.llm.gemini import GeminiClient
from app.models import Candidate

log = logging.getLogger("tekno-pusula.video_collector")

PEXELS_VIDEOS_URL = "https://api.pexels.com/videos/search"
WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"
MAX_VIDEO_BYTES = 45 * 1024 * 1024  # 45 MB üst sınır


def collect_video(
    llm: GeminiClient,
    candidate: Candidate | None,
    entities: list[str],
    post_dir: Path,
) -> Path | None:
    """Konuyla ilgili internetten gerçek bir MP4/WebM video bulup indirir.

    Öncelik sırası:
      1. Haber makalesinin içindeki gömülü gerçek video (og:video / <video src="*.mp4">)
      2. Wikimedia Commons gerçek video araması (varlık/şirket/ürün adı ile)
      3. Pexels Videos API (konuya uygun İngilizce arama sorguları ile)
    """
    video_dir = post_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    dest = video_dir / "source_video.mp4"

    # 1) Makale sayfasındaki gömülü gerçek video
    if candidate and candidate.url:
        article_vid = _find_article_video(candidate.url)
        if article_vid and _download_video(article_vid, dest):
            log.info("Makale içinden gerçek video indirildi: %s", article_vid)
            return dest

    # 2) Wikimedia Commons gerçek video araması
    for ent in (entities or [])[:2]:
        wiki_vid = _search_wikimedia_video(ent)
        if wiki_vid and _download_video(wiki_vid, dest):
            log.info("Wikimedia Commons gerçek video indirildi (%s): %s", ent, wiki_vid)
            return dest

    # 3) Pexels Videos API
    queries = _video_queries(llm, candidate, entities)
    for q in queries:
        for orient in ("portrait", "landscape"):
            for url in _search_pexels_videos(q, orientation=orient):
                if _download_video(url, dest):
                    log.info("Pexels gerçek video indirildi (%s, %s): %s", q, orient, url)
                    return dest

    log.warning("İnternetten uygun video indirilemedi.")
    return None


def _find_article_video(article_url: str) -> str | None:
    """Haber sayfasındaki og:video veya <video>/<source> MP4 bağlantısını bulur."""
    resp = http_get(article_url, retries=1, timeout=15)
    if resp is None or resp.status_code != 200:
        return None
    html = resp.text[:250_000]

    # og:video / twitter:player:stream
    meta_patterns = [
        r'<meta[^>]+property=["\'](?:og:video|og:video:secure_url|og:video:url)["\'][^>]+content=["\']([^"\']+\.mp4[^"\']*)["\']',
        r'<meta[^>]+content=["\']([^"\']+\.mp4[^"\']*)["\'][^>]+property=["\'](?:og:video|og:video:secure_url|og:video:url)["\']',
        r'<source[^>]+src=["\']([^"\']+\.mp4[^"\']*)["\']',
        r'<video[^>]+src=["\']([^"\']+\.mp4[^"\']*)["\']',
    ]
    for pat in meta_patterns:
        m = re.search(pat, html, flags=re.IGNORECASE)
        if m:
            raw_url = m.group(1).strip()
            if not raw_url.startswith("http"):
                raw_url = urljoin(article_url, raw_url)
            return raw_url
    return None


def _search_wikimedia_video(entity: str) -> str | None:
    """Wikimedia Commons'ta varlık adıyla gerçek video (.webm / .mp4) arar."""
    if not entity or len(entity.strip()) < 2:
        return None
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"filetype:video {entity}",
        "gsrlimit": 5,
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "format": "json",
    }
    resp = http_get(f"{WIKIMEDIA_API_URL}?{urlencode(params)}", retries=1, timeout=15)
    if resp is None or resp.status_code != 200:
        return None
    try:
        pages = resp.json().get("query", {}).get("pages", {})
    except ValueError:
        return None
    for page in pages.values():
        for info in page.get("imageinfo", []) or []:
            mime = (info.get("mime") or "").lower()
            size = int(info.get("size") or 0)
            url = info.get("url") or ""
            if ("video/mp4" in mime or "video/webm" in mime) and 100_000 < size < MAX_VIDEO_BYTES:
                return url
    return None


def _search_pexels_videos(query: str, *, orientation: str = "portrait", per_page: int = 6) -> list[str]:
    """Pexels Videos API'den gerçek HD MP4 video URL'lerini döndürür."""
    api_key = settings().pexels_api_key
    if not api_key:
        return []
    params = {
        "query": query,
        "orientation": orientation,
        "size": "medium",
        "per_page": per_page,
    }
    resp = http_get(
        f"{PEXELS_VIDEOS_URL}?{urlencode(params)}",
        headers={"Authorization": api_key},
        retries=2,
        timeout=20,
    )
    if resp is None or resp.status_code != 200:
        return []
    try:
        videos = resp.json().get("videos", []) or []
    except ValueError:
        return []

    urls: list[str] = []
    for vid in videos:
        dur = int(vid.get("duration") or 0)
        if dur < 3 or dur > 90:
            continue
        files = vid.get("video_files", []) or []
        # HD (720p - 1920p) MP4 dosyalarını tercih et
        mp4_files = [
            f for f in files
            if "mp4" in (f.get("file_type") or "").lower()
            and f.get("link")
            and 540 <= int(f.get("width") or 0) <= 2160
        ]
        mp4_files.sort(
            key=lambda f: abs(int(f.get("height") or 0) - 1280)
        )
        if mp4_files:
            urls.append(mp4_files[0]["link"])
    return urls


def _video_queries(llm: GeminiClient, candidate: Candidate | None, entities: list[str]) -> list[str]:
    """Haber konusuna uygun İngilizce gerçek video arama sorguları üretir."""
    out: list[str] = []
    if candidate:
        try:
            prompt = prompts.IMAGE_SEARCH_PROMPT.format(
                title=candidate.title,
                entities=", ".join(entities or candidate.entities or []),
            )
            ans = llm.generate_text(prompt, label="video-query")
            for line in ans.splitlines():
                q = line.strip().strip("-•*0123456789. ").strip()
                if 2 < len(q) < 60:
                    out.append(q)
        except Exception as exc:
            log.debug("Video sorgu üretimi atlandı: %s", exc)
    for ent in (entities or [])[:2]:
        if ent and ent.lower() not in [x.lower() for x in out]:
            out.append(ent)
    return out[:4]


def _download_video(url: str, dest: Path) -> bool:
    """Video dosyasını indirir ve boyutunu doğrular."""
    resp = http_get(url, retries=2, timeout=35)
    if resp is None or resp.status_code != 200:
        return False
    content = resp.content
    if not content or len(content) < 50_000 or len(content) > MAX_VIDEO_BYTES:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return True
