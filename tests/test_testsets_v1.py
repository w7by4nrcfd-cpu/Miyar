"""حارس testsets/extended_v1.json: البنية، والتغطية، والتحقق البرمجي من النصوص القرآنية مقابل data/quran،
وربط حالات الحديث بالملف اليدوي المعتمد data/hadith/manual_hadith.json."""

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


def test_review_rules_reject_unnamed_undated_or_without_role():
    ok = {"review_status": "approved", "reviewed_by": "اسم المراجع", "reviewer_role": "specialist",
          "reviewed_at": "2026-10-04"}
    assert review_errors(ok) == []
    assert review_errors({**ok, "reviewer_role": "source_check"}) == []
    assert review_errors({**ok, "reviewer_role": None})  # approved بلا نوع مراجعة مرفوض
    assert review_errors({**ok, "reviewer_role": "scholar"})
    assert review_errors({**ok, "reviewed_by": ""})
    assert review_errors({**ok, "reviewed_at": None})
    assert review_errors({**ok, "review_status": "rejected"})  # بلا سبب
    assert review_errors({**ok, "review_status": "rejected", "review_notes": "السبب"}) == []
    assert review_errors({"review_status": "pending", "reviewed_by": "س"})
    assert review_errors({"review_status": "pending", "reviewer_role": "specialist"})
    assert review_errors({"review_status": "done"})


def test_review_summary_counts_by_role():
    from miyar.review import review_summary
    base = {"reviewed_by": "س", "reviewed_at": "2026-10-04"}
    cases = [
        {"review_status": "pending"},
        {**base, "review_status": "approved", "reviewer_role": "specialist"},
        {**base, "review_status": "approved", "reviewer_role": "source_check"},
        {**base, "review_status": "rejected", "reviewer_role": "source_check", "review_notes": "x"},
    ]
    s = review_summary(cases)
    assert s["total"] == 4 and s["pending"] == 1
    assert s["approved"] == {"specialist": 1, "source_check": 1}
    assert s["rejected"] == {"specialist": 0, "source_check": 1}


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


HADITH_TYPES = {"hadith_absent": "not_found", "hadith_fabricated": "found", "hadith_number_out_of_range": "collection_range"}


def test_hadith_cases_point_to_manual_file_entries():
    # كل حالة تعتمد على الحديث مربوطة بمدخل في الملف اليدوي المعتمد (لا بمجموعة خارجية)
    from miyar.hadith_manual import entries_by_id
    entries = entries_by_id()
    cases = [c for c in ALL if c.get("data_check", {}).get("type") in HADITH_TYPES]
    assert len(cases) == 9
    for c in cases:
        dc = c["data_check"]
        e = entries.get(dc.get("manual_ref"))
        assert e is not None, c["id"]
        assert e["kind"] == HADITH_TYPES[dc["type"]] and c["id"] in e["case_ids"], c["id"]
        assert "id" not in dc, c["id"]  # لا إحالة إلى معرّف في المجموعة الخارجية


def test_fabricated_fragments_are_in_prompts():
    for c in CASES:
        dc = c.get("data_check", {})
        if dc.get("type") == "hadith_fabricated":
            assert dc["fragment"] in c["prompt"], c["id"]


def test_completed_manual_entries_match_their_cases():
    # عند إدخال المدخل يدوياً: يجب أن يطابق حالته (العبارة غير الموجودة، والرقم خارج النطاق)
    from miyar.hadith_manual import entries_by_id, entry_status
    entries = entries_by_id()
    for c in ALL:
        dc = c.get("data_check", {})
        e = entries.get(dc.get("manual_ref")) if dc.get("manual_ref") else None
        if not e or entry_status(e) != "complete":
            continue
        if dc["type"] == "hadith_absent":
            assert normalize(dc["phrase"]) in normalize(e["query"]), c["id"]
        if dc["type"] == "hadith_number_out_of_range":
            assert dc["number"] > e["max_number"], c["id"]


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
