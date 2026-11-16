import json
from unittest.mock import Mock

import pytest

from app.models import PlatformStatus
from app.publish import publisher


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
