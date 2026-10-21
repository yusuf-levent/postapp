"""Gerçek ve birebir konuyla ilgili video toplama (AI video üretimi YOK).

Kurallar:
1. Daha önce kullanılmış hiçbir video URL'si tekrar kullanılamaz (dedup).
2. Öncelik haber makalesinin kendi içindeki gömülü gerçek videodur (og:video / <video src>).
3. Stok/arşiv videoları (Wikimedia / Pexels) yalnızca:
   - Açıklama/başlık metni haber konusuyla çelişmiyorsa (örn. Amazon -> rainforest/orman YASAK,
     Disney -> theme park/statue YASAK) VE
   - Gemini Vision (görsel doğrulama) video önizleme karesinin haber başlığıyla BİREBİR
     ve doğrudan ilgili gerçek bir teknoloji/ürün görüntüsü olduğunu onaylarsa kabul edilir.
4. Uygun ve doğrulanmış gerçek video bulunamazsa None döner; böylece Instagram ve TikTok'a
   saçma/alakasız video yerine otomatik olarak 6'lı bilgi slaytı paylaşılır.
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
MAX_VIDEO_BYTES = 45 * 1024 * 1024  # 45 MB üst sınır

# Yanlış anlamaya yol açan kelimeler (Amazon -> orman, Apple -> meyve, Disney -> lunapark vb.)
BANNED_SLUG_WORDS = {
    "rainforest", "forest", "jungle", "tree", "trees", "nature", "river", "waterfall",
    "animal", "bird", "monkey", "fruit", "orchard", "cooking", "kitchen", "food",
    "amusement", "park", "statue", "mickey", "castle", "fireworks", "parade",
    "beach", "ocean", "mountain", "sunset", "flower", "garden", "wedding", "dance",
}


def collect_video(
    llm: GeminiClient,
    candidate: Candidate | None,
    entities: list[str],
    post_dir: Path,
) -> Path | None:
    """Konuyla birebir ilgili, tekrarsız ve doğrulanmış gerçek MP4 video indirir.

    Doğrulanmış gerçek video bulunamazsa None döner (6'lı slayta düşer).
    """
    if not candidate:
        return None

    used_urls = _load_used_video_urls()
    video_dir = post_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    dest = video_dir / "source_video.mp4"

    # 1) Haber makalesinin kendi içindeki gömülü gerçek video (en güvenilir kaynak)
    if candidate.url:
        article_vid = _find_article_video(candidate.url)
        if article_vid and article_vid not in used_urls:
            if _download_video(article_vid, dest):
                _save_video_meta(video_dir, article_vid, "article")
                log.info("Makale içinden gerçek video indirildi: %s", article_vid)
                return dest

    # 2) Gerçek ürün/haber videoları: Wikimedia Commons B-roll (CC lisanslı, atıf otomatik)
    queries = _strict_video_queries(llm, candidate, entities)
    # B-roll sorguları: "NVIDIA RTX 5090 b-roll", "iPhone unboxing" vb.
    broll_queries = []
    for q in queries:
        broll_queries.append(f"{q} b-roll")
        broll_queries.append(q)
    if entities:
        broll_queries.insert(0, f"{entities[0]} b-roll")

    for q in broll_queries[:4]:
        for cand_vid in _search_wikimedia_video_candidates(q):
            vurl = cand_vid["video_url"]
            slug = cand_vid["slug"].lower()
            thumb_url = cand_vid["thumb_url"]
            if vurl in used_urls:
                continue
            if any(bw in slug for bw in BANNED_SLUG_WORDS):
                log.info("Alakasız video elendi (yasaklı kelime): %s", slug)
                continue
            if not _verify_video_relevance(llm, candidate.title, entities, slug, thumb_url):
                log.info("Video Gemini doğrulamasından geçemedi, elendi: %s", slug)
                continue
            if _download_video(vurl, dest):
                meta = _save_video_meta(video_dir, vurl, f"wikimedia:{q}")
                if meta is not None:
                    meta["license"] = cand_vid.get("license", "")
                    meta["author"] = cand_vid.get("author", "")
                    meta["credit_url"] = cand_vid.get("page_url", "")
                    (video_dir / "video_meta.json").write_text(
                        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                log.info("Gerçek ürün videosu (Wikimedia B-roll) indirildi (%s): %s", slug, vurl)
                return dest

    # 3) Stok video API'leri (Pexels → Pixabay → NASA) — Gemini Vision ile doğrulanırsa!
    # Her sağlayıcıdan aday topla (öncelik: Pexels → Pixabay → NASA)
    providers = [
        ("pexels", _search_pexels_candidates),
        ("pixabay", _search_pixabay_candidates),
        ("nasa", _search_nasa_candidates),
    ]
    for q in queries:
        for provider_name, search_fn in providers:
            for cand_vid in search_fn(q):
                vurl = cand_vid["video_url"]
                slug = cand_vid["slug"].lower()
                thumb_url = cand_vid["thumb_url"]
                if vurl in used_urls:
                    continue
                if any(bw in slug for bw in BANNED_SLUG_WORDS):
                    log.info("Alakasız video elendi (yasaklı kelime): %s", slug)
                    continue
                if not _verify_video_relevance(llm, candidate.title, entities, slug, thumb_url):
                    log.info("Video Gemini doğrulamasından geçemedi, elendi: %s", slug)
                    continue
                if _download_video(vurl, dest):
                    _save_video_meta(video_dir, vurl, f"{provider_name}:{q}")
                    log.info("Doğrulanmış gerçek video indirildi (%s:%s): %s", provider_name, q, vurl)
                    return dest

    log.info("Bu haber için birebir uyumlu gerçek video bulunamadı; 6'lı slayt paylaşılacak.")
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
                # Pexels dosya ID bazlı tekilleştirme
                m = re.search(r"/video-files/(\d+)/", u)
                if m:
                    used.add(f"pexels_id:{m.group(1)}")
                # Pixabay ID bazlı tekilleştirme
                m = re.search(r"pixabay\.com/.*?_(\d+)", u)
                if m:
                    used.add(f"pixabay_id:{m.group(1)}")
                # NASA ID bazlı tekilleştirme
                m = re.search(r"images-assets\.nasa\.gov/video/([^/]+)/", u)
                if m:
                    used.add(f"nasa_id:{m.group(1)}")
        except Exception:
            pass
    # Eski postlardan manuel backfill: data/used_videos.txt (her satır bir URL)
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


def _search_wikimedia_video_candidates(query: str, *, limit: int = 8) -> list[dict[str, str]]:
    """Wikimedia Commons'tan gerçek ürün/haber videoları (B-roll) arar.

    Commons API'si key gerektirmez. Videolar WebM/VP9 transcode olarak sunulur;
    mevcut en yüksek çözünürlüklü transcode seçilir. Lisans ve atıf bilgisi döndürülür.
    """
    used = _load_used_video_urls()
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
        retries=2,
        timeout=20,
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
        # Dosya bilgisi + lisans + transcode listesi
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

        # En iyi transcode (1080p > 480p > 360p) veya orijinal
        best_url = ""
        for key in ("1080p.vp9.webm", "1080p.mpeg4.mov", "480p.vp9.webm", "480p.mpeg4.mov", "360p.mpeg4.mov"):
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
                "thumb_url": thumb_url or vi.get("url", ""),
                "slug": title,
                "license": license_name,
                "author": artist,
                "page_url": f"https://commons.wikimedia.org/wiki/{title.replace(' ', '_')}",
            })
    return out


def _find_article_video(article_url: str) -> str | None:
    """Haber sayfasındaki og:video veya <video>/<source> MP4 bağlantısını bulur."""
    resp = http_get(article_url, retries=1, timeout=15)
    if resp is None or resp.status_code != 200:
        return None
    html = resp.text[:250_000]

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


def _search_pexels_candidates(query: str, *, per_page: int = 5) -> list[dict[str, str]]:
    """Pexels Videos API'den aday videoları (video_url, thumb_url, slug) döndürür."""
    api_key = settings().pexels_api_key
    if not api_key:
        return []
    used = _load_used_video_urls()
    params = {
        "query": query,
        "orientation": "portrait",
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

    out: list[dict[str, str]] = []
    for vid in videos:
        vid_id = str(vid.get("id") or "")
        if f"pexels_id:{vid_id}" in used:
            continue
        dur = int(vid.get("duration") or 0)
        if dur < 5 or dur > 60:
            continue
        page_url = str(vid.get("url") or "")
        thumb_url = str(vid.get("image") or "")
        files = vid.get("video_files", []) or []
        mp4_files = [
            f for f in files
            if "mp4" in (f.get("file_type") or "").lower()
            and f.get("link")
            and 540 <= int(f.get("width") or 0) <= 2160
        ]
        mp4_files.sort(key=lambda f: abs(int(f.get("height") or 0) - 1280))
        if mp4_files and thumb_url:
            out.append({
                "video_url": mp4_files[0]["link"],
                "thumb_url": thumb_url,
                "slug": page_url,
            })
    return out


def _search_pixabay_candidates(query: str, *, per_page: int = 10) -> list[dict[str, str]]:
    """Pixabay Videos API'den aday videoları döndürür (ücretsiz API key gerekir)."""
    api_key = settings().pixabay_api_key
    if not api_key:
        return []
    used = _load_used_video_urls()
    params = {
        "key": api_key,
        "q": query,
        "video_type": "all",
        "orientation": "all",  # yatay videolar renderer'da 9:16'ya kırpılır
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
        if dur < 5 or dur > 60:
            continue
        page_url = str(vid.get("pageURL") or "")
        thumb_url = str(vid.get("picture_id") or "")
        # picture_id bir thumbnail URL'si değil; hits.videos.large.thumbnail kullan
        vids = vid.get("videos") or {}
        thumb = ""
        for size in ("large", "medium", "small", "tiny"):
            t = (vids.get(size) or {}).get("thumbnail") or ""
            if t:
                thumb = t
                break
        mp4_url = ""
        # Dikey/karesel tercih: large → medium → tiny
        for size in ("large", "medium", "small", "tiny"):
            v = (vids.get(size) or {})
            link = v.get("url") or ""
            w = int(v.get("width") or 0)
            if link and (w == 0 or 540 <= w <= 2160):
                mp4_url = link
                break
        if mp4_url and thumb:
            out.append({"video_url": mp4_url, "thumb_url": thumb, "slug": page_url})
    return out


def _search_nasa_candidates(query: str, *, per_page: int = 10) -> list[dict[str, str]]:
    """NASA Image/Video Library'den aday videoları döndürür (API key opsiyonel)."""
    used = _load_used_video_urls()
    params = {
        "q": query,
        "media_type": "video",
        "page_size": per_page,
    }
    headers = {}
    api_key = settings().nasa_api_key
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    resp = http_get(
        f"{NASA_SEARCH_URL}?{urlencode(params)}",
        headers=headers,
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
        nasa_id = ""
        thumb_url = ""
        title = ""
        for d in (item.get("data") or []):
            nasa_id = str(d.get("nasa_id") or "")
            title = str(d.get("title") or "")
            for l in (d.get("links") or []):
                if l.get("render") == "image":
                    thumb_url = str(l.get("href") or "")
        if not nasa_id:
            continue
        if f"nasa_id:{nasa_id}" in used:
            continue
        # Dosya listesini çek (collection.json) ve uygun MP4 seç
        media_resp = http_get(NASA_MEDIA_URL.format(nasa_id=nasa_id), retries=1, timeout=15)
        if media_resp is None or media_resp.status_code != 200:
            continue
        try:
            items2 = media_resp.json() or []
        except ValueError:
            continue
        mp4_url = ""
        for f in items2:
            href = str(f.get("href") or "")
            if href.endswith(".mp4") and ("~orig" in href or "~small" in href):
                mp4_url = href
                break
        if mp4_url and thumb_url:
            out.append({"video_url": mp4_url, "thumb_url": thumb_url, "slug": title})
    return out


def _strict_video_queries(llm: GeminiClient, candidate: Candidate, entities: list[str]) -> list[str]:
    """Haberdeki somut donanım/cihaz için 4 spesifik İngilizce arama terimi üretir."""
    prompt = (
        f"News headline: {candidate.title}\n"
        f"Entities: {', '.join(entities or candidate.entities or [])}\n\n"
        "Task: If this news is about a specific physical hardware device (e.g. smartwatch, GPU chip, "
        "electric car, robot, VR headset, earbuds), output at most 2 ultra-specific English search queries "
        "describing ONLY the physical device itself (e.g. 'smartwatch screen closeup', 'computer graphics card gpu'). "
        "NEVER use ambiguous brand names alone like 'Amazon' (returns jungle), 'Disney' (returns theme park), "
        "or 'Apple' (returns fruit). If the news is purely about corporate lawsuits, bankruptcy, or abstract policy "
        "with no physical device to show, output ONLY the word: NONE"
    )
    try:
        ans = llm.generate_text(prompt, label="video-strict-query").strip()
        if "NONE" in ans.upper():
            return []
        out: list[str] = []
        for line in ans.splitlines():
            q = line.strip().strip("-•*0123456789. \"'").strip()
            if 3 < len(q) < 55 and "none" not in q.lower():
                out.append(q)
        return out[:4]
    except Exception:
        return []


def _verify_video_relevance(
    llm: GeminiClient,
    headline: str,
    entities: list[str],
    slug: str,
    thumb_url: str,
) -> bool:
    """Gemini Vision ile video önizleme karesini (thumbnail) gerçekten görüntüler ve haberle uyumunu doğrular."""
    import os
    import tempfile

    from app.common import http_get as _http_get

    # Thumbnail'i indir ve Gemini'ye görsel olarak gönder
    tmp_path = None
    if thumb_url:
        try:
            resp = _http_get(thumb_url, retries=1, timeout=15)
            if resp is not None and resp.status_code == 200 and len(resp.content) > 5000:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                    tmp.write(resp.content)
                    tmp_path = tmp.name
        except Exception:
            tmp_path = None

    prompt = (
        f"News headline: {headline}\n"
        f"Entities: {', '.join(entities)}\n"
        f"Video description (URL slug): {slug}\n\n"
        "TASK: Look at the provided video thumbnail image. Does it show a real technology/physical "
        "device/product that DIRECTLY relates to the news headline above?\n"
        "REJECT rules (answer NO):\n"
        "- Nature, forest, trees, rivers, animals, amusement park, statue, food, dance, beach etc. -> NO\n"
        "- Broken phone or irrelevant device when news is about smartwatch -> NO\n"
        "- Random/unrelated stock footage that doesn't match the headline -> NO\n"
        "- Abstract graphics, generic office scenes, or people talking -> NO\n"
        "Answer with ONE word ONLY: YES or NO."
    )
    try:
        if tmp_path:
            ans = llm.analyze_images(prompt, [tmp_path], label="video-vision-check").strip().upper()
        else:
            ans = llm.generate_text(prompt, label="video-text-check").strip().upper()
        return ans.startswith("YES") or ans.startswith("EVET")
    except Exception:
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


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
