"""سلامة المجموعة الخارجية غير المعتمدة (data/unapproved/hadith/): محفوظة للتاريخ والتطوير فقط، لا للموقع ولا للتشغيل الرسمي."""

import gzip
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ("id", "collection", "collection_ar", "number", "text", "grade", "grade_basis", "source")


def test_hadith_data_integrity():
    counts: Counter[str] = Counter()
    ids = set()
    with gzip.open(ROOT / "data/unapproved/hadith/sahihayn.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            h = json.loads(line)
            assert all(h.get(k) for k in REQUIRED), h.get("id")
            assert h["grade"] == "صحيح" and h["grade_basis"] == "collection"
            assert h["id"] not in ids
            ids.add(h["id"])
            counts[h["collection"]] += 1
    assert counts == {"bukhari": 7580, "muslim": 7360}



def test_weak_fabricated_set():
    doc = json.loads((ROOT / "data/unapproved/hadith/weak_fabricated.json").read_text(encoding="utf-8"))
    items = doc["items"]
    assert doc["license_declared"] == "Unlicense" and doc["license_note"]
    assert doc["grade_display_policy"]
    assert 1 <= len(items) <= 30  # مجموعة صغيرة
    assert len({i["id"] for i in items}) == len(items)
    for item in items:
        assert item["text"] and item["number"] and item["source"]
        assert item["status"] in doc["status_meaning"]
        assert item["review_status"] in ("pending", "approved")
        assert (item["review_status"] == "approved") == bool(item["reviewed_by"])
        for g in item["grades"]:
            tr = g["translation_ar"]
            assert tr["scholar"] and tr["grade"]
            # الترجمة العربية غير مراجَعة ما لم يُسمَّ مراجِع
            assert tr["review_status"] in ("pending", "approved")
            assert (tr["review_status"] == "approved") == bool(tr["reviewed_by"])
        by = {g["scholar"]: g["grade"] for g in item["grades"]}
        # قاعدة الاختيار: عالمان على الأقل حكما بالوضع، ولا حكم بالصحة أو الحسن
        assert by.get("Al-Albani") == "Mawdu" and by.get("Shuaib Al Arnaut") == "Mawdu"
        assert not any("Sahih" in g or "Hasan" in g for g in by.values())
