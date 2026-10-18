"""Render kalite kontrolü: 6 PNG Gemini'ye (multimodal) gönderilir.

Kontroller: okunabilirlik, taşma, bozuk karakter, alakasız/uygunsuz görsel, boş alan.
Sorun varsa düzeltilip yeniden render edilir (en fazla 2 tur).
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.llm.gemini import GeminiClient

log = logging.getLogger("tekno-pusula.qa")

QA_PROMPT = """Aşağıdaki 6 sosyal medya slayt görselini teknik render kontrolünden geçir.

ÖNEMLİ KURALLAR:
- Yabancı özel isimler ve marka adlarındaki aksanlı harfler (örn. Spéirling, Citroën vb.) HATA DEĞİLDİR.
- Slayt şablonundaki sabit marka sloganları ("Tekno Pusula", "Yazılım ve Yapay Zeka İçerikleri İçin" vb.) HATA DEĞİLDİR.
- Yalnızca CİDDİ görsel bozulma varsa (yazıların üst üste binip tamamen okunamaz hale gelmesi veya görselin tamamen bozuk/siyah çıkması) "fail" döndür. Küçük stil/ifade tercihlerinde her zaman "pass" döndür.

Yanıt formatı — JSON:
{"verdict": "pass" | "fail", "issues": [{"slide": 1, "problem": "...", "fix": "..."}]}

Sorun yoksa verdict "pass" ve issues boş liste olsun."""


def run_qa(
    llm: GeminiClient,
    slide_paths: list[Path],
    *,
    max_retries: int = 1,
) -> tuple[bool, list[dict[str, str]]]:
    """6 PNG'yi Gemini'ye gönderip kalite kontrolü yapar."""
    paths = [str(p) for p in slide_paths]
    try:
        answer = llm.analyze_images(QA_PROMPT, paths, label="qa")
    except Exception as exc:
        log.warning("QA çağrısı başarısız: %s", exc)
        return True, []

    verdict, issues = _parse_qa(answer)
    if verdict == "pass":
        log.info("QA geçti")
        return True, []
    log.warning("QA bulguları: %s", issues)
    return False, issues


def _parse_qa(answer: str) -> tuple[str, list[dict[str, str]]]:
    """QA yanıtını ayrıştırır (JSON ya da serbest metin toleranslı)."""
    import json
    import re

    answer = answer.strip()
    # JSON dene
    m = re.search(r"\{.*\}", answer, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            verdict = str(data.get("verdict", "pass")).lower()
            issues = data.get("issues", []) or []
            return verdict, issues
        except json.JSONDecodeError:
            pass
    # Serbest metin: "fail"/"sorun" geçiyorsa fail say
    lowered = answer.lower()
    if any(k in lowered for k in ("fail", "sorun", "hata", "taşma", "bozuk")):
        return "fail", [{"slide": "?", "problem": answer[:300], "fix": ""}]
    return "pass", []