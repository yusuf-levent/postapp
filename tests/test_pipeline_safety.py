from datetime import datetime, timezone
from unittest.mock import Mock

from app import main
from app.models import Candidate
from app.scheduling import needs_recovery


def test_no_due_slot_does_not_construct_llm(monkeypatch):
    monkeypatch.setattr(main, "_recovery_pass", lambda **kwargs: None)
    monkeypatch.setattr(main, "find_due_slots", lambda *args: [])
    monkeypatch.setattr(main.history_store, "load_history", lambda: [])
    monkeypatch.setattr(main.history_store, "load_skipped_slots", lambda: [])
    llm = Mock(side_effect=AssertionError("AI should not be initialized"))
    monkeypatch.setattr(main, "GeminiClient", llm)
    assert main.run() == 0
    llm.assert_not_called()


def test_rejected_dry_run_never_commits_or_touches_publishing(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(main, "GeminiClient", Mock())
    monkeypatch.setattr(main.history_store, "slot_already_done", lambda *args: False)
    monkeypatch.setattr(main.history_store, "load_history", lambda: [])
    monkeypatch.setattr(main.history_store, "entries_for_day", lambda *args: [])
    monkeypatch.setattr(main, "collect_all", lambda **kwargs: [Candidate(title="Camera straps", url="u")])
    monkeypatch.setattr(main, "shortlist", lambda *args, **kwargs: [])
    commit = Mock(side_effect=AssertionError("Preview must not commit"))
    publish = Mock(side_effect=AssertionError("Rejected content must not publish"))
    monkeypatch.setattr(main, "commit_and_push", commit)
    monkeypatch.setattr(main, "publish_all", publish)
    assert main.run(slot="09:00", force_type="news", dry_run=True) == 0
    commit.assert_not_called()
    publish.assert_not_called()


def test_pending_buffer_id_triggers_recovery_even_without_a_due_slot():
    now = datetime.now(timezone.utc)
    h = [{"created_at":now.isoformat(),"status_per_platform":[
        {"state":"submitted","external_id":"known-id","attempts":1}]}]
    assert needs_recovery(h, now)
    h[0]["status_per_platform"][0]["external_id"] = ""
    assert not needs_recovery(h, now)
