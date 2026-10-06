"""توليد ملف الأحاديث المحلي data/unapproved/hadith/sahihayn.jsonl.gz (مجموعة غير معتمدة؛ حُذف المجلد من آخر نسخة في 2026-10-06 ويبقى في تاريخ git؛ السكربت محفوظ للتوثيق).

المصدر: fawazahmed0/hadith-api (ترخيص معلن: Unlicense؛ سلسلة المصادر غير واضحة — انظر SOURCES.md) بإصدار مثبّت برقم commit.
الاستخدام:
    python scripts/build_hadith_data.py               # تنزيل من GitHub
    python scripts/build_hadith_data.py --src DIR     # من ملفات محلية منزّلة مسبقاً
"""

from __future__ import annotations

import argparse
import gzip
import json
import urllib.request
from pathlib import Path

COMMIT = "df57907be35291c91ad6a6691180e22ca9920784"
BASE_URL = f"https://raw.githubusercontent.com/fawazahmed0/hadith-api/{COMMIT}/editions"

COLLECTIONS = {
    "bukhari": {"file": "ara-bukhari.json", "name_ar": "صحيح البخاري"},
    "muslim": {"file": "ara-muslim.json", "name_ar": "صحيح مسلم"},
}

OUT = Path(__file__).resolve().parent.parent / "data" / "unapproved" / "hadith" / "sahihayn.jsonl.gz"


def load(src: Path | None, filename: str) -> dict:
    if src is not None:
        return json.loads((src / filename).read_text(encoding="utf-8"))
    with urllib.request.urlopen(f"{BASE_URL}/{filename}", timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def build(src: Path | None) -> dict:
    stats = {}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 يجعل الملف الناتج حتمياً (نفس البايتات في كل تشغيل)
    with open(OUT, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        for key, meta in COLLECTIONS.items():
            data = load(src, meta["file"])
            kept = skipped = 0
            for h in data["hadiths"]:
                text = (h.get("text") or "").strip()
                if not text:
                    skipped += 1
                    continue
                number = h.get("arabicnumber") or h["hadithnumber"]
                rec = {
                    "id": f"{key}:{h['hadithnumber']}",
                    "collection": key,
                    "collection_ar": meta["name_ar"],
                    "number": str(number),
                    "api_number": h["hadithnumber"],
                    "book": h.get("reference", {}).get("book"),
                    "in_book": h.get("reference", {}).get("hadith"),
                    "text": text,
                    "grade": "صحيح",
                    "grade_basis": "collection",
                    "source": f"fawazahmed0/hadith-api@{COMMIT[:12]}/{meta['file']}",
                }
                gz.write((json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8"))
                kept += 1
            stats[key] = {"kept": kept, "skipped_empty": skipped}
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=None)
    args = ap.parse_args()
    print(json.dumps(build(args.src), ensure_ascii=False))
