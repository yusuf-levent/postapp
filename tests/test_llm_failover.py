from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import responses
from google.genai import errors

from app.llm.gemini import GeminiClient, LLMError
from app.models import SearchQueries


def client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-primary")
    monkeypatch.setenv("GEMINI_BACKUP_API_KEY", "test-backup")
    from app.llm import gemini
    monkeypatch.setattr(gemini, "MIN_INTERVAL_SECONDS", 0)
    clients = [Mock(), Mock()]
    monkeypatch.setattr(gemini.genai, "Client", Mock(side_effect=clients))
    return GeminiClient(), clients


def quota_error():
    return errors.ClientError(429, {"error":{"code":429,"message":"GenerateRequestsPerDay quota exhausted"}})


def test_exhausted_primary_uses_backup_and_does_not_reset(monkeypatch):
    llm, clients = client(monkeypatch)
    clients[0].models.generate_content.side_effect = quota_error()
    clients[1].models.generate_content.return_value = SimpleNamespace(text='{"queries":["computer chip"]}')
    for _ in range(2):
        assert llm.generate_structured("query", SearchQueries).queries == ["computer chip"]
    assert clients[0].models.generate_content.call_count == 2  # two models, once each
    assert clients[1].models.generate_content.call_count == 2


def test_all_daily_quotas_stop_without_repeated_requests(monkeypatch):
    llm, clients = client(monkeypatch)
    for c in clients:
        c.models.generate_content.side_effect = quota_error()
    for _ in range(2):
        with pytest.raises(LLMError):
            llm.generate_text("test")
    assert sum(c.models.generate_content.call_count for c in clients) == 4


@responses.activate
def test_optional_text_provider_validates_schema(monkeypatch):
    monkeypatch.setenv("TEXT_FALLBACK_API_KEY", "test-text-key")
    llm, clients = client(monkeypatch)
    for c in clients:
        c.models.generate_content.side_effect = quota_error()
    responses.post("https://api.groq.com/openai/v1/chat/completions", json={
        "choices":[{"message":{"content":'{"queries":["processor closeup"]}'}}]})
    assert llm.generate_structured("query", SearchQueries).queries == ["processor closeup"]
    assert "text-fallback/llama-3.3-70b-versatile" in llm.model_usage


def test_grounding_is_opt_in_and_does_not_consume_free_quota(monkeypatch):
    llm, clients = client(monkeypatch)
    assert llm.search_grounded("find", allowed_domains=["example.com"]) == []
    assert all(c.models.generate_content.call_count == 0 for c in clients)


def test_vision_never_falls_back_to_a_text_only_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("TEXT_FALLBACK_API_KEY", "test-text-key")
    llm, clients = client(monkeypatch)
    for c in clients:
        c.models.generate_content.side_effect = quota_error()
    image = tmp_path / "a.png"
    image.write_bytes(b"sample")
    llm._text_fallback = Mock()
    with pytest.raises(LLMError):
        llm.analyze_images("look", [str(image)])
    llm._text_fallback.assert_not_called()
