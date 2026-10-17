"""Karakter limitleri testleri (platform açıklamaları)."""
from __future__ import annotations

from app.config import platforms_config
from app.models import Caption, Captions
from app.write.captions import _effective_length, _find_limit_violations


def _captions(**overrides) -> Captions:
    defaults = {
        "instagram": Caption(text="a" * 100, hashtags=["ai", "tech"]),
        "tiktok": Caption(text="a" * 100, hashtags=["ai"]),
        "x": Caption(text="a" * 100, hashtags=["ai"]),
        "threads": Caption(text="a" * 100, hashtags=["ai"]),
        "linkedin": Caption(text="a" * 100, hashtags=["ai"]),
        "facebook": Caption(text="a" * 100, hashtags=["ai"]),
    }
    defaults.update(overrides)
    return Captions(**defaults)


def test_platform_limits_defined():
    cfg = platforms_config()
    assert cfg.platforms["x"].limit == 280
    assert cfg.platforms["threads"].limit == 500
    assert cfg.platforms["linkedin"].limit == 3000
    assert cfg.platforms["instagram"].limit == 2200


def test_no_violation_when_short():
    assert _find_limit_violations(_captions()) == {}


def test_under_min_hashtags_not_a_violation():
    # Alt sınır bir hedef, kısıt değil; kısa açıklama ihlal sayılmaz
    caps = _captions(instagram=Caption(text="a" * 50, hashtags=[]))
    assert _find_limit_violations(caps) == {}


def test_x_limit_violation():
    caps = _captions(x=Caption(text="a" * 300, hashtags=[]))
    v = _find_limit_violations(caps)
    assert "x" in v


def test_threads_byte_counting():
    # Emoji UTF-8 byte sayılır: 1 emoji = 4 byte
    text = "Merhaba 💬"
    assert _effective_length("threads", text) == len(text.encode("utf-8"))
    assert _effective_length("threads", text) > len(text)


def test_x_url_counts_as_23():
    text = "Haber: https://example.com/very/long/path/that/is/longer/than/23"
    length = _effective_length("x", text)
    # URL 23 karakter sayılır, gerçek URL'den kısa
    assert length < len(text)


def test_hashtag_limit_violation():
    caps = _captions(
        instagram=Caption(text="a", hashtags=[f"h{i}" for i in range(20)])
    )
    v = _find_limit_violations(caps)
    assert "instagram.hashtags" in v


def test_linkedin_limit_ok():
    caps = _captions(
        instagram=Caption(text="a" * 100, hashtags=["ai", "tech", "ml"]),
        tiktok=Caption(text="a" * 100, hashtags=["ai"]),
        x=Caption(text="a" * 100, hashtags=["ai"]),
        threads=Caption(text="a" * 100, hashtags=["ai"]),
        linkedin=Caption(text="a" * 2900, hashtags=["a", "b", "c"]),
        facebook=Caption(text="a" * 100, hashtags=["ai"]),
    )
    assert _find_limit_violations(caps) == {}