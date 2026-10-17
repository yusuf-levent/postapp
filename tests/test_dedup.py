"""URL normalizasyonu ve dedup testleri."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models import Candidate, HistoryEntry
from app.select.dedup import is_duplicate, normalize_url, title_similarity


# ------------------------------------------------------------- normalize_url
def test_normalize_url_strips_utm():
    url = "https://www.theverge.com/news/123?utm_source=twitter&utm_medium=social&fbclid=abc"
    assert normalize_url(url) == "https://theverge.com/news/123"


def test_normalize_url_removes_www_and_trailing_slash():
    url = "https://www.techcrunch.com/story/ai-chip/"
    assert normalize_url(url) == "https://techcrunch.com/story/ai-chip"


def test_normalize_url_keeps_meaningful_params():
    url = "https://example.com/article?id=42&ref=nav"
    assert normalize_url(url) == "https://example.com/article?id=42"


def test_normalize_url_case_insensitive():
    a = normalize_url("https://WWW.Example.com/Path/")
    b = normalize_url("https://example.com/path")
    assert a == b


# ---------------------------------------------------------- title_similarity
def test_title_similarity_exact_match():
    assert title_similarity("NVIDIA yeni GPU duyurdu", "NVIDIA yeni GPU duyurdu") == 100.0


def test_title_similarity_high_for_reworded():
    sim = title_similarity(
        "OpenAI GPT-5 modelini resmen tanıttı",
        "OpenAI resmen GPT-5 modelini tanıttı",
    )
    assert sim >= 85


def test_title_similarity_low_for_different():
    sim = title_similarity(
        "Apple yeni iPhone çıkardı",
        "Yapay zeka ilaç keşfini hızlandırıyor",
    )
    assert sim < 60


def test_title_similarity_turkish_chars():
    sim = title_similarity("Şirket çip üretiyor", "Sirket cip uretiyor")
    assert sim == 100.0


# -------------------------------------------------------------- is_duplicate
def _hist(title: str, url: str = "", entities: list | None = None,
          event_type: str = "", days_ago: int = 0) -> HistoryEntry:
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return HistoryEntry(
        id=f"h-{days_ago}-{title[:10]}",
        date="2026-10-15",
        slot="09:00",
        type="news",
        title_tr=title,
        original_title=title,
        canonical_url=url,
        entities=entities or [],
        event_type=event_type,
        created_at=created.isoformat(),
    )


def test_duplicate_same_url():
    url = "https://techcrunch.com/story/ai-chip"
    cand = Candidate(title="Yeni haber", url=url, published=datetime.now(timezone.utc))
    dup, reason = is_duplicate(cand, [_hist("Başka başlık", url=url)])
    assert dup
    assert "canonical URL" in reason


def test_duplicate_similar_title():
    cand = Candidate(
        title="OpenAI GPT-5 modelini resmen tanıttı",
        url="https://example.com/new",
        published=datetime.now(timezone.utc),
    )
    hist = [_hist("OpenAI resmen GPT-5 modelini tanıttı", url="https://example.com/old")]
    dup, reason = is_duplicate(cand, hist)
    assert dup
    assert "başlık benzerliği" in reason


def test_duplicate_same_event_within_window():
    cand = Candidate(
        title="Tamamen farklı bir başlık",
        url="https://example.com/a",
        entities=["OpenAI"],
        event_type="product_launch",
        published=datetime.now(timezone.utc),
    )
    hist = [_hist("Bambaşka başlık", url="https://example.com/b",
                  entities=["OpenAI"], event_type="product_launch", days_ago=3)]
    dup, reason = is_duplicate(cand, hist)
    assert dup
    assert "aynı olay" in reason


def test_same_event_outside_window_is_ok():
    cand = Candidate(
        title="Tamamen farklı bir başlık",
        url="https://example.com/a",
        entities=["OpenAI"],
        event_type="product_launch",
        published=datetime.now(timezone.utc),
    )
    hist = [_hist("Bambaşka başlık", url="https://example.com/b",
                  entities=["OpenAI"], event_type="product_launch", days_ago=30)]
    dup, _ = is_duplicate(cand, hist)
    assert not dup


def test_fresh_candidate_is_not_duplicate():
    cand = Candidate(
        title="Hiç alakasız yepyeni bir haber",
        url="https://example.com/fresh",
        published=datetime.now(timezone.utc),
    )
    dup, _ = is_duplicate(cand, [])
    assert not dup


def test_daily_entity_limit():
    cand = Candidate(
        title="Sıradışı bir başlık burada",
        url="https://example.com/x",
        entities=["Google"],
        event_type="earnings",
        published=datetime.now(timezone.utc),
    )
    today = [
        _hist("Post 1", url="https://example.com/1", entities=["Google"]),
        _hist("Post 2", url="https://example.com/2", entities=["Google"]),
    ]
    dup, reason = is_duplicate(cand, [], today_posts=today)
    assert dup
    assert "günlük entity limiti" in reason