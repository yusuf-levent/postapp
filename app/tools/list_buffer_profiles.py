"""Buffer profil (kanal) listesi çıkarıcı.

Çalıştırma:
  python -m app.tools.list_buffer_profiles
  veya GitHub Actions → tools workflow → "list_buffer_profiles"

Çıktıda ASLA token görünmez; yalnızca kanal ID, servis adı ve URL.
"""
from __future__ import annotations

import json
import logging

from app.publish.buffer_client import list_profiles


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s"
    )
    log = logging.getLogger("buffer-profiles")

    try:
        profiles = list_profiles()
    except Exception as exc:
        log.error("Profil listesi alınamadı: %s", exc)
        return 1

    if not profiles:
        log.warning(
            "Hiç kanal bulunamadı. BUFFER_ACCESS_TOKEN_A/B secret'larını kontrol edin."
        )
        return 0

    print("\n# Buffer Kanal (Profil) Listesi")
    print("\nGitHub Secrets'a şu değerleri ekleyin:\n")
    secret_map = {
        "instagram": "BUFFER_PROFILE_INSTAGRAM",
        "tiktok": "BUFFER_PROFILE_TIKTOK",
        "twitter": "BUFFER_PROFILE_X",
        "facebook": "BUFFER_PROFILE_FACEBOOK",
        "linkedin": "BUFFER_PROFILE_LINKEDIN",
        "threads": "THREADS_USER_ID (kullanıcı ID)",
    }
    for p in profiles:
        service = p["service"]
        secret = secret_map.get(service, f"(bilinmeyen servis: {service})")
        print(f"- {p['name']} ({service}, hesap {p['account']})")
        print(f"  channel_id: {p['channel_id']}")
        print(f"  URL: {p['url']}")
        print(f"  secret adı: {secret}")
        if p["disconnected"] == "True":
            print("  ⚠️ Bu kanal Buffer'a bağlı DEĞİL!")
        print()

    print("\nHam JSON (otomasyon için):")
    print(json.dumps(profiles, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())