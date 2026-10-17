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
                            evidence=[Evidence(url="u", quote=quote)])]
    r2 = [ClaimVerification(claim="X %40 arttı", verdict="supported",
                            evidence=[Evidence(url="u", quote=quote)])]
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