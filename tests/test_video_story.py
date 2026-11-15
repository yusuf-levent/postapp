from app.render.video_renderer import ReelScene, build_storyboard, overlay_html
from app.render.qa import _parse_qa
from app.models import ClaimVerification, Evidence
from app.verify.verifier import validate_evidence


def test_real_card_schema_populates_all_video_scenes():
    deck = {"cover":{"title":"Yeni çip", "subtitle":"Kaynaklı açıklama"}}
    for key in ("context", "details", "impact"):
        deck[key] = {"cards":[{"card_title":key, "card_body":f"Somut bilgi: {key}"}]}
    scenes = build_storyboard(deck)
    assert len(scenes) == 4
    assert [s.body for s in scenes[1:]] == ["Somut bilgi: context", "Somut bilgi: details", "Somut bilgi: impact"]


def test_video_text_is_html_escaped():
    result = overlay_html(ReelScene("TEST", "<script>bad</script>", "a & b"),
                          index=0, total=4, sources=["a"], fonts_dir=None)
    assert "<script>" not in result
    assert "a &amp; b" in result


def test_unparseable_visual_qa_cannot_pass():
    assert _parse_qa("looks fine")[0] == "fail"
    assert _parse_qa('{"issues":[]}')[0] == "fail"


def test_a_quote_from_a_different_url_is_not_evidence():
    item = ClaimVerification(claim="a", verdict="supported", evidence=[Evidence(url="https://wrong.com", quote="exact text")])
    assert validate_evidence([item], [item], {"https://right.com":"exact text"})[0].verdict == "not_found"


def test_same_publisher_aliases_are_not_independent_sources():
    from app.common import source_identity
    assert source_identity("https://blog.google/story") == source_identity("https://deepmind.google/blog/story")
    assert source_identity("https://www.bbc.com/news/1") == source_identity("https://news.bbc.co.uk/2")
    assert source_identity("https://blogs.microsoft.com/1") == source_identity("https://microsoft.com/2")
