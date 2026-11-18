"""Read the published Turkish discussion and prepare Tekno Pusula's cards."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from textwrap import shorten
from uuid import UUID
from zoneinfo import ZoneInfo

import requests

from app.models import Caption, Captions

SITE_URL = "https://weetis.com"
EDITOR_CODE = "E0D17A11"
ISTANBUL = ZoneInfo("Europe/Istanbul")


@dataclass(frozen=True)
class Discussion:
    id: str
    title: str
    body: str

    @property
    def url(self) -> str:
        return f"{SITE_URL}/tr/d/{self.id}"


def fetch_discussion(date_label: str) -> Discussion | None:
    """The featured post can outlive its publication date or be set manually."""
    with requests.Session() as session:
        response = session.get(f"{SITE_URL}/api/featured", params={"lang": "tr"}, timeout=12)
        response.raise_for_status()
        featured = response.json().get("post")
        if not featured:
            return None
        discussion_id = str(UUID(featured["id"]))

        response = session.get(f"{SITE_URL}/api/post", params={"id": discussion_id}, timeout=12)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        post = response.json()["post"]

    if (post.get("id") != discussion_id or post.get("language") != "tr"
            or post.get("kind") != "discussion" or post.get("author_code") != EDITOR_CODE):
        return None
    published = datetime.fromtimestamp(post["created"] / 1000, ISTANBUL)
    if published.date().isoformat() != date_label:
        return None

    title = " ".join(post["title"].split())
    body = " ".join(post["body"].split())
    return Discussion(discussion_id, title, body) if title and body else None


def build_cards(discussion: Discussion) -> dict:
    title = shorten(discussion.title, width=60, placeholder="…")
    return {
        "cover": {
            "category_label": "Günün tartışması",
            "title": title if title != "…" else discussion.title[:59] + "…",
            "highlight_words": [title.split()[0]] if title != "…" else [],
            "highlight_color": "yellow",
            "subtitle": "Weetis’te bugün bu konuyu konuşuyoruz.",
            "source_tags": ["Weetis"],
        },
        "context": {
            "heading": "Bugün Ne Tartışıyoruz?",
            "cards": [{"card_title": "Tartışmanın konusu",
                       "card_body": shorten(discussion.body, width=340, placeholder="…")}],
        },
        "stat": {
            "big_stat": "NEDEN?",
            "stat_caption": "Görüşünün dayanağı ne?",
            "stat_quote": "Seni o görüşe götüren nedeni tek cümleyle anlat.",
        },
        "details": {
            "heading": "Bir Örnek Ver",
            "cards": [
                {"card_title": "Deneyimin", "card_body": "Buna benzer bir durum yaşadıysan ne olduğunu anlat."},
                {"card_title": "Kararın", "card_body": "Aynı durumda ne yapardın? Seçimini ne belirlerdi?"},
            ],
        },
        "impact": {
            "heading": "Hangi Koşulda Fikrin Değişir?",
            "cards": [{"card_title": "Karşı görüş",
                       "card_body": "Sana ters gelen görüşün hangi durumda geçerli olabileceğini düşün."}],
        },
        "cta": {
            "question": "Bu konuda sen ne düşünüyorsun?",
            "reminder_line": "Weetis’te hesap açmadan yorum bırakabilirsin. Bağlantı açıklamada.",
        },
        "tag_label_2": "KONU",
        "tag_label_3": "GEREKÇE",
        "tag_label_4": "DENEYİM",
        "tag_label_5": "KARŞI GÖRÜŞ",
        "tag_label_6": "WEETIS TARTIŞMASI",
        "show_follow_cta": False,
    }


def build_captions(discussion: Discussion) -> Captions:
    # Leave room for the call to action and URL, even with double-width X text.
    title = shorten(discussion.title, width=70, placeholder="…")
    question = "Kendi deneyimini ve görüşünün nedenini yaz. Weetis’te hesap açmadan yorum bırakabilirsin."
    text = f"{title}\n\n{question}\n\n{discussion.url}"
    return Captions(**{
        platform: Caption(text=text + ("?s=th" if platform == "threads" else ""))
        for platform in Captions.model_fields
    })
