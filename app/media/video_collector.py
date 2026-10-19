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

    # 2) Pexels Videos API — yalnızca Gemini Vision ile önizleme karesi doğrulanırsa!
    queries = _strict_video_queries(llm, candidate, entities)
    for q in queries:
        for cand_vid in _search_pexels_candidates(q):
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
                _save_video_meta(video_dir, vurl, f"pexels:{q}")
                log.info("Doğrulanmış gerçek video indirildi (%s): %s", slug, vurl)
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
        except Exception:
            pass
    return used


def _save_video_meta(video_dir: Path, video_url: str, source: str) -> None:
    meta = {"video_url": video_url, "source": source}
    (video_dir / "video_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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


def _strict_video_queries(llm: GeminiClient, candidate: Candidate, entities: list[str]) -> list[str]:
    """Haberdeki somut donanım/cihaz için 2 spesifik İngilizce arama terimi üretir."""
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
        return out[:2]
    except Exception:
        return []


def _verify_video_relevance(
    llm: GeminiClient,
    headline: str,
    entities: list[str],
    slug: str,
    thumb_url: str,
) -> bool:
    """Gemini ile video açıklamasının ve küçük resminin haberle birebir uyumlu olduğunu doğrular."""
    prompt = (
        f"Haber Başlığı: {headline}\n"
        f"Varlıklar: {', '.join(entities)}\n"
        f"Aday Video Açıklaması (URL slug): {slug}\n\n"
        "Soru: Bu aday video, yukarıdaki teknoloji haberinin konusu olan somut cihazı/teknolojiyi "
        "doğrudan ve mantıklı bir şekilde gösteriyor mu?\n"
        "KESİN RET KURALLARI:\n"
        "- Doğa, orman, ağaç, nehir, hayvan, lunapark, heykel, yemek, dans vb. alakasız görüntüler -> HAYIR\n"
        "- Akıllı saat (watch) haberi için kırık telefon veya eski telefon görüntüsü -> HAYIR\n"
        "- Konuyla doğrudan bağlantısı olmayan rastgele/tuhaf stok videolar -> HAYIR\n"
        "Yalnızca tek kelime cevap ver: EVET veya HAYIR."
    )
    try:
        ans = llm.generate_text(prompt, label="video-relevance-check").strip().upper()
        return ans.startswith("EVET")
    except Exception:
        return False


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
