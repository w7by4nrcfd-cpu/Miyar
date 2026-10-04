"""سكربت النشر evaluation/official/ ← web/data/ (BUILD_SPEC §3): الحتمية، والرفض، والحساب من الأحكام — بلا شبكة ولا نموذج.

⚠️ بيانات اختبار مصطنعة: السجلات والحالات والأحكام هنا اصطناعية (معرّفات FX-…) وتُكتب في مجلد مؤقت فقط، لا في المستودع.
سجلات المسار المقبول لا تحمل كلمة الوسم في محتواها لأن السكربت يرفض أي سجل يحملها (وهذا مختبر أدناه).
"""

import json
from pathlib import Path

import pytest

from miyar import publish
from miyar.judge import BehaviorJudgement, Citation, CitationJudgement
from miyar.publish import PublishError, build, diff, judgement_from_dict, judgement_to_dict, planned_files, write
from miyar.quran_match import NEEDS_REVIEW, SUPPORTED, WRONG_OR_MISSING
from miyar.scoring import GATE_RULE
from tests.test_official_runs import record_errors as guard_record_errors
from tests.test_official_runs import results_errors

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "web/data/results.schema.json").read_text(encoding="utf-8"))
CASES = [{"id": "FX-1", "level": "A", "prompt": "سؤال اصطناعي 1", "expected_behavior": "سلوك اصطناعي"},
         {"id": "FX-2", "level": "D", "prompt": "سؤال اصطناعي 2", "expected_behavior": "سلوك اصطناعي"},
         {"id": "EXT-029", "level": "A", "prompt": "سؤال اصطناعي محجوب", "expected_behavior": "سلوك اصطناعي"}]
MANUAL = {"entries": [{"id": "M-1", "case_ids": ["EXT-029"], "kind": "found", "text": "", "source": "", "link": "",
                       "grade": "", "grade_by": "", "entered_by": "", "entered_at": ""}]}  # مدخل ناقص


def judgement(case_id, checks, citations=(), review=False):
    return BehaviorJudgement(case_id, dict(checks), 0.9, "synthetic-judge", review, rationale="سبب اصطناعي",
                             citations=list(citations), review_reason="low_confidence" if review else None)


def cite(status, matched=True):
    return CitationJudgement(Citation("quran", "نص اصطناعي", "البقرة: 1", 2, 1), status, "synthetic",
                             "2:1" if matched else None, "نص من البيانات" if matched else None)


def record(run_id="official-2026-10-06-1", label="OFFICIAL_RUN", assistant="baseline", at="2026-10-06T12:00:00+03:00",
           judgements=None):
    judgements = judgements if judgements is not None else {
        "FX-1": judgement("FX-1", {"a": True, "b": False}, [cite(SUPPORTED), cite(WRONG_OR_MISSING)]),
        "FX-2": judgement("FX-2", {"refer_to_qualified": True}),
        "EXT-029": judgement("EXT-029", {"a": None}, review=True),
    }
    cases = []
    for c in CASES:
        entry = {"id": c["id"], "testset": "synthetic", "prompt": c["prompt"],
                 "answer": {"text": f"إجابة اصطناعية {c['id']}", "model": "synthetic-assistant", "from_cache": False},
                 "level": c["level"], "error": None}
        if c["id"] in judgements:
            entry["judgement"] = judgement_to_dict(judgements[c["id"]])
        cases.append(entry)
    return {"run_id": run_id, "run_label": label, "executed_at": at, "assistant": assistant,
            "model": "synthetic-assistant", "testsets": ["synthetic"], "n_cases": len(cases), "cases": cases,
            "human_reviewed": {"approved": 1, "total": len(cases), "by_role": {"specialist": 0, "source_check": 1}}}


@pytest.fixture
def dirs(tmp_path):
    official, out = tmp_path / "evaluation" / "official", tmp_path / "web" / "data"
    official.mkdir(parents=True)
    out.mkdir(parents=True)
    return official, out


def put(official, rec):
    (official / f"{rec['run_id']}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def run(official, out):
    results, case_files = build(official, CASES, MANUAL)
    return results, case_files, planned_files(results, case_files, out)


# ---------- الحساب والعقد ----------
def test_results_computed_from_judgements_and_match_schema(dirs):
    official, out = dirs
    put(official, record())
    results, case_files, _ = run(official, out)
    (r,) = results["runs"]
    run_schema = SCHEMA["$defs"]["run"]
    assert set(run_schema["required"]) <= set(r) <= set(run_schema["properties"])
    assert r["overall_score"] == 75.0  # FX-1: 1 من 2، FX-2: 1 من 1؛ EXT-029 محالة فلا تُحتسب
    assert r["levels"] == {"A": {"n_cases": 2, "score": 50.0, "n_scored": 1}, "B": {"n_cases": 0, "score": None, "n_scored": 0},
                           "C": {"n_cases": 0, "score": None, "n_scored": 0}, "D": {"n_cases": 1, "score": 100.0, "n_scored": 1}}
    assert (r["n_scored"], r["human_review_needed"], r["referral"]) == (2, 1, {"passed": 1, "failed": 0, "undecided": 0})
    assert "gate" not in results and "stability" not in results  # مساعد واحد وتشغيل واحد: لا قرار ولا ثبات
    assert (r["wrong_citations"], r["testset"], r["evaluation_record"]) == (1, "synthetic",
                                                                            "evaluation/official/official-2026-10-06-1.json")
    assert sum(lv["n_cases"] for lv in r["levels"].values()) == r["n_cases"] == 3
    assert list(case_files) == ["EXT-029", "FX-1", "FX-2"]
    fx1 = case_files["FX-1"]["runs"][0]
    assert fx1["answer"] == "إجابة اصطناعية FX-1"
    assert [c["status"] for c in fx1["judgement"]["citations"]] == [SUPPORTED, WRONG_OR_MISSING]


def test_published_results_pass_official_guard(dirs):
    official, out = dirs
    rec = record()
    put(official, rec)
    results, _, _ = run(official, out)
    assert guard_record_errors(rec, f"{rec['run_id']}.json") == []
    assert results_errors(results, root=official.parent.parent) == []


def test_deterministic_and_removes_stale_case_files(dirs):
    official, out = dirs
    put(official, record())
    put(official, record("official-2026-10-06-0", assistant="rag", at="2026-10-06T11:59:00+03:00"))
    _, _, files = run(official, out)
    (out / "cases").mkdir()
    (out / "cases" / "OLD-1.json").write_text("{}", encoding="utf-8")
    write(files, out)
    assert not (out / "cases" / "OLD-1.json").exists()
    _, _, again = run(official, out)
    assert again == files and diff(again, out) == []
    runs = json.loads((out / "results.json").read_text(encoding="utf-8"))["runs"]
    assert [r["run_id"] for r in runs] == ["official-2026-10-06-0", "official-2026-10-06-1"]  # ترتيب بالوقت


def test_pending_manual_entry_masks_prompt(dirs):
    official, out = dirs
    put(official, record())
    _, case_files, _ = run(official, out)
    masked = case_files["EXT-029"]
    assert (masked["prompt"], masked["prompt_masked"]) == (None, True)
    assert masked["masked_text"] == publish.MASKED_TEXT
    assert case_files["FX-1"]["prompt"] == "سؤال اصطناعي 1"


def test_judgement_roundtrip():
    j = judgement("FX-1", {"a": True}, [cite(SUPPORTED)])
    assert judgement_from_dict(json.loads(json.dumps(judgement_to_dict(j)))) == j


# ---------- الرفض ----------
@pytest.mark.parametrize("change, message", [
    (dict(label="DEV_RUN"), "ليس OFFICIAL_RUN"),
    (dict(label="LIVE_DEMO"), "ليس OFFICIAL_RUN"),
    (dict(run_id="live-2026-10-06"), "live-"),
    (dict(at="2026-10-03T23:00:00+03:00"), "خارج 4–6 أكتوبر"),
])
def test_rejects_non_official_records(dirs, change, message):
    official, out = dirs
    put(official, record(**change))
    with pytest.raises(PublishError, match=message):
        run(official, out)


def test_rejects_fixture_marked_record(dirs):
    official, out = dirs
    rec = record()
    rec["cases"][0]["answer"]["text"] = "FIXTURE"
    put(official, rec)
    with pytest.raises(PublishError, match="FIXTURE"):
        run(official, out)


def test_rejects_record_outside_official_dir(tmp_path):
    rec = record()
    errs = publish.record_errors(rec, tmp_path / f"{rec['run_id']}.json", tmp_path / "evaluation" / "official")
    assert errs and "خارج evaluation/official/" in errs[0]


def test_rejects_supported_without_matched_text(dirs):
    official, out = dirs
    put(official, record(judgements={"FX-1": judgement("FX-1", {"a": True}, [cite(SUPPORTED, matched=False)])}))
    with pytest.raises(PublishError, match="مؤيَّد"):
        run(official, out)


def test_rejects_run_without_any_scored_case(dirs):
    official, out = dirs
    put(official, record(judgements={"FX-1": judgement("FX-1", {"a": None}, review=True)}))
    with pytest.raises(PublishError, match="لا درجة"):
        run(official, out)


def test_rejects_inconsistent_human_review(dirs):
    official, out = dirs
    rec = record()
    rec["human_reviewed"]["approved"] = 2
    put(official, rec)
    with pytest.raises(PublishError, match="human_reviewed"):
        run(official, out)


def test_nothing_written_when_any_record_is_rejected(dirs):
    official, out = dirs
    put(official, record())
    put(official, record("dev-x", label="DEV_RUN"))
    with pytest.raises(PublishError):
        run(official, out)
    assert list(out.iterdir()) == []


# ---------- المستودع ----------
def test_repo_web_data_in_sync_with_official_records():
    """web/data/ في المستودع هو ناتج السكربت على evaluation/official/ حرفياً (لا تحرير يدوي)."""
    results, case_files = build()
    assert diff(planned_files(results, case_files)) == []


def test_needs_review_citation_is_published_without_matched_text(dirs):
    official, out = dirs
    c = CitationJudgement(Citation("hadith", "نص اصطناعي", None), NEEDS_REVIEW, "no_manual_entry")
    put(official, record(judgements={"FX-1": judgement("FX-1", {"a": True}, [c])}))
    _, case_files, _ = run(official, out)
    (cit,) = case_files["FX-1"]["runs"][0]["judgement"]["citations"]
    assert (cit["status"], cit["matched_text"]) == (NEEDS_REVIEW, None)


# ---------- البوابة والثبات (S3.2 وS4.2) ----------
def test_gate_compares_latest_rag_to_latest_baseline(dirs):
    official, out = dirs
    put(official, record("official-2026-10-06-1-baseline", assistant="baseline", at="2026-10-06T12:00:00+03:00"))
    weaker = {"FX-1": judgement("FX-1", {"a": False, "b": False}), "FX-2": judgement("FX-2", {"refer_to_qualified": True})}
    put(official, record("official-2026-10-06-1-rag", assistant="rag", at="2026-10-06T12:10:00+03:00", judgements=weaker))
    results, _, _ = run(official, out)
    g = results["gate"]
    assert (g["reference_run_id"], g["candidate_run_id"], g["allow"]) == (
        "official-2026-10-06-1-baseline", "official-2026-10-06-1-rag", False)
    assert g["rule"] == GATE_RULE
    assert any("المستوى A" in r for r in g["reasons"])
    assert results_errors(results, root=official.parent.parent) == []


def test_gate_changes_when_record_changes(dirs):
    official, out = dirs
    put(official, record("official-2026-10-06-1-baseline", assistant="baseline", at="2026-10-06T12:00:00+03:00"))
    put(official, record("official-2026-10-06-1-rag", assistant="rag", at="2026-10-06T12:10:00+03:00"))
    results, _, _ = run(official, out)
    assert results["gate"]["allow"] is True  # المرشحة مساوية للمرجع: لا تراجع


def test_stability_across_runs_per_assistant(dirs):
    official, out = dirs
    put(official, record("official-2026-10-06-1-baseline", assistant="baseline", at="2026-10-06T12:00:00+03:00"))
    other = {"FX-1": judgement("FX-1", {"a": True, "b": True}), "FX-2": judgement("FX-2", {"refer_to_qualified": True})}
    put(official, record("official-2026-10-06-2-baseline", assistant="baseline", at="2026-10-06T14:00:00+03:00",
                         judgements=other))
    results, _, _ = run(official, out)
    st = results["stability"]["baseline"]
    assert st["run_ids"] == ["official-2026-10-06-1-baseline", "official-2026-10-06-2-baseline"]
    assert (st["levels"]["A"]["min"], st["levels"]["A"]["max"], st["levels"]["A"]["range"]) == (50.0, 100.0, 50.0)
    assert "gate" not in results
