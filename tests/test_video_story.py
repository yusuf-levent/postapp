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


def test_event_image_is_preferred_to_an_incidental_ceo_portrait(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from app.media import collector
    from app.models import Candidate, ImageCandidate
    event = ImageCandidate(source="ogimage", url="https://example.com/rocket.png")
    monkeypatch.setattr(collector.ogimage, "og_image", lambda *a, **kw: event)
    def accept(llm, image, candidate, directory, width, selected):
        selected.append(image)
        return True
    monkeypatch.setattr(collector, "_accept_and_save", accept)
    portrait, stock = Mock(), Mock()
    monkeypatch.setattr(collector.wikimedia, "person_image", portrait)
    monkeypatch.setattr(collector.pexels, "search_images", stock)
    result = collector.collect_images(Mock(), Candidate(title="SpaceX catches Starship", url="u"), ["Elon Musk"], tmp_path)
    assert result == [event]
    portrait.assert_not_called()
    stock.assert_not_called()


def test_factual_review_uses_source_text_and_visual_review_only_checks_rendering():
    from unittest.mock import Mock
    from app.render.qa import run_qa, TextReview
    llm = Mock()
    llm.generate_structured.return_value = TextReview(verdict="pass")
    llm.analyze_images.return_value = '{"verdict":"pass","issues":[]}'
    assert run_qa(llm, [], verified_claims=["The upper stage was caught; the booster was not."],
                  content_json='{"title":"Upper stage caught"}', captions_json="captions")[0]
    text_prompt = llm.generate_structured.call_args.args[0]
    assert "The upper stage was caught" in text_prompt
    assert '"title":"Upper stage caught"' in text_prompt
    visual_prompt = llm.analyze_images.call_args.args[0]
    assert "The upper stage was caught" not in visual_prompt
    assert "yalnızca teknik görsel" in visual_prompt


def test_nasa_search_parses_string_collection_and_item_links(monkeypatch):
    from unittest.mock import Mock
    from app.media import video_collector

    search_resp = Mock(status_code=200)
    search_resp.json.return_value = {
        "collection": {
            "items": [{
                "data": [{"nasa_id": "NASA-TEST-1", "title": "Rocket Launch HD"}],
                "links": [{"render": "image", "href": "https://images-assets.nasa.gov/video/NASA-TEST-1/thumb.jpg"}],
            }]
        }
    }
    media_resp = Mock(status_code=200)
    media_resp.json.return_value = [
        "https://images-assets.nasa.gov/video/NASA-TEST-1/NASA-TEST-1~small.mp4",
        "https://images-assets.nasa.gov/video/NASA-TEST-1/NASA-TEST-1~orig.mp4",
    ]
    monkeypatch.setattr(video_collector, "_load_used_video_urls", lambda: set())
    monkeypatch.setattr(video_collector, "http_get", Mock(side_effect=[search_resp, media_resp]))
    results = video_collector._search_nasa_candidates("rocket launch")
    assert len(results) == 1
    assert results[0]["video_url"].endswith("~orig.mp4")
    assert results[0]["thumb_url"].endswith("thumb.jpg")


def test_pexels_rejects_low_res_and_accepts_landscape_and_portrait_hd(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.media import video_collector

    resp = Mock(status_code=200)
    resp.json.return_value = {
        "videos": [
            {
                "id": 1, "duration": 12, "url": "https://pexels.com/video/low-res-1",
                "image": "https://img/1.jpg", "user": {"name": "A"},
                "video_files": [{"file_type": "video/mp4", "width": 640, "height": 360, "link": "https://v/low.mp4"}],
            },
            {
                "id": 2, "duration": 15, "url": "https://pexels.com/video/microchip-hd-2",
                "image": "https://img/2.jpg", "user": {"name": "B"},
                "video_files": [{"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "https://v/land1080.mp4"}],
            },
            {
                "id": 3, "duration": 15, "url": "https://pexels.com/video/server-portrait-3",
                "image": "https://img/3.jpg", "user": {"name": "C"},
                "video_files": [{"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "https://v/port1080.mp4"}],
            },
        ]
    }
    monkeypatch.setattr(video_collector, "settings", lambda: SimpleNamespace(pexels_api_key="k"))
    monkeypatch.setattr(video_collector, "_load_used_video_urls", lambda: set())
    monkeypatch.setattr(video_collector, "http_get", lambda *a, **kw: resp)
    results = video_collector._search_pexels_candidates("microchip")
    assert [r["video_url"] for r in results] == ["https://v/port1080.mp4", "https://v/land1080.mp4"]


def test_verify_downloaded_video_rejects_low_res_and_low_fps(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from app.media import video_collector, video_probe

    fake = tmp_path / "v.mp4"
    fake.write_bytes(b"0" * 100)
    monkeypatch.setattr(video_probe, "probe_video", lambda p: {"duration": 12.0, "width": 854, "height": 480, "fps": 30.0})
    assert not video_collector._verify_downloaded_video(Mock(), "Chip news", ["NVIDIA"], fake, mode="broll")
    monkeypatch.setattr(video_probe, "probe_video", lambda p: {"duration": 12.0, "width": 1920, "height": 1080, "fps": 12.0})
    assert not video_collector._verify_downloaded_video(Mock(), "Chip news", ["NVIDIA"], fake, mode="broll")


def test_find_article_video_supports_jsonld_and_webm(monkeypatch):
    from unittest.mock import Mock
    from app.media import video_collector

    resp = Mock(status_code=200, text='<html><script>{"@type":"VideoObject","contentUrl":"https://cdn.example.com/demo.webm"}</script></html>')
    monkeypatch.setattr(video_collector, "http_get", lambda *a, **kw: resp)
    assert video_collector._find_article_video("https://example.com/post") == "https://cdn.example.com/demo.webm"


def test_find_article_videos_captures_custom_attr_and_filters_ads(monkeypatch):
    from unittest.mock import Mock
    from app.media import video_collector

    html = (
        '<div or-mp4-video-url="https://storage.googleapis.com/blog/genie-4-demo.mp4"></div>'
        '<a href="https://doubleclick.net/pixel.mp4"></a>'
    )
    monkeypatch.setattr(video_collector, "http_get", lambda *a, **kw: Mock(status_code=200, text=html))
    urls = video_collector._find_article_videos("https://blog.google/genie-4/")
    assert urls == ["https://storage.googleapis.com/blog/genie-4-demo.mp4"]


def test_voiceover_script_skips_card_headings_on_middle_scenes_and_guards_numbers():
    from unittest.mock import Mock
    from app.media.voiceover import ReelNarration, build_narration_lines, clean_speech_text, scene_script

    assert clean_speech_text("Yeni çip 🚀 %40 hızlı https://ex.com #AI") == "Yeni çip %40 hızlı"
    assert scene_script(ReelScene("NE OLDU?", "Nvidia H200 kararı", "Satışlar durduruldu"), index=0) == "Nvidia H200 kararı. Satışlar durduruldu."
    # 2. sahnede "Erişime Açıldı." kart başlığını robot gibi okumamalı
    assert scene_script(ReelScene("BİLMEN GEREKEN", "Erişime Açıldı", "Genie 4 artık API üzerinden açık"), index=1) == "Genie 4 artık API üzerinden açık."

    scenes = [
        ReelScene("NE OLDU?", "Google Genie 4 Açıldı", "720p etkileşimli dünyalar geliyor."),
        ReelScene("BİLMEN GEREKEN", "Erişime Açıldı", "Gemini API üzerinden kullanılabiliyor."),
    ]
    llm = Mock()
    llm.generate_structured.return_value = ReelNarration(lines=[
        "Google, Genie 4 ile 720p dünyaları geliştiricilere açtı.",
        "Model şu an doğrudan Gemini API üzerinden denenebiliyor.",
    ])
    lines = build_narration_lines(scenes, llm=llm, verified_claims=["720p çözünürlük", "Gemini API"])
    assert lines[0].startswith("Google, Genie 4")

    # Uydurma sayı (999) eklerse reddedilip güvenli fallback'e düşmeli
    llm.generate_structured.return_value = ReelNarration(lines=[
        "Google, Genie 4 ile 999 kat hızlı dünyalar açtı.",
        "Model şu an Gemini API üzerinden denenebiliyor.",
    ])
    safe_lines = build_narration_lines(scenes, llm=llm, verified_claims=["720p çözünürlük", "Gemini API"])
    assert "999" not in " ".join(safe_lines)
    assert safe_lines[1] == "Gemini API üzerinden kullanılabiliyor."


def test_banned_slug_words_block_irrelevant_and_abstract_stock():
    from app.media.video_collector import _slug_is_banned

    assert _slug_is_banned("https://pexels.com/video/business-meeting-handshake-123")
    assert _slug_is_banned("https://pexels.com/video/amazon-rainforest-river-456")
    assert _slug_is_banned("https://www.pexels.com/video/abstract-data-visualization-in-motion-36252897/")
    assert not _slug_is_banned("https://pexels.com/video/microchip-silicon-wafer-789")
