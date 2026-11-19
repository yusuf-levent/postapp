"""Orkestrasyon: topla → seç → doğrula → üret → görselleştir → render → paylaş.

CLI:
  python -m app.main --slot auto --type auto --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path

from app.collect.article import enrich_candidate
from app.collect.dates import nearest_slot, slot_type, today_label, within_lookback
from app.collect.rss import collect_all
from app.collect.weetis import build_captions as build_weetis_captions
from app.collect.weetis import build_cards as build_weetis_cards
from app.collect.weetis import fetch_discussion
from app.common import now_istanbul, slugify, turkish_upper, source_identity
from app.config import OUTPUT_DIR, platforms_config, schedule_config, settings
from app.llm.gemini import GeminiClient
from app.media.collector import collect_images, make_abstract_background
from app.media.logos import save_logo
from app.media.video_collector import collect_video
from app.models import (
    Candidate,
    Captions,
    CaptionsDoc,
    HistoryEntry,
    PlatformStatus,
)
from app.publish.publisher import publish_all, recover_failed
from app.render.fonts import ensure_fonts
from app.render.qa import run_qa
from app.render.renderer import render_deck
from app.render.templates.styles import CSS
from app.render.video_renderer import render_reel_video
from app.media.video_probe import probe_video
from app.select.dedup import is_duplicate, normalize_url
from app.select.scoring import build_source_index, score_candidates
from app.select.editorial import annotate, rejection_reason, shortlist
from app.scheduling import due_slots as find_due_slots
from app.scheduling import needs_recovery, within_recovery_window
from app.store import history as history_store
from app.store.git_ops import commit_and_push
from app.store.issues import close_resolved_issues, notify_post_published, open_issue
from app.verify.crosscheck import (
    corroborating_from_rss,
    crosscheck_query,
    extract_claims,
    find_corroborating_sources,
)
from app.verify.report import write_verification_report
from app.verify.verifier import decide, validate_evidence, verify_claims_round
from app.write.captions import generate_captions
from app.write.slides import generate_edu_deck, generate_slides

log = logging.getLogger("tekno-pusula")

MAX_CANDIDATES = 4
MAX_SOURCES_FOR_VERIFICATION = 3


class SlotSkipped(Exception):
    """Slot atlandı (uyarıyla biter, workflow başarısız DEĞİL)."""


def run(
    *,
    slot: str = "auto",
    force_type: str = "auto",
    dry_run: bool = False,
) -> int:
    """Ana akış. Dönüş: 0 (başarılı veya slot atlandı — asla 1 değil)."""
    started = time.time()
    sched = schedule_config()

    date_label = today_label()
    _recovery_pass(dry_run=dry_run)
    # 2) Slot ve tip
    if slot == "auto":
        if not dry_run:
            now_ist = now_istanbul()
            due_slots = find_due_slots(sched, [e.model_dump() for e in history_store.load_history()]
                                      + history_store.load_skipped_slots(), now_ist)
            if not due_slots:
                log.info("Bugün (%s) için saati gelmiş bekleyen slot yok (hepsi yayınlanmış veya henüz saati gelmedi), çıkılıyor.", date_label)
                return 0
            if len(due_slots) > 1:
                log.info("Bugün için bekleyen %d slot sırayla çalıştırılacak: %s", len(due_slots), due_slots)
                rc = 0
                for s in due_slots:
                    sub_rc = run(slot=s, force_type=force_type, dry_run=dry_run)
                    if sub_rc != 0:
                        rc = sub_rc
                return rc
            slot = due_slots[0]
        else:
            slot = nearest_slot()

    ptype = slot_type(slot, force_type=force_type)
    log.info("Slot: %s (%s), tarih: %s, tip: %s, dry_run: %s",
             slot, now_istanbul().strftime("%H:%M"), date_label, ptype, dry_run)

    # 3) Idempotent kontrol: aynı slot için zaten yayınlanmış post var mı?
    if history_store.slot_already_done(date_label, slot):
        log.info("Bu slot için zaten post üretilmiş (%s %s), tekrar üretilmiyor.",
                 date_label, slot)
        return 0
    if ptype == "weetis":
        return _run_weetis(date_label, slot, dry_run=dry_run, started=started)

    # 3b) Eğer bu slot için daha önce dry_run ile üretilmiş hazır bir post klasörü varsa,
    # yeniden üretmek yerine doğrudan onu yayınla!
    if not dry_run:
        existing_rc = _publish_existing_dry_run(
            date_label=date_label,
            slot=slot,
            force_type=force_type,
            started=started,
        )
        if existing_rc is not None:
            return existing_rc

    llm = GeminiClient()

    # 4) Toplama
    all_candidates = collect_all(max_days=sched["max_lookback_days"], include_official=True)
    if not all_candidates:
        log.warning("Hiç aday toplanamadı.")
        if ptype == "news" and sched.get("fallback_to_edu"):
            ptype = "edu"
        else:
            _skip_slot(date_label, slot, "aday bulunamadı", dry_run=dry_run)
            return 0

    # 5) Seçim: dedup + puanlama
    history = history_store.load_history()
    today_posts = history_store.entries_for_day(date_label)
    source_index = build_source_index(all_candidates)
    editorial_candidates = [annotate(c) for c in all_candidates if not rejection_reason(c)]
    scored = score_candidates(editorial_candidates, source_index=source_index)
    scored = [c for c in scored if not is_duplicate(c, history, today_posts=today_posts)[0]]
    scored = shortlist(llm, scored, history, mode=ptype)

    selected: Candidate | None = None
    verifications = []
    verified_claims = []
    source_texts: dict[str, str] = {}
    source_names: list[str] = []
    cross_urls: list[str] = []
    tried = 0
    max_candidates = sched.get("max_candidates_per_run", MAX_CANDIDATES)
    single_source_pool: list[Candidate] = []

    for cand in scored:
        if tried >= max_candidates:
            break
        dup, reason = is_duplicate(cand, history, today_posts=today_posts)
        if dup:
            log.info("Aday reddedildi (dedup): %s — %s", cand.title[:60], reason)
            continue

        # Makale metni + tarih doğrulama
        enriched = enrich_candidate(cand)
        if enriched is None:
            continue

        # Kritik: enrich_candidate makale sayfasından tarihi GÜNCELLEDİ.
        # Yeni tarih lookback penceresi DIŞINDA ise aday DÜŞÜRÜLMELİ.
        # (Aksi halde 1 aylık eski haber "bugünün haberi" gibi paylaşılır.)
        if not within_lookback(enriched.published, sched["max_lookback_days"]):
            log.info(
                "Aday reddedildi (eski haber): %s — yayın tarihi %s lookback penceresi dışında",
                enriched.title[:60], enriched.published,
            )
            continue

        tried += 1
        log.info("Aday deneniyor (%d/%d): %s", tried, max_candidates, cand.title[:70])

        try:
            if ptype == "edu":
                result = _verify_candidate(llm, enriched, all_candidates, allow_single_source=True)
            else:
                result = _verify_candidate(llm, enriched, all_candidates)
        except Exception as exc:
            log.warning("Doğrulama hatası, sonraki adaya geçiliyor: %s", exc)
            continue

        if result is None:
            if ptype == "news" and len(enriched.raw.get("full_text", "")) >= 500:
                single_source_pool.append(enriched)
            log.info("Aday doğrulanamadı, sıradaki adaya geçiliyor.")
            continue

        dup, reason = is_duplicate(enriched, history, today_posts=today_posts)
        if dup:
            log.info("Doğrulama sonrası tekrar/çeşitlilik kontrolü: %s", reason)
            continue

        selected = enriched
        verifications = result["verifications"]
        verified_claims = result["usable"]
        source_texts = result["source_texts"]
        source_names = result["source_names"]
        cross_urls = result["cross_urls"]
        break

    # 5b) İki bağımsız kaynaklı / resmi aday geçemediyse, tam metinli whitelist
    #     adaylarda sıkı tek-kaynak (2 tur + birebir alıntı + ≥3 iddia) yedeğini dene.
    if selected is None and ptype == "news" and single_source_pool:
        log.info(
            "2 kaynaklı aday bulunamadı; en yüksek puanlı %d tam metinli whitelist aday "
            "sıkı 2-turlu alıntı doğrulamasıyla deneniyor.",
            min(len(single_source_pool), 3),
        )
        for enriched in single_source_pool[:3]:
            try:
                result = _verify_candidate(
                    llm, enriched, all_candidates, allow_single_source=True,
                )
            except Exception as exc:
                log.warning("Tek kaynak doğrulama hatası: %s", exc)
                continue
            if result is None:
                continue
            dup, reason = is_duplicate(enriched, history, today_posts=today_posts)
            if dup:
                log.info("Doğrulama sonrası tekrar/çeşitlilik kontrolü: %s", reason)
                continue
            selected = enriched
            verifications = result["verifications"]
            verified_claims = result["usable"]
            source_texts = result["source_texts"]
            source_names = result["source_names"]
            cross_urls = result["cross_urls"]
            break

    # 6) Haber yoksa eğitim postuna düş
    if selected is None:
        if ptype == "news" and sched.get("fallback_to_edu"):
            log.warning("Doğrulanabilir haber bulunamadı, eğitim postuna dönülüyor.")
            ptype = "edu"
        else:
            _skip_slot(date_label, slot, "editöryal ve doğrulama kurallarını geçen aday yok", dry_run=dry_run)
            return 0

    # 7) Post klasörü
    post_dir = _make_post_dir(date_label, slot, selected, ptype)
    log.info("Post klasörü: %s", post_dir)

    # 8) Doğrulama raporu
    write_verification_report(
        post_dir,
        title=selected.title if selected else "Eğitim İçeriği",
        canonical_url=selected.url if selected else "",
        source_names=source_names,
        verifications=verifications,
        source_texts=source_texts,
        round1=verifications,
        round2=verifications,
        accepted=True,
    )

    # 9) İçerik üretimi
    if ptype == "edu":
        claims_text = "\n".join(f"- {v.claim}" for v in verified_claims) or "Yapay zeka, büyük dil modelleri (LLM), çip mimarileri ve modern yazılım mühendisliği kavramları."
        deck_model = generate_edu_deck(llm, claims_text, source_names or ["Tekno Pusula"])
        deck = _edu_deck_to_dict(deck_model)
    else:
        deck_model = generate_slides(llm, verified_claims, source_names)
        deck = _slide_deck_to_dict(deck_model, source_names)

    # content.json
    (post_dir / "content.json").write_text(
        json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 10) Görseller + logo
    entities = (selected.entities or []) if selected else []
    images = collect_images(llm, selected, entities, post_dir) if selected else []
    bg_image_paths: list[str] = []
    if images:
        bg_image_paths = [img.local_path for img in images if img.local_path]
    if not bg_image_paths:
        abstract = make_abstract_background(post_dir / "images" / "abstract-bg.png")
        bg_image_paths = [str(abstract)]
    # Her slayt için farklı arka plan (6 slaytta da aynı görsel kullanılmaz)
    deck_bg = _assign_backgrounds(bg_image_paths)

    # Logo
    logo_svg = ""
    primary_entity = entities[0] if entities else ""
    if primary_entity:
        logo_path = post_dir / "images" / "logo.svg"
        if save_logo(primary_entity, str(logo_path)):
            logo_svg = logo_path.read_text(encoding="utf-8")
        else:
            log.info("Logo bulunamadı, logo alanı boş bırakılıyor: %s", primary_entity)

    # 11) Render (fontlar önce hazır olsun)
    fonts_dir = ensure_fonts()
    deck["logo_svg"] = logo_svg
    # Reserve required text/vision calls before optional video searches.
    reference_claims = [f"{v.claim}\n" + "\n".join(f"Kaynak ({e.url}): {e.quote}" for e in v.evidence)
                        for v in verified_claims]
    for qa_attempt in range(2):
        (post_dir / "content.json").write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
        render_inputs = []
        for i in range(1, 7):
            d = dict(deck)
            d["bg_image"] = _to_file_url(deck_bg[i - 1])
            render_inputs.append(d)
        rendered = _render_with_backgrounds(render_inputs, post_dir, fonts_dir)
        captions = generate_captions(llm, json.dumps(deck, ensure_ascii=False)[:6000], source_names)
        qa_ok, qa_issues = run_qa(llm, rendered["slides"], verified_claims=reference_claims,
                                 captions_json=captions.model_dump_json(), content_json=json.dumps(deck, ensure_ascii=False))
        if qa_ok:
            break
        (post_dir / f"qa_issues-{qa_attempt + 1}.json").write_text(
            json.dumps(qa_issues, ensure_ascii=False, indent=2), encoding="utf-8")
        if qa_attempt or any("servisine erişilemedi" in str(i.get("problem", "")) for i in qa_issues):
            raise RuntimeError(f"Görsel/içerik kalite kontrolü geçmedi: {qa_issues}")
        feedback = "\n".join(str(i.get("problem", "")) for i in qa_issues)
        if ptype == "edu":
            deck = _edu_deck_to_dict(generate_edu_deck(llm, "\n".join(reference_claims), source_names, feedback=feedback))
        else:
            deck = _slide_deck_to_dict(generate_slides(llm, verified_claims, source_names, feedback=feedback), source_names)
        deck["logo_svg"] = logo_svg

    # 11b) Reels & TikTok için gerçek video topla + Hibrit ses (orijinal ses veya Türkçe seslendirme + fon müziği) + 9:16 video üret
    reel_path: Path | None = None
    music_info: dict[str, Any] | None = None
    voiceover_info: dict[str, Any] | None = None
    try:
        if cross_urls:
            source_video = collect_video(llm, selected, entities, post_dir, extra_urls=cross_urls)
        else:
            source_video = collect_video(llm, selected, entities, post_dir)
        if source_video and source_video.exists():
            # Video kredisi (Wikimedia CC BY atıfı için zorunlu)
            try:
                vmeta_path = post_dir / "video" / "video_meta.json"
                if vmeta_path.exists():
                    video_meta = json.loads(vmeta_path.read_text(encoding="utf-8"))
                    _write_video_credit(post_dir, video_meta)
                    deck["video_illustrative"] = bool(video_meta.get("illustrative"))
            except Exception:
                pass
            src_probe = probe_video(source_video)
            has_orig_audio = bool(src_probe.get("has_audio")) and not bool(deck.get("video_illustrative"))
            from app.media.voiceover import synthesize_storyboard_voiceover
            from app.render.video_renderer import build_storyboard

            voiceover_info = synthesize_storyboard_voiceover(
                build_storyboard(deck),
                post_dir / "video",
                llm=llm,
                verified_claims=reference_claims,
            )
            # Archive.org fon müziği yalnızca hem orijinal ses hem seslendirme yoksa son çare olarak kullanılır
            if not has_orig_audio and voiceover_info is None:
                from app.media.music import find_music as _find_music

                dest_music = post_dir / "video" / "music.mp3"
                music_info = _find_music(
                    llm,
                    selected.title if selected else "",
                    entities,
                    duration=15.0,
                    dest=dest_music,
                )
                if music_info:
                    _write_music_credit(post_dir, music_info)
            reel_path = render_reel_video(
                deck, source_video, post_dir,
                fonts_dir=fonts_dir, music_info=music_info, voiceover_info=voiceover_info,
            )
    except Exception as exc:
        log.warning("Reels/TikTok video üretim adımı atlandı: %s", exc)

    # 11c) GERÇEK video bulunamadıysa SAHTE video (slayt zoom) ÜRETİLMEZ.
    #      reel_path None kalır → Instagram/TikTok'a normal görsel carousel gönderilir.
    #      (Kullanıcı isteği: slaytı yakınlaştırıp "video" olarak gönderme!)
    if reel_path is None:
        log.info(
            "Bu haber için doğrulanmış gerçek video bulunamadı; "
            "sahte slideshow video ÜRETİLMEDİ. Instagram/TikTok'a görsel carousel gönderilecek."
        )

    _write_captions(post_dir, captions, source_names, selected,
                    title_tr=deck.get("cover", {}).get("title", ""))

    # 14) Meta
    _write_meta(post_dir, slot, ptype, llm, started, tried, selected)

    # 15) Commit + push (görseller ve reel.mp4 herkese açık URL için)
    title_tr = deck.get("cover", {}).get("title", "")
    entry = HistoryEntry(
        id=f"{date_label}-{slot.replace(':', '')}",
        date=date_label,
        slot=slot,
        type=ptype,
        title_tr=title_tr,
        original_title=selected.title if selected else "",
        source_urls=[selected.url] if selected else [],
        canonical_url=normalize_url(selected.url) if selected else "",
        entities=entities,
        event_type=selected.event_type if selected else "",
        embedding=selected.embedding if selected else [],
        created_at=now_istanbul().isoformat(timespec="seconds"),
        verified_claims_count=len(verified_claims),
        topic=selected.topic if selected else "",
        primary_entity=selected.primary_entity if selected else "",
        event_key=selected.event_key if selected else "",
    )
    return _publish_prepared(
        entry, post_dir, captions, rendered, reel_path,
        dry_run=dry_run, started=started, tried=tried,
    )


def _run_weetis(date_label: str, slot: str, *, dry_run: bool, started: float) -> int:
    discussion = fetch_discussion(date_label)
    if discussion is None:
        log.warning("Weetis'te bugüne ait yayına hazır tartışma yok (%s %s).", date_label, slot)
        return 0

    if any(entry.type == "weetis" and entry.event_key == discussion.id
           for entry in history_store.load_history()):
        _skip_slot(date_label, slot, "Weetis tartışması zaten işlendi", dry_run=dry_run)
        return 0

    source = Candidate(title=discussion.title, url=discussion.url)
    post_dir = _make_post_dir(date_label, slot, source, "weetis")
    deck = build_weetis_cards(discussion)
    captions = build_weetis_captions(discussion)
    title = deck["cover"]["title"]
    (post_dir / "content.json").write_text(json.dumps(deck, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_captions(post_dir, captions, ["Weetis"], source, title_tr=title)

    backgrounds = [
        make_abstract_background(post_dir / "images" / f"abstract-bg-{index}.png", variant=index)
        for index in range(3)
    ]
    inputs = [
        {**deck, "bg_image": str(backgrounds[index % len(backgrounds)])}
        for index in range(6)
    ]
    rendered = _render_with_backgrounds(inputs, post_dir, ensure_fonts())
    entry = HistoryEntry(
        id=f"{date_label}-{slot.replace(':', '')}",
        date=date_label,
        slot=slot,
        type="weetis",
        title_tr=title,
        original_title=discussion.title,
        source_urls=[discussion.url],
        canonical_url=discussion.url,
        created_at=now_istanbul().isoformat(timespec="seconds"),
        event_key=discussion.id,
    )
    return _publish_prepared(entry, post_dir, captions, rendered, None, dry_run=dry_run, started=started)


def _publish_prepared(
    entry: HistoryEntry, post_dir: Path, captions: Captions, rendered: dict, reel_path: Path | None,
    *, dry_run: bool, started: float, tried: int = 0,
) -> int:
    date_label, slot = entry.date, entry.slot
    if not dry_run:
        entry.status_per_platform = [PlatformStatus(platform=name) for name in platforms_config().platforms]
        (post_dir / "status.json").write_text(json.dumps({
            "dry_run": False,
            "platforms": {status.platform: status.model_dump() for status in entry.status_per_platform},
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        # Recovery must find a prepared post even if the process stops before
        # final history update or its original catch-up window has expired.
        history_store.append_entry(entry)
    commit_msg = (
        f"🤖 post: {date_label} {slot} – "
        f"{(entry.original_title or entry.type)[:60]}"
    )
    if not dry_run:
        if not commit_and_push(commit_msg, [post_dir.relative_to(_repo_root()), "data/history.json"]):
            raise RuntimeError("Medya dosyaları GitHub'a kaydedilemedi; paylaşım başlatılmadı.")

    # 16) Paylaşım
    channel_map = _channel_map() if not dry_run else {}
    image_urls = _public_urls(date_label, post_dir, rendered["slides"])
    image_urls_9x16 = _public_urls(
        date_label, post_dir, rendered.get("slides_9x16", []), subdir="slides_9x16"
    )
    video_url = _public_video_url(post_dir, reel_path)
    status_caption_map = {
        k: _format_caption_text(k, getattr(captions, k).text, getattr(captions, k).hashtags)
        for k in ("instagram", "tiktok", "x", "threads", "linkedin", "facebook")
    }
    thread_replies = [] if entry.type == "weetis" else _thread_replies(status_caption_map["x"], image_urls)

    statuses = publish_all(
        post_dir,
        captions=status_caption_map,
        image_urls=image_urls,
        image_urls_9x16=image_urls_9x16,
        video_url=video_url,
        channel_map=channel_map,
        thread_replies=thread_replies,
        dry_run=dry_run,
        checkpoint=(lambda: _checkpoint_post(post_dir, entry)) if not dry_run else None,
    )

    # 17) Final platform states replace the durable pending reservation.
    #
    # KRİTİK: history.json commit'i, bildirim/issue adımından ÖNCE yapılmalıdır.
    # Bu sıra garanti edilmezse bildirim exception'ı workflow'u çökertir ve
    # history push EDİLEMEZ → sonraki cron turu aynı slotu TEKRAR YAYINLAR
    # (tüm platformlarda aynı post birden fazla gider).
    entry.status_per_platform = list(statuses.values())
    if not dry_run:
        history_store.append_entry(entry)

    # 19) Gün özeti
    _update_daily_summary(date_label)
    summary_path = OUTPUT_DIR / date_label / "daily_summary.md"

    # history + status + daily_summary commit — EN KRİTİK ADIM, ilk sırada.
    # Bu commit başarılıysa slot tamamlanmış sayılır ve tekrar yayınlanmaz.
    if not dry_run and not commit_and_push(
        f"🤖 status: {date_label} {slot}",
        [
            "data/history.json",
            "data/token_state.json",
            post_dir.relative_to(_repo_root()),
            summary_path.relative_to(_repo_root()),
        ],
    ):
        raise RuntimeError("Paylaşım günlüğü GitHub'a kaydedilemedi.")

    # 18) Başarısız platformlar için issue; başarılılar için açık issue kapat.
    # Bu adımlar ASLA workflow'u çökertmemeli (history zaten yukarıda push edildi).
    failed = [s for s in statuses.values() if s.state == "failed"]
    try:
        for st in failed:
            try:
                open_issue(st.platform, date_label, st.last_error)
            except Exception as exc:
                log.warning("Issue açılamadı (%s): %s", st.platform, exc)
        for st in statuses.values():
            if st.state == "published":
                try:
                    close_resolved_issues(st.platform)
                except Exception as exc:
                    log.warning("Issue kapatılamadı (%s): %s", st.platform, exc)

        if not dry_run:
            try:
                notify_post_published(
                    date_label=date_label,
                    slot=slot,
                    ptype=entry.type,
                    title_tr=entry.title_tr,
                    statuses=statuses,
                    image_urls=image_urls,
                    caption_preview=status_caption_map.get("instagram", ""),
                    source_urls=entry.source_urls,
                )
            except Exception as exc:
                log.warning("Bildirim gönderilemedi: %s", exc)
    except Exception as exc:
        log.warning("Yayın sonrası bakım adımları atlandı: %s", exc)

    elapsed = time.time() - started
    log.info("Tamamlandı: %s %s (%.1fs, %d denenen aday)", date_label, slot, elapsed, tried)
    if failed and not dry_run:
        log.error("%d platformda kalıcı paylaşım hatası var.", len(failed))
        return 1
    return 0


# ============================================================ yardımcı fonksiyonlar
def _format_caption_text(platform: str, text: str, hashtags: list[str] | None = None) -> str:
    """Açıklama metnine platform karakter/byte limitini aşmayacak şekilde hashtag ekler."""
    base = (text or "").strip()
    if not hashtags:
        return base
    rules = platforms_config().platforms.get(platform)
    limit = rules.limit if rules else 2000
    tags_str = " ".join(f"#{h.lstrip('#').strip()}" for h in hashtags if h.lstrip("#").strip())
    if not tags_str or tags_str in base:
        return base
    combined = f"{base}\n\n{tags_str}"
    length = len(combined.encode("utf-8")) if platform == "threads" else len(combined)
    if length <= limit:
        return combined
    return base


def _publish_existing_dry_run(
    *,
    date_label: str,
    slot: str,
    force_type: str,
    started: float,
) -> int | None:
    """Aynı gün ve slot için dry_run ile üretilmiş hazır bir klasör varsa onu yayınlar."""
    date_dir = OUTPUT_DIR / date_label
    if not date_dir.exists():
        return None
    slot_compact = slot.replace(":", "")
    candidates = sorted(
        [d for d in date_dir.iterdir() if d.is_dir() and slot_compact in d.name],
        reverse=True,
    )
    target_dir: Path | None = None
    for d in candidates:
        status_file = d / "status.json"
        captions_file = d / "captions.json"
        meta_file = d / "meta.json"
        if not (status_file.exists() and captions_file.exists()):
            continue
        try:
            st_data = json.loads(status_file.read_text(encoding="utf-8"))
            meta_data = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
        except Exception:
            continue
        # Old previews were not editorially reviewed by this pipeline version.
        if meta_data.get("pipeline_version") != 2 or meta_data.get("slot") != slot:
            continue
        if force_type in ("news", "edu") and meta_data.get("type") and meta_data.get("type") != force_type:
            continue
        target_dir = d
        break

    if target_dir is None:
        return None

    log.info("Mevcut dry-run post klasörü bulundu, doğrudan yayınlanıyor: %s", target_dir.name)
    cap_doc = json.loads((target_dir / "captions.json").read_text(encoding="utf-8"))
    meta_doc = (
        json.loads((target_dir / "meta.json").read_text(encoding="utf-8"))
        if (target_dir / "meta.json").exists()
        else {}
    )
    raw_caps = cap_doc.get("captions", {})
    status_caption_map: dict[str, str] = {}
    for k, v in raw_caps.items():
        if isinstance(v, dict):
            status_caption_map[k] = _format_caption_text(k, v.get("text", ""), v.get("hashtags", []))
        else:
            status_caption_map[k] = str(v)

    slide_paths = sorted((target_dir / "slides").glob("slide-*.png"))
    slide_916_paths = sorted((target_dir / "slides_9x16").glob("slide-*.png"))
    image_urls = _public_urls(date_label, target_dir, slide_paths)
    image_urls_9x16 = _public_urls(date_label, target_dir, slide_916_paths, subdir="slides_9x16")
    reel_path = target_dir / "video" / "reel.mp4"
    video_url = _public_video_url(target_dir, reel_path if reel_path.exists() else None)
    thread_replies = _thread_replies(status_caption_map.get("x", ""), image_urls)

    canonical_url = cap_doc.get("canonical_url") or meta_doc.get("canonical_url") or ""
    title_tr = cap_doc.get("title_tr") or target_dir.name
    ptype = meta_doc.get("type") or ("news" if force_type == "news" else "edu")
    entry = HistoryEntry(
        id=f"{date_label}-{slot.replace(':', '')}",
        date=date_label,
        slot=slot,
        type=ptype,
        title_tr=title_tr,
        original_title=title_tr,
        source_urls=[canonical_url] if canonical_url else [],
        canonical_url=normalize_url(canonical_url) if canonical_url else "",
        entities=meta_doc.get("entities", []),
        event_type=meta_doc.get("event_type", ""),
        embedding=[],
        created_at=now_istanbul().isoformat(timespec="seconds"),
        verified_claims_count=1,
        topic=meta_doc.get("topic", ""),
        primary_entity=meta_doc.get("primary_entity", ""),
        event_key=meta_doc.get("event_key", ""),
    )
    statuses = publish_all(
        target_dir,
        captions=status_caption_map,
        image_urls=image_urls,
        image_urls_9x16=image_urls_9x16,
        video_url=video_url,
        channel_map=_channel_map(),
        thread_replies=thread_replies,
        dry_run=False,
        checkpoint=lambda: _checkpoint_post(target_dir, entry),
    )
    entry.status_per_platform = list(statuses.values())
    history_store.append_entry(entry)

    # Save history before optional notification/issue requests, also on resume.
    if not commit_and_push(f"🤖 status: {date_label} {slot}",
                           ["data/history.json", target_dir.relative_to(_repo_root())]):
        raise RuntimeError("Yayın geçmişi kaydedilemedi.")

    failed = [s for s in statuses.values() if s.state == "failed"]
    for st in failed:
        open_issue(st.platform, date_label, st.last_error)
    for st in statuses.values():
        if st.state == "published":
            close_resolved_issues(st.platform)

    notify_post_published(
        date_label=date_label,
        slot=slot,
        ptype=ptype,
        title_tr=title_tr,
        statuses=statuses,
        image_urls=image_urls,
        caption_preview=status_caption_map.get("instagram", ""),
        source_urls=[canonical_url] if canonical_url else [],
    )

    _update_daily_summary(date_label)
    summary_path = OUTPUT_DIR / date_label / "daily_summary.md"
    commit_and_push(
        f"🤖 status: {date_label} {slot}",
        [
            "data/history.json",
            "data/token_state.json",
            target_dir.relative_to(_repo_root()),
            summary_path.relative_to(_repo_root()),
        ],
    )
    elapsed = time.time() - started
    log.info("Mevcut post yayınlandı: %s (%.1fs)", target_dir.name, elapsed)
    if failed:
        log.error("%d platformda paylaşım hatası var.", len(failed))
        return 1
    return 0


def _verify_candidate(
    llm: GeminiClient,
    candidate: Candidate,
    all_candidates: list[Candidate],
    *,
    allow_single_source: bool = False,
) -> dict | None:
    """Aday için tüm doğrulama hattını çalıştırır. Geçemezse None.

    Güvenlik ilkeleri:
    - Kaynak yalnızca whitelist (güvenilir haber veya resmi şirket kaynağı) olabilir.
    - Öncelik her zaman ≥2 bağımsız kaynakta doğrulanmış haberlerdedir.
    - Resmi şirket duyurusu (official whitelist) tam metniyle kendi başına birincil kaynaktır.
    - Tek haber kaynağı yedeği (allow_single_source) yalnızca tam metin (≥500 krk),
      2 turlu mutabakat, kodla birebir alıntı doğrulaması ve ≥3 doğrulanmış iddia ile geçer.
    """
    from app.config import sources_config

    cfg = sources_config()
    if not cfg.is_allowed_url(candidate.url):
        log.info("Whitelist dışı kaynak reddedildi: %s", candidate.url)
        return None

    full_text = candidate.raw.get("full_text", "")
    article_text = full_text or candidate.summary
    if len(article_text.strip()) < 200:
        log.info("Makale metni doğrulama için çok kısa (%d karakter), reddedildi.", len(article_text.strip()))
        return None

    # Aşama 1: çapraz kaynak araması (önce RSS eşleşmesi, yoksa grounding)
    info = crosscheck_query(llm, candidate)
    candidate.entities = list(dict.fromkeys([*candidate.entities, *info.entities]))
    candidate.event_type = info.event_type

    rss_cross = corroborating_from_rss(all_candidates, candidate, info)
    if rss_cross:
        all_cross = rss_cross
    else:
        cross = find_corroborating_sources(llm, candidate, info)
        all_cross = cross + rss_cross

    # Kaynak metinlerini topla (kendi makalesi + en fazla 3 çapraz kaynak)
    source_texts: dict[str, str] = {candidate.url: article_text}
    url_to_name: dict[str, str] = {candidate.url: candidate.source_name}
    cross_urls = []
    for c in all_cross[:MAX_SOURCES_FOR_VERIFICATION]:
        from app.collect.article import extract_text

        text, _ = extract_text(c["url"])
        if text:
            source_texts[c["url"]] = text
            url_to_name[c["url"]] = c.get("source") or c.get("title", "")[:40]
            cross_urls.append(c["url"])

    official_domains = [s.domain for s in cfg.official]
    is_official_primary = any(d in candidate.url.lower() for d in official_domains)
    independent_sources = len({source_identity(u) for u in source_texts})

    if independent_sources < 2:
        if is_official_primary and len(full_text) >= 300:
            log.info("Resmi şirket kaynağı (birincil): %s — 2 turlu alıntı doğrulamasına geçiliyor.", candidate.source_name)
        elif allow_single_source and len(full_text) >= 500:
            log.info("Tek kaynaklı whitelist doğrulama yedeği: %s", candidate.source_name)
        else:
            log.info("2 bağımsız kaynak yok (%d), reddedildi.", independent_sources)
            return None

    # Aşama 2: iddia çıkarımı
    claims = extract_claims(llm, article_text)
    if not claims:
        return None

    # Aşama 3-4: iki tur doğrulama + kodla alıntı kontrolü
    round1 = verify_claims_round(llm, claims, source_texts, round_number=1)
    round2 = verify_claims_round(llm, claims, source_texts, round_number=2)
    final = validate_evidence(round1, round2, source_texts)

    ok, usable, reason = decide(final)
    if not ok:
        log.info("Karar: RED — %s", reason)
        return None

    main_domains = {source_identity(ev.url) for ev in final[0].evidence}
    verified_domains = {source_identity(ev.url) for v in usable for ev in v.evidence}
    required_sources = sched_min_sources()

    if len(verified_domains) < required_sources:
        if is_official_primary and len(full_text) >= 300 and len(usable) >= 2:
            log.info("Resmi kaynak %d doğrulanmış iddia ile onaylandı.", len(usable))
        elif allow_single_source and len(full_text) >= 500 and len(usable) >= 3:
            log.info("Tek whitelist kaynak %d doğrulanmış iddia ile onaylandı.", len(usable))
        else:
            log.info(
                "Ana iddia/olay iki ayrı kaynakta kanıtlanamadı (main=%d, total=%d); aday reddedildi.",
                len(main_domains), len(verified_domains),
            )
            return None

    # Yalnızca doğrulamaya gerçekten kanıt sağlayan kaynakların adlarını kullan
    used_urls = {ev.url for v in usable for ev in v.evidence}
    used_urls.add(candidate.url)
    source_names = list(dict.fromkeys(
        url_to_name[u] for u in source_texts if u in used_urls and url_to_name.get(u)
    ))
    verified_source_texts = {u: txt for u, txt in source_texts.items() if u in used_urls}
    verified_cross_urls = [u for u in cross_urls if u in used_urls]

    return {
        "verifications": final,
        "usable": usable,
        "source_texts": verified_source_texts,
        "source_names": source_names,
        "cross_urls": verified_cross_urls,
    }


def sched_min_sources() -> int:
    return schedule_config().get("verification", {}).get("min_independent_sources", 2)


def _recovery_pass(*, dry_run: bool) -> None:
    """Zamanı gelen yeniden denemeleri ve durum sorgularını çalıştırır."""
    if dry_run:
        return
    now = now_istanbul()
    channel_map = None
    for entry in history_store.load_history():
        if not needs_recovery([entry.model_dump()], now):
            continue
        post_dir = _find_post_dir(entry)
        if not post_dir or not (post_dir / "captions.json").exists():
            continue
        try:
            raw_caps = json.loads(
                (post_dir / "captions.json").read_text(encoding="utf-8")
            )["captions"]
            captions = {
                k: (
                    _format_caption_text(k, v.get("text", ""), v.get("hashtags", []))
                    if isinstance(v, dict)
                    else str(v)
                )
                for k, v in raw_caps.items()
            }
            image_urls = _public_urls(
                entry.date,
                post_dir,
                sorted((post_dir / "slides").glob("slide-*.png")),
            )
            image_urls_9x16 = _public_urls(
                entry.date,
                post_dir,
                sorted((post_dir / "slides_9x16").glob("slide-*.png")),
                subdir="slides_9x16",
            )
            reel_path = post_dir / "video" / "reel.mp4"
            video_url = _public_video_url(post_dir, reel_path if reel_path.exists() else None)
            if channel_map is None:
                channel_map = _channel_map()
            recovered = recover_failed(
                post_dir,
                captions=captions,
                image_urls=image_urls,
                image_urls_9x16=image_urls_9x16,
                video_url=video_url,
                channel_map=channel_map,
                history_statuses=entry.status_per_platform,
                thread_replies=[] if entry.type == "weetis" else _thread_replies(captions.get("x", ""), image_urls),
                recent=within_recovery_window(entry.created_at, now),
                checkpoint=lambda: _checkpoint_post(post_dir, entry),
            )
            if recovered:
                entry.status_per_platform = list(recovered.values())
                history_store.append_entry(entry)
                for st in recovered.values():
                    if st.state == "published":
                        close_resolved_issues(st.platform)
                _update_daily_summary(entry.date)
                summary_path = OUTPUT_DIR / entry.date / "daily_summary.md"
                commit_and_push(
                    f"🤖 recover: {entry.date} {entry.slot}",
                    [
                        "data/history.json",
                        post_dir.relative_to(_repo_root()),
                        summary_path.relative_to(_repo_root()),
                    ],
                )
            log.info("Kurtarma turu yapıldı: %s %s", entry.date, entry.slot)
        except Exception as exc:
            log.warning("Kurtarma turu başarısız: %s", exc)


def _find_post_dir(entry: HistoryEntry) -> Path | None:
    date_dir = OUTPUT_DIR / entry.date
    if not date_dir.exists():
        return None
    slot_compact = entry.slot.replace(":", "")
    for d in sorted(date_dir.iterdir(), reverse=True):
        if d.is_dir() and slot_compact in d.name:
            return d
    return None


def _make_post_dir(
    date_label: str, slot: str, selected: Candidate | None, ptype: str
) -> Path:
    """output/YYYY-MM-DD/NN-HHMM-slug/ klasörü oluşturur."""
    order = [item["time"] for item in schedule_config()["slots"]]
    idx = order.index(slot) + 1 if slot in order else 1
    slug = slugify(selected.title if selected else ptype)
    name = f"{idx:02d}-{slot.replace(':', '')}-{slug}"
    post_dir = OUTPUT_DIR / date_label / name
    for sub in ("slides", "slides_9x16", "images", "sources", "video"):
        (post_dir / sub).mkdir(parents=True, exist_ok=True)
    return post_dir


def _slide_deck_to_dict(deck, source_names: list[str]) -> dict:
    d = deck.model_dump()
    d["tag_label_2"] = "BAĞLAM"
    d["tag_label_3"] = "ÖNE ÇIKAN RAKAM"
    d["tag_label_4"] = "DETAYLAR"
    d["tag_label_5"] = "NEDEN ÖNEMLİ?"
    d["tag_label_6"] = "ETKİLEŞİM"
    return d


def _edu_deck_to_dict(deck) -> dict:
    d = deck.model_dump()
    d["context"] = {
        "heading": d["problem"]["heading"],
        "cards": d["problem"]["cards"],
    }
    d["stat"] = {
        "big_stat": "💡",
        "stat_caption": d["steps"][0]["heading"] if d["steps"] else "",
        "stat_quote": d["steps"][0]["code_block"] if d["steps"] else "",
    }
    d["details"] = {
        "heading": d["steps"][1]["heading"] if len(d["steps"]) > 1 else "ADIM ADIM",
        "cards": d["steps"][1]["cards"] if len(d["steps"]) > 1 else [],
    }
    d["impact"] = {
        "heading": d["steps"][2]["heading"] if len(d["steps"]) > 2 else "PRATİK İPUÇLARI",
        "cards": d["steps"][2]["cards"] if len(d["steps"]) > 2 else [],
    }
    d["cta"] = {
        "question": d["cta"]["question"],
        "reminder_line": d["cta"].get("reminder_line", ""),
    }
    d["tag_label_2"] = "NEDEN ÖNEMLİ?"
    d["tag_label_3"] = "İPUCU"
    d["tag_label_4"] = "ADIM ADIM"
    d["tag_label_5"] = "PRATİK"
    d["tag_label_6"] = "ETKİLEŞİM"
    return d


def _assign_backgrounds(paths: list[str]) -> list[str]:
    """Doğrulanmış görselleri slaytlara dağıtır."""
    if not paths:
        return [""] * 6
    out = []
    for i in range(6):
        out.append(paths[i % len(paths)])
    return out


def _to_file_url(path: str) -> str:
    if not path:
        return ""
    return "file:///" + str(path).replace("\\", "/")


def _render_with_backgrounds(
    decks: list[dict], post_dir: Path, fonts_dir: Path
) -> dict:
    """Her slaytı kendi arka planıyla render eder (4:5 + 9:16)."""
    import asyncio

    from app.render.renderer import render_png, render_png_9x16, render_slide_html

    brand = {
        "width": 1080, "height": 1350,
        "width_9x16": 1080, "height_9x16": 1920,
    }
    results: dict[str, list[Path]] = {"slides": [], "slides_9x16": []}
    slides_dir = post_dir / "slides"
    slides_916_dir = post_dir / "slides_9x16"

    async def _run() -> None:
        for i, deck in enumerate(decks, start=1):
            html = render_slide_html(deck, i)
            dest = slides_dir / f"slide-{i}.png"
            await render_png(
                html, dest, width=brand["width"], height=brand["height"],
                fonts_dir=fonts_dir,
            )
            results["slides"].append(dest)
            dest916 = slides_916_dir / f"slide-{i}.png"
            await render_png_9x16(
                html, dest916,
                brand["width"], brand["height"],
                brand["width_9x16"], brand["height_9x16"],
                fonts_dir=fonts_dir,
            )
            results["slides_9x16"].append(dest916)

    asyncio.run(_run())
    return results


def _write_captions(
    post_dir: Path, captions, source_names: list[str], selected: Candidate | None,
    *, title_tr: str = "",
) -> None:
    """captions.json + captions.md yazar."""
    doc = {
        "captions": captions.model_dump(),
        "source_names": source_names,
        "title_tr": title_tr or (selected.title if selected else ""),
        "canonical_url": selected.url if selected else "",
    }
    (post_dir / "captions.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = ["# Platform Açıklamaları", ""]
    for key, cap in captions.model_dump().items():
        lines.append(f"## {key.upper()}")
        lines.append("")
        lines.append(cap["text"])
        if cap["hashtags"]:
            lines.append("")
            lines.append(" ".join(f"#{h.lstrip('#')}" for h in cap["hashtags"]))
        lines.append("")
    (post_dir / "captions.md").write_text("\n".join(lines), encoding="utf-8")


def _write_meta(
    post_dir: Path,
    slot: str,
    ptype: str,
    llm: GeminiClient,
    started: float,
    tried: int,
    selected: Candidate | None,
) -> None:
    meta = {
        "pipeline_version": 2,
        "slot": slot,
        "type": ptype,
        "model": llm._model,
        "duration_seconds": round(time.time() - started, 1),
        "candidates_tried": tried,
        "gemini_calls": llm.call_count,
        "model_usage": llm.model_usage,
        "canonical_url": selected.url if selected else "",
        "entities": selected.entities if selected else [],
        "event_type": selected.event_type if selected else "",
        "topic": selected.topic if selected else "",
        "primary_entity": selected.primary_entity if selected else "",
        "event_key": selected.event_key if selected else "",
        "editorial": selected.raw.get("editorial", {}) if selected else {},
        "generated_at": now_istanbul().isoformat(timespec="seconds"),
    }
    (post_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _channel_map() -> dict[str, tuple[str, str]]:
    """config/platforms.yaml + GitHub Secrets / Buffer API otomatik keşiften platform → (account, channel_id)."""
    import os

    from app.publish.buffer_client import list_profiles

    cfg = platforms_config()
    secret_names = {
        "instagram": ("BUFFER_PROFILE_INSTAGRAM", "BUFFER_PROFILE_ID_INSTAGRAM"),
        "tiktok": ("BUFFER_PROFILE_TIKTOK", "BUFFER_PROFILE_ID_TIKTOK"),
        "x": ("BUFFER_PROFILE_X", "BUFFER_PROFILE_ID_X"),
        "facebook": ("BUFFER_PROFILE_FACEBOOK", "BUFFER_PROFILE_ID_FACEBOOK"),
        "linkedin": ("BUFFER_PROFILE_LINKEDIN", "BUFFER_PROFILE_ID_LINKEDIN"),
    }
    out: dict[str, tuple[str, str]] = {}
    for account, platforms in cfg.accounts.items():
        for platform in platforms:
            env_keys = secret_names.get(platform, ())
            channel_id = ""
            for k in env_keys:
                val = os.environ.get(k, "").strip()
                if val:
                    channel_id = val
                    break
            out[platform] = (account, channel_id)

    # Buffer API'den canlı kanal/hesap (A/B) eşleşmelerini doğrula ve eksikleri tamamla
    try:
        profiles = list_profiles()
        service_to_platform = {
            "instagram": "instagram",
            "tiktok": "tiktok",
            "twitter": "x",
            "x": "x",
            "facebook": "facebook",
            "linkedin": "linkedin",
        }
        for prof in profiles:
            svc = (prof.get("service") or "").lower()
            plat = service_to_platform.get(svc, "")
            cid = prof.get("channel_id", "")
            acc = prof.get("account", "A")
            if plat and cid and prof.get("disconnected") == "False":
                out[plat] = (acc, cid)
                log.info(
                    "Buffer kanalı doğrulandı: %s → hesap %s (%s)",
                    plat, acc, cid,
                )
    except Exception as exc:
        log.warning("Buffer kanal otomatik keşfi başarısız: %s", exc)

    return out


def _checkpoint_post(post_dir: Path, entry: HistoryEntry) -> None:
    status_file = post_dir / "status.json"
    journal = json.loads(status_file.read_text(encoding="utf-8"))["platforms"]
    entry.status_per_platform = [PlatformStatus.model_validate(st) for st in journal.values()]
    history_store.append_entry(entry)
    if not commit_and_push("🤖 publish: platform durum günlüğü",
                           [status_file.relative_to(_repo_root()), "data/history.json"]):
        raise RuntimeError("Platform durum günlüğü kaydedilemedi; yayın durduruldu.")


def _public_urls(
    date_label: str, post_dir: Path, slide_paths: list[Path], *, subdir: str = "slides"
) -> list[str]:
    """raw.githubusercontent.com üzerinden herkese açık görsel URL'leri."""
    cfg = settings()
    repo = cfg.github_repository or "OWNER/REPO"
    rel = post_dir.relative_to(_repo_root()).as_posix()
    return [
        f"https://raw.githubusercontent.com/{repo}/main/{rel}/{subdir}/{p.name}"
        for p in slide_paths
    ]


def _public_video_url(post_dir: Path, reel_path: Path | None) -> str:
    """raw.githubusercontent.com üzerinden herkese açık MP4 video URL'si."""
    if not reel_path or not reel_path.exists():
        return ""
    cfg = settings()
    repo = cfg.github_repository or "OWNER/REPO"
    rel = post_dir.relative_to(_repo_root()).as_posix()
    return f"https://raw.githubusercontent.com/{repo}/main/{rel}/video/{reel_path.name}"


def _video_has_audio_track(video_path: Path) -> bool:
    """ffprobe ile video dosyasında ses izi olup olmadığını kontrol eder."""
    import shutil as _shutil
    import subprocess as _subprocess

    if not _shutil.which("ffprobe"):
        return False
    try:
        proc = _subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0",
             str(video_path.resolve())],
            capture_output=True, text=True, timeout=10,
        )
        return "audio" in (proc.stdout or "").lower()
    except Exception:
        return False


def _write_music_credit(post_dir: Path, music_info: dict[str, Any]) -> None:
    """Kullanılan müziğin telif/atıf bilgisini credits.json'a ekler."""
    import json as _json

    credits_path = post_dir / "credits.json"
    credits: dict[str, Any] = {}
    if credits_path.exists():
        try:
            credits = _json.loads(credits_path.read_text(encoding="utf-8"))
        except Exception:
            credits = {}
    credits.setdefault("music", [])
    if isinstance(credits.get("music"), list):
        credits["music"].append({
            "title": music_info.get("title", ""),
            "artist": music_info.get("artist", ""),
            "license": music_info.get("license", ""),
            "license_url": music_info.get("license_url", ""),
            "source_url": music_info.get("url", ""),
        })
    credits_path.write_text(
        _json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _write_video_credit(post_dir: Path, video_meta: dict[str, Any]) -> None:
    """Kullanılan videonun telif/atıf bilgisini credits.json'a ekler (Wikimedia CC BY için zorunlu)."""
    import json as _json

    if not video_meta.get("license") and not video_meta.get("author"):
        return  # stok kaynaklar (Pexels/Pixabay) atıf gerektirmez
    credits_path = post_dir / "credits.json"
    credits: dict[str, Any] = {}
    if credits_path.exists():
        try:
            credits = _json.loads(credits_path.read_text(encoding="utf-8"))
        except Exception:
            credits = {}
    credits.setdefault("video", [])
    if isinstance(credits.get("video"), list):
        credits["video"].append({
            "source": video_meta.get("source", ""),
            "url": video_meta.get("video_url", ""),
            "license": video_meta.get("license", ""),
            "author": video_meta.get("author", ""),
            "credit_url": video_meta.get("credit_url") or video_meta.get("page_url", ""),
        })
    credits_path.write_text(
        _json.dumps(credits, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _thread_replies(x_caption: str, image_urls: list[str]) -> list[dict]:
    """X'te 5-6. görseller yanıt tweetine gider (thread)."""
    if len(image_urls) <= 4:
        return []
    return [
        {"text": "Devamı 👇", "images": image_urls[4:6]},
    ]


def _repo_root() -> Path:
    from app.config import REPO_ROOT

    return REPO_ROOT


def _skip_slot(date_label: str, slot: str, reason: str, *, dry_run: bool = False) -> None:
    """Slot atlanır; sebep loglanır ve günlük özet yazılır. Workflow BAŞARISIZ DEĞİL."""
    log.warning("SLOT ATLANDI: %s %s — %s", date_label, slot, reason)
    summary = OUTPUT_DIR / date_label / "daily_summary.md"
    summary.parent.mkdir(parents=True, exist_ok=True)
    line = f"- ⏭️ `{slot}` slotu atlandı — {reason}\n"
    if summary.exists():
        content = summary.read_text(encoding="utf-8")
        if line not in content:
            summary.write_text(content + line, encoding="utf-8")
    else:
        summary.write_text(f"# Günlük Özet — {date_label}\n\n{line}", encoding="utf-8")
    if not dry_run:
        history_store.mark_slot_skipped(date_label, slot, reason)
        if not commit_and_push(f"🤖 skip: {date_label} {slot}",
                               [summary.relative_to(_repo_root()), "data/skipped_slots.json"]):
            raise RuntimeError("Atlanan slot kaydedilemedi.")


def _update_daily_summary(date_label: str) -> None:
    """Gün özeti dosyasını günceller."""
    entries = history_store.entries_for_day(date_label)
    summary = OUTPUT_DIR / date_label / "daily_summary.md"
    summary.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# Günlük Özet — {date_label}", ""]
    for e in sorted(entries, key=lambda x: x.slot):
        published = sum(1 for s in e.status_per_platform if s.state == "published")
        total = len(e.status_per_platform) or 1
        icon = "✅" if published == total else ("⚠️" if published else "❌")
        lines.append(
            f"- {icon} `{e.slot}` [{e.type}] {e.title_tr} "
            f"— {published}/{total} platform"
        )
    summary.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Tekno Pusula post üretici")
    parser.add_argument("--slot", default="auto", help="HH:MM veya 'auto'")
    parser.add_argument(
        "--type", dest="force_type", default="auto",
        choices=["auto", "news", "edu"], help="İçerik tipi",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Paylaşma, sadece üret ve commit et",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return run(slot=args.slot, force_type=args.force_type, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
