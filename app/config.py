"""Yapılandırma yükleme (pydantic-settings + YAML dosyaları)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
DATA_DIR = REPO_ROOT / "data"
OUTPUT_DIR = REPO_ROOT / "output"
ASSETS_DIR = REPO_ROOT / "assets"


class Settings(BaseSettings):
    """Ortam değişkenlerinden gelen gizli anahtarlar ve model ayarları.

    Gizli değerler asla loglanmaz; mask_secret() ile maskeleme yapılır.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Gemini
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-3.5-flash-lite", alias="GEMINI_MODEL")
    gemini_fallback_model: str = Field(
        default="gemini-3.1-flash-lite", alias="GEMINI_FALLBACK_MODEL"
    )

    # Görseller / videolar
    pexels_api_key: str = Field(default="", alias="PEXELS_API_KEY")
    pixabay_api_key: str = Field(default="", alias="PIXABAY_API_KEY")
    nasa_api_key: str = Field(default="", alias="NASA_API_KEY")

    # Buffer (GraphQL API, api.buffer.com)
    buffer_access_token_a: str = Field(default="", alias="BUFFER_ACCESS_TOKEN_A")
    buffer_access_token_b: str = Field(default="", alias="BUFFER_ACCESS_TOKEN_B")

    # Threads Graph API
    threads_access_token: str = Field(default="", alias="THREADS_ACCESS_TOKEN")
    threads_user_id: str = Field(default="", alias="THREADS_USER_ID")

    # Secret güncelleme için PAT (Threads token yenileme)
    gh_pat: str = Field(default="", alias="GH_PAT")

    # GitHub Actions ortamı
    github_repository: str = Field(default="", alias="GITHUB_REPOSITORY")
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    run_id: str = Field(default="", alias="GITHUB_RUN_ID")

    dry_run: bool = Field(default=False, alias="DRY_RUN")


class Source(BaseModel):
    name: str
    url: str
    domain: str


class SourcesConfig(BaseModel):
    news: list[Source]
    official: list[Source]
    verification_only_domains: list[str] = Field(default_factory=list)
    excluded_topics: list[str] = Field(default_factory=list)

    @property
    def all_feeds(self) -> list[Source]:
        return self.news + self.official

    @property
    def allowed_domains(self) -> list[str]:
        return [s.domain for s in self.all_feeds] + self.verification_only_domains

    def is_allowed_url(self, url: str) -> bool:
        u = url.lower()
        return any(d in u for d in self.allowed_domains)


class PlatformRules(BaseModel):
    limit: int
    hashtags: tuple[int, int] = (0, 0)
    max_images: int = 10
    url_length: int = 0
    use_9x16: bool = False
    thread_extra_images: bool = False


class PlatformsConfig(BaseModel):
    accounts: dict[str, list[str]]
    buffer: dict[str, Any]
    threads: dict[str, Any]
    platforms: dict[str, PlatformRules]
    media: dict[str, int] = Field(default_factory=dict)


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def sources_config() -> SourcesConfig:
    return SourcesConfig(**load_yaml("sources.yaml"))


@lru_cache(maxsize=1)
def platforms_config() -> PlatformsConfig:
    return PlatformsConfig(**load_yaml("platforms.yaml"))


@lru_cache(maxsize=1)
def schedule_config() -> dict[str, Any]:
    return load_yaml("schedule.yaml")


@lru_cache(maxsize=1)
def brand_config() -> dict[str, Any]:
    return load_yaml("brand.yaml")


def mask_secret(value: str, keep: int = 4) -> str:
    """Loglarda secret maskeler. Boşsa olduğu gibi döner."""
    if not value:
        return "(boş)"
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep)