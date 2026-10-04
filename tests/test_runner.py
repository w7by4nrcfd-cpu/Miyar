"""runner: تحميل الحالات، والتشغيل على مساعد، وحفظ السجل — بمساعد وهمي ونقل وهمي، بلا شبكة.

⚠️ FIXTURE: الإجابات والنماذج والمعرّفات هنا مصطنعة للاختبار، وليست نتائج تشغيل حقيقية.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from miyar import runner
from miyar.assistants import baseline
from miyar.llm import CallBudgetExceeded
from miyar.runner import DEV_RUN, OFFICIAL_RUN, RIYADH, Answer, load_cases, run_testset, save_run
from tests.test_official_runs import record_errors

ROOT = Path(__file__).resolve().parent.parent
TS = [ROOT / "testsets/official_v0.json", ROOT / "testsets/extended_v1.json"]
FIXED = lambda: datetime(2026, 10, 4, 12, 0, tzinfo=RIYADH)  # noqa: E731


class FakeTarget:
    """مساعد وهمي: يعيد إجابة FIXTURE، ويرفع خطأً للأسئلة المحددة."""

    def __init__(self, name="fixture-assistant", fail_on=(), budget_after=None):
        self.name, self.model = name, "fixture-model"
        self.fail_on, self.budget_after, self.calls = set(fail_on), budget_after, []

    def answer(self, prompt, context=None):
        self.calls.append((prompt, context))
        if self.budget_after is not None and len(self.calls) > self.budget_after:
            raise CallBudgetExceeded("FIXTURE: بلغ السقف")
        if prompt in self.fail_on:
            raise RuntimeError("FIXTURE: فشل مصطنع")
        return Answer(text=f"إجابة FIXTURE عن: {prompt[:20]}", model=self.model)


def test_load_cases_keeps_order_tags_testset_and_rejects_duplicates(tmp_path):
    cases = load_cases(TS)
    off = json.loads(TS[0].read_text(encoding="utf-8"))["cases"]
    ext = json.loads(TS[1].read_text(encoding="utf-8"))["cases"]
    assert [c["id"] for c in cases] == [c["id"] for c in off + ext]
    assert {c["testset"] for c in cases[:len(off)]} == {"official_v0"}
    assert {c["testset"] for c in cases[len(off):]} == {"extended_v1"}
    dup = tmp_path / "dup.json"
    dup.write_text(json.dumps({"name": "dup", "cases": off[:1]}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        load_cases([TS[0], dup])


def test_run_records_every_case_with_answers_errors_and_review_counts():
    cases = load_cases(TS[:1])
    t = FakeTarget(fail_on={cases[2]["prompt"]})
    rec = run_testset(cases, t, DEV_RUN, now=FIXED)
    assert rec.n_cases == len(cases) == len(t.calls)  # N = كل الحالات المطروحة، والفاشلة لا تُحذف
    assert [r.case_id for r in rec.cases] == [c["id"] for c in cases]
    failed = rec.cases[2]
    assert failed.answer is None and failed.error.startswith("RuntimeError")
    assert all(r.answer and r.answer.model == "fixture-model" for i, r in enumerate(rec.cases) if i != 2)
    assert rec.executed_at == "2026-10-04T12:00:00+03:00" and rec.assistant == "fixture-assistant"
    assert rec.model == "fixture-model" and rec.testsets == ["official_v0"]
    hr = rec.human_reviewed
    assert hr["total"] == rec.n_cases and hr["approved"] == hr["by_role"]["specialist"] + hr["by_role"]["source_check"]
    assert rec.cases[0].level == cases[0]["level"]


def test_injected_context_is_passed_to_the_assistant():
    cases = [c for c in load_cases(TS) if c.get("injected_context")]
    assert cases, "مجموعة الاختبار فيها حالات بنص مرفق"
    t = FakeTarget()
    run_testset(cases, t, DEV_RUN, now=FIXED)
    assert [ctx for _, ctx in t.calls] == [c["injected_context"] for c in cases]


def test_budget_exhaustion_is_recorded_per_case_not_hidden():
    cases = load_cases(TS[:1])[:4]
    rec = run_testset(cases, FakeTarget(budget_after=2), DEV_RUN, now=FIXED)
    assert [bool(r.error) for r in rec.cases] == [False, False, True, True]
    assert rec.to_dict()["n_errors"] == 2 and rec.to_dict()["n_cases"] == 4


def test_official_run_requires_fresh_run_id_in_the_assistant_client(tmp_path):
    env = {"MIYAR_LLM_MODEL_ASSISTANT": "fixture-model", "MIYAR_RUN_MODE": "cached", "MIYAR_LLM_CACHE_DIR": str(tmp_path)}
    cases = load_cases(TS[:1])[:1]
    with pytest.raises(ValueError):  # لا run_id في العميل
        run_testset(cases, baseline.build(env), OFFICIAL_RUN, now=FIXED)
    target = baseline.build({**env, "MIYAR_RUN_ID": "official-fixture-1"})
    with pytest.raises(ValueError):  # run_id مختلف عن معرّف العميل
        run_testset(cases, target, OFFICIAL_RUN, run_id="official-fixture-2", now=FIXED)
    rec = run_testset(cases, target, OFFICIAL_RUN, now=FIXED)
    assert rec.run_id == "official-fixture-1"
    assert rec.cases[0].error.startswith("CacheMiss")  # وضع cached بلا مخزن: لا استدعاء، والخطأ مسجّل


def test_dev_run_id_defaults_and_is_valid():
    rec = run_testset(load_cases(TS[:1])[:1], FakeTarget(), DEV_RUN, now=FIXED)
    assert rec.run_id == "dev-fixture-assistant-20261004T120000"
    with pytest.raises(ValueError):
        run_testset(load_cases(TS[:1])[:1], FakeTarget(), DEV_RUN, run_id="bad id/..", now=FIXED)
    with pytest.raises(ValueError):
        run_testset(load_cases(TS[:1])[:1], FakeTarget(), "OTHER", now=FIXED)


def test_save_run_separates_dev_and_official_and_never_overwrites(tmp_path):
    cases = load_cases(TS[:1])[:2]
    dev = run_testset(cases, FakeTarget(), DEV_RUN, run_id="dev-fixture", now=FIXED)
    off = run_testset(cases, FakeTarget(), OFFICIAL_RUN, run_id="official-fixture", now=FIXED)
    with pytest.raises(ValueError):
        save_run(off, tmp_path / "dev")
    with pytest.raises(ValueError):
        save_run(dev, tmp_path / "official")

    p = save_run(dev, tmp_path / "dev")
    assert "DEV_RUN" in p.read_text(encoding="utf-8")  # يطابق حارس tests/test_dev_runs.py
    with pytest.raises(FileExistsError):
        save_run(dev, tmp_path / "dev")

    q = save_run(off, tmp_path / "official")
    data = json.loads(q.read_text(encoding="utf-8"))
    assert record_errors(data, q.name) == []  # يطابق حارس السجلات الرسمية ومخططها
    assert data["cases"][0]["id"] == cases[0]["id"] and data["cases"][0]["answer"]["text"].startswith("إجابة FIXTURE")


def test_runner_never_imports_the_judge():
    text = (ROOT / "miyar/runner.py").read_text(encoding="utf-8")
    assert "import judge" not in text and "from .judge" not in text and "from miyar.judge" not in text


def test_main_runs_baseline_in_cached_mode_without_network(tmp_path, monkeypatch):
    monkeypatch.setenv("MIYAR_LLM_MODEL_ASSISTANT", "fixture-model")
    monkeypatch.setenv("MIYAR_RUN_MODE", "cached")
    monkeypatch.setenv("MIYAR_LLM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(runner, "DEV_DIR", tmp_path / "dev")
    assert runner.main(["--assistant", "baseline", "--testset", "official_v0"]) == 0
    files = list((tmp_path / "dev").glob("*.json"))
    rec = json.loads(files[0].read_text(encoding="utf-8"))
    assert rec["run_label"] == "DEV_RUN" and rec["n_cases"] == 12 and rec["n_errors"] == 12  # لا مخزن ولا شبكة
