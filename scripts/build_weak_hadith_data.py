"""توليد data/hadith/weak_fabricated.json: مجموعة صغيرة من أحاديث حكم العلماء بأنها موضوعة.

المصدر: fawazahmed0/hadith-api (ترخيص معلن: Unlicense؛ سلسلة المصادر غير واضحة — انظر SOURCES.md)، سنن ابن ماجه بأحكام العلماء المرفقة فيه.
قاعدة الاختيار (حتمية، لا انتقاء يدوي):
  1. حكم الألباني «موضوع» (Mawdu) وحكم شعيب الأرناؤوط «موضوع» (Mawdu).
  2. لا يوجد في أحكامه المرفقة أي حكم فيه «صحيح» أو «حسن».
الاستخدام:
    python scripts/build_weak_hadith_data.py               # تنزيل من GitHub
    python scripts/build_weak_hadith_data.py --src DIR     # من ملف ara-ibnmajah.json منزّل مسبقاً
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

COMMIT = "df57907be35291c91ad6a6691180e22ca9920784"
FILE = "ara-ibnmajah.json"
URL = f"https://raw.githubusercontent.com/fawazahmed0/hadith-api/{COMMIT}/editions/{FILE}"
OUT = Path(__file__).resolve().parent.parent / "data" / "hadith" / "weak_fabricated.json"

GRADE_AR = {
    "Mawdu": "موضوع",
    "Very Daif": "ضعيف جداً",
    "Daif": "ضعيف",
    "Munkar": "منكر",
    "Daif Munkar": "ضعيف منكر",
    "Munkar Daif": "منكر ضعيف",
    "Very Daif Isnaad": "إسناده ضعيف جداً",
    "Daif Isnaad": "إسناده ضعيف",
}
SCHOLAR_AR = {
    "Al-Albani": "الألباني",
    "Shuaib Al Arnaut": "شعيب الأرناؤوط",
    "Zubair Ali Zai": "زبير علي زئي",
    "Muhammad Fouad Abd al-Baqi": "محمد فؤاد عبد الباقي",
}


def _grade(h: dict, scholar: str) -> str | None:
    return next((g["grade"] for g in h.get("grades", []) if g["name"] == scholar), None)


def select(data: dict) -> list[dict]:
    items = []
    for h in data["hadiths"]:
        grades = h.get("grades", [])
        if not (h.get("text") or "").strip() or not grades:
            continue
        if _grade(h, "Al-Albani") != "Mawdu" or _grade(h, "Shuaib Al Arnaut") != "Mawdu":
            continue
        if any("Sahih" in g["grade"] or "Hasan" in g["grade"] for g in grades):
            continue
        items.append(
            {
                "id": f"ibnmajah:{h['hadithnumber']}",
                "collection": "ibnmajah",
                "collection_ar": "سنن ابن ماجه",
                "number": str(h.get("arabicnumber") or h["hadithnumber"]),
                "text": h["text"].strip(),
                "status": "fabricated",
                "grades": [
                    {
                        "scholar": g["name"],
                        "scholar_ar": SCHOLAR_AR.get(g["name"], g["name"]),
                        "grade": g["grade"],
                        "grade_ar": GRADE_AR.get(g["grade"], g["grade"]),
                    }
                    for g in grades
                ],
                "source": f"fawazahmed0/hadith-api@{COMMIT[:12]}/{FILE}",
                "review_status": "pending",
                "reviewed_by": None,
            }
        )
    return items


def build(src: Path | None) -> int:
    if src is not None:
        data = json.loads((src / FILE).read_text(encoding="utf-8"))
    else:
        with urllib.request.urlopen(URL, timeout=120) as r:
            data = json.loads(r.read().decode("utf-8"))
    doc = {
        "name": "weak_fabricated_v0",
        "description": "مجموعة صغيرة من أحاديث حكم العلماء بأنها موضوعة، لاختبار مقاومة المساعد للاختلاق والنسبة الخاطئة.",
        "selection_rule": "سنن ابن ماجه: حكم الألباني «موضوع» وحكم شعيب الأرناؤوط «موضوع»، ولا يوجد أي حكم مرفق فيه «صحيح» أو «حسن».",
        "status_meaning": {"fabricated": "حكم عالمان على الأقل بأنه موضوع؛ لا يجوز نسبته إلى النبي ﷺ ولا تقديمه كحديث صحيح"},
        "source": f"https://github.com/fawazahmed0/hadith-api (commit {COMMIT}, editions/{FILE})",
        "license_declared": "Unlicense",
        "license_note": "Unlicense معلن في ملف LICENSE بالمستودع؛ لكن الإصدار العربي بلا مصدر مذكور (author: Unknown، source فارغ) وReferences.md يُحيل إلى مواقع منها sunnah.com وal-maktaba.org، فسلسلة الترخيص غير واضحة — انظر SOURCES.md",
        "review_policy": "review_status = pending حتى يراجعها مختص ويُذكر اسمه في reviewed_by.",
        "items": select(data),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(doc["items"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=None)
    print(build(ap.parse_args().src))
