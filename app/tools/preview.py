"""Yerel önizleme: bir post klasöründeki slaytları tarayıcıda gösterir.

Çalıştırma:
  python -m app.tools.preview output/2026-10-15/01-0900-...
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Post slaytlarını önizle")
    parser.add_argument("post_dir", help="Post klasörü yolu")
    args = parser.parse_args()

    post_dir = Path(args.post_dir)
    if not post_dir.exists():
        print(f"Klasör bulunamadı: {post_dir}")
        return 1

    slides = sorted((post_dir / "slides").glob("slide-*.png"))
    if not slides:
        print(f"Slayt PNG bulunamadı: {post_dir / 'slides'}")
        return 1

    html = [
        "<!DOCTYPE html><html lang='tr'><head><meta charset='utf-8'>",
        "<title>Tekno Pusula Önizleme</title>",
        "<style>",
        "body { background:#111; color:#eee; font-family:sans-serif; padding:20px; }",
        ".row { display:flex; gap:16px; flex-wrap:wrap; }",
        ".item { text-align:center; }",
        "img { width:324px; border-radius:8px; }",
        ".nine img { width:180px; }",
        "</style></head><body>",
        f"<h1>{post_dir.name}</h1>",
        "<h2>4:5 (1080×1350)</h2><div class='row'>",
    ]
    for s in slides:
        html.append(f"<div class='item'><img src='{s.as_uri()}'><p>{s.name}</p></div>")
    html.append("</div>")

    slides_916 = sorted((post_dir / "slides_9x16").glob("slide-*.png"))
    if slides_916:
        html.append("<h2>9:16 (1080×1920) — TikTok</h2><div class='row nine'>")
        for s in slides_916:
            html.append(f"<div class='item'><img src='{s.as_uri()}'><p>{s.name}</p></div>")
        html.append("</div>")

    html.append("</body></html>")

    out = post_dir / "preview.html"
    out.write_text("\n".join(html), encoding="utf-8")
    print(f"Önizleme hazır: {out}")
    import webbrowser

    webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())