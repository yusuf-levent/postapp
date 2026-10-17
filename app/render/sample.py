"""Örnek post render aracı: gerçek Gemini verisi olmadan tasarım önizlemesi.

Çalıştırma:
  python -m app.render.sample

Bölüm 8'deki tasarımı doğrulamak için örnek bir postu yerelde render eder
(output/_sample/ altına). Görsel indirmez; soyut gradient arka plan kullanır.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.config import REPO_ROOT
from app.media.collector import make_abstract_background
from app.render.fonts import ensure_fonts
from app.render.renderer import render_png, render_png_9x16, render_slide_html

log = logging.getLogger("tekno-pusula.sample")

OUT_DIR = REPO_ROOT / "output" / "_sample"


def sample_deck() -> dict:
    """Gerçekçi örnek içerik: 6 slayt (referans tasarıma birebir uygun)."""
    return {
        "cover": {
            "category_label": "YAPAY ZEKA DONANIMI • YARI İLETKEN SAVAŞLARI",
            "title": "Nvidia'ya Karşı Hamle: Maia 300 Duyuruldu!",
            "highlight_words": ["Nvidia'ya", "Maia", "300"],
            "highlight_color": "yellow",
            "subtitle": "Microsoft, Nvidia'ya olan milyarlarca dolarlık bağımlılığını kırmak için 3. nesil özel yapay zeka hızlandırıcısı Maia 300'ü resmen tanıttı.",
            "source_tags": ["the verge", "microsoft"],
        },
        "context": {
            "heading": "Devrimsel Chiplet Mimarisi",
            "cards": [
                {
                    "card_title": "TSMC N2P 2 Nanometre Üretim",
                    "card_body": "Maia 300; hesaplama, bellek denetleyicisi ve I/O fonksiyonlarını modüler ayıran gelişmiş chiplet mimarisiyle TSMC'nin en yeni 2nm bandında üretiliyor.",
                },
                {
                    "card_title": "Maksimum Hesaplama Yoğunluğu",
                    "card_body": "Modüler mimari sayesinde silikon yüzeyinin neredeyse tamamı saf yapay zeka işlem gücüne tahsis edilerek termal verimlilik zirveye çıkarıldı.",
                },
            ],
        },
        "stat": {
            "big_stat": "%40",
            "stat_caption": "Megavat Başına Daha Fazla Token Verimliliği",
            "stat_quote": "Microsoft Cloud EVP Scott Guthrie: 'Maia 300, sektörün lider GPU sistemlerine kıyasla megavat başına %40 daha fazla token üretiyor. 96 hızlandırıcılı tam kabin konfigürasyonunda ise Maia 200'e göre 7 kat daha yüksek throughput sağlıyor!'",
        },
        "details": {
            "heading": "Ajan Çağının Yeni Motoru",
            "cards": [
                {
                    "card_title": "Akıl Yürütme ve Uzun Bağlam",
                    "card_body": "Çip; klasik sohbet modellerinin ötesinde derin akıl yürütme (reasoning), ultra düşük gecikmeli ses ve çok adımlı otonom ajan görevleri için baştan tasarlandı.",
                },
                {
                    "card_title": "Tüm Ürünlerin Birincil Beyni",
                    "card_body": "Microsoft Copilot, GitHub Copilot ve Azure Foundry üzerindeki devasa üretim iş yükleri kademeli olarak Nvidia sistemlerinden Maia 300'e taşınacak.",
                },
            ],
        },
        "impact": {
            "heading": "Süleyman: 'Silikona Kadar İnmeliyiz'",
            "cards": [
                {
                    "card_title": "Model ile Çipin Ortak Tasarımı",
                    "card_body": "Microsoft AI CEO'su Mustafa Suleyman: 'DeepMind, OpenAI ve Anthropic ile yarışmak için silikona kadar tüm yığına sahip olmalıyız. Modellerimizi Maia ile birlikte tasarlıyoruz.'",
                },
                {
                    "card_title": "Çok Gigawatt'lık Dağıtım (2027)",
                    "card_body": "Microsoft, 2027'den itibaren veri merkezlerinde çok gigawatt ölçeğinde Maia 300 dağıtımı yaparak Nvidia ve AMD'ye olan harici bağımlılığını sonlandıracak.",
                },
            ],
        },
        "cta": {
            "question": "Microsoft'un kendi çipi Maia 300 ile Nvidia'ya meydan okuması, yapay zeka pazarındaki yüksek GPU maliyetlerini düşürüp kartları yeniden dağıtabilir mi?",
            "reminder_line": "Düşüncelerini yorumlarda paylaşmayı unutma! 💬",
        },
        "tag_label_2": "YENİ MİMARİ • TSMC 2NM VE CHIPLET",
        "tag_label_3": "ENERJİ VE HIZ • GPU'LARA KARŞI REKOR",
        "tag_label_4": "İŞ YÜKLERİ • COPILOT VE AJAN ÇAĞI",
        "tag_label_5": "STRATEJİ • SİLİKONDAN MODELE TAM HAKİMİYET",
        "tag_label_6": "GELECEK • ÇİP SAVAŞLARI",
    }


MICROSOFT_SVG = (
    '<svg viewBox="0 0 24 24" fill="#FFFFFF" xmlns="http://www.w3.org/2000/svg">'
    '<path d="M1 1h10.5v10.5H1V1zm12.5 0H24v10.5H13.5V1zM1 13.5h10.5V24H1V13.5zm12.5 0H24V24H13.5V13.5z"/>'
    "</svg>"
)


def render_sample() -> Path:
    """Örnek postu render eder; klasör yolunu döndürür."""
    logging.basicConfig(level=logging.INFO)
    fonts_dir = ensure_fonts()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    bgs = [
        make_abstract_background(OUT_DIR / "images" / f"abstract-bg-{v}.png", variant=v)
        for v in range(3)
    ]

    deck = sample_deck()
    results = {"slides": [], "slides_9x16": []}

    async def _render() -> None:
        for i in range(1, 7):
            d = dict(deck)
            d["bg_image"] = str(bgs[(i - 1) % len(bgs)])
            d["logo_svg"] = MICROSOFT_SVG
            html = render_slide_html(d, i)

            dest = OUT_DIR / "slides" / f"slide-{i}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            await render_png(
                html, dest, width=1080, height=1350, fonts_dir=fonts_dir
            )
            results["slides"].append(dest)

            dest916 = OUT_DIR / "slides_9x16" / f"slide-{i}.png"
            dest916.parent.mkdir(parents=True, exist_ok=True)
            await render_png_9x16(
                html, dest916, 1080, 1350, 1080, 1920, fonts_dir=fonts_dir
            )
            results["slides_9x16"].append(dest916)
            print(f"  [OK] slide-{i}.png (4:5 + 9:16)")

    asyncio.run(_render())
    return OUT_DIR


if __name__ == "__main__":
    out = render_sample()
    print(f"\nÖrnek post hazır: {out}")
    print(f"Önizleme: python -m app.tools.preview {out}")