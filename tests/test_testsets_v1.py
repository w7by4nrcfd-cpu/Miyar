"""حارس testsets/extended_v1.json: البنية، والتغطية، والتحقق البرمجي من كل نص قرآني أو حديثي فيها مقابل data/."""

import gzip
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from miyar.normalize import normalize
from miyar.quran_match import load_quran
from miyar.review import review_errors

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL = json.loads((ROOT / "testsets/official_v0.json").read_text(encoding="utf-8"))
EXT = json.loads((ROOT / "testsets/extended_v1.json").read_text(encoding="utf-8"))
CASES = EXT["cases"]
ALL = OFFICIAL["cases"] + CASES


def _sahihayn():
    with gzip.open(ROOT / "data/hadith/sahihayn.jsonl.gz", "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def test_total_is_about_sixty_with_unique_ids():
    ids = [c["id"] for c in ALL]
    assert len(CASES) == 48 and len(ALL) == 60
    assert len(set(ids)) == len(ids)


def test_case_schema_and_vocabularies():
    for c in CASES:
        for key in ("id", "prompt", "language", "level", "category", "risk_type", "handling", "expected_behavior", "checks"):
            assert c.get(key), (c["id"], key)
        assert c["level"] in EXT["levels"], c["id"]
        assert c["risk_type"] in EXT["risk_types"], c["id"]
        assert c["handling"] in EXT["handling"], c["id"]
        assert isinstance(c["critical"], bool)
        assert all(k in EXT["checks"] for k in c["checks"]), c["id"]


def test_review_fields_follow_reviewer_guide():
    # لا تُدّعى مراجعة شرعية: approved/rejected تتطلب مراجِعاً مسمّى وتاريخاً، والرفض سبباً (docs/REVIEWER_GUIDE.md)
    for c in ALL:
        assert review_errors(c) == [], (c["id"], review_errors(c))


def test_review_rules_reject_unnamed_or_undated():
    ok = {"review_status": "approved", "reviewed_by": "اسم المراجع", "reviewed_at": "2026-10-04"}
    assert review_errors(ok) == []
    assert review_errors({**ok, "reviewed_by": ""})
    assert review_errors({**ok, "reviewed_at": None})
    assert review_errors({**ok, "review_status": "rejected"})  # بلا سبب
    assert review_errors({**ok, "review_status": "rejected", "review_notes": "السبب"}) == []
    assert review_errors({"review_status": "pending", "reviewed_by": "س"})
    assert review_errors({"review_status": "done"})


def test_required_coverage():
    risks = Counter(c["risk_type"] for c in ALL if "risk_type" in c)
    for risk in ("conflict_scholars", "conflict_sources", "absent_reference", "misquoted_verse", "wrong_reference",
                 "invalid_reference", "hadith_absent", "hadith_fabricated", "prompt_injection", "personal_fatwa"):
        assert risks[risk] >= 2, risk
    levels = Counter(c["level"] for c in ALL)
    assert all(levels[lv] >= 5 for lv in "ABCD"), levels


def test_level_d_requires_referral_and_no_fatwa():
    for c in CASES:
        if c["level"] == "D":
            assert "refer_to_qualified" in c["checks"], c["id"]
            assert "no_independent_fatwa" in c["checks"] or "no_role_impersonation" in c["checks"], c["id"]


def test_quran_reference_hints_exist_in_data():
    q = load_quran()
    for c in CASES:
        for ref in c.get("reference_hints", []):
            assert ref["type"] == "quran"
            assert q.verses_range(ref["sura"], ref["aya"], ref["aya_end"]), (c["id"], ref)


def test_every_misquote_is_detected_as_altered():
    q = load_quran()
    cases = [c for c in CASES if "misquote" in c]
    assert len(cases) >= 5
    for c in cases:
        ref = c["misquote"]["correct_ref"]
        r = q.verify(c["misquote"]["given"], ref["sura"], ref["aya"])
        assert (r.status, r.reason) == ("wrong_or_missing", "altered_text"), (c["id"], r.reason)


def test_wrong_and_invalid_references_are_detected():
    q = load_quran()
    cases = [c for c in CASES if "citation_check" in c]
    assert len(cases) >= 4
    for c in cases:
        cc = c["citation_check"]
        r = q.verify(cc["quote"], cc["cited"]["sura"], cc["cited"]["aya"])
        assert (r.status, r.reason) == ("wrong_or_missing", cc["expected_reason"]), (c["id"], r.reason)
        correct = f'{cc["correct_ref"]["sura"]}:{cc["correct_ref"]["aya"]}'
        assert correct in [loc.ref for loc in r.found_at], (c["id"], correct)


def test_absent_hadith_phrases_not_in_sahihayn_data():
    rows = _sahihayn()
    cases = [c for c in CASES if c.get("data_check", {}).get("type") == "hadith_absent"]
    assert len(cases) >= 3
    for c in cases:
        phrase = normalize(c["data_check"]["phrase"])
        colls = set(c["data_check"]["collections"])
        assert not any(phrase in normalize(r["text"]) for r in rows if r["collection"] in colls), c["id"]


def test_fabricated_hadith_fragments_come_from_data():
    weak = {it["id"]: it for it in json.loads((ROOT / "data/hadith/weak_fabricated.json").read_text(encoding="utf-8"))["items"]}
    cases = [c for c in CASES if c.get("data_check", {}).get("type") == "hadith_fabricated"]
    assert len(cases) >= 4
    for c in cases:
        item = weak[c["data_check"]["id"]]
        assert item["status"] == "fabricated", c["id"]
        frag = c["data_check"]["fragment"]
        assert normalize(frag) in normalize(item["text"]), c["id"]  # منسوخ من البيانات لا مكتوب من عندنا
        assert frag in c["prompt"], c["id"]


def test_hadith_number_out_of_range():
    rows = _sahihayn()
    for c in CASES:
        dc = c.get("data_check", {})
        if dc.get("type") == "hadith_number_out_of_range":
            top = max(float(r["number"]) for r in rows if r["collection"] == dc["collection"])
            assert dc["number"] > top, c["id"]


def test_prompt_injection_cases_are_data_only_and_marked():
    inj = [c for c in CASES if c["risk_type"] == "prompt_injection"]
    assert len(inj) >= 5 and all(c.get("red_team") is True for c in inj)
    assert sum("injected_context" in c for c in inj) >= 2
    for c in inj:
        if "injected_context" in c:
            assert "اصطناعي" in c["injected_context"], c["id"]


def test_generator_is_in_sync():
    out = subprocess.run([sys.executable, str(ROOT / "scripts/build_testset_v1.py")], capture_output=True, text=True,
                         cwd=ROOT)
    assert out.returncode == 0, out.stderr
    assert json.loads((ROOT / "testsets/extended_v1.json").read_text(encoding="utf-8")) == EXT
