"""Yüksek kaliteli ve konuyla uyumlu gerçek video toplama (AI video üretimi YOK).

İki aşamalı yaklaşım:
1. Aşama 1 (Birebir gerçek görüntü): Haber makalesi + çapraz doğrulama kaynaklarındaki
   gömülü resmi videolar (.mp4/.webm/JSON-LD VideoObject) ve spesifik ürün araması.
2. Aşama 2 (Temsili teknoloji B-roll): Aşama 1 bulunamazsa ve haberin somut bir teknoloji/
   bilim/donanım/uzay görsel karşılığı varsa Pexels/Pixabay/NASA üzerinden HD (≥720p)
   temsili B-roll aranır; videoda şeffafça "Temsili görüntü" rozeti basılır.
   Soyut hukuk/siyaset/şirket skandalı gibi görsel karşılığı olmayan haberlerde zorla
   stok video aranmaz → None döner ve temiz 6'lı slayt paylaşılır.

Kalite ve alaka garantileri:
- Aynı video URL/ID'si tekrar kullanılmaz (dedup).
- Stok adayları indirilmeden önce yasaklı slug + thumbnail Vision ön elemesinden geçer.
- İndirilen video en az 720p HD, ≥23 fps, ≥7.5s ve 3 farklı zaman noktasından (%15, %50, %80)
  Gemini Vision onayı almak zorundadır.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import urlencode, urljoin

from app.common import http_get
from app.config import OUTPUT_DIR, settings
from app.llm.gemini import GeminiClient
from app.models import Candidate

log = logging.getLogger("tekno-pusula.video_collector")

PEXELS_VIDEOS_URL = "https://api.pexels.com/videos/search"
PIXABAY_VIDEOS_URL = "https://pixabay.com/api/videos/"
NASA_SEARCH_URL = "https://images-api.nasa.gov/search"
NASA_MEDIA_URL = "https://images-assets.nasa.gov/video/{nasa_id}/collection.json"
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"

MAX_VIDEO_BYTES = 50 * 1024 * 1024  # 50 MB üst sınır (1080p klipler için)
MIN_VIDEO_SHORT_SIDE = 720          # Minimum 720p HD (360p/480p bulanık videolar elenir)
MIN_VIDEO_FPS = 23.0                # Akıcı kare hızı eşiği
MIN_VIDEO_DURATION = 7.5            # Saniye
MAX_DOWNLOAD_ATTEMPTS = 6           # Toplam indirme bütçesi

# Alakasız / yanlış anlamaya yol açan veya soyut klişe stok kelimeleri
BANNED_SLUG_WORDS = {
    "rainforest", "forest", "jungle", "tree", "trees", "nature", "river", "waterfall",
    "animal", "bird", "monkey", "dog", "cat", "horse", "farm", "fruit", "orchard",
    "cooking", "kitchen", "food", "coffee", "cafe", "restaurant",
    "amusement", "park", "statue", "mickey", "castle", "fireworks", "parade",
    "beach", "ocean", "mountain", "sunset", "flower", "garden", "wedding", "dance",
    "party", "fashion", "fitness", "yoga", "couple", "family", "baby", "child",
    "handshake", "meeting", "smiling", "interview", "cartoon", "gaming",
    # Soyut / klişe CGI / neon animasyon yasağı
    "abstract", "visualization", "particles", "particle", "neon", "motion",
    "animation", "animated", "plexus", "matrix", "binary", "background",
    "wallpaper", "futuristic", "cyber", "cyberpunk", "glow", "glowing",
    "lines", "waves", "loop", "hologram", "fractal", "geometric", "tunnel",
    "vortex", "sphere", "grid", "hud", "graphic", "graphics", "illustration",
    "render", "cgi", "sci", "scifi", "spacecraft-cgi", "pattern", "texture",
}

BANNED_ARTICLE_VIDEO_PATTERNS = (
    "doubleclick", "googlesyndication", "adservice", "analytics", "tracker",
    "pixel", "sponsor", "promo-ad", "/ads/", "avatar", "favicon", "emoji",
)

SPACE_KEYWORDS = (
    "nasa", "space", "rocket", "satellite", "orbit", "lunar", "moon", "mars",
    "voyager", "starship", "blue origin", "spacex", "telescope", "asteroid",
    "astronaut", "launch", "probe", "uzay", "roket", "uydu",
)


def _is_space_topic(headline: str, entities: list[str]) -> bool:
    haystack = f"{headline} {' '.join(entities)}".lower()
    return any(kw in haystack for kw in SPACE_KEYWORDS)


def _slug_is_banned(slug: str) -> bool:
    tokens = set(re.findall(r"[a-z]+", (slug or "").lower()))
    return bool(tokens & BANNED_SLUG_WORDS)


def collect_video(
    llm: GeminiClient,
    candidate: Candidate | None,
    entities: list[str],
    post_dir: Path,
    *,
    extra_urls: list[str] | None = None,
) -> Path | None:
    """Bounded, HD-only, Vision-verified video collection (article -> strict -> B-roll)."""
    if not candidate:
        return None
    used = _load_used_video_urls()
    video_dir = post_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    dest = video_dir / "source_video.mp4"
    attempted_downloads: set[str] = set()
    seen_thumbs: set[str] = set()
    all_entities = list(dict.fromkeys([*(entities or []), *(candidate.entities or [])]))
    space_topic = _is_space_topic(candidate.title, all_entities)

    def accept(item: dict[str, str], source: str, *, mode: str) -> bool:
        url = item.get("video_url", "")
        if not url or url in used or url in attempted_downloads or len(attempted_downloads) >= MAX_DOWNLOAD_ATTEMPTS:
            return False
        if source != "article" and _slug_is_banned(item.get("slug", "")):
            return False
        # Stok kaynaklarında indirmeden önce ucuz thumbnail ön elemesi
        thumb_url = item.get("thumb_url", "")
        if source != "article" and thumb_url and thumb_url not in seen_thumbs:
            seen_thumbs.add(thumb_url)
            if not _verify_video_relevance(llm, candidate.title, all_entities, item.get("slug", ""), thumb_url, mode=mode):
                log.info("Video thumbnail elendi (%s/%s): %s", source, mode, item.get("slug", "")[:70])
                return False
        attempted_downloads.add(url)
        if not _download_video(url, dest):
            return False
        if not _verify_downloaded_video(llm, candidate.title, all_entities, dest, mode=mode):
            dest.unlink(missing_ok=True)
            return False
        meta = _save_video_meta(video_dir, url, source)
        meta.update({key: item.get(key, "") for key in ("license", "author", "page_url")})
        meta["illustrative"] = source != "article"
        meta["mode"] = mode
        (video_dir / "video_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Video onaylandı (%s/%s): %s", source, mode, url[:90])
        return True

    # 1) Makale ve çapraz doğrulama kaynaklarındaki gömülü gerçek videolar (tüm MP4/WebM adayları)
    article_urls = list(dict.fromkeys(u for u in [candidate.url, *(extra_urls or [])] if u))
    for page_url in article_urls[:3]:
        for article_video in _find_article_videos(page_url)[:3]:
            if accept({"video_url": article_video, "slug": candidate.title}, "article", mode="strict"):
                return dest
            if len(attempted_downloads) >= MAX_DOWNLOAD_ATTEMPTS:
                return None

    # 2) Aşama 1: Spesifik ürün / araştırma araması (HD kaynaklar önce, Wikimedia en sonda)
    strict_queries = _strict_video_queries(llm, candidate, all_entities)
    strict_providers = [
        ("pexels", _search_pexels_candidates),
        ("pixabay", _search_pixabay_candidates),
    ]
    if space_topic:
        strict_providers.insert(0, ("nasa", _search_nasa_candidates))
    strict_providers.append(("wikimedia", lambda q: _search_wikimedia_video_candidates(q, limit=2)))

    for query in strict_queries[:2]:
        for provider, search in strict_providers:
            for item in search(query)[:2]:
                if accept(item, provider, mode="strict"):
                    return dest
                if len(attempted_downloads) >= MAX_DOWNLOAD_ATTEMPTS:
                    return None

    # 3) Aşama 2: Konuya doğrudan uyan yüksek kaliteli temsili teknoloji B-roll
    broll_queries = _broll_video_queries(llm, candidate, all_entities)
    broll_providers = [
        ("pexels", _search_pexels_candidates),
        ("pixabay", _search_pixabay_candidates),
    ]
    if space_topic:
        broll_providers.insert(0, ("nasa", _search_nasa_candidates))

    for query in broll_queries[:2]:
        for provider, search in broll_providers:
            for item in search(query)[:3]:
                if accept(item, provider, mode="broll"):
                    return dest
                if len(attempted_downloads) >= MAX_DOWNLOAD_ATTEMPTS:
                    return None

    return None


def _load_used_video_urls() -> set[str]:
    """Daha önceki postlarda kullanılmış tüm video URL'lerini döndürür (aynı video tekrarlanmaz)."""
    used: set[str] = set()
    if not OUTPUT_DIR.exists():
        return used
    for meta_file in OUTPUT_DIR.glob("*/*/video/video_meta.json"):
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            u = data.get("video_url", "").strip()
            if u:
                used.add(u)
                m = re.search(r"/video-files/(\d+)/", u)
                if m:
                    used.add(f"pexels_id:{m.group(1)}")
                m = re.search(r"pixabay\.com/.*?_(\d+)", u)
                if m:
                    used.add(f"pixabay_id:{m.group(1)}")
                m = re.search(r"images-assets\.nasa\.gov/video/([^/]+)/", u)
                if m:
                    used.add(f"nasa_id:{m.group(1)}")
        except Exception:
            pass
    backfill = OUTPUT_DIR.parent / "data" / "used_videos.txt"
    if backfill.exists():
        try:
            for line in backfill.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    used.add(line)
        except Exception:
            pass
    return used


def _save_video_meta(video_dir: Path, video_url: str, source: str) -> dict:
    meta = {"video_url": video_url, "source": source}
    (video_dir / "video_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return meta


def _search_wikimedia_video_candidates(query: str, *, limit: int = 4) -> list[dict[str, str]]:
    """Wikimedia Commons'tan HD (1080p/720p) videolar arar."""
    params = {
        "action": "query",
        "list": "search",
        "srnamespace": "6",
        "srsearch": f"filetype:video {query}",
        "srlimit": limit,
        "format": "json",
    }
    resp = http_get(
        f"{WIKIMEDIA_API}?{urlencode(params)}",
        headers={"User-Agent": "TeknoPusula/1.0 (github-actions)"},
        retries=1,
        timeout=15,
    )
    if resp is None or resp.status_code != 200:
        return []
    try:
        hits = resp.json().get("query", {}).get("search", []) or []
    except ValueError:
        return []

    out: list[dict[str, str]] = []
    for hit in hits:
        title = hit.get("title") or ""
        if not title.startswith("File:"):
            continue
        iparams = {
            "action": "query",
            "titles": title,
            "prop": "videoinfo",
            "viprop": "derivatives|url|size|mime|extmetadata",
            "format": "json",
        }
        r2 = http_get(
            f"{WIKIMEDIA_API}?{urlencode(iparams)}",
            headers={"User-Agent": "TeknoPusula/1.0 (github-actions)"},
            retries=1,
            timeout=15,
        )
        if r2 is None or r2.status_code != 200:
            continue
        try:
            pages = r2.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values()), {})
            vi = (page.get("videoinfo") or [{}])[0]
        except (ValueError, StopIteration):
            continue

        # Yalnızca 1080p/720p HD transcode veya orijinal dosya (360p/480p alınmaz)
        best_url = ""
        for key in ("1080p.vp9.webm", "1080p.mpeg4.mov", "720p.vp9.webm", "720p.mpeg4.mov"):
            for d in (vi.get("derivatives") or []):
                if d.get("transcodekey") == key:
                    best_url = d.get("src") or ""
                    break
            if best_url:
                break
        if not best_url:
            best_url = vi.get("url") or ""

        em = vi.get("extmetadata") or {}
        license_name = (em.get("LicenseShortName") or {}).get("value", "")
        artist_raw = (em.get("Artist") or {}).get("value", "")
        artist = re.sub(r"<[^>]+>", "", artist_raw).strip()

        thumb_url = ""
        for d in (vi.get("derivatives") or []):
            if "thumb" in (d.get("transcodekey") or "").lower():
                thumb_url = d.get("src") or ""
                break

        if best_url and "video" in (vi.get("mime") or ""):
            out.append({
                "video_url": best_url,
                "thumb_url": thumb_url,
                "slug": title,
                "license": license_name,
                "author": artist,
                "page_url": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
            })
    return out


def _find_article_videos(article_url: str) -> list[str]:
    """Haber sayfasındaki gömülü gerçek .mp4/.webm videolarını bulur.

    og:video, <video>/<source>, JSON-LD VideoObject, custom HTML öznitelikleri
    (ör. or-mp4-video-url, data-video-url) ve gömülü JSON içindeki doğrudan
    video bağlantılarını öncelik sırasıyla döndürür.
    """
    resp = http_get(article_url, retries=1, timeout=15)
    if resp is None or resp.status_code != 200:
        return []
    html = resp.text[:600_000]

    priority_patterns = [
        r'<meta[^>]+property=["\'](?:og:video|og:video:secure_url|og:video:url)["\'][^>]+content=["\']([^"\']+\.(?:mp4|webm)[^"\']*)["\']',
        r'<meta[^>]+content=["\']([^"\']+\.(?:mp4|webm)[^"\']*)["\'][^>]+property=["\'](?:og:video|og:video:secure_url|og:video:url)["\']',
        r'(?:or-mp4-video-url|data-video-url|data-mp4-url|data-video-src|data-src)\s*=\s*["\']([^"\']+\.(?:mp4|webm)[^"\']*)["\']',
        r'<source[^>]+src=["\']([^"\']+\.(?:mp4|webm)[^"\']*)["\']',
        r'<video[^>]+src=["\']([^"\']+\.(?:mp4|webm)[^"\']*)["\']',
        r'"(?:contentUrl|videoUrl|mp4Url|src)"\s*:\s*"(https?:\\/\\/[^"]+\.(?:mp4|webm)[^"]*|https?://[^"]+\.(?:mp4|webm)[^"]*)"',
        r'(https?://[^\s"\'<>\\]+\.(?:mp4|webm)(?:\?[^\s"\'<>\\]*)?)',
    ]

    found: list[str] = []
    seen: set[str] = set()
    for pat in priority_patterns:
        for m in re.finditer(pat, html, flags=re.IGNORECASE):
            raw_url = m.group(1).strip().replace("\\/", "/")
            if not raw_url.startswith("http"):
                raw_url = urljoin(article_url, raw_url)
            low = raw_url.lower()
            if any(bad in low for bad in BANNED_ARTICLE_VIDEO_PATTERNS):
                continue
            if raw_url not in seen:
                seen.add(raw_url)
                found.append(raw_url)
    return found


def _find_article_video(article_url: str) -> str | None:
    """Geriye dönük uyumluluk: ilk makale videosunu döndürür."""
    videos = _find_article_videos(article_url)
    return videos[0] if videos else None


def _search_pexels_candidates(query: str, *, per_page: int = 8) -> list[dict[str, str]]:
    """Pexels Videos API'den HD (≥720p, dikey+yatay) aday videoları döndürür."""
    api_key = settings().pexels_api_key
    if not api_key:
        return []
    used = _load_used_video_urls()
    params = {
        "query": query,
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

    ranked: list[tuple[int, dict[str, str]]] = []
    for vid in videos:
        vid_id = str(vid.get("id") or "")
        if f"pexels_id:{vid_id}" in used:
            continue
        dur = int(vid.get("duration") or 0)
        if dur < 8 or dur > 60:
            continue
        page_url = str(vid.get("url") or "")
        thumb_url = str(vid.get("image") or "")
        files = vid.get("video_files", []) or []
        hd_files = [
            f for f in files
            if "mp4" in (f.get("file_type") or "").lower()
            and f.get("link")
            and min(int(f.get("width") or 0), int(f.get("height") or 0)) >= MIN_VIDEO_SHORT_SIDE
            and max(int(f.get("width") or 0), int(f.get("height") or 0)) <= 2560
        ]
        if not hd_files or not thumb_url:
            continue
        # 1080p HD en öncelikli, çok ağır 4K yerine ideal 1080p seç
        hd_files.sort(key=lambda f: abs(min(int(f.get("width") or 0), int(f.get("height") or 0)) - 1080))
        chosen = hd_files[0]
        w, h = int(chosen.get("width") or 0), int(chosen.get("height") or 0)
        # Dikey (9:16) 1080p videolara hafif sıralama önceliği ver
        priority = (2 if h > w else 1) * 1000 + min(w, h)
        ranked.append((priority, {
            "video_url": chosen["link"],
            "thumb_url": thumb_url,
            "slug": page_url,
            "license": "Pexels License",
            "author": str((vid.get("user") or {}).get("name") or ""),
            "page_url": page_url,
        }))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in ranked]


def _search_pixabay_candidates(query: str, *, per_page: int = 8) -> list[dict[str, str]]:
    """Pixabay Videos API'den HD (≥720p) aday videoları döndürür."""
    api_key = settings().pixabay_api_key
    if not api_key:
        return []
    used = _load_used_video_urls()
    params = {
        "key": api_key,
        "q": query,
        "video_type": "all",
        "per_page": per_page,
    }
    resp = http_get(
        f"{PIXABAY_VIDEOS_URL}?{urlencode(params)}",
        retries=2,
        timeout=20,
    )
    if resp is None or resp.status_code != 200:
        return []
    try:
        hits = resp.json().get("hits", []) or []
    except ValueError:
        return []

    out: list[dict[str, str]] = []
    for vid in hits:
        vid_id = str(vid.get("id") or "")
        if f"pixabay_id:{vid_id}" in used:
            continue
        dur = int(vid.get("duration") or 0)
        if dur < 8 or dur > 60:
            continue
        page_url = str(vid.get("pageURL") or "")
        tags = str(vid.get("tags") or "")
        vids = vid.get("videos") or {}
        thumb = ""
        for size in ("large", "medium", "small"):
            t = (vids.get(size) or {}).get("thumbnail") or ""
            if t:
                thumb = t
                break
        mp4_url = ""
        # Yalnızca HD (≥720p) sürümleri al: large → medium
        for size in ("large", "medium"):
            v = vids.get(size) or {}
            link = v.get("url") or ""
            w, h = int(v.get("width") or 0), int(v.get("height") or 0)
            if link and min(w, h) >= MIN_VIDEO_SHORT_SIDE and max(w, h) <= 2560:
                mp4_url = link
                break
        if mp4_url and thumb:
            out.append({
                "video_url": mp4_url,
                "thumb_url": thumb,
                "slug": f"{page_url} {tags}".strip(),
                "license": "Pixabay License",
                "author": str(vid.get("user") or ""),
                "page_url": page_url,
            })
    return out


def _search_nasa_candidates(query: str, *, per_page: int = 8) -> list[dict[str, str]]:
    """NASA Image/Video Library'den HD aday videoları döndürür."""
    used = _load_used_video_urls()
    params = {
        "q": query,
        "media_type": "video",
        "page_size": per_page,
    }
    resp = http_get(
        f"{NASA_SEARCH_URL}?{urlencode(params)}",
        retries=2,
        timeout=25,
    )
    if resp is None or resp.status_code != 200:
        return []
    try:
        items = resp.json().get("collection", {}).get("items", []) or []
    except ValueError:
        return []

    out: list[dict[str, str]] = []
    for item in items:
        data_list = item.get("data") or []
        if not data_list:
            continue
        d = data_list[0]
        nasa_id = str(d.get("nasa_id") or "")
        title = str(d.get("title") or "")
        if not nasa_id or f"nasa_id:{nasa_id}" in used:
            continue
        thumb_url = ""
        for lnk in (item.get("links") or []):
            if lnk.get("render") == "image" and lnk.get("href"):
                thumb_url = str(lnk["href"])
                break
        media_resp = http_get(NASA_MEDIA_URL.format(nasa_id=nasa_id), retries=1, timeout=15)
        if media_resp is None or media_resp.status_code != 200:
            continue
        try:
            assets = media_resp.json() or []
        except ValueError:
            continue
        # NASA collection.json string listesi (veya dict listesi) dönebilir
        mp4_urls: list[str] = []
        for entry in assets:
            href = entry if isinstance(entry, str) else str((entry or {}).get("href") or "")
            if href.lower().endswith(".mp4") and href.startswith("http"):
                mp4_urls.append(href)
        mp4_url = ""
        for suffix in ("~orig.mp4", "~large.mp4", "~medium.mp4"):
            match = next((u for u in mp4_urls if u.lower().endswith(suffix)), "")
            if match:
                mp4_url = match
                break
        if mp4_url and thumb_url:
            out.append({
                "video_url": mp4_url,
                "thumb_url": thumb_url,
                "slug": title,
                "license": "NASA Public Domain",
                "author": "NASA",
                "page_url": f"https://images.nasa.gov/details/{nasa_id}",
            })
    return out


def _verify_downloaded_video(
    llm: GeminiClient,
    headline: str,
    entities: list[str],
    path: Path,
    *,
    mode: str = "strict",
) -> bool:
    import subprocess
    from app.media.video_probe import probe_video

    info = probe_video(path)
    duration = float(info.get("duration") or 0)
    short_side = min(int(info.get("width") or 0), int(info.get("height") or 0))
    fps = float(info.get("fps") or 0)
    if duration < MIN_VIDEO_DURATION or short_side < MIN_VIDEO_SHORT_SIDE:
        log.info("Video kalite filtresini geçemedi (süre=%.1fs, min_kenar=%dpx)", duration, short_side)
        return False
    if fps and fps < MIN_VIDEO_FPS:
        log.info("Video FPS filtresini geçemedi (fps=%.1f)", fps)
        return False

    frames = []
    try:
        for index, fraction in enumerate((0.15, 0.5, 0.8)):
            frame = path.parent / f"check-{index}.jpg"
            proc = subprocess.run(
                ["ffmpeg", "-y", "-ss", str(duration * fraction), "-i", str(path),
                 "-frames:v", "1", "-vf", "scale=640:-2", str(frame)],
                capture_output=True, timeout=30,
            )
            if proc.returncode != 0 or not frame.exists():
                return False
            frames.append(frame)

        if mode == "broll":
            prompt = (
                f"Headline: {headline}\nEntities: {', '.join(entities)}\n"
                "These are three frames from ONE candidate illustrative B-roll video for a Turkish tech news Reel. "
                "Inspect ALL three frames strictly.\n"
                "APPROVE (YES) ONLY IF all three frames are REAL-WORLD CAMERA FOOTAGE (physically filmed, NOT CGI) "
                "of sharp, clear physical technology/science/hardware/space environments that DIRECTLY match the "
                "concrete subject of the headline (e.g. real semiconductor chip/wafer for chip news, real server room "
                "hardware for data center/cloud news, real robotic arm or lab equipment for robotics/biotech news, "
                "real rocket/satellite for space news).\n"
                "STRICT REJECT (NO) IF ANY frame shows:\n"
                "- Abstract animations, glowing dots/lines/particles, data visualizations, 3D CGI/neon graphics, "
                "matrix/binary/cyberpunk/hologram loops, futuristic HUD overlays\n"
                "- Unrelated nature/scenery/animals/food, generic smiling people, office meetings, handshakes\n"
                "- Video games/cartoons, wrong brand logo or wrong product, text/watermarks, blurry/dark footage.\n"
                "Respond with ONE word only: YES or NO."
            )
        else:
            prompt = (
                f"Headline: {headline}\nEntities: {', '.join(entities)}\n"
                "These are three frames from ONE candidate news video. Inspect ALL frames. "
                "Is this real, sharp, clear footage directly relevant to the specific subject? "
                "Reject unrelated scenery, generic offices, games, abstract animations, wrong products/brands, "
                "static screenshots, watermarks across the subject, or blurry/illegible footage. "
                "A real screen recording demonstrating the named software is acceptable. Do not infer unseen details. "
                "Respond with one word: YES or NO."
            )
        answer = llm.analyze_images(prompt, [str(p) for p in frames], label=f"video-frames-{mode}")
        return answer.strip().upper().startswith(("YES", "EVET"))
    except Exception as exc:
        log.warning("Gerçek video kareleri doğrulanamadı: %s", type(exc).__name__)
        return False
    finally:
        for frame in frames:
            frame.unlink(missing_ok=True)


def _strict_video_queries(llm: GeminiClient, candidate: Candidate, entities: list[str]) -> list[str]:
    """Haberdeki somut ürün/araştırma için en fazla 2 spesifik İngilizce arama terimi üretir."""
    prompt = (
        f"News headline: {candidate.title}\n"
        f"Entities: {', '.join(entities or candidate.entities or [])}\n\n"
        "Task: Output at most 2 specific English video search queries for the exact product, hardware, or research. "
        "NEVER use ambiguous brand names alone like 'Amazon' (returns jungle), 'Disney' (returns theme park), "
        "or 'Apple' (returns fruit). If no exact product footage exists in public archives, return an empty list."
    )
    try:
        from app.models import SearchQueries
        result = llm.generate_structured(
            prompt + "\nReturn {queries: []} if none, otherwise at most 2 short queries.",
            SearchQueries, label="video-strict-query",
        )
        return [q.strip() for q in result.queries if 3 < len(q.strip()) < 55 and q.upper() != "NONE"][:2]
    except Exception:
        return []


def _broll_video_queries(llm: GeminiClient, candidate: Candidate, entities: list[str]) -> list[str]:
    """Yalnızca gerçek dünyada filme alınabilecek fiziksel B-roll sorguları üretir (soyut haberlerde boş)."""
    prompt = (
        f"News headline: {candidate.title}\n"
        f"Summary: {(candidate.summary or '')[:400]}\n"
        f"Entities: {', '.join(entities or candidate.entities or [])}\n\n"
        "Task: Produce at most 2 concrete, PHYSICAL real-world camera footage search queries (2-4 words each) "
        "for Pexels/Pixabay ONLY IF this story has a clear real-world physical hardware, lab, or industrial scene.\n"
        "Good examples:\n"
        "- Chips / GPU manufacturing / export -> 'microchip processor close up', 'silicon wafer cleanroom'\n"
        "- Data center / cloud infrastructure -> 'data center server rack'\n"
        "- Robotics / autonomous car -> 'robotic arm laboratory', 'self driving car lidar'\n"
        "- Space / rocket / satellite -> 'rocket launch pad', 'satellite earth orbit'\n"
        "- Biotech / medical / physical sensor -> 'chemistry laboratory equipment', 'microscope lab scientist'\n"
        "STRICT REJECT — return EMPTY list {queries: []} IF:\n"
        "- The news is about a software/API/AI model launch with no specific physical hardware (do NOT use cliché stock!),\n"
        "- The news is about lawsuits, politics, IPO stock prices, executive drama, or corporate finance.\n"
        "NEVER use brand names and NEVER output words like 'abstract', 'visualization', 'futuristic', 'neon', "
        "'digital', 'network', 'animation', 'cyber', 'office', or 'people'."
    )
    try:
        from app.models import SearchQueries
        result = llm.generate_structured(
            prompt + "\nReturn {queries: [...]}.",
            SearchQueries, label="video-broll-query",
        )
        cleaned = []
        for q in result.queries:
            qs = q.strip()
            if 3 < len(qs) < 45 and qs.upper() != "NONE" and not _slug_is_banned(qs):
                cleaned.append(qs)
        return cleaned[:2]
    except Exception:
        return []


def _verify_video_relevance(
    llm: GeminiClient,
    headline: str,
    entities: list[str],
    slug: str,
    thumb_url: str,
    *,
    mode: str = "strict",
) -> bool:
    """İndirmeden önce ucuz thumbnail + slug ön elemesi (Gemini Vision)."""
    import os
    import tempfile

    from app.common import http_get as _http_get

    tmp_path = None
    if thumb_url:
        try:
            resp = _http_get(thumb_url, retries=1, timeout=15)
            if resp is not None and resp.status_code == 200 and len(resp.content) > 4000:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp.write(resp.content)
                    tmp_path = tmp.name
        except Exception:
            tmp_path = None

    if mode == "broll":
        prompt = (
            f"News headline: {headline}\n"
            f"Entities: {', '.join(entities)}\n"
            f"Video metadata: {slug}\n\n"
            "TASK: Look at this video thumbnail. Is it REAL-WORLD CAMERA FOOTAGE (NOT CGI, NOT abstract animation) "
            "of physical technology/hardware/science/space equipment that DIRECTLY matches the headline above?\n"
            "Answer NO if it shows: abstract glowing lines/dots/particles/data visualizations/neon CGI/matrix graphics, "
            "nature/forest/animals/food/beach, smiling people/office meetings/handshakes, cartoons/games, watermarks, "
            "blurry footage, wrong brand logos, or anything off-topic.\n"
            "Answer ONE word ONLY: YES or NO."
        )
    else:
        prompt = (
            f"News headline: {headline}\n"
            f"Entities: {', '.join(entities)}\n"
            f"Video description (URL slug): {slug}\n\n"
            "TASK: Look at the provided video thumbnail image. Does it show a real technology/physical "
            "device/product that DIRECTLY relates to the news headline above?\n"
            "REJECT rules (answer NO):\n"
            "- Nature, forest, trees, rivers, animals, amusement park, statue, food, dance, beach etc. -> NO\n"
            "- Random/unrelated stock footage that doesn't match the headline -> NO\n"
            "- Abstract graphics, generic office scenes, or people talking -> NO\n"
            "Answer with ONE word ONLY: YES or NO."
        )
    try:
        if tmp_path:
            ans = llm.analyze_images(prompt, [tmp_path], label=f"video-thumb-{mode}").strip().upper()
        else:
            ans = llm.generate_text(prompt, label=f"video-text-{mode}").strip().upper()
        return ans.startswith("YES") or ans.startswith("EVET")
    except Exception:
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _download_video(url: str, dest: Path) -> bool:
    """Video dosyasını indirir ve boyutunu doğrular."""
    resp = http_get(url, retries=2, timeout=40)
    if resp is None or resp.status_code != 200:
        return False
    content = resp.content
    if not content or len(content) < 80_000 or len(content) > MAX_VIDEO_BYTES:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return True
