"""Modern, dinamik, telifsiz fon müziği seçimi ve indirme (API anahtarsız).

Kaynak önceliği:
1. Incompetech (Kevin MacLeod — CC BY 4.0): 500+ stüdyo kalitesinde modern
   elektronik, synth, lo-fi, upbeat/driving parça. Doğrudan yüksek kaliteli MP3.
2. Openverse Audio API (CC0 / CC BY): Modern electro-pop, synthwave, lo-fi beat.
3. Internet Archive (son çare): Sıkı filtrelenmiş ticari kullanıma uygun MP3.

Kurallar:
- Yalnızca ticari kullanıma uygun (CC0 / CC BY / CC BY-SA) lisanslar kabul edilir.
- Komedi, ortaçağ, korku, polka, vals, podcast, oyun soundtrack vb. türler elenir.
- Daha önce kullanılan şarkılar takip edilir; her paylaşımda farklı bir parça seçilir.
- Kredi bilgisi (title, artist, license, url) credits.json'a yazılır.
"""
from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path
from urllib.parse import quote, urlencode

from app.common import http_get
from app.config import OUTPUT_DIR

log = logging.getLogger("tekno-pusula.music")

INCOMPETECH_CATALOG = "https://incompetech.com/music/royalty-free/pieces.json"
INCOMPETECH_MP3 = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/{filename}"
OPENVERSE_AUDIO = "https://api.openverse.org/v1/audio/"
ARCHIVE_SEARCH = "https://archive.org/advancedsearch.php"
ARCHIVE_META = "https://archive.org/metadata/{identifier}"
ARCHIVE_DOWNLOAD = "https://archive.org/download/{identifier}/{filename}"

# Modern elektronik / synth / pop / chill / energetic Incompetech genre ID'leri
MODERN_INCOMPETECH_GENRES = {"6", "7", "11", "16", "25", "26"}

# İstenmeyen tür / ruh hali / enstrüman kelimeleri
BANNED_MUSIC_FEELS = (
    "humorous", "comedy", "medieval", "ren faire", "horror", "eerie",
    "christmas", "holiday", "waltz", "polka", "silent film", "western",
    "country", "march", "circus", "halloween", "sad", "somber", "mournful",
)
BANNED_INSTRUMENTS = ("banjo", "accordion", "tuba", "bagpipe", "kazoo", "ukulele", "harpsichord")
MODERN_INSTRUMENTS = ("synth", "drum", "bass", "electronic", "percussion", "guitar", "piano")

# Ticari kullanıma uygun lisans anahtarları
ALLOWED_LICENSE_TOKENS = (
    "publicdomain",
    "cc0",
    "zero",
    "licenses/by/4",
    "licenses/by/3",
    "licenses/by/2",
    "by-sa",
    "bysa",
    "attribution",
    "sharealike",
)
BANNED_LICENSE_TOKENS = ("noncommercial", "non-commercial", "/nc/", "-nc", "-nd", "by-nc", "noderiv")

BANNED_AUDIO_TERMS = (
    "pokemon", "pkmn", "podcast", "speech", "talk", "radio", "sermon",
    "interview", "lecture", "audiobook", "soundtrack", "ost", "karaoke",
    "vocal", "singing", "live", "concert", "episode", "sfx", "sound effect",
    "heart beat", "heartbeat", "footstep", "rain", "wind", "noise",
)

MAX_MUSIC_BYTES = 25 * 1024 * 1024  # 25 MB üst sınır
MIN_MUSIC_SECONDS = 25
MAX_MUSIC_SECONDS = 320

# Haber temasına göre modern Openverse arama sorguları
MOOD_OPENVERSE_QUERIES = {
    "energetic": ["synthwave beat", "electro pop upbeat", "cyberpunk electronic"],
    "driving": ["electronic driving beat", "techno house loop", "modern synth beat"],
    "chill": ["lofi hip hop beat", "chill electronic beat", "modern ambient synth"],
    "cinematic": ["epic electronic synth", "futuristic electronic", "cinematic synth beat"],
}


def _parse_hms(raw: object) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str) and raw.strip():
        parts = raw.strip().split(":")
        try:
            return sum(float(p) * (60 ** (len(parts) - 1 - i)) for i, p in enumerate(parts))
        except ValueError:
            return 0.0
    return 0.0


def _load_used_music() -> set[str]:
    """Son postlarda kullanılan müzik URL ve başlıklarını döndürür (tekrar çalmayı önler)."""
    used: set[str] = set()
    if not OUTPUT_DIR.exists():
        return used
    for credit_file in OUTPUT_DIR.glob("*/*/credits.json"):
        try:
            data = json.loads(credit_file.read_text(encoding="utf-8"))
            music = data.get("music") or {}
            for key in ("url", "title"):
                val = str(music.get(key) or "").strip().lower()
                if val:
                    used.add(val)
        except Exception:
            pass
    return used


def _pick_mood(llm, title: str, entities: list[str]) -> str:
    """Haber için tek kelimelik modern müzik atmosferi seçer."""
    prompt = (
        f"News headline: {title}\n"
        f"Entities: {', '.join(entities or [])}\n\n"
        "Pick ONE mood word for modern Reels/TikTok background music for this tech news:\n"
        "- energetic (exciting launch, breakthrough, fast innovation)\n"
        "- driving (AI chips, cybersecurity, industry competition, robotics)\n"
        "- chill (software update, developer tool, tutorial, daily tech)\n"
        "- cinematic (space, rocket, major scientific discovery)\n"
        "Respond with ONE word only."
    )
    try:
        ans = llm.generate_text(prompt, label="music-mood").strip().lower()
        for mood in ("energetic", "driving", "chill", "cinematic"):
            if mood in ans:
                return mood
    except Exception as exc:
        log.debug("Müzik ruh hali seçilemedi, varsayılan kullanılacak: %s", exc)
    low = f"{title} {' '.join(entities or [])}".lower()
    if any(k in low for k in ("space", "rocket", "nasa", "satellite", "voyager", "uzay")):
        return "cinematic"
    if any(k in low for k in ("chip", "gpu", "nvidia", "security", "hack", "robot")):
        return "driving"
    return "energetic"


def _incompetech_score(piece: dict, mood: str) -> float | None:
    """Incompetech parçasının modern Reels/TikTok uygunluğunu puanlar; uygunsuzsa None."""
    filename = str(piece.get("filename") or "").strip()
    title = str(piece.get("title") or "").strip()
    if not filename or not title or not filename.lower().endswith(".mp3"):
        return None
    genre = str(piece.get("genre") or "").strip()
    if genre not in MODERN_INCOMPETECH_GENRES:
        return None
    feel = str(piece.get("feel") or "").lower()
    desc = str(piece.get("description") or "").lower()
    instruments = str(piece.get("instruments") or "").lower()
    haystack = f"{title.lower()} {feel} {desc}"

    if any(bad in haystack for bad in BANNED_MUSIC_FEELS):
        return None
    if any(bad in instruments for bad in BANNED_INSTRUMENTS):
        return None
    if not any(good in instruments for good in MODERN_INSTRUMENTS):
        return None

    seconds = _parse_hms(piece.get("length"))
    if seconds and (seconds < 45 or seconds > MAX_MUSIC_SECONDS):
        return None

    try:
        bpm = int(piece.get("bpm") or 0)
    except (TypeError, ValueError):
        bpm = 0
    if bpm and not (78 <= bpm <= 150):
        return None

    score = 10.0
    if genre in ("7", "16", "6", "26"):  # Electronica / Modern Pop / Synth
        score += 8.0
    if "synth" in instruments:
        score += 5.0
    if "drum" in instruments or "bass" in instruments:
        score += 4.0

    mood_tokens = {
        "energetic": ("bright", "uplifting", "grooving", "bouncy", "driving"),
        "driving": ("driving", "action", "grooving", "intense", "dark"),
        "chill": ("relaxed", "calming", "grooving", "bright"),
        "cinematic": ("epic", "driving", "mysterious", "action", "uplifting"),
    }.get(mood, ("grooving", "driving", "bright"))
    score += sum(3.0 for tok in mood_tokens if tok in feel)
    return score


def _find_incompetech_music(mood: str, used: set[str], dest: Path) -> dict | None:
    """Incompetech (Kevin MacLeod, CC BY 4.0) kataloğundan modern şarkı seçip indirir."""
    resp = http_get(INCOMPETECH_CATALOG, retries=2, timeout=20)
    if resp is None or resp.status_code != 200:
        log.warning("Incompetech kataloğu alınamadı (status=%s)", resp.status_code if resp else "none")
        return None
    try:
        pieces = resp.json() or []
    except ValueError:
        return None

    candidates: list[tuple[float, dict]] = []
    for piece in pieces:
        title = str(piece.get("title") or "").strip()
        filename = str(piece.get("filename") or "").strip()
        url = INCOMPETECH_MP3.format(filename=quote(filename))
        if title.lower() in used or url.lower() in used:
            continue
        sc = _incompetech_score(piece, mood)
        if sc is not None:
            candidates.append((sc, piece))

    if not candidates:
        return None

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    # En yüksek puanlı 25 şarkı arasından rastgele seçerek her videoda çeşitlilik sağla
    top_pool = [p for _, p in candidates[:25]]
    random.shuffle(top_pool)

    for piece in top_pool[:5]:
        title = str(piece.get("title") or "").strip()
        filename = str(piece.get("filename") or "").strip()
        url = INCOMPETECH_MP3.format(filename=quote(filename))
        if _download(url, dest):
            seconds = _parse_hms(piece.get("length"))
            log.info(
                "Modern müzik indirildi (Incompetech/%s): %s (bpm=%s, feel=%s)",
                mood, title, piece.get("bpm"), piece.get("feel"),
            )
            return {
                "path": dest,
                "title": title,
                "artist": "Kevin MacLeod (incompetech.com)",
                "license": "CC BY 4.0 (http://creativecommons.org/licenses/by/4.0/)",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "url": url,
                "source": "incompetech",
                "duration": seconds,
            }
    return None


def _find_openverse_music(mood: str, used: set[str], dest: Path) -> dict | None:
    """Openverse Audio API'den CC0 / CC-BY modern beat/şarkı indirir."""
    queries = list(MOOD_OPENVERSE_QUERIES.get(mood, MOOD_OPENVERSE_QUERIES["energetic"]))
    random.shuffle(queries)
    for query in queries[:2]:
        params = {
            "q": query,
            "category": "music",
            "license_type": "commercial",
            "page_size": 12,
        }
        resp = http_get(f"{OPENVERSE_AUDIO}?{urlencode(params)}", retries=1, timeout=15)
        if resp is None or resp.status_code != 200:
            continue
        try:
            results = resp.json().get("results", []) or []
        except ValueError:
            continue
        random.shuffle(results)
        for item in results:
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            creator = str(item.get("creator") or "Bilinmiyor").strip()
            lic = str(item.get("license") or "").lower()
            lic_url = str(item.get("license_url") or "")
            dur_ms = int(item.get("duration") or 0)
            if not url or not url.lower().endswith(".mp3"):
                continue
            if title.lower() in used or url.lower() in used:
                continue
            if dur_ms and (dur_ms < MIN_MUSIC_SECONDS * 1000 or dur_ms > MAX_MUSIC_SECONDS * 1000):
                continue
            if lic not in ("cc0", "pdm", "by", "by-sa"):
                continue
            haystack = f"{title} {creator}".lower()
            if any(term in haystack for term in BANNED_AUDIO_TERMS):
                continue
            if _download(url, dest):
                log.info("Modern müzik indirildi (Openverse/%s): %s – %s", mood, title, creator)
                return {
                    "path": dest,
                    "title": title or "Openverse Track",
                    "artist": creator,
                    "license": f"CC {lic.upper()} (ticari kullanıma uygun)",
                    "license_url": lic_url,
                    "url": str(item.get("foreign_landing_url") or url),
                    "source": "openverse",
                    "duration": dur_ms / 1000.0 if dur_ms else 0.0,
                }
    return None


def _license_ok(license_url: str) -> bool:
    """Ticari kullanıma uygun lisans kontrolü (NC/ND hariç tutulur)."""
    if not license_url:
        return False
    low = license_url.lower()
    if any(tok in low for tok in BANNED_LICENSE_TOKENS):
        return False
    return any(tok in low for tok in ALLOWED_LICENSE_TOKENS)


def _search_archive(query: str, *, rows: int = 12) -> list[dict]:
    """Internet Archive'da enstrümantal MP3 müzik arar (son çare yedek)."""
    q = (
        f'mediatype:(audio) AND format:(MP3) AND '
        f'({query}) NOT subject:(vocals) NOT subject:(podcast) '
        f'NOT subject:(speech) NOT subject:(audiobook) NOT subject:(soundtrack)'
    )
    url = (
        f"{ARCHIVE_SEARCH}?q={quote(q)}"
        "&fl[]=identifier&fl[]=title&fl[]=creator&fl[]=licenseurl&fl[]=downloads"
        f"&sort[]=downloads+desc&rows={rows}&output=json"
    )
    resp = http_get(url, retries=1, timeout=20)
    if resp is None or resp.status_code != 200:
        return []
    try:
        return resp.json().get("response", {}).get("docs", []) or []
    except ValueError:
        return []


def _find_mp3(identifier: str) -> tuple[str, float] | None:
    resp = http_get(ARCHIVE_META.format(identifier=identifier), retries=1, timeout=15)
    if resp is None or resp.status_code != 200:
        return None
    try:
        files = resp.json().get("files", []) or []
    except ValueError:
        return None
    for f in files:
        fmt = (f.get("format") or "").upper()
        name = f.get("name") or ""
        if "MP3" not in fmt or not name.lower().endswith(".mp3"):
            continue
        try:
            size = int(f.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if size and size > MAX_MUSIC_BYTES:
            continue
        seconds = _parse_hms(f.get("length"))
        return name, seconds
    return None


def _download(url: str, dest: Path) -> bool:
    resp = http_get(url, retries=2, timeout=45)
    if resp is None or resp.status_code != 200:
        return False
    data = resp.content
    if not data or len(data) < 25_000 or len(data) > MAX_MUSIC_BYTES:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def find_music(
    llm,
    title: str,
    entities: list[str],
    *,
    duration: float,
    dest: Path,
) -> dict | None:
    """Konuya uygun modern, kaliteli, telifsiz müzik indirir (Incompetech → Openverse → Archive)."""
    used = _load_used_music()
    mood = _pick_mood(llm, title, entities)
    log.info("Müzik atmosferi seçildi: %s", mood)

    # 1. Öncelik: Incompetech (Kevin MacLeod — CC BY 4.0 stüdyo prodüksiyon)
    found = _find_incompetech_music(mood, used, dest)
    if found:
        return found

    # 2. Yedek: Openverse Audio API (CC0 / CC BY modern beat/synth)
    found = _find_openverse_music(mood, used, dest)
    if found:
        return found

    # 3. Son çare: Internet Archive
    seen: set[str] = set()
    for doc in _search_archive("subject:(electronic) OR subject:(synthwave) OR subject:(lofi)"):
        ident = str(doc.get("identifier") or "").strip()
        if not ident or ident in seen:
            continue
        seen.add(ident)
        meta_haystack = f"{ident} {doc.get('title') or ''} {doc.get('creator') or ''}".lower()
        if any(term in meta_haystack for term in BANNED_AUDIO_TERMS):
            continue
        lic_url = str(doc.get("licenseurl") or "")
        if not _license_ok(lic_url):
            continue
        mp3 = _find_mp3(ident)
        if not mp3:
            continue
        filename, seconds = mp3
        if seconds and (seconds < MIN_MUSIC_SECONDS or seconds > MAX_MUSIC_SECONDS):
            continue
        url = ARCHIVE_DOWNLOAD.format(identifier=ident, filename=filename)
        if url.lower() in used:
            continue
        if _download(url, dest):
            log.info("Yedek müzik indirildi (Archive): %s (%s)", ident, filename)
            return {
                "path": dest,
                "title": str(doc.get("title") or ident),
                "artist": str(doc.get("creator") or "Bilinmiyor"),
                "license": "Creative Commons (ticari kullanıma uygun)",
                "license_url": lic_url,
                "url": f"https://archive.org/details/{ident}",
                "source": "internet-archive",
                "duration": seconds,
            }

    log.info("Uygun telifsiz müzik bulunamadı; video sessiz kalacak.")
    return None
