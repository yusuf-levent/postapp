"""Doğrulama hattı testleri: alıntı doğrulama, iki tur, karar kuralları."""
from __future__ import annotations

from app.models import ClaimVerification, Evidence
from app.verify.verifier import decide, quote_in_source, validate_evidence


SOURCE_TEXTS = {
    "https://a.com/1": (
        "NVIDIA, yeni Blackwell mimarisini duyurdu. Şirket, yeni çipin "
        "yapay zeka eğitiminde %40 daha verimli olduğunu açıkladı. "
        "CEO Jensen Huang konuyla ilgili açıklama yaptı."
    ),
}


def test_quote_found_exact():
    assert quote_in_source(
        "%40 daha verimli olduğunu açıkladı", SOURCE_TEXTS
    )


def test_quote_found_normalized():
    assert quote_in_source(
        "NVIDIA yeni Blackwell mimarisini duyurdu", SOURCE_TEXTS
    )


def test_fabricated_quote_rejected():
    """Uydurma alıntı tespit edilmeli (≥90 fuzzy eşleşme yok)."""
    assert not quote_in_source(
        "Şirket hisseleri %75 oranında yükseldi", SOURCE_TEXTS
    )


def test_empty_quote_rejected():
    assert not quote_in_source("", SOURCE_TEXTS)


def test_two_rounds_disagree_becomes_not_found():
    r1 = [ClaimVerification(claim="X %40 arttı", verdict="supported",
                            evidence=[Evidence(url="u", quote="%40 daha verimli olduğunu açıkladı")])]
    r2 = [ClaimVerification(claim="X %40 arttı", verdict="not_found", evidence=[])]
    final = validate_evidence(r1, r2, SOURCE_TEXTS)
    assert final[0].verdict == "not_found"


def test_two_rounds_agree_and_quote_valid():
    quote = "%40 daha verimli olduğunu açıkladı"
    r1 = [ClaimVerification(claim="X %40 arttı", verdict="supported",
                            evidence=[Evidence(url="https://a.com/1", quote=quote)])]
    r2 = [ClaimVerification(claim="X %40 arttı", verdict="supported",
                            evidence=[Evidence(url="https://a.com/1", quote=quote)])]
    final = validate_evidence(r1, r2, SOURCE_TEXTS)
    assert final[0].verdict == "supported"
    assert len(final[0].evidence) == 1


def test_fabricated_evidence_invalidates():
    """Alıntı uydurmaysa kanıt geçersiz, iddia not_found olur."""
    r1 = [ClaimVerification(claim="X", verdict="supported",
                            evidence=[Evidence(url="u", quote="tamamen uydurma alıntı metni")])]
    r2 = [ClaimVerification(claim="X", verdict="supported",
                            evidence=[Evidence(url="u", quote="tamamen uydurma alıntı metni")])]
    final = validate_evidence(r1, r2, SOURCE_TEXTS)
    assert final[0].verdict == "not_found"


# -------------------------------------------------------------- karar kuralları
def test_contradicted_rejects_everything():
    vers = [
        ClaimVerification(claim="A", verdict="supported", evidence=[]),
        ClaimVerification(claim="B", verdict="contradicted", evidence=[]),
    ]
    ok, _, reason = decide(vers)
    assert not ok
    assert "çelişkili" in reason


def test_main_claim_not_found_rejects():
    vers = [
        ClaimVerification(claim="ana iddia", verdict="not_found", evidence=[]),
        ClaimVerification(claim="ikincil", verdict="supported", evidence=[]),
    ]
    ok, _, reason = decide(vers)
    assert not ok
    assert "ana iddia" in reason


def test_all_not_found_rejects():
    vers = [ClaimVerification(claim="A", verdict="not_found", evidence=[])]
    ok, _, _ = decide(vers)
    assert not ok


def test_supported_claims_accepted_and_not_found_removed():
    vers = [
        ClaimVerification(claim="ana", verdict="supported", evidence=[]),
        ClaimVerification(claim="ikincil", verdict="not_found", evidence=[]),
        ClaimVerification(claim="üçüncül", verdict="supported", evidence=[]),
    ]
    ok, usable, _ = decide(vers)
    assert ok
    assert len(usable) == 2
    assert all(v.verdict == "supported" for v in usable)


def test_validate_evidence_handles_ana_iddia_prefix_and_url_normalization():
    quote = "%40 daha verimli olduğunu açıkladı"
    r1 = [ClaimVerification(
        claim="[ANA İDDİA] X %40 arttı",
        verdict="supported",
        evidence=[Evidence(url="https://a.com/1/", quote=quote)],
    )]
    r2 = [ClaimVerification(
        claim="X %40 arttı",
        verdict="supported",
        evidence=[Evidence(url="https://a.com/1?utm_source=rss", quote=quote)],
    )]
    final = validate_evidence(r1, r2, SOURCE_TEXTS)
    assert final[0].verdict == "supported"
    assert len(final[0].evidence) == 1
    assert final[0].evidence[0].url == "https://a.com/1"


def test_validate_evidence_rejects_not_found_placeholder_quote():
    r1 = [ClaimVerification(
        claim="X", verdict="supported",
        evidence=[Evidence(url="https://a.com/1", quote="not_found")],
    )]
    r2 = [ClaimVerification(
        claim="X", verdict="supported",
        evidence=[Evidence(url="https://a.com/1", quote="not_found")],
    )]
    final = validate_evidence(r1, r2, SOURCE_TEXTS)
    assert final[0].verdict == "not_found"


def test_corroborating_from_rss_blocks_generic_word_false_positives():
    from app.models import Candidate, CrosscheckInfo
    from app.verify.crosscheck import corroborating_from_rss

    genie = Candidate(
        title="Genie 4 is now available",
        url="https://blog.google/technology/ai/genie-4/",
        summary="Google releases Genie 4 world model.",
        source_name="Google Blog",
    )
    gta = Candidate(
        title="UK joins in GTA 6 frenzy as game becomes available worldwide",
        url="https://www.bbc.co.uk/news/articles/gta6",
        summary="Gamers line up for GTA 6 launch.",
        source_name="BBC News",
    )
    forum = Candidate(
        title="Forum, a Dedicated App for Facebook Groups, Is Now Available in Indonesia",
        url="https://about.fb.com/news/2026/11/forum/",
        summary="Meta launches Forum app in Indonesia.",
        source_name="Meta Newsroom",
    )
    info = CrosscheckInfo(search_query="Genie 4 Google", entities=["Google", "Genie 4"], event_type="product_launch")
    matches = corroborating_from_rss([genie, gta, forum], genie, info)
    assert matches == []


def test_corroborating_from_rss_ranks_real_match_first():
    from app.models import Candidate, CrosscheckInfo
    from app.verify.crosscheck import corroborating_from_rss

    selected = Candidate(
        title="Blue Origin will launch Google's AI server satellites in 2029",
        url="https://www.theverge.com/tech/blue-origin-google-satellites",
        summary="Google partners with Blue Origin on Project Suncatcher satellites.",
        source_name="The Verge",
        entities=["Google", "Blue Origin"],
    )
    noise = Candidate(
        title="Google's AI feature in Search gets its own incognito mode",
        url="https://techcrunch.com/2026/11/19/google-search-incognito/",
        summary="Google adds temporary threads to Search AI Mode.",
        source_name="TechCrunch",
        entities=["Google"],
    )
    real = Candidate(
        title="We're partnering with Blue Origin on our first heavy-lift Project Suncatcher",
        url="https://blog.google/technology/blue-origin-suncatcher/",
        summary="Google and Blue Origin will launch AI server satellites in 2029.",
        source_name="Google Blog",
        entities=["Google", "Blue Origin"],
    )
    info = CrosscheckInfo(
        search_query="Blue Origin Google AI satellites",
        entities=["Blue Origin", "Google", "Project Suncatcher"],
        event_type="partnership",
    )
    matches = corroborating_from_rss([selected, noise, real], selected, info)
    assert matches
    assert matches[0]["url"] == real.url
    assert all(m["url"] != noise.url for m in matches)


def test_verify_candidate_rejects_non_whitelist_url():
    from unittest.mock import Mock
    from app.main import _verify_candidate
    from app.models import Candidate

    bad = Candidate(
        title="Fake rumor",
        url="https://random-fake-blog.example/post",
        raw={"full_text": "x" * 1000},
    )
    assert _verify_candidate(Mock(), bad, [], allow_single_source=True) is None


def test_verify_candidate_accepts_official_primary_source_with_verified_quotes(monkeypatch):
    from unittest.mock import Mock
    from app import main
    from app.models import Candidate, Claim, ClaimVerification, CrosscheckInfo, Evidence

    url = "https://blog.google/technology/ai/project-suncatcher/"
    text = (
        "Google announced Project Suncatcher with Blue Origin. "
        "The heavy-lift rocket will launch AI server satellites in 2029. "
        "Engineers tested radiation-hardened chips for orbital compute. "
    ) * 4
    cand = Candidate(title="Project Suncatcher", url=url, source_name="Google Blog",
                     source_kind="official", raw={"full_text": text})
    monkeypatch.setattr(main, "crosscheck_query", lambda llm, c: CrosscheckInfo(entities=["Google", "Blue Origin"]))
    monkeypatch.setattr(main, "corroborating_from_rss", lambda *a, **kw: [])
    monkeypatch.setattr(main, "find_corroborating_sources", lambda *a, **kw: [])
    monkeypatch.setattr(main, "extract_claims", lambda llm, t: [
        Claim(claim="Google, Blue Origin ile Project Suncatcher'ı duyurdu", is_main=True),
        Claim(claim="Yapay zeka sunucu uyduları 2029'da fırlatılacak"),
    ])
    v_list = [
        ClaimVerification(
            claim="Google, Blue Origin ile Project Suncatcher'ı duyurdu",
            verdict="supported",
            evidence=[Evidence(url=url, quote="Google announced Project Suncatcher with Blue Origin.")],
        ),
        ClaimVerification(
            claim="Yapay zeka sunucu uyduları 2029'da fırlatılacak",
            verdict="supported",
            evidence=[Evidence(url=url, quote="The heavy-lift rocket will launch AI server satellites in 2029.")],
        ),
    ]
    monkeypatch.setattr(main, "verify_claims_round", lambda *a, **kw: v_list)
    res = main._verify_candidate(Mock(), cand, [])
    assert res is not None
    assert len(res["usable"]) == 2
    assert res["source_names"] == ["Google Blog"]


def test_verify_candidate_single_news_fallback_requires_three_verified_claims(monkeypatch):
    from unittest.mock import Mock
    from app import main
    from app.models import Candidate, Claim, ClaimVerification, CrosscheckInfo, Evidence

    url = "https://www.wired.com/story/ai-chip-test/"
    text = (
        "Researchers built a new photonic AI chip at MIT. "
        "The chip cuts power consumption by 40 percent in lab tests. "
        "Commercial trials are planned for 2027. "
    ) * 6
    cand = Candidate(title="Photonic AI chip", url=url, source_name="Wired",
                     source_kind="news", raw={"full_text": text})
    monkeypatch.setattr(main, "crosscheck_query", lambda llm, c: CrosscheckInfo(entities=["MIT"]))
    monkeypatch.setattr(main, "corroborating_from_rss", lambda *a, **kw: [])
    monkeypatch.setattr(main, "find_corroborating_sources", lambda *a, **kw: [])
    monkeypatch.setattr(main, "extract_claims", lambda llm, t: [
        Claim(claim="MIT yeni fotonik yapay zeka çipi geliştirdi", is_main=True),
        Claim(claim="Çip güç tüketimini %40 azaltıyor"),
    ])
    v_two = [
        ClaimVerification(
            claim="MIT yeni fotonik yapay zeka çipi geliştirdi",
            verdict="supported",
            evidence=[Evidence(url=url, quote="Researchers built a new photonic AI chip at MIT.")],
        ),
        ClaimVerification(
            claim="Çip güç tüketimini %40 azaltıyor",
            verdict="supported",
            evidence=[Evidence(url=url, quote="The chip cuts power consumption by 40 percent in lab tests.")],
        ),
    ]
    monkeypatch.setattr(main, "verify_claims_round", lambda *a, **kw: v_two)
    # Normal modda 2 kaynak yok -> reddedilir
    assert main._verify_candidate(Mock(), cand, []) is None
    # Tek kaynak yedeğinde bile sadece 2 iddia yetmez (en az 3 gerekir)
    assert main._verify_candidate(Mock(), cand, [], allow_single_source=True) is None
    # 3 doğrulanmış iddiayla tek whitelist kaynak yedeği geçer
    v_three = v_two + [
        ClaimVerification(
            claim="Ticari denemeler 2027 için planlanıyor",
            verdict="supported",
            evidence=[Evidence(url=url, quote="Commercial trials are planned for 2027.")],
        )
    ]
    monkeypatch.setattr(main, "verify_claims_round", lambda *a, **kw: v_three)
    res = main._verify_candidate(Mock(), cand, [], allow_single_source=True)
    assert res is not None
    assert len(res["usable"]) == 3
