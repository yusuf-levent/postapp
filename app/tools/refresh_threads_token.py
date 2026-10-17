"""Threads long-lived token yenileme aracı.

Çalıştırma:
  python -m app.tools.refresh_threads_token [--force]

Long-lived token 60 gün geçerlidir. 40 günü geçtiyse (veya --force ile)
yenilenir ve yeni token GitHub REST API ile repo secret'ına yazılır.
data/token_state.json'a yalnızca tarih yazılır, token ASLA kaydedilmez.
"""
from __future__ import annotations

import argparse
import logging

from app.publish.threads_client import maybe_refresh_token


def main() -> int:
    parser = argparse.ArgumentParser(description="Threads token yenileme")
    parser.add_argument("--force", action="store_true", help="Tarih kontrolü olmadan yenile")
    parser.add_argument("--dry-run", action="store_true", help="Yenileme yapma, sadece göster")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s"
    )

    try:
        result = maybe_refresh_token(dry_run=args.dry_run, force=args.force)
    except Exception as exc:
        logging.error("Token yenileme başarısız: %s", exc)
        return 1

    print(f"Sonuç: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())