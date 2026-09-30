import gzip
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ("id", "collection", "collection_ar", "number", "text", "grade", "grade_basis", "source")


def test_hadith_data_integrity():
    counts: Counter[str] = Counter()
    ids = set()
    with gzip.open(ROOT / "data/hadith/sahihayn.jsonl.gz", "rt", encoding="utf-8") as f:
        for line in f:
            h = json.loads(line)
            assert all(h.get(k) for k in REQUIRED), h.get("id")
            assert h["grade"] == "صحيح" and h["grade_basis"] == "collection"
            assert h["id"] not in ids
            ids.add(h["id"])
            counts[h["collection"]] += 1
    assert counts == {"bukhari": 7580, "muslim": 7360}


def test_weak_fabricated_set():
    from miyar.normalize import normalize

    doc = json.loads((ROOT / "data/hadith/weak_fabricated.json").read_text(encoding="utf-8"))
    items = doc["items"]
    assert 1 <= len(items) <= 20  # مجموعة صغيرة
    assert len({i["id"] for i in items}) == len(items)
    sahihayn = [
        normalize(json.loads(line)["text"])
        for line in gzip.open(ROOT / "data/hadith/sahihayn.jsonl.gz", "rt", encoding="utf-8")
    ]
    for item in items:
        assert item["status"] in doc["status_meaning"]
        assert item["review_status"] in ("pending", "approved")
        assert (item["review_status"] == "approved") == bool(item["reviewed_by"])
        assert item["rulings"], item["id"]
        key = normalize(item["text"]).replace(" ", "")
        for r in item["rulings"]:
            for k in ("scholar", "ruling", "book", "page_or_number", "dorar_text"):
                assert r[k], (item["id"], k)
            assert r["verify_url"].startswith("https://dorar.net/h/")
            # النص المخزّن مطابق حرفياً لنص المصدر (بعد التوحيد وحذف المسافات والأقواس)
            assert normalize(r["dorar_text"].replace("[", "").replace("]", "")).replace(" ", "") == key
        # لا يوجد في الصحيحين
        needle = normalize(item["text"])
        assert not any(needle in t for t in sahihayn), item["id"]
