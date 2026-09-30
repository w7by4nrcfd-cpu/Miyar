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
