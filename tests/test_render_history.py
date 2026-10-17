"""Render taşma kontrolü ve history testleri."""
from __future__ import annotations

from pathlib import Path

from app.models import HistoryEntry
from app.render.fit import enforce_min_sizes
from app.render.renderer import render_slide_html
from app.render.turkish import tr_upper
from app.store import history as history_store


# ---------------------------------------------------------------- render html
def _deck() -> dict:
    return {
        "cover": {
            "category_label": "yapay zeka donanımı",
            "title": "Microsoft Maia 300 tanıtıldı",
            "highlight_words": ["Maia 300"],
            "highlight_color": "yellow",
            "subtitle": "şirketin ilk özel yapay zeka çipi",
            "source_tags": ["the verge", "microsoft"],
        },
        "context": {
            "heading": "ne oldu?",
            "cards": [
                {"card_title": "ilk çip", "card_body": "Şirket özel çipini tanıttı."},
                {"card_title": "verimlilik", "card_body": "%40 daha verimli olduğu açıklandı."},
            ],
        },
        "stat": {
            "big_stat": "%40",
            "stat_caption": "daha verimli",
            "stat_quote": "Şirket, yeni çipin %40 daha verimli olduğunu açıkladı.",
        },
        "details": {
            "heading": "nasıl çalışıyor?",
            "cards": [
                {"card_title": "mimari", "card_body": "Özel tasarım bir mimari kullanılıyor."},
                {"card_title": "üretim", "card_body": "Gelişmiş üretim süreciyle üretiliyor."},
            ],
        },
        "impact": {
            "heading": "neden önemli?",
            "cards": [
                {"card_title": "sektör", "card_body": "Yeni bir rekabet alanı açılıyor."},
                {"card_title": "kullanıcı", "card_body": "Daha hızlı hizmetler gelebilir."},
            ],
        },
        "cta": {
            "question": "Sizce özel çip yarışında kim öne geçecek?",
            "reminder_line": "Düşüncelerini yorumlarda paylaşmayı unutma! 💬",
        },
        "bg_image": "",
        "logo_svg": "",
        "tag_label_2": "BAĞLAM",
        "tag_label_3": "ÖNE ÇIKAN RAKAM",
        "tag_label_4": "DETAYLAR",
        "tag_label_5": "NEDEN ÖNEMLİ?",
        "tag_label_6": "ETKİLEŞİM",
    }


def test_cover_renders_turkish_upper():
    html = render_slide_html(_deck(), 1)
    assert 'lang="tr"' in html
    # Türkçe büyük harf kuralları: Türkçe kelimelerde i → İ, ı → I;
    # İngilizce teknoloji markalarında (Microsoft, Maia) ASCII I korunur.
    assert "YAPAY ZEKA DONANIMI" in html
    assert "MICROSOFT" in html
    assert "MİCROSOFT" not in html
    assert "ŞİRKETİN İLK ÖZEL YAPAY ZEKA ÇİPİ" in html
    assert "TANITILDI" in html
    assert "IÇIN" not in html  # noktasız I hatası olmamalı


def test_cover_highlight_span():
    html = render_slide_html(_deck(), 1)
    assert 'class="hl-yellow"' in html
    assert "MAIA 300" in html


def test_content_slide_uses_cards_and_bullets():
    html = render_slide_html(_deck(), 2)
    assert "card-badge" in html
    assert "01" in html
    assert '<span class="hl-yellow">NE</span> OLDU?' in html


def test_slides_are_full_html_documents():
    for i in (1, 2, 3, 6):
        html = render_slide_html(_deck(), i)
        assert html.lstrip().startswith("<!DOCTYPE html>")
        assert '<html lang="tr">' in html


def test_stat_slide_renders_big_number():
    html = render_slide_html(_deck(), 3)
    assert "%40" in html
    assert "DAHA VERİMLİ" in html


def test_cta_slide_renders():
    html = render_slide_html(_deck(), 6)
    assert "SENİN GÖRÜŞÜN NE?" in html
    assert "Kaydet" in html


def test_progress_dots_present():
    html = render_slide_html(_deck(), 2)
    assert html.count('class="dot') == 6


def test_no_dotless_i_bug_in_html():
    for i in range(1, 7):
        html = render_slide_html(_deck(), i)
        assert "IÇIN" not in html
        assert "MILYAR" not in html


# ------------------------------------------------------------------- fit
def test_enforce_min_sizes_floor():
    out = enforce_min_sizes({"cover_title_px": 30, "heading_px": 20, "body_px": 10})
    assert out["cover_title_px"] == 64
    assert out["heading_px"] == 32
    assert out["body_px"] == 18


# ---------------------------------------------------------------- history
def test_history_roundtrip(tmp_path, monkeypatch):
    fake_file = tmp_path / "history.json"
    monkeypatch.setattr(history_store, "HISTORY_FILE", fake_file)

    entry = HistoryEntry(
        id="2026-10-15-0900",
        date="2026-10-15",
        slot="09:00",
        type="news",
        title_tr="Başlık",
        original_title="Title",
        created_at="2026-10-15T09:00:00+03:00",
    )
    history_store.append_entry(entry)
    loaded = history_store.load_history()
    assert len(loaded) == 1
    assert loaded[0].id == "2026-10-15-0900"


def test_slot_already_done(tmp_path, monkeypatch):
    fake_file = tmp_path / "history.json"
    monkeypatch.setattr(history_store, "HISTORY_FILE", fake_file)

    entry = HistoryEntry(
        id="x", date="2026-10-15", slot="09:00", type="news",
        created_at="2026-10-15T09:00:00+03:00",
    )
    history_store.append_entry(entry)
    assert history_store.slot_already_done("2026-10-15", "09:00")
    assert not history_store.slot_already_done("2026-10-15", "12:00")


def test_append_replaces_same_id(tmp_path, monkeypatch):
    fake_file = tmp_path / "history.json"
    monkeypatch.setattr(history_store, "HISTORY_FILE", fake_file)

    for title in ("ilk", "ikinci"):
        history_store.append_entry(
            HistoryEntry(id="same", date="2026-10-15", slot="09:00",
                         type="news", title_tr=title,
                         created_at="2026-10-15T09:00:00+03:00")
        )
    loaded = history_store.load_history()
    assert len(loaded) == 1
    assert loaded[0].title_tr == "ikinci"