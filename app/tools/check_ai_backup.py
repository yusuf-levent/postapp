"""Check the configured backup key with two small, read-only model calls."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from pydantic import BaseModel

from app.config import settings
from app.llm.gemini import GeminiClient


class HealthResult(BaseModel):
    ok: bool


def main() -> int:
    key = settings().gemini_backup_api_key
    if not key:
        print("GEMINI_BACKUP_API_KEY tanımlı değil.")
        return 2
    # Passing the backup explicitly deduplicates the configured key list, so
    # this cannot accidentally report success using the primary credential.
    llm = GeminiClient(api_key=key)
    result = llm.generate_structured('Return JSON with ok=true.', HealthResult, label="backup-structured-check")
    with TemporaryDirectory() as temp:
        path = Path(temp) / "color.png"
        Image.new("RGB", (128, 128), (255, 0, 0)).save(path)
        color = llm.analyze_images("Name the dominant color. Reply with one uppercase English color name.",
                                   [str(path)], label="backup-vision-check")
    ok = result.ok and color.strip().upper().rstrip(".! ") == "RED"
    print(json.dumps({"backup_key_ok": ok, "models": llm.model_usage}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
