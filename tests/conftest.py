"""Test yardımcıları."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Proje kökünü sys.path'e ekle
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _clear_config_caches():
    """Her testten önce lru_cache'leri temizle (env değişkenleri testlerde değişir)."""
    from app.config import settings, sources_config, platforms_config, schedule_config

    settings.cache_clear()
    sources_config.cache_clear()
    platforms_config.cache_clear()
    schedule_config.cache_clear()
    yield
    settings.cache_clear()