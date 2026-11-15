"""Görsel seçimi: slaytlar için öncelikli görsel kaynakları + alakalılık kontrolü.

Öncelik: gerçek kişi (Wikimedia) → ürün/olay (og:image / resmi) → Pexels → soyut.
Her slayt için UYGUN bir arka plan seçilir; 6 slaytta da aynı görsel kullanılmaz.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.common import turkish_lower
from app.config import brand_config
from app.llm import prompts
from app.llm.gemini import GeminiClient
from app.media import ogimage, pexels, wikimedia
from app.models import Candidate, ImageCandidate, SearchQueries

log = logging.getLogger("tekno-pusula.media")


def collect_images(
    llm: GeminiClient,
    candidate: Candidate,
    entities: list[str],
    post_dir: Path,
    *,
    min_width: int = 1000,
) -> list[ImageCandidate]:
    """Slaytlar için görsel toplar, indirir, alakalılığı Gemini ile doğrular.

    Dönüş: en fazla 6 görsel (her slayt için bir adet). Hiçbiri yoksa soyut
    gradient üretilir (render katmanı CSS ile çizer).
    """
    images_dir = post_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    selected: list[ImageCandidate] = []

    # 1. Gerçek kişiler (haberde CEO/araştırmacı vb. geçiyorsa)
    for person in _person_entities(entities):
        if len(selected) >= 3:
            break
        cand = wikimedia.person_image(person)
        if cand and _accept_and_save(llm, cand, candidate, images_dir, min_width, selected):
            log.info("Kişi görseli alındı: %s", person)

    # 2. Ürün/olay görseli: makalenin og:image'i
    if len(selected) < 3:
        cand = ogimage.og_image(candidate.url, min_width=min_width)
        if cand and _accept_and_save(llm, cand, candidate, images_dir, min_width, selected):
            log.info("og:image alındı")

    # 3. Pexels — Gemini'nin ürettiği İngilizce sorgularla
    queries = _image_queries(llm, candidate)
    for query in queries:
        if len(selected) >= 3:
            break
        for cand in pexels.search_images(query, min_width=min_width)[:2]:
            if len(selected) >= 3:
                break
            if _accept_and_save(llm, cand, candidate, images_dir, min_width, selected):
                log.info("Pexels görseli alındı: %s", query)

    # Do not fill remaining slots with unrelated generic chips/office images.
    _write_credits(post_dir, selected)
    return selected


def _accept_and_save(
    llm: GeminiClient,
    img: ImageCandidate,
    candidate: Candidate,
    images_dir: Path,
    min_width: int,
    already: list[ImageCandidate],
) -> bool:
    """Görseli indirir, boyut + alakalılık kontrolünden geçirir, kabul eder."""
    if img.width and img.width < min_width:
        return False
    # Aynı görseli iki kez kullanma
    if any(a.url == img.url for a in already):
        return False

    dest = images_dir / f"img-{len(already)+1}.png"
    from app.media.ogimage import download_image

    ok, width, height = download_image(img.url, str(dest))
    if not ok or width < min_width:
        log.debug("Görsel indirilemedi veya çok dar: %s", img.url)
        dest.unlink(missing_ok=True)
        return False
    img.local_path = str(dest)
    img.width = width
    img.height = height

    # Alakalılık kontrolü (Gemini multimodal)
    if not _is_relevant(llm, img, candidate):
        log.info("Görsel alakasız bulundu, atlanıyor: %s", img.url)
        dest.unlink(missing_ok=True)
        return False

    already.append(img)
    return True


def _is_relevant(llm: GeminiClient, img: ImageCandidate, candidate: Candidate) -> bool:
    """Gemini'ye 'bu görsel konuyla alakalı mı?' diye sorar."""
    if not img.local_path:
        return True
    prompt = prompts.IMAGE_RELEVANCE_PROMPT.format(title=candidate.title)
    try:
        answer = llm.analyze_images(
            prompt, [img.local_path], label="img-relevance"
        )
    except Exception as exc:
        log.warning("Görsel alakalılık kontrolü yapılamadı, görsel atlandı: %s", exc)
        return False
    normalized = turkish_lower(answer.strip())[:20]
    return normalized.startswith("evet") or normalized.startswith("yes")


def _image_queries(llm: GeminiClient, candidate: Candidate) -> list[str]:
    """Gemini'den İngilizce Pexels arama sorguları üretir."""
    prompt = prompts.IMAGE_QUERY_PROMPT.format(
        title=candidate.title, summary=candidate.summary[:1000]
    )
    try:
        result = llm.generate_structured(
            prompt + "\nReturn queries as a JSON list field, at most 2 short English noun phrases. No introduction.",
            SearchQueries, label="img-queries",
        )
    except Exception as exc:
        log.warning("Görsel sorgusu üretilemedi: %s", exc)
        return []
    return [q.strip() for q in result.queries if 3 < len(q.strip()) <= 60][:2]


def _person_entities(entities: list[str]) -> list[str]:
    """Entity listesinden kişi olabilecekleri ayırır (2-3 kelimelik adlar)."""
    return [e for e in entities if 1 < len(e.split()) <= 4][:2]


def _write_credits(post_dir: Path, images: list[ImageCandidate]) -> None:
    """credits.json: görsel lisans ve kaynak bilgileri (mevcut müzik/video kredilerini korur)."""
    credits_path = post_dir / "credits.json"
    credits: dict[str, Any] = {}
    if credits_path.exists():
        try:
            credits = json.loads(credits_path.read_text(encoding="utf-8"))
        except Exception:
            credits = {}
    credits["images"] = [
        {
            "source": img.source,
            "url": img.url,
            "local_path": img.local_path,
            "license": img.license,
            "author": img.author,
            "credit_url": img.credit_url,
            "width": img.width,
            "height": img.height,
            "alt_text": img.alt_text,
        }
        for img in images
    ]
    credits["note"] = "Görsel lisansları ilgili kaynakların kendi şartlarına tabidir."
    credits_path.write_text(
        json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def make_abstract_background(dest: Path, *, variant: int = 0) -> Path:
    """Hiç görsel yoksa markaya uygun, görünür silikon/wafer/teknoloji dokulu arka plan üretir.

    Yapay zekayla görsel üretimi YAPILMAZ; bu saf Pillow prosedürel dokusudur.
    """
    import math
    from PIL import Image, ImageDraw, ImageFilter

    w, h = 1080, 1350
    img = Image.new("RGB", (w, h), (10, 14, 22))
    draw = ImageDraw.Draw(img)

    # Zengin koyu teknoloji gradyanı + sıcak/soğuk silikon yansımaları
    palettes = [
        ((38, 32, 24), (16, 28, 44), (8, 10, 16)),   # sıcak altın/silikon -> lacivert
        ((14, 38, 52), (22, 26, 38), (8, 10, 16)),   # cyan teknoloji -> koyu
        ((34, 28, 18), (18, 22, 30), (7, 9, 13)),    # bakır wafer -> koyu
    ]
    top_c, mid_c, bot_c = palettes[variant % len(palettes)]

    for y in range(h):
        t = y / h
        if t < 0.55:
            u = t / 0.55
            r = int(top_c[0] * (1 - u) + mid_c[0] * u)
            g = int(top_c[1] * (1 - u) + mid_c[1] * u)
            b = int(top_c[2] * (1 - u) + mid_c[2] * u)
        else:
            u = (t - 0.55) / 0.45
            r = int(mid_c[0] * (1 - u) + bot_c[0] * u)
            g = int(mid_c[1] * (1 - u) + bot_c[1] * u)
            b = int(mid_c[2] * (1 - u) + bot_c[2] * u)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # Çip / wafer perspektif ızgara ve mikro-devre blokları (üst %65'te belirgin)
    cx, cy = w // 2, int(h * 0.30)
    if variant % 3 == 0:
        # Kapak stili: metalik çip çerçevesi + silikon die ızgarası
        frame = [190, 80, 890, 680]
        draw.rounded_rectangle(frame, radius=18, fill=(88, 82, 72), outline=(140, 132, 118), width=4)
        die = [270, 175, 810, 595]
        draw.rectangle(die, fill=(14, 22, 30), outline=(45, 75, 95), width=3)
        for gx in range(die[0] + 55, die[2], 90):
            draw.line([(gx, die[1]), (gx, die[3])], fill=(52, 74, 88), width=2)
        for gy in range(die[1] + 55, die[3], 84):
            draw.line([(die[0], gy), (die[2], gy)], fill=(52, 74, 88), width=2)
    else:
        # İç slayt stili: diyagonal wafer devre dokusu
        for i in range(-h, w + h, 44):
            draw.line([(i, 0), (i - int(h * 0.6), h)], fill=(38, 48, 62), width=2)
        for i in range(0, w + h, 64):
            draw.line([(0, i), (w, i - int(w * 0.5))], fill=(30, 40, 54), width=1)
        for bx in range(120, w - 120, 180):
            for by in range(100, h - 200, 160):
                if (bx + by + variant * 30) % 3 == 0:
                    draw.rectangle(
                        [bx, by, bx + 110, by + 70],
                        outline=(0, 140, 180) if variant % 2 else (160, 135, 50),
                        width=2,
                    )

    img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "PNG")
    return dest
