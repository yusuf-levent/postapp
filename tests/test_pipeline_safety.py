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


def test_failed_quality_review_repairs_once_and_preview_never_publishes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.models import Caption, Captions, ClaimVerification, Evidence, SlideDeck
    from app.render.sample import sample_deck

    post = tmp_path / "post"
    post.mkdir()
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(main, "GeminiClient", lambda: SimpleNamespace(_model="test", call_count=0, model_usage={}))
    monkeypatch.setattr(main.history_store, "slot_already_done", lambda *args: False)
    monkeypatch.setattr(main.history_store, "load_history", lambda: [])
    monkeypatch.setattr(main.history_store, "entries_for_day", lambda *args: [])
    cand = Candidate(title="An important AI release", url="https://a.com/news", published=datetime.now(timezone.utc))
    monkeypatch.setattr(main, "collect_all", lambda **kwargs: [cand])
    monkeypatch.setattr(main, "shortlist", lambda llm, candidates, history, **kwargs: candidates)
    monkeypatch.setattr(main, "enrich_candidate", lambda c: c)
    fact = ClaimVerification(claim="Kaynaklı olgu", verdict="supported", evidence=[Evidence(url="https://a.com",quote="source fact")])
    monkeypatch.setattr(main, "_verify_candidate", lambda *args: {
        "verifications":[fact], "usable":[fact], "source_texts":{}, "source_names":["A"], "cross_urls":[]})
    deck = SlideDeck.model_validate(sample_deck())
    generate = Mock(return_value=deck)
    monkeypatch.setattr(main, "generate_slides", generate)
    monkeypatch.setattr(main, "_make_post_dir", lambda *args: post)
    monkeypatch.setattr(main, "collect_images", lambda *args: [])
    monkeypatch.setattr(main, "collect_video", lambda *args: None)
    monkeypatch.setattr(main, "save_logo", lambda *args: False)
    monkeypatch.setattr(main, "ensure_fonts", lambda: tmp_path)
    monkeypatch.setattr(main, "_render_with_backgrounds", lambda *args: {"slides":[],"slides_9x16":[]})
    captions = Captions(**{p:Caption(text="Kaynaklı açıklama") for p in ("instagram","tiktok","x","threads","linkedin","facebook")})
    monkeypatch.setattr(main, "generate_captions", lambda *args: captions)
    review = Mock(side_effect=[(False,[{"problem":"Bileşen adını açık yaz"}]),(True,[])])
    monkeypatch.setattr(main, "run_qa", review)
    monkeypatch.setattr(main, "_public_urls", lambda *args, **kwargs: [])
    monkeypatch.setattr(main, "_public_video_url", lambda *args: "")
    commit = Mock(side_effect=AssertionError("Preview must not commit"))
    channels = Mock(side_effect=AssertionError("Preview must not connect to Buffer"))
    monkeypatch.setattr(main, "commit_and_push", commit)
    monkeypatch.setattr(main, "_channel_map", channels)
    assert main.run(slot="09:00", force_type="news", dry_run=True) == 0
    assert generate.call_count == 2 and review.call_count == 2
    assert generate.call_args.kwargs["feedback"] == "Bileşen adını açık yaz"
    assert (post / "status.json").exists()
    commit.assert_not_called()
    channels.assert_not_called()
