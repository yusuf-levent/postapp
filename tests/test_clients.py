"""Buffer ve Threads client'ları için HTTP mock'lu testler."""
from __future__ import annotations

import pytest
import responses

from app.publish.buffer_client import BufferClient, API_URL
from app.publish.retry import PermanentError, TransientError
from app.publish.threads_client import GRAPH_BASE, ThreadsClient, threads_char_length


# ------------------------------------------------------------- BufferClient
@responses.activate
def test_buffer_create_post_success():
    responses.add(
        responses.POST,
        API_URL,
        json={
            "data": {
                "createPost": {
                    "__typename": "PostActionSuccess",
                    "post": {
                        "id": "post-1",
                        "status": "sent",
                        "externalLink": "https://x.com/status/1",
                    },
                }
            }
        },
        status=200,
    )
    client = BufferClient(access_token="buf_test_token")
    result = client.create_post(
        channel_id="ch-1",
        text="Merhaba",
        image_urls=["https://example.com/a.png"],
        platform="instagram",
    )
    assert result["id"] == "post-1"
    assert result["status"] == "sent"
    assert len(responses.calls) == 1
    # Authorization header doğru mu?
    assert "Bearer buf_test_token" in responses.calls[0].request.headers["Authorization"]


@responses.activate
def test_buffer_unauthorized_is_permanent():
    responses.add(responses.POST, API_URL, json={}, status=401)
    client = BufferClient(access_token="bad")
    with pytest.raises(PermanentError):
        client.create_post(channel_id="c", text="t", image_urls=[], platform="x")


@responses.activate
def test_buffer_rate_limit_is_transient():
    responses.add(
        responses.POST,
        API_URL,
        json={"errors": [{"message": "Too many", "extensions": {"code": "RATE_LIMIT_EXCEEDED"}}]},
        status=200,
    )
    client = BufferClient(access_token="t")
    with pytest.raises(TransientError):
        client.create_post(channel_id="c", text="t", image_urls=[], platform="x")


@responses.activate
def test_buffer_graphql_error_union():
    responses.add(
        responses.POST,
        API_URL,
        json={
            "data": {
                "createPost": {
                    "__typename": "LimitReachedError",
                    "message": "Günlük limit doldu",
                }
            }
        },
        status=200,
    )
    client = BufferClient(access_token="t")
    with pytest.raises(PermanentError):
        client.create_post(channel_id="c", text="t", image_urls=[], platform="x")


@responses.activate
def test_buffer_assets_payload_shape():
    """CreatePostInput.assets şekil kontrolü: AssetInput.image.url."""
    captured = {}

    def _callback(request):
        import json

        captured.update(json.loads(request.body))
        return (
            200,
            {},
            '{"data": {"createPost": {"__typename": "PostActionSuccess", '
            '"post": {"id": "p", "status": "sent", "externalLink": ""}}}}',
        )

    responses.add_callback(responses.POST, API_URL, callback=_callback)
    client = BufferClient(access_token="t")
    client.create_post(
        channel_id="ch-1",
        text="Merhaba dünya",
        image_urls=["https://example.com/a.png", "https://example.com/b.png"],
        platform="linkedin",
    )
    inp = captured["variables"]["input"]
    assert inp["channelId"] == "ch-1"
    assert inp["mode"] == "shareNow"
    assert inp["schedulingType"] == "automatic"
    assert len(inp["assets"]) == 2
    assert inp["assets"][0]["image"]["url"] == "https://example.com/a.png"


# ------------------------------------------------------------ ThreadsClient
def test_threads_char_length_counts_emoji_as_utf8():
    # "a" = 1 byte, "💬" = 4 byte → toplam 5
    assert threads_char_length("a💬") == 5
    assert threads_char_length("abc") == 3


def test_threads_client_requires_credentials(monkeypatch):
    monkeypatch.delenv("THREADS_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("THREADS_USER_ID", raising=False)
    with pytest.raises(PermanentError):
        ThreadsClient(access_token="", user_id="")


@responses.activate
def test_threads_carousel_flow(monkeypatch):
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("THREADS_USER_ID", "uid")

    # 1-2. çocuk container'lar
    responses.add(
        responses.POST,
        f"{GRAPH_BASE}/uid/threads",
        json={"id": "child-1"}, status=200,
    )
    responses.add(
        responses.POST,
        f"{GRAPH_BASE}/uid/threads",
        json={"id": "child-2"}, status=200,
    )
    # 3. carousel container
    responses.add(
        responses.POST,
        f"{GRAPH_BASE}/uid/threads",
        json={"id": "main-1"}, status=200,
    )
    # container durum poll → FINISHED
    responses.add(
        responses.GET,
        f"{GRAPH_BASE}/main-1",
        json={"status": "FINISHED"}, status=200,
    )
    # publish
    responses.add(
        responses.POST,
        f"{GRAPH_BASE}/uid/threads_publish",
        json={"id": "media-1"}, status=200,
    )
    # permalink
    responses.add(
        responses.GET,
        f"{GRAPH_BASE}/media-1",
        json={"permalink": "https://www.threads.net/@user/post/1"}, status=200,
    )

    client = ThreadsClient()
    result = client.publish_carousel(
        ["https://example.com/a.png", "https://example.com/b.png"], "Merhaba 💬"
    )
    assert result["id"] == "media-1"
    assert "threads.net" in result["permalink"]


@responses.activate
def test_threads_rejects_over_limit_text(monkeypatch):
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("THREADS_USER_ID", "uid")
    client = ThreadsClient()
    with pytest.raises(PermanentError):
        client.publish_text("x" * 501)