"""Türkçe büyük/küçük harf dönüşüm testleri (en kritik görsel hata kaynağı)."""
from __future__ import annotations

from app.common import slugify, turkish_lower, turkish_upper, normalize_text
from app.render.turkish import ensure_no_dotless_i_bug, tr_lower, tr_title, tr_upper


def test_upper_icin():
    assert tr_upper("için") == "İÇİN"
    assert tr_upper("için") != "IÇIN"


def test_upper_milyarlarca():
    assert tr_upper("milyarlarca") == "MİLYARLARCA"


def test_upper_mixed():
    assert tr_upper("yapay zeka") == "YAPAY ZEKA"


def test_upper_with_i_and_i_dotless():
    # "ılık" → "ILIK" (ı → I), "ilk" → "İLK" (i → İ)
    assert tr_upper("ılık") == "ILIK"
    assert tr_upper("ilk") == "İLK"


def test_upper_preserves_existing_turkish_upper():
    assert tr_upper("İstanbul") == "İSTANBUL"
    assert tr_upper("Iğdır") == "IĞDIR"


def test_lower_i():
    assert tr_lower("İSTANBUL") == "istanbul"
    assert tr_lower("ILIK") == "ılık"


def test_title_case():
    result = tr_title("yapay zeka çipleri")
    assert result == "Yapay Zeka Çipleri"


def test_no_dotless_i_bug():
    # "İÇİN" doğru; "IÇIN" hatalı kalıp
    assert ensure_no_dotless_i_bug("İÇİN İÇİN")
    assert not ensure_no_dotless_i_bug("IÇIN IÇIN")


def test_common_upper_matches_render_upper():
    assert turkish_upper("için") == tr_upper("için")


def test_normalize_text_turkish():
    assert normalize_text("Şirket Çip Üretiyor!") == "sirket cip uretiyor"


def test_slugify_turkish():
    assert slugify("Yapay Zeka: Büyük Devrim!") == "yapay-zeka-buyuk-devrim"


def test_upper_emoji_safe():
    assert "💬" in tr_upper("yorum yap 💬")