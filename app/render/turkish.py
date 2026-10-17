"""Türkçe metin işleme: büyük/küçük harf kuralları (i→İ, ı→I)."""
from __future__ import annotations

import re


# İngilizce marka ve teknik terimler: "i -> İ" yapılmaz, standart "I" kullanılır
TECH_ASCII_WORDS = {
    "microsoft", "nvidia", "maia", "chiplet", "tsmc", "silicon", "copilot",
    "github", "openai", "deepmind", "anthropic", "google", "meta", "apple",
    "amazon", "aws", "azure", "intel", "amd", "qualcomm", "broadcom", "arm",
    "samsung", "huawei", "ibm", "oracle", "adobe", "mistral", "deepseek",
    "xai", "hugging", "linkedin", "tiktok", "instagram", "threads", "facebook",
    "twitter", "buffer", "linux", "windows", "android", "ios", "python",
    "javascript", "typescript", "rust", "golang", "docker", "kubernetes",
    "api", "gpu", "cpu", "npu", "tpu", "llm", "ai", "agi", "ram", "vram",
    "ssd", "pcie", "wifi", "bluetooth", "usb", "hdmi", "oled", "miniled",
}


def tr_upper(text: str) -> str:
    """Türkçe kurallarıyla büyük harf. 'IÇIN' gibi hatalar asla oluşmaz.

    İngilizce marka ve teknik terimler (Microsoft, Nvidia, Maia, AI vb.)
    'MİCROSOFT' olmaması için standart büyük harfe (MICROSOFT) çevrilir.
    """
    def _word_upper(m: re.Match[str]) -> str:
        w = m.group(0)
        if w.lower() in TECH_ASCII_WORDS:
            return w.replace("İ", "I").replace("ı", "I").upper()
        return w.replace("i", "İ").replace("ı", "I").upper()

    return re.sub(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", _word_upper, text)


def tr_lower(text: str) -> str:
    """Türkçe kurallarıyla küçük harf: İ→i, I→ı."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def tr_title(text: str) -> str:
    """Başlık formatı: her kelimenin ilk harfi büyük (Türkçe kurallarıyla)."""
    words = text.split(" ")
    out = []
    for w in words:
        if w.isupper() and len(w) > 3:
            out.append(tr_upper(w))  # kısaltmalar büyük kalır
        else:
            out.append(tr_upper(w[:1]) + tr_lower(w[1:]) if w else w)
    return " ".join(out)


def ensure_no_dotless_i_bug(text: str) -> bool:
    """Yanlış büyük harf dönüşümü kontrolü: 'IÇIN', 'MILYARLARCA' gibi hatalar.

    Türkçe'de "için" → "İÇİN" olmalı; "IÇIN" yazarsak hata vardır.
    Bu kontrol, İ/ı dönüşümünden SONRA metinde hata kalmadığını doğrular.
    """
    # Bilinen hatalı kalıplar: noktasız I + Türkçe harf kombinasyonları
    buggy_patterns = [
        r"I[ÇĞŞÖÜ]",   # IÇ, IĞ, IŞ, IÖ, IÜ — "i"den gelmeliyse İ olmalıydı
        r"[ÇĞŞÖÜ]I",   # ÇI vb. — bu doğru olabilir (çı → ÇI), o yüzden sadece kontrol
    ]
    # Gerçek hata tespiti için orijinal metin gerekir; bu fonksiyon
    # yalnızca IÇIN gibi bilinen yanlış kalıpları yakalar.
    return not re.search(r"I[ÇĞŞÖÜ]", text)


def wrap_text(text: str, max_line_chars: int) -> str:
    """Metni satır uzunluğu sınırına göre böler (CSS'te de kırılır, bu ek güvence)."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        if current and len(" ".join(current + [word])) > max_line_chars:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)