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
    monkeypatch.setattr(gemini, "MODEL_POOL", ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite"))
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


def test_last_available_model_recovers_from_a_transient_503(monkeypatch):
    llm, clients = client(monkeypatch)
    from app.llm import gemini
    monkeypatch.setattr(gemini.time, "sleep", lambda seconds: None)
    clients[0].models.generate_content.side_effect = quota_error()
    attempts = []
    def generate(**kwargs):
        attempts.append(kwargs["model"])
        if kwargs["model"] == "gemini-3.5-flash-lite":
            raise quota_error()
        if attempts.count("gemini-3.1-flash-lite") == 1:
            raise errors.ServerError(503, {"error":{"code":503,"message":"Service unavailable"}})
        return SimpleNamespace(text="ok")
    clients[1].models.generate_content.side_effect = generate
    assert llm.generate_text("test") == "ok"
    assert attempts.count("gemini-3.5-flash-lite") == 1
    assert attempts.count("gemini-3.1-flash-lite") == 2


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


def test_gemma_fallback_uses_prompted_json_and_validates_schema(monkeypatch):
    llm, clients = client(monkeypatch)
    from app.llm import gemini
    monkeypatch.setattr(gemini, "MODEL_POOL", ("gemma-4-31b-it",))
    clients[0].models.generate_content.side_effect = quota_error()
    def generate(**kwargs):
        if not kwargs["model"].startswith("gemma-"):
            raise quota_error()
        return SimpleNamespace(text='```json\n{"queries":["robot arm"]}\n```')
    clients[1].models.generate_content.side_effect = generate
    assert llm.generate_structured("search", SearchQueries).queries == ["robot arm"]
    call = clients[1].models.generate_content.call_args
    assert call.kwargs["model"] == "gemma-4-31b-it"
    assert call.kwargs["config"].response_schema is None
    assert "JSON schema" in call.kwargs["contents"]


def test_gemma_can_review_actual_images(tmp_path, monkeypatch):
    llm, clients = client(monkeypatch)
    from app.llm import gemini
    monkeypatch.setattr(gemini, "MODEL_POOL", ("gemma-4-31b-it",))
    clients[0].models.generate_content.side_effect = quota_error()
    def generate(**kwargs):
        if not kwargs["model"].startswith("gemma-"):
            raise quota_error()
        return SimpleNamespace(text="YES")
    clients[1].models.generate_content.side_effect = generate
    path = tmp_path / "a.png"
    path.write_bytes(b"sample")
    assert llm.analyze_images("relevant?", [str(path)]) == "YES"
    assert clients[1].models.generate_content.call_args.kwargs["model"] == "gemma-4-31b-it"


def test_invalid_gemma_json_tries_next_variant_without_bypassing_schema(monkeypatch):
    llm, clients = client(monkeypatch)
    from app.llm import gemini
    monkeypatch.setattr(gemini, "MODEL_POOL", ("gemma-4-31b-it", "gemma-4-26b-a4b-it"))
    def generate(**kwargs):
        if kwargs["model"].startswith("gemini-"):
            raise quota_error()
        return SimpleNamespace(text='not JSON' if "31b" in kwargs["model"] else '{"queries":["valid"]}')
    clients[0].models.generate_content.side_effect = generate
    clients[1].models.generate_content.side_effect = quota_error()
    assert llm.generate_structured("search", SearchQueries).queries == ["valid"]
    assert llm._model == "gemma-4-26b-a4b-it"


def test_healthy_backup_gemini_is_preferred_to_gemma(monkeypatch):
    llm, clients = client(monkeypatch)
    from app.llm import gemini
    monkeypatch.setattr(gemini, "MODEL_POOL", ("gemma-4-31b-it",))
    def generate(**kwargs):
        if kwargs["model"].startswith("gemini-"):
            raise quota_error()
        return SimpleNamespace(text="slower fallback")
    clients[0].models.generate_content.side_effect = generate
    clients[1].models.generate_content.return_value = SimpleNamespace(text="backup")
    assert llm.generate_text("test") == "backup"
    assert all(not c.kwargs["model"].startswith("gemma-") for c in clients[0].models.generate_content.call_args_list)
