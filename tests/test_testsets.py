import json
from pathlib import Path

import pytest

from miyar.normalize import normalize
from miyar.quran_match import load_quran
from miyar.review import review_errors

ROOT = Path(__file__).resolve().parent.parent
TS = json.loads((ROOT / "testsets/official_v0.json").read_text(encoding="utf-8"))


def test_twelve_official_cases_unique_ids():
    ids = [c["id"] for c in TS["cases"]]
    assert len(ids) == 12 and len(set(ids)) == 12


@pytest.mark.parametrize("case", TS["cases"], ids=lambda c: c["id"])
def test_case_schema(case):
    for key in ("id", "official_prompt", "prompt", "language", "level", "category", "expected_behavior", "checks"):
        assert case.get(key), key
    assert case["level"] in TS["levels"]
    assert isinstance(case["critical"], bool)
    assert case["checks"] and all(c in TS["checks"] for c in case["checks"])
    # لا تُدّعى مراجعة شرعية دون مراجِع مسمّى وتاريخ (والرفض بسبب مكتوب)
    assert review_errors(case) == [], review_errors(case)


def test_level_d_requires_referral_and_no_fatwa():
    for c in TS["cases"]:
        if c["level"] == "D":
            assert {"no_independent_fatwa", "refer_to_qualified"} <= set(c["checks"])


def test_quran_reference_hints_exist_in_data():
    q = load_quran()
    for c in TS["cases"]:
        for ref in c.get("reference_hints", []):
            assert ref["type"] == "quran"
            assert q.verses_range(ref["sura"], ref["aya"], ref["aya_end"]), (c["id"], ref)


def test_misquote_case_is_detected_by_quran_match():
    q = load_quran()
    case = next(c for c in TS["cases"] if "misquote" in c)
    ref = case["misquote"]["correct_ref"]
    r = q.verify(case["misquote"]["given"], ref["sura"], ref["aya"])
    assert r.status == "wrong_or_missing" and r.reason == "altered_text"


def test_hadith_absent_case_points_to_manual_file():
    # التحقق من الحديث يعتمد على الملف اليدوي المعتمد، لا على مجموعة خارجية
    from miyar.hadith_manual import entries_by_id
    case = next(c for c in TS["cases"] if c.get("data_check", {}).get("type") == "hadith_absent")
    entry = entries_by_id()[case["data_check"]["manual_ref"]]
    assert entry["kind"] == "not_found" and case["id"] in entry["case_ids"]
