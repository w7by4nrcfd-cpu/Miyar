"""المساعد rag بنقل وهمي — لا اتصال بالشبكة ولا استهلاك للحصة.

⚠️ FIXTURE: الأسئلة والإجابات والنماذج والمفتاح ومدخلات الحديث هنا مصطنعة للاختبار، وليست بيانات حقيقية ولا نتائج.
الآيات في اختبار البحث من بيانات Quranpedia الفعلية (data/quran/).
"""

import ast
import json
from pathlib import Path

from miyar.assistants import baseline, rag
from miyar.targets import CONTEXT_CLOSE, CONTEXT_OPEN

ROOT = Path(__file__).resolve().parent.parent
FAKE_KEY = "FAKE-KEY-for-tests-only-789"  # ليس مفتاحاً حقيقياً


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "body": json.loads(body)})
        return self.responses.pop(0)


def ok(text):
    body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2}}
    return 200, {}, json.dumps(body, ensure_ascii=False).encode()


def _env(tmp_path, mode="live", **extra):
    env = {
        "MIYAR_LLM_PROVIDER": "gemini",
        "MIYAR_LLM_MODEL_ASSISTANT": "fixture-assistant-model",
        "MIYAR_LLM_MODEL_JUDGE": "fixture-judge-model",
        "MIYAR_RUN_MODE": mode,
        "MIYAR_LLM_CACHE_DIR": str(tmp_path),
        "MIYAR_LIVE_MAX_CALLS_PER_DAY": "5",
        "GEMINI_API_KEY": FAKE_KEY,
    }
    env.update(extra)
    return env


FIXTURE_MANUAL = {"entries": [
    {"id": "H-FX1", "case_ids": ["FX"], "kind": "found", "text": "حديث FIXTURE عن الصدق والأمانة",
     "source": "مصدر FIXTURE", "link": "https://dorar.net/h/fixture", "grade": "صحيح", "grade_by": "قائل FIXTURE",
     "entered_by": "FIXTURE", "entered_at": "2026-10-04"},
    {"id": "H-FX2", "case_ids": ["FX"], "kind": "found", "text": "حديث FIXTURE ناقص عن الصدق",
     "source": "", "link": "", "grade": "", "grade_by": "", "entered_by": "FIXTURE", "entered_at": "2026-10-04"},
    {"id": "H-FX3", "case_ids": ["FX"], "kind": "not_found", "query": "الصدق", "searched_in": "الدرر",
     "link": "https://dorar.net/x", "entered_by": "FIXTURE", "entered_at": "2026-10-04"},
]}


def small_retriever():
    quran = [rag.Passage("quran", "FX 1:1", "الصدق يهدي الى البر"), rag.Passage("quran", "FX 1:2", "والشمس وضحاها")]
    return rag.Retriever(quran, rag.hadith_passages(FIXTURE_MANUAL))


def test_only_complete_found_hadith_entries_are_retrievable():
    ps = rag.hadith_passages(FIXTURE_MANUAL)
    assert [p.ref for p in ps] == ["H-FX1"]  # الناقص وnot_found لا يُسترجعان
    assert "صحيح" in ps[0].meta and "قائل FIXTURE" in ps[0].meta and "dorar.net" in ps[0].meta


def test_retrieval_is_lexical_and_ignores_function_words():
    r = small_retriever()
    assert [p.ref for p in r.search("ما فضل الصدق؟")] == ["FX 1:1", "H-FX1"]
    assert r.search("هل من في على") == []  # كلمات وظيفية فقط: لا مقطع


def test_default_retriever_finds_verse_in_quranpedia_data():
    refs = [p.ref for p in rag.default_retriever().search("ما معنى لا إكراه في الدين؟")]
    assert refs[0] == "البقرة 2:256"
    assert all(p.kind in ("quran", "hadith") for p in rag.default_retriever().search("الصلاة"))


def test_rag_sends_sources_before_question_and_keeps_injected_context_separate(tmp_path):
    t = FakeTransport(ok("إجابة FIXTURE"))
    target = rag.build(_env(tmp_path), transport=t, retriever=small_retriever())
    assert target.name == "rag" and target.model == "fixture-assistant-model"
    ans = target.answer("ما فضل الصدق؟", "نص مرفق FIXTURE")
    assert (ans.text, ans.from_cache) == ("إجابة FIXTURE", False)

    sent = t.calls[0]["body"]
    prompt = sent["contents"][0]["parts"][0]["text"]
    assert prompt.index(rag.SOURCES_OPEN) < prompt.index(rag.SOURCES_CLOSE) < prompt.index(CONTEXT_OPEN)
    assert prompt.index(CONTEXT_CLOSE) < prompt.index("ما فضل الصدق؟")
    assert "[قرآن — FX 1:1] الصدق يهدي الى البر" in prompt and "[حديث — H-FX1]" in prompt
    assert "H-FX2" not in prompt and "والشمس" not in prompt
    assert sent["systemInstruction"]["parts"][0]["text"] == rag.SYSTEM
    assert "fixture-assistant-model" in t.calls[0]["url"]
    assert FAKE_KEY not in json.dumps(sent, ensure_ascii=False)


def test_no_match_is_stated_explicitly_in_sources_block(tmp_path):
    t = FakeTransport(ok("FIXTURE"))
    rag.build(_env(tmp_path), transport=t, retriever=small_retriever()).answer("Is this a question?")
    prompt = t.calls[0]["body"]["contents"][0]["parts"][0]["text"]
    assert "لم يُعثر في المصادر المعتمدة" in prompt


def test_rag_uses_same_model_as_baseline_and_store_avoids_second_call(tmp_path):
    t = FakeTransport(ok("مرة واحدة FIXTURE"))
    env = _env(tmp_path)
    assert rag.build(env, transport=t, retriever=small_retriever()).model == baseline.build(env, transport=t).model
    first = rag.build(env, transport=t, retriever=small_retriever()).answer("ما فضل الصدق؟")
    again = rag.build(_env(tmp_path, mode="cached"), transport=t, retriever=small_retriever()).answer("ما فضل الصدق؟")
    assert len(t.calls) == 1 and again.text == first.text and again.from_cache is True


def test_rag_does_not_import_judge_or_extract():
    tree = ast.parse((ROOT / "miyar/assistants/rag.py").read_text(encoding="utf-8"))
    mods = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not any(m.endswith(("judge", "extract")) for m in mods)
