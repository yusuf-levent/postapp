"""Doğrulama raporu üretimi: verification.md + evidence.json + sources/."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.common import now_istanbul
from app.models import ClaimVerification, Evidence


def write_verification_report(
    post_dir: Path,
    *,
    title: str,
    canonical_url: str,
    source_names: list[str],
    verifications: list[ClaimVerification],
    source_texts: dict[str, str],
    round1: list[ClaimVerification],
    round2: list[ClaimVerification],
    accepted: bool,
    reject_reason: str = "",
) -> None:
    """verification.md, evidence.json ve sources/*.txt yazar."""
    checked_at = now_istanbul().isoformat(timespec="seconds")

    # sources/ klasörüne kaynak metinleri kaydet (makale silinse de kanıt kalsın)
    sources_dir = post_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)
    for i, (url, text) in enumerate(source_texts.items(), start=1):
        fname = f"source-{i}.txt"
        (sources_dir / fname).write_text(
            f"URL: {url}\nErişim zamanı: {checked_at}\n\n{text}", encoding="utf-8"
        )

    # evidence.json (makine okunur)
    evidence = {
        "title": title,
        "canonical_url": canonical_url,
        "source_names": source_names,
        "checked_at": checked_at,
        "accepted": accepted,
        "reject_reason": reject_reason,
        "claims": [v.model_dump() for v in verifications],
        "round1": [v.model_dump() for v in round1],
        "round2": [v.model_dump() for v in round2],
        "source_texts": {u: len(t) for u, t in source_texts.items()},
    }
    (post_dir / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # verification.md (insan okunur)
    lines = [
        "# Doğrulama Raporu",
        "",
        f"**Haber:** {title}",
        f"**Canonical URL:** {canonical_url}",
        f"**Kaynaklar:** {', '.join(source_names)}",
        f"**Kontrol zamanı:** {checked_at}",
        f"**Sonuç:** {'✅ YAYINLANABİLİR' if accepted else '❌ REDDEDİLDİ — ' + reject_reason}",
        "",
        "---",
        "",
        "## İddia Bazlı Sonuçlar",
        "",
    ]
    for i, v in enumerate(verifications, start=1):
        icon = {"supported": "✅", "contradicted": "❌", "not_found": "⚠️"}[v.verdict]
        lines.append(f"### {i}. {v.claim}")
        lines.append(f"- **Karar:** {icon} `{v.verdict}`")
        if v.evidence:
            lines.append("- **Kanıtlar:**")
            for ev in v.evidence:
                lines.append(f"  - [{ev.url}]({ev.url})")
                lines.append(f"    > {ev.quote}")
        else:
            lines.append("- **Kanıt:** yok")
        lines.append("")

    lines.extend(
        [
            "---",
            "",
            "## İki Tur Karşılaştırması",
            "",
            "| İddia | 1. Tur | 2. Tur | Nihai |",
            "|-------|--------|--------|-------|",
        ]
    )
    r2 = {v.claim[:60]: v.verdict for v in round2}
    for v in verifications:
        r1_verdict = next(
            (x.verdict for x in round1 if x.claim[:60] == v.claim[:60]), "?"
        )
        lines.append(
            f"| {v.claim[:60]} | {r1_verdict} | {r2.get(v.claim[:60], '?')} | {v.verdict} |"
        )

    lines.extend(["", "## Kaynak Metinleri", ""])
    for i, url in enumerate(source_texts.keys(), start=1):
        lines.append(f"- `sources/source-{i}.txt` — {url}")

    (post_dir / "verification.md").write_text("\n".join(lines), encoding="utf-8")