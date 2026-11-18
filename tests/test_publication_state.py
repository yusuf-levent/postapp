import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
import responses

from app import main
from app.models import HistoryEntry, PlatformStatus
from app.publish import publisher
from app.publish.buffer_client import API_URL, BufferClient
from app.scheduling import needs_recovery


@pytest.mark.parametrize("remote,expected", [("sent","published"),("sending","submitted"),
                                             ("scheduled","submitted"),("error","failed"),("unknown","submitted")])
def test_buffer_acceptance_is_not_automatically_publication(monkeypatch, remote, expected):
    api = Mock()
    api.create_post.return_value = {"id":"remote-1", "status":remote, "error":{"message":"upload rejected"}}
    monkeypatch.setattr(publisher, "client_for_account", lambda account: api)
    st = publisher.publish_platform("facebook", caption="text", image_urls=["u"], channel_id="channel")
    assert st.state == expected
    assert st.external_id == "remote-1"


def test_known_remote_id_is_reconciled_without_resubmission(monkeypatch):
    api = Mock()
    api.get_post_status.return_value = {"id":"remote-1", "status":"sent"}
    monkeypatch.setattr(publisher, "client_for_account", lambda account: api)
    st = PlatformStatus(platform="instagram", state="submitted", external_id="remote-1")
    assert publisher.publish_platform("instagram", caption="", image_urls=[], status=st).state == "published"
    api.create_post.assert_not_called()
    api.create_video_post.assert_not_called()


def test_uncertain_result_without_id_is_never_resent(monkeypatch):
    api = Mock()
    monkeypatch.setattr(publisher, "client_for_account", api)
    st = PlatformStatus(platform="instagram", state="submitted")
    publisher.publish_platform("instagram", caption="", image_urls=[], status=st)
    api.assert_not_called()


def test_durable_journal_precedes_api_call(tmp_path, monkeypatch):
    api = Mock()
    monkeypatch.setattr(publisher, "client_for_account", lambda account: api)
    monkeypatch.setattr(publisher, "maybe_refresh_token", lambda: {})
    monkeypatch.setattr(publisher, "wait_for_public_urls", lambda urls: True)
    def create(**kwargs):
        saved = json.loads((tmp_path / "status.json").read_text())
        assert saved["platforms"]["facebook"]["state"] == "submitted"
        return {"id":"remote-1", "status":"sent"}
    api.create_post.side_effect = create
    checkpoint = Mock()
    states = publisher.publish_all(tmp_path, captions={"facebook":"text"}, image_urls=["u"],
                                   channel_map={"facebook":("A","channel")}, checkpoint=checkpoint)
    assert states["facebook"].state == "published"
    assert checkpoint.call_count == 2


def test_failed_checkpoint_prevents_external_post(tmp_path, monkeypatch):
    api = Mock()
    monkeypatch.setattr(publisher, "client_for_account", lambda account: api)
    monkeypatch.setattr(publisher, "maybe_refresh_token", lambda: {})
    monkeypatch.setattr(publisher, "wait_for_public_urls", lambda urls: True)
    with pytest.raises(RuntimeError):
        publisher.publish_all(tmp_path, captions={"facebook":"text"}, image_urls=["u"],
                              channel_map={"facebook":("A","channel")}, checkpoint=Mock(side_effect=RuntimeError("git failed")))
    api.create_post.assert_not_called()


def test_missing_media_stops_before_platform_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(publisher, "maybe_refresh_token", lambda: {})
    monkeypatch.setattr(publisher, "wait_for_public_urls", lambda urls: False)
    api = Mock()
    monkeypatch.setattr(publisher, "client_for_account", api)
    with pytest.raises(publisher.PublisherError):
        publisher.publish_all(tmp_path, captions={"facebook":"text"}, image_urls=["u"], channel_map={})
    api.assert_not_called()


def test_recovery_uses_newer_journal_instead_of_stale_history(tmp_path, monkeypatch):
    (tmp_path / "status.json").write_text(json.dumps({"platforms": {
        "facebook": PlatformStatus(platform="facebook", state="submitted", external_id="saved-id").model_dump()
    }}))
    api = Mock()
    api.get_post_status.return_value = {"id":"saved-id", "status":"sent"}
    monkeypatch.setattr(publisher, "client_for_account", lambda account: api)
    result = publisher.recover_failed(tmp_path, captions={"facebook":"text"}, image_urls=["u"],
                                      channel_map={"facebook":("A","channel")},
                                      history_statuses=[PlatformStatus(platform="facebook")])
    assert result["facebook"].state == "published"
    api.create_post.assert_not_called()


def test_recovery_does_not_submit_unavailable_media(tmp_path, monkeypatch):
    api = Mock()
    monkeypatch.setattr(publisher, "client_for_account", api)
    monkeypatch.setattr(publisher, "wait_for_public_urls", lambda urls: False)
    with pytest.raises(publisher.PublisherError):
        publisher.recover_failed(tmp_path, captions={"facebook":"text"}, image_urls=["missing"],
                                  channel_map={"facebook":("A","channel")},
                                  history_statuses=[PlatformStatus(platform="facebook")])
    api.assert_not_called()


@responses.activate
def test_buffer_rejection_leaves_budget_and_accepted_post_id_survives_poll_limit(monkeypatch):
    client = BufferClient(access_token="test-token")
    monkeypatch.setattr(publisher, "client_for_account", lambda account: client)
    responses.post(API_URL, status=429, json={}, headers={"Retry-After": "3600"})
    responses.post(API_URL, json={"data": {"createPost": {
        "__typename": "PostActionSuccess", "post": {"id": "remote-1", "status": "sending"},
    }}})
    responses.post(API_URL, status=429, json={}, headers={"Retry-After": "3600"})

    st = PlatformStatus(platform="instagram", state="failed", attempts=4)
    publish_args = dict(caption="text", image_urls=[], video_url="video", channel_id="channel", status=st)
    publisher.publish_platform("instagram", **publish_args)
    assert st.state == "pending" and st.attempts == 4
    assert st.retry_at > datetime.now(timezone.utc).timestamp()
    publisher.publish_platform("instagram", **publish_args)
    assert len(responses.calls) == 1

    st.retry_at = 1
    publisher.publish_platform("instagram", **publish_args)
    assert st.state == "submitted" and st.external_id == "remote-1"
    assert st.retry_at > datetime.now(timezone.utc).timestamp()
    assert st.attempts == 5
    assert len(responses.calls) == 3


def test_recovery_runs_due_buffer_retry_after_normal_window(tmp_path, monkeypatch):
    now = datetime.now(timezone.utc)
    st = PlatformStatus(platform="instagram", retry_at=int(now.timestamp()) + 3600)
    legacy = PlatformStatus(platform="tiktok", state="failed", attempts=5)
    entry = HistoryEntry(
        id="post", date="2026-11-16", slot="12:00", type="news",
        created_at=(now - timedelta(days=3)).isoformat(), status_per_platform=[st, legacy],
    )
    monkeypatch.setattr(main.history_store, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(main, "_repo_root", lambda: tmp_path)
    post_dir = tmp_path / entry.date / "post"
    post_dir.mkdir(parents=True)
    (post_dir / "captions.json").write_text(json.dumps({"captions": {
        "instagram": "text", "tiktok": "text",
    }}))
    monkeypatch.setattr(main, "_find_post_dir", lambda entry: post_dir)
    monkeypatch.setattr(main, "_channel_map", lambda: {"instagram": ("A", "channel")})
    monkeypatch.setattr(main, "commit_and_push", Mock(return_value=True))
    monkeypatch.setattr(main, "close_resolved_issues", Mock())
    api = Mock()
    monkeypatch.setattr(publisher, "client_for_account", lambda account: api)
    api.create_post.return_value = {"id": "remote-1", "status": "sending"}
    api.get_post_status.return_value = {"id": "remote-1", "status": "sent"}

    main.history_store.save_history([entry])
    assert not needs_recovery([entry.model_dump()], now)
    main._recovery_pass(dry_run=False)
    api.create_post.assert_not_called()

    st.retry_at = int(now.timestamp()) - 1
    main.history_store.save_history([entry])
    assert needs_recovery([entry.model_dump()], now)
    main._recovery_pass(dry_run=False)
    api.create_post.assert_called_once()
    saved = main.history_store.load_history()[0]
    assert saved.status_per_platform[0].external_id == "remote-1"
    assert needs_recovery([saved.model_dump()], now)

    main._recovery_pass(dry_run=False)
    api.create_post.assert_called_once()
    api.get_post_status.assert_called_once_with("remote-1")
    states = main.history_store.load_history()[0].status_per_platform
    assert [s.state for s in states] == ["published", "failed"]
    assert states[0].retry_at == 0
