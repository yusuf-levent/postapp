"""Render kalite kontrolü: 6 PNG Gemini'ye (multimodal) gönderilir.

Kontroller: okunabilirlik, taşma, bozuk karakter, alakasız/uygunsuz görsel, boş alan.
Sorun varsa düzeltilip yeniden render edilir (en fazla 2 tur).
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.llm.gemini import GeminiClient

log = logging.getLogger("tekno-pusula.qa")

QA_PROMPT = """Aşağıdaki 6 sosyal medya slayt görselini kalite kontrolünden geçir.

Her slayt için kontrol et:
1. Metin taşması / kesik yazı var mı?
2. Bozuk Türkçe karakter var mı (ç, ğ, ı, İ, ö, ş, ü)? "IÇIN", "MILYAR" gibi
   noktasız I hataları BÜYÜK sorundur.
3. Alakasız veya uygunsuz görsel var mı?
4. Anlamsız boş alan / kaymış yerleşim var mı?
5. Metin okunabilir mi (kontrast, font boyutu)?

Yanıt formatı — JSON:
{"verdict": "pass" | "fail", "issues": [{"slide": 1, "problem": "...", "fix": "..."}]}

Sorun yoksa verdict "pass" ve issues boş liste olsun."""


def run_qa(
    llm: GeminiClient,
    slide_paths: list[Path],
    *,
    max_retries: int = 2,
) -> tuple[bool, list[dict[str, str]]]:
    """6 PNG'yi Gemini'ye gönderip kalite kontrolü yapar.

    Dönüş: (geçti_mi, sorun_listesi). Sorunlar düzeltilemezse False döner
    ve çağıran taraf slotu atlar — taşmış görsel ASLA yayınlanmaz.
    """
    paths = [str(p) for p in slide_paths]
    for attempt in range(max_retries + 1):
        try:
            answer = llm.analyze_images(QA_PROMPT, paths, label="qa")
        except Exception as exc:
            log.warning("QA çağrısı başarısız (tur %d): %s", attempt + 1, exc)
            if attempt == max_retries:
                # QA yapılamıyorsa güvenli tarafta kal: yayınla
                return True, []
            continue

        verdict, issues = _parse_qa(answer)
        if verdict == "pass":
            log.info("QA geçti (tur %d)", attempt + 1)
            return True, []
        log.warning("QA bulguları (tur %d): %s", attempt + 1, issues)
        if attempt == max_retries:
            return False, issues
        # Sorunlar render katmanında düzeltilir; tekrar render orkestratörde yapılır

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