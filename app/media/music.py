"""Otomatik telifsiz fon müziği seçimi ve indirme (ücretsiz, anahtarsız).

Kaynak: Internet Archive (advancedsearch.php + metadata API) — API key gerektirmez.

Kurallar:
1. Haber konusuna göre Gemini 2-4 basit müzik etiketi üretir (örn. "technology ambient corporate").
2. Internet Archive'da MP3 formatında, ticari kullanıma uygun (CC0 / CC-BY / CC-BY-SA)
   enstrümantal müzik aranır. Lisansı belirsiz veya NC (ticari olmayan) kayıtlar ATLANIR.
3. Seçilen parça indirilir; video süresine göre FFmpeg ile kırpılır (gerekiyorsa loop).
4. Kullanılan müziğin adı + sanatçı + lisans bilgisi döndürülür (credits.json'a yazılır).

Hiç uygun müzik bulunamazsa None döner; video sessiz bırakılır (sessiz Reels normaldir).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from urllib.parse import quote

from app.common import http_get

log = logging.getLogger("tekno-pusula.music")

ARCHIVE_SEARCH = "https://archive.org/advancedsearch.php"
ARCHIVE_META = "https://archive.org/metadata/{identifier}"
ARCHIVE_DOWNLOAD = "https://archive.org/download/{identifier}/{filename}"

# Ticari kullanıma uygun lisans anahtarları (URL'de geçen parçalar)
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
# Ticari kullanıma UYGUN OLMAYAN lisanslar (NC, ND vb.)
BANNED_LICENSE_TOKENS = ("noncommercial", "non-commercial", "/nc/", "-nc", "-nd", "by-nc", "noderiv")

MAX_MUSIC_BYTES = 30 * 1024 * 1024  # 30 MB üst sınır
MAX_MUSIC_SECONDS = 300  # 5 dakika üst sınır (güvenlik)


def music_query_tags(llm, title: str, entities: list[str]) -> list[str]:
    """Haber konusuna göre müzik arama etiketleri üretir (düşük sıcaklıktaki LLM)."""
    prompt = (
        f"News headline: {title}\n"
        f"Entities: {', '.join(entities or [])}\n\n"
        "Task: output 3 English music search tags suitable as calm background music for this "
        "news video. Choose mood/genre tags like: ambient, corporate, technology, electronic, "
        "documentary, cinematic, uplifting, minimal, synth, modern. "
        "NEVER output artist names or song titles, ONLY mood/genre tags. "
        "One tag per line."
    )
    try:
        ans = llm.generate_text(prompt, label="music-tags").strip()
    except Exception as exc:  # LLM yoksa genel etiketlere düş
        log.warning("Müzik etiketi üretilemedi: %s", exc)
        return ["ambient", "technology", "corporate"]
    out: list[str] = []
    for line in ans.splitlines():
        t = re.sub(r"[^a-z0-9 \-]", " ", line.lower()).strip()
        if 2 < len(t) < 30 and t not in out:
            out.append(t)
    return (out[:4] or ["ambient", "technology", "corporate"])


def _license_ok(license_url: str) -> bool:
    """Ticari kullanıma uygun lisans kontrolü (NC/ND hariç tutulur)."""
    if not license_url:
        return False
    low = license_url.lower()
    if any(tok in low for tok in BANNED_LICENSE_TOKENS):
        return False
    return any(tok in low for tok in ALLOWED_LICENSE_TOKENS)


def _search_archive(query: str, *, rows: int = 12) -> list[dict]:
    """Internet Archive'da enstrümantal MP3 müzik arar."""
    # format:(MP3) + mediatype:(audio) + enstrümantal ipuçları
    q = (
        f'mediatype:(audio) AND format:(MP3) AND '
        f'({query}) NOT subject:(vocals)'
    )
    url = (
        f"{ARCHIVE_SEARCH}?q={quote(q)}"
        "&fl[]=identifier&fl[]=title&fl[]=creator&fl[]=licenseurl&fl[]=downloads"
        "&sort[]=downloads+desc&rows={rows}&output=json"
    ).format(rows=rows)
    resp = http_get(url, retries=2, timeout=25)
    if resp is None or resp.status_code != 200:
        log.warning("Archive.org arama başarısız (status=%s)", resp.status_code if resp else "none")
        return []
    try:
        docs = resp.json().get("response", {}).get("docs", []) or []
    except ValueError:
        return []
    return docs


def _find_mp3(identifier: str) -> tuple[str, float] | None:
    """Identifier için MP3 dosya adı ve saniye cinsinden süreyi döndürür."""
    resp = http_get(ARCHIVE_META.format(identifier=identifier), retries=2, timeout=20)
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
        length = f.get("length")
        seconds = 0.0
        if isinstance(length, (int, float)):
            seconds = float(length)
        elif isinstance(length, str):
            # "2:06" biçiminde olabilir
            parts = length.split(":")
            try:
                seconds = sum(float(p) * (60 ** (len(parts) - 1 - i)) for i, p in enumerate(parts))
            except ValueError:
                seconds = 0.0
        return name, seconds
    return None


def _download(url: str, dest: Path) -> bool:
    resp = http_get(url, retries=2, timeout=45)
    if resp is None or resp.status_code != 200:
        return False
    data = resp.content
    if not data or len(data) < 20_000 or len(data) > MAX_MUSIC_BYTES:
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
    """Konuya uygun telifsiz müziği indirir. Bulamazsa None döner.

    Dönen dict: {"path": Path, "title": ..., "artist": ..., "license": ..., "license_url": ..., "url": ...}
    """
    tags = music_query_tags(llm, title, entities)
    log.info("Müzik arama etiketleri: %s", tags)

    queries = [
        "(" + " OR ".join(f"subject:({t})" for t in tags) + ")",
        "(" + " OR ".join(f"title:({t})" for t in tags) + ")",
        "subject:(background) AND subject:(instrumental)",
    ]
    seen: set[str] = set()
    for query in queries:
        for doc in _search_archive(query):
            ident = str(doc.get("identifier") or "").strip()
            if not ident or ident in seen:
                continue
            seen.add(ident)
            lic_url = str(doc.get("licenseurl") or "")
            if not _license_ok(lic_url):
                continue
            mp3 = _find_mp3(ident)
            if not mp3:
                continue
            filename, seconds = mp3
            if seconds and seconds > MAX_MUSIC_SECONDS:
                continue
            url = ARCHIVE_DOWNLOAD.format(identifier=ident, filename=filename)
            if _download(url, dest):
                log.info("Müzik indirildi: %s (%s)", ident, filename)
                return {
                    "path": dest,
                    "title": str(doc.get("title") or ident),
                    "artist": str(doc.get("creator") or "Bilinmiyor"),
                    "license": "Creative Commons (ticari kullanıma uygun)",
                    "license_url": lic_url,
                    "url": f"https://archive.org/details/{ident}",
                    "source": "internet-archive",
                }
    log.info("Uygun telifsiz müzik bulunamadı; video sessiz kalacak.")
    return None