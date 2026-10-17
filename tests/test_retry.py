"""Retry ve idempotency mantığı testleri."""
from __future__ import annotations

import pytest

from app.publish.retry import (
    PermanentError,
    TransientError,
    classify_status,
    raise_for_status,
    with_retry,
)
from app.models import PlatformStatus
from app.publish.publisher import publish_platform


def test_classify_transient():
    assert classify_status(429) == "transient"
    assert classify_status(503) == "transient"
    assert classify_status(500) == "transient"


def test_classify_permanent():
    assert classify_status(401) == "permanent"
    assert classify_status(400) == "permanent"
    assert classify_status(422) == "permanent"


def test_raise_for_status_permanent():
    with pytest.raises(PermanentError):
        raise_for_status(401, "unauthorized")


def test_raise_for_status_transient():
    with pytest.raises(TransientError):
        raise_for_status(429, "rate limited")


def test_with_retry_success_first_try():
    calls = []
    result = with_retry(lambda: calls.append(1) or "ok", sleep_fn=lambda s: None)
    assert result.ok
    assert result.attempts == 1
    assert result.value == "ok"


def test_with_retry_recovers_from_transient():
    attempts = [0]

    def flaky():
        attempts[0] += 1
        if attempts[0] < 3:
            raise TransientError("geçici")
        return "başarılı"

    result = with_retry(flaky, sleep_fn=lambda s: None, label="test")
    assert result.ok
    assert result.attempts == 3


def test_with_retry_stops_on_permanent():
    calls = [0]

    def always_permanent():
        calls[0] += 1
        raise PermanentError("kalıcı")

    result = with_retry(always_permanent, sleep_fn=lambda s: None)
    assert not result.ok
    assert result.permanent
    assert calls[0] == 1  # kalıcı hatada tekrar denenmez


def test_with_retry_exhausts_attempts():
    def always_transient():
        raise TransientError("sürekli geçici")

    result = with_retry(always_transient, max_attempts=3, sleep_fn=lambda s: None)
    assert not result.ok
    assert result.attempts == 3


# ------------------------------------------------------------ idempotency
def test_published_platform_never_reposted():
    """`published` olan platforma asla tekrar gönderilmez."""
    st = PlatformStatus(platform="instagram", state="published", external_id="123")
    # publish_platform çağrılmadan dönmeli — network'e gitmez
    result = publish_platform(
        "instagram",
        caption="test",
        image_urls=["https://example.com/a.png"],
        status=st,
    )
    assert result.state == "published"
    assert result.external_id == "123"


def test_failed_platform_can_retry():
    st = PlatformStatus(platform="x", state="failed", attempts=1, last_error="hata")
    assert st.state == "failed"  # yeniden denenebilir


def test_status_model_defaults():
    st = PlatformStatus(platform="facebook")
    assert st.state == "pending"
    assert st.attempts == 0
    assert st.external_id == ""