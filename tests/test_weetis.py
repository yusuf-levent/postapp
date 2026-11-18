from datetime import datetime

import pytest
import responses

from app import main
from app.collect.weetis import EDITOR_CODE, ISTANBUL, SITE_URL, fetch_discussion
from app.config import schedule_config
from app.render.renderer import render_slide_html
from app.scheduling import due_slots


POST_ID = "d4258ef7-adb4-50a6-9982-d952a3a49389"
DAY = "2026-11-18"


def mock_discussion(*, author=EDITOR_CODE, day=DAY):
    responses.get(f"{SITE_URL}/api/featured?lang=tr", json={"post": {"id": POST_ID}})
    responses.get(f"{SITE_URL}/api/post?id={POST_ID}", json={
        "post": {
            "id": POST_ID, "language": "tr", "kind": "discussion", "author_code": author,
            "created": int(datetime.fromisoformat(day).replace(tzinfo=ISTANBUL).timestamp() * 1000),
            "title": "Cursor mı, Copilot mı?", "body": "Kırılan testi nasıl düzeltirsin?",
        },
    })


@pytest.mark.parametrize("author,day", [(EDITOR_CODE, "2026-11-17"), ("manual-editor", DAY)])
@responses.activate
def test_stale_or_manually_featured_discussion_is_ignored(author, day):
    mock_discussion(author=author, day=day)
    assert fetch_discussion(DAY) is None


@responses.activate
def test_1800_workflow_uses_weetis_source_and_preserves_platform_history(tmp_path, monkeypatch):
    mock_discussion()
    monkeypatch.setattr(main, "today_label", lambda: DAY)
    monkeypatch.setattr(main, "now_istanbul", lambda: datetime(2026, 11, 18, 18, 0, tzinfo=ISTANBUL))
    monkeypatch.setattr(main, "OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(main, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(main, "_channel_map", lambda: {})
    monkeypatch.setattr(main.history_store, "HISTORY_FILE", tmp_path / "history.json")
    monkeypatch.setattr(main.history_store, "SKIPPED_FILE", tmp_path / "skipped_slots.json")
    monkeypatch.setattr(main, "commit_and_push", lambda *args: True)
    monkeypatch.setattr(main, "close_resolved_issues", lambda *args: None)
    monkeypatch.setattr(main, "notify_post_published", lambda **kwargs: None)
    monkeypatch.setattr(main, "ensure_fonts", lambda: tmp_path)
    monkeypatch.setattr(main, "make_abstract_background", lambda path, **kwargs: path)
    monkeypatch.setattr(main, "GeminiClient", lambda: pytest.fail("Weetis should use published text"))

    def render(decks, post_dir, fonts_dir):
        assert len(decks) == 6
        assert "Kırılan testi nasıl düzeltirsin?" in render_slide_html(decks[1], 2)
        return {"slides": [post_dir / "slides" / f"slide-{i}.png" for i in range(1, 7)]}

    monkeypatch.setattr(main, "_render_with_backgrounds", render)

    def publish(post_dir, **kwargs):
        saved = main.history_store.load_history()[0]
        assert (saved.type, saved.event_key) == ("weetis", POST_ID)
        assert all(status.state == "pending" for status in saved.status_per_platform)
        assert kwargs["captions"]["threads"].endswith(f"/tr/d/{POST_ID}?s=th")
        assert len(kwargs["image_urls"]) == 6
        for status in saved.status_per_platform:
            status.state = "published"
        return {status.platform: status for status in saved.status_per_platform}

    monkeypatch.setattr(main, "publish_all", publish)
    assert main.run() == 0
    assert main.run() == 0
    assert len(responses.calls) == 2
    assert all(status.state == "published" for status in main.history_store.load_history()[0].status_per_platform)
    assert due_slots(schedule_config(), [{"date": DAY, "slot": "18:00"}],
                     datetime(2026, 11, 18, 20, 0, tzinfo=ISTANBUL)) == ["20:00"]
