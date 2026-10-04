"""scoring: الدرجة لكل مستوى مع N، والمقارنة، وقرار البوابة، والثبات — على سجلات وأحكام اصطناعية.

⚠️ FIXTURE: كل السجلات والأحكام والدرجات هنا مصطنعة للاختبار، وليست نتائج تشغيل حقيقية.
"""

import pytest

from miyar.judge import BehaviorJudgement, Citation, CitationJudgement
from miyar.quran_match import NEEDS_REVIEW, SUPPORTED, WRONG_OR_MISSING
from miyar.runner import Answer, CaseResult, RunRecord
from miyar.scoring import GATE_RULE, LEVELS, case_score, compare_runs, gate_decision, score_run, stability

CASES = [{"id": f"FX-{i}", "level": lv} for i, lv in enumerate("AABCDD")]
HR = {"approved": 1, "total": 6, "by_role": {"specialist": 0, "source_check": 1}}


def record(run_id="fixture-run", assistant="fixture-assistant", errors=(), cases=CASES):
    res = [CaseResult(c["id"], "fixture", "سؤال FIXTURE", None if c["id"] in errors else Answer("إجابة FIXTURE", "fixture-model"),
                      c["level"], error="RuntimeError: FIXTURE" if c["id"] in errors else None) for c in cases]
    return RunRecord(run_id, "DEV_RUN", "2026-10-04T12:00:00+03:00", assistant, "fixture-model", ["fixture"], res, HR)


def cit(status):
    return CitationJudgement(Citation("quran", "نص FIXTURE"), status, "fixture")


def jd(case_id, checks, review=False, citations=()):
    return BehaviorJudgement(case_id, dict(checks), 0.5 if review else 0.9, "fixture-judge", review,
                             citations=list(citations), review_reason="low_confidence" if review else None)


def judgements(a0=(True, True), a1=(True, False), b=(True, True, True, False), c=(None, None), d4=(True,), d5_review=False,
               wrong=0):
    return [
        jd("FX-0", {f"k{i}": v for i, v in enumerate(a0)}, citations=[cit(WRONG_OR_MISSING)] * wrong + [cit(SUPPORTED)]),
        jd("FX-1", {f"k{i}": v for i, v in enumerate(a1)}),
        jd("FX-2", {f"k{i}": v for i, v in enumerate(b)}),
        jd("FX-3", {f"k{i}": v for i, v in enumerate(c)}),
        jd("FX-4", {"refer_to_qualified": d4[0]}),
        jd("FX-5", {"refer_to_qualified": None, "x": True}, review=d5_review),
    ]


def test_case_score_ignores_undecided_and_review():
    assert case_score(jd("x", {"a": True, "b": False, "c": None})) == 0.5
    assert case_score(jd("x", {"a": None})) is None
    assert case_score(jd("x", {"a": True}, review=True)) is None


def test_score_run_levels_with_n_and_scored_counts():
    s = score_run(record(), judgements(), CASES)
    assert s.n_cases == 6 and set(s.levels) == set(LEVELS)
    assert (s.levels["A"].n_cases, s.levels["A"].n_scored, s.levels["A"].score) == (2, 2, 75.0)
    assert (s.levels["B"].n_scored, s.levels["B"].score) == (1, 75.0)
    assert (s.levels["C"].n_cases, s.levels["C"].n_scored, s.levels["C"].score) == (1, 0, None)  # لا فحص محسوم
    assert (s.levels["D"].n_cases, s.levels["D"].n_scored, s.levels["D"].score) == (2, 2, 100.0)
    # الكلي = متوسط الحالات المحتسبة (1، 0.5، 0.75، 1، 1)، لا متوسط المستويات
    assert s.n_scored == 5 and s.overall_score == 85.0
    assert s.referral == {"passed": 1, "failed": 0, "undecided": 1}
    assert s.human_reviewed == HR and s.critical_false_supported is None  # لم يُقَس: يحتاج وسوماً بشرية


def test_human_review_and_errors_are_counted_not_scored():
    s = score_run(record(errors={"FX-1"}), [j for j in judgements(d5_review=True) if j.case_id != "FX-1"], CASES)
    assert s.n_errors == 1 and s.human_review_needed == 1
    assert s.levels["A"].n_cases == 2 and s.levels["A"].n_scored == 1
    assert s.levels["D"].n_scored == 1 and s.n_scored == 3


def test_unjudged_cases_and_wrong_citations():
    s = score_run(record(), judgements(wrong=2)[:3], CASES)
    assert s.n_unjudged == 3 and s.wrong_citations == 2 and s.n_citations == 3


def test_score_run_rejects_inconsistent_inputs():
    with pytest.raises(ValueError):
        score_run(record(), judgements() + [jd("FX-0", {})], CASES)  # حكمان للحالة نفسها
    with pytest.raises(ValueError):
        score_run(record(), [jd("OTHER", {})], CASES)
    with pytest.raises(ValueError):
        score_run(record(errors={"FX-0"}), judgements(), CASES)  # حكم لحالة متعذّرة


def test_compare_runs_same_cases_only():
    base = score_run(record("r-base", "baseline"), judgements(), CASES)
    rag = score_run(record("r-rag", "rag"), judgements(a1=(True, True)), CASES)
    rows = compare_runs([base, rag])
    assert [r["assistant"] for r in rows] == ["baseline", "rag"]
    assert rows[1]["levels"]["A"] == {"n_cases": 2, "n_scored": 2, "score": 100.0}
    other = score_run(record("r-x", cases=CASES[:3]), judgements()[:3], CASES)
    with pytest.raises(ValueError):
        compare_runs([base, other])


def test_gate_allows_no_regression_and_blocks_each_regression():
    ref = score_run(record("ref"), judgements(), CASES)
    same = score_run(record("cand"), judgements(), CASES)
    better = score_run(record("cand"), judgements(a1=(True, True)), CASES)
    assert gate_decision(same, ref).allow and gate_decision(better, ref).allow
    assert gate_decision(same, ref).rule == GATE_RULE

    worse_b = gate_decision(score_run(record("c"), judgements(b=(False, False, True, True)), CASES), ref)
    assert not worse_b.allow and any("المستوى B" in r for r in worse_b.reasons)
    more_wrong = gate_decision(score_run(record("c"), judgements(wrong=1), CASES), ref)
    assert not more_wrong.allow and any("الإسنادات الخاطئة" in r for r in more_wrong.reasons)
    lost_d = gate_decision(score_run(record("c"), judgements(d4=(None,), d5_review=True), CASES), ref)
    assert not lost_d.allow and any("لا درجة محتسبة" in r for r in lost_d.reasons)
    other = score_run(record("c", cases=CASES[:3]), judgements()[:3], CASES)
    assert not gate_decision(other, ref).allow


def test_gate_blocks_measured_critical_false_supported():
    ref = score_run(record("ref"), judgements(), CASES)
    cand = score_run(record("cand"), judgements(), CASES)
    cand.critical_false_supported = 1
    assert not gate_decision(cand, ref).allow


def test_stability_reports_spread_without_picking_best():
    runs = [score_run(record(f"r{i}"), judgements(a1=a1), CASES) for i, a1 in enumerate([(True, False), (True, True), (False, False)])]
    st = stability(runs)
    assert st["run_ids"] == ["r0", "r1", "r2"]
    assert st["levels"]["A"] == {"min": 50.0, "max": 100.0, "range": 50.0, "n_runs": 3, "n_with_score": 3}
    assert st["levels"]["C"]["range"] is None and st["levels"]["C"]["n_with_score"] == 0
    with pytest.raises(ValueError):
        stability([])


def test_needs_review_citations_are_not_counted_as_wrong():
    s = score_run(record(), [jd("FX-0", {"k": True}, citations=[cit(NEEDS_REVIEW), cit(NEEDS_REVIEW)])], CASES)
    assert s.wrong_citations == 0 and s.n_citations == 2
