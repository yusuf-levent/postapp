from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.models import Candidate, EditorialBatch, EditorialDecision, HistoryEntry
from app.scheduling import due_slots
from app.select.dedup import is_duplicate
from app.select.editorial import annotate, rejection_reason, shortlist
from app.select.editorial import canonical_entity
from app.select.scoring import score_candidates


@pytest.mark.parametrize("title", [
    "Wandrd's magnetic camera straps are my new favorite accessory",
    "The Apple MacBook Pro is on sale at its lowest price",
    "Canon announces new lens caps", "Black Friday camera deals",
])
def test_low_value_items_never_reach_the_editor(title):
    llm = Mock()
    assert not shortlist(llm, [Candidate(title=title, url="https://a.com")], [], mode="news")
    llm.generate_structured.assert_not_called()


def test_real_ai_news_is_not_blocked_by_accessory_filter():
    assert not rejection_reason(Candidate(title="Google releases an open AI model for researchers", url="u"))


def test_brand_limit_works_before_llm_entity_extraction():
    history = [HistoryEntry(id="one", date="2026-11-15", slot="09:00", type="news",
                            original_title="Canon reveals a cinema camera", entities=["Canon"],
                            created_at=datetime.now(timezone.utc).isoformat())]
    candidate = Candidate(title="Canon launches a new camera lens", url="https://new.com")
    duplicate, reason = is_duplicate(candidate, [], today_posts=history)
    assert duplicate and "entity" in reason


def test_brand_aliases_count_as_same_company():
    history = [HistoryEntry(id="one", date="2026-11-15", slot="09:00", type="news",
                            entities=["Google"], primary_entity="Google", title_tr="Maps güncellendi")]
    c = annotate(Candidate(title="DeepMind releases a new reasoning system", url="u"))
    assert is_duplicate(c, [], today_posts=history)[0]
    assert canonical_entity("Google DeepMind") == canonical_entity("Alphabet Inc.") == "google"
    assert canonical_entity("Canon Inc.") == "canon"


def test_editor_cannot_pass_unreviewed_or_low_importance_candidates():
    llm = Mock()
    llm.generate_structured.return_value = EditorialBatch(items=[
        EditorialDecision(index=0, publishable=True, importance=3, topic="consumer"),
        EditorialDecision(index=1, publishable=True, importance=9, topic="ai", event_key="new-ai-release"),
    ])
    pool = [Candidate(title=t, url=f"https://a.com/{i}") for i, t in enumerate(("Camera launches", "Open model release", "Unreviewed"))]
    assert [c.title for c in shortlist(llm, pool, [], mode="news")] == ["Open model release"]
    assert not shortlist(llm, pool, [], mode="edu")


def test_same_event_key_survives_rewording_and_source_changes():
    h = HistoryEntry(id="h", date="2026-11-15", slot="09:00", type="news",
                     title_tr="Model duyuruldu", event_key="google-sample-release",
                     created_at=datetime.now(timezone.utc).isoformat())
    c = Candidate(title="A totally different headline", url="https://b.com", event_key=h.event_key)
    assert is_duplicate(c, [h])[0]


def test_exact_publication_second_does_not_beat_importance():
    now = datetime.now(timezone.utc)
    important = Candidate(title="OpenAI announces a breakthrough chip", summary="New GPU is 40% faster",
                          url="https://a.com", published=now - timedelta(hours=4))
    minor = Candidate(title="A camera accessory", url="https://b.com", published=now)
    assert score_candidates([minor, important])[0] is important


@pytest.mark.parametrize("hour,minute,expected", [(8,59,[]),(9,0,["09:00"]),(10,31,[]),
                                                   (15,20,["15:00"]),(23,0,[])])
def test_only_current_slot_is_due(hour, minute, expected):
    schedule = {"slots": [{"time": t} for t in ("09:00", "12:00", "15:00", "18:00", "21:00")],
                "max_catchup_minutes": 90}
    assert due_slots(schedule, [], datetime(2026,11,15,hour,minute,tzinfo=timezone.utc)) == expected


def test_completed_slot_is_not_reopened():
    assert due_slots({"slots": [{"time":"09:00"}]}, [{"date":"2026-11-15","slot":"09:00"}],
                     datetime(2026,11,15,9,5,tzinfo=timezone.utc)) == []


def test_editor_fills_missing_event_key_and_other_topic_for_publishable_item():
    llm = Mock()
    llm.generate_structured.return_value = EditorialBatch(items=[
        EditorialDecision(index=0, publishable=True, importance=8, topic="other", event_key="", reason="Somut bilimsel yenilik"),
        EditorialDecision(index=1, publishable=False, importance=8, topic="ai", event_key="skip-me", reason="Dedikodu"),
    ])
    pool = [
        Candidate(title="AI nose startup achieves human-level scent detection", url="https://a.com/1"),
        Candidate(title="Internal rumor about executive", url="https://a.com/2"),
    ]
    selected = shortlist(llm, pool, [], mode="news")
    assert len(selected) == 1
    assert selected[0].event_key
    assert selected[0].topic != "other"
