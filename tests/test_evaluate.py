"""كاتب السجل الكامل (miyar/evaluate.py): المساعد ← الاستخراج ← الحكم ← سجل يقرؤه publish — بنقل وهمي، بلا شبكة.

⚠️ بيانات اختبار مصطنعة: الإجابات وإخراج المستخرِج والحَكَم والنماذج هنا اصطناعية، والمفتاح ليس حقيقياً، والسجلات تُكتب في مجلد مؤقت فقط.
لا تحمل الإجابات كلمة الوسم في محتواها لأن publish يرفض أي سجل يحملها، والاختبار هنا أن السجل الناتج يُنشر.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from miyar import evaluate as ev
from miyar.assistants import baseline
from miyar.judge import min_confidence_from_env
from miyar.llm import client_from_env
from miyar.publish import build as publish_build
from miyar.publish import record_from_dict

FAKE_KEY = "FAKE-KEY-for-tests-only-987"  # ليس مفتاحاً حقيقياً
RIYADH = timezone(timedelta(hours=3))
NOW = lambda: datetime(2026, 10, 6, 12, 0, tzinfo=RIYADH)  # noqa: E731 — داخل أيام التحدي
ASSISTANT, JUDGE = "synthetic-assistant-model", "synthetic-judge-model"


def gemini_ok(text):
    body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2}}
    return 200, {}, json.dumps(body, ensure_ascii=False).encode()


class RoutingTransport:
    """يجيب حسب الدور: المساعد، أو المستخرِج، أو الحَكَم (من تعليمات النظام)."""

    def __init__(self, extract_text='{"citations": []}', fail_assistant_for=()):
        self.calls = []
        self.extract_text = extract_text
        self.fail_assistant_for = fail_assistant_for

    def __call__(self, url, headers, body, timeout):
        req = json.loads(body)
        system = req.get("systemInstruction", {}).get("parts", [{}])[0].get("text", "")
        prompt = req["contents"][0]["parts"][0]["text"]
        if f"/models/{ASSISTANT}:" in url:
            self.calls.append("assistant")
            if any(q in prompt for q in self.fail_assistant_for):
                return 500, {}, b'{"error": "synthetic"}'
            return gemini_ok(f"إجابة اصطناعية للاختبار عن: {prompt[:40]}")  # مختلفة لكل حالة، فلا يعيدها المخزن
        if system.startswith("أنت أداة استخراج"):
            self.calls.append("extract")
            return gemini_ok(self.extract_text)
        self.calls.append("judge")
        checks = [line[2:].split(":")[0] for line in prompt.split("\n") if line.startswith("- ") and ":" in line
                  and not line.startswith("- «")]
        return gemini_ok(json.dumps({"checks": {c: True for c in checks}, "confidence": 0.9, "rationale": "سبب اصطناعي"},
                                    ensure_ascii=False))


def env(tmp_path, mode="live", run_id="official-test-1", cap="500"):
    return {"MIYAR_LLM_MODEL_ASSISTANT": ASSISTANT, "MIYAR_LLM_MODEL_JUDGE": JUDGE, "MIYAR_LLM_MODEL_JUDGE_FALLBACK": "",
            "MIYAR_RUN_MODE": mode, "MIYAR_LLM_CACHE_DIR": str(tmp_path / "cache"), "MIYAR_LIVE_MAX_CALLS_PER_DAY": cap,
            "GEMINI_API_KEY": FAKE_KEY, "MIYAR_RUN_ID": run_id}


def setup(tmp_path, t, **kw):
    e = env(tmp_path, **kw)
    target = baseline.build(e, t)
    jclient, jmodel = client_from_env(e, t, role="judge")
    return target, ev.JudgeSetup(jclient, jmodel, 0.75)


def test_case_selections():
    official = ev.select_cases("official_v0")
    plus = ev.select_cases("official_v0+critical")
    every = ev.select_cases("all")
    assert len(official) == 12 and [c["id"] for c in plus[:12]] == [c["id"] for c in official]
    assert all(c.get("critical") is True for c in plus[12:]) and len(every) == 60
    assert len(plus) == 12 + sum(1 for c in every[12:] if c.get("critical") is True)
    with pytest.raises(ValueError):
        ev.select_cases("غير معروف")


def test_full_pipeline_writes_record_that_publish_accepts(tmp_path):
    t = RoutingTransport()
    target, judge = setup(tmp_path, t)
    cases = ev.select_cases("official_v0")
    rec = ev.evaluate(cases, target, judge, "OFFICIAL_RUN", selection="official_v0", run_id="official-test-1",
                      commit="abc123", now=NOW)
    assert (rec["n_cases"], rec["n_judged"], rec["n_judge_errors"]) == (12, 12, 0)
    assert t.calls.count("assistant") == 12 and t.calls.count("extract") == 12 and t.calls.count("judge") == 12
    assert (rec["commit"], rec["case_selection"], rec["judge_model"]) == ("abc123", "official_v0", JUDGE)
    assert all(c["judgement"]["judge_model"] == JUDGE for c in rec["cases"])
    official = tmp_path / "evaluation" / "official"
    path = ev.save(rec, official)
    results, case_files = publish_build(official)
    (run,) = results["runs"]
    assert (run["n_cases"], run["overall_score"], run["evaluation_record"]) == (12, 100.0, f"evaluation/official/{path.name}")
    assert sum(lv["n_cases"] for lv in run["levels"].values()) == 12 and len(case_files) == 12


def test_identical_requests_are_not_sent_twice(tmp_path):
    # إجابتان متطابقتان ← طلب استخراج واحد فقط (المخزن)، وطلبا حكم مختلفان لأن السؤال جزء منهما
    t = RoutingTransport()
    target, judge = setup(tmp_path, t)
    case = ev.select_cases("official_v0")[0]
    rec = ev.evaluate([case, {**case, "id": "OFF-01-copy"}], target, judge, "DEV_RUN", selection="test",
                      run_id="official-test-1", now=NOW)
    assert rec["n_judged"] == 2 and t.calls.count("assistant") == 1 and t.calls.count("extract") == 1


def test_pending_manual_entry_case_is_referred_without_judge_call(tmp_path):
    t = RoutingTransport()
    target, judge = setup(tmp_path, t)
    case = next(c for c in ev.select_cases("official_v0+critical") if c["id"] == "EXT-028")  # H-004 ناقص
    rec = ev.evaluate([case], target, judge, "DEV_RUN", selection="test", run_id="official-test-1", now=NOW)
    j = rec["cases"][0]["judgement"]
    assert (j["needs_human_review"], j["review_reason"]) == (True, "manual_entry_pending")
    assert t.calls == ["assistant", "extract"]


def test_judge_failure_is_recorded_and_case_kept(tmp_path):
    t = RoutingTransport(extract_text="ليس JSON")
    target, judge = setup(tmp_path, t)
    cases = ev.select_cases("official_v0")[:2]
    rec = ev.evaluate(cases, target, judge, "DEV_RUN", selection="test", run_id="official-test-1", now=NOW)
    assert rec["n_cases"] == 2 and rec["n_judged"] == 0 and rec["n_judge_errors"] == 2
    assert all("ExtractionError" in c["judge_error"] and "judgement" not in c for c in rec["cases"])


def test_unanswered_case_is_not_judged(tmp_path):
    cases = ev.select_cases("official_v0")[:2]
    t = RoutingTransport(fail_assistant_for=(cases[0]["prompt"],))
    target, judge = setup(tmp_path, t)
    rec = ev.evaluate(cases, target, judge, "DEV_RUN", selection="test", run_id="official-test-1", now=NOW)
    first, second = rec["cases"]
    assert first["error"] and "judgement" not in first and "judge_error" not in first
    assert "judgement" in second and t.calls.count("extract") == 1


def test_cached_mode_replays_without_any_call(tmp_path):
    cases = ev.select_cases("official_v0")[:3]
    live = RoutingTransport()
    target, judge = setup(tmp_path, live)
    first = ev.evaluate(cases, target, judge, "DEV_RUN", selection="test", run_id="official-test-1", now=NOW)
    replay = RoutingTransport()
    target, judge = setup(tmp_path, replay, mode="cached")
    second = ev.evaluate(cases, target, judge, "DEV_RUN", selection="test", run_id="official-test-1", now=NOW)
    assert replay.calls == []
    strip = lambda r: [{k: v for k, v in c.items() if k != "answer"} | {"answer": c["answer"]["text"]} for c in r["cases"]]  # noqa: E731
    assert [c["judgement"]["checks"] for c in strip(first)] == [c["judgement"]["checks"] for c in strip(second)]


def test_official_run_requires_run_id(tmp_path):
    t = RoutingTransport()
    target, judge = setup(tmp_path, t, run_id="")
    with pytest.raises(ValueError, match="OFFICIAL_RUN"):
        ev.evaluate(ev.select_cases("official_v0")[:1], target, judge, "OFFICIAL_RUN", selection="test", now=NOW)
    assert t.calls == []


def test_save_guards(tmp_path):
    t = RoutingTransport()
    target, judge = setup(tmp_path, t)
    rec = ev.evaluate(ev.select_cases("official_v0")[:1], target, judge, "DEV_RUN", selection="test",
                      run_id="official-test-1", now=NOW)
    with pytest.raises(ValueError):
        ev.save(rec, tmp_path / "evaluation" / "official")
    dev = tmp_path / "evaluation" / "dev"
    ev.save(rec, dev)
    with pytest.raises(FileExistsError):
        ev.save(rec, dev)
    with pytest.raises(ValueError):
        ev.save({**rec, "run_label": "OFFICIAL_RUN"}, dev)


def test_record_roundtrips_through_publish_reader(tmp_path):
    t = RoutingTransport()
    target, judge = setup(tmp_path, t)
    rec = ev.evaluate(ev.select_cases("official_v0")[:2], target, judge, "OFFICIAL_RUN", selection="test",
                      run_id="official-test-1", now=NOW)
    back = record_from_dict(json.loads(json.dumps(rec, ensure_ascii=False)))
    assert [c.case_id for c in back.cases] == [c["id"] for c in rec["cases"]] and back.run_label == "OFFICIAL_RUN"


def test_min_confidence_comes_from_env_by_default():
    assert ev.JudgeSetup(None, JUDGE, min_confidence_from_env({})).min_confidence == 0.75
