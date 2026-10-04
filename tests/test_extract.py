"""extract: استخراج الآيات من إجابة المساعد بنقل وهمي، والتحقق البرمجي الذي يمنع المستخرِج من التأليف.

⚠️ FIXTURE: إجابات المساعد وإخراج المستخرِج هنا مصطنعة للاختبار، وليست نتائج حقيقية.
نصوص الآيات المستعملة منسوخة من بيانات المشروع (Quranpedia) أو محرّفة عمداً لاختبار الرفض.
"""

import json
from pathlib import Path

import pytest

from miyar.extract import KIND_QURAN, ExtractionError, build_request, extract, parse_output, validate
from miyar.judge import Citation
from miyar.llm import CacheMiss, client_from_env
from miyar.quran_match import QuranIndex

ROOT = Path(__file__).resolve().parent.parent
FAKE_KEY = "FAKE-KEY-for-tests-only-789"  # ليس مفتاحاً حقيقياً
IDX = QuranIndex.load()


class FakeTransport:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "body": json.loads(body)})
        return self.responses.pop(0)


def ok(payload):
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2}}
    return 200, {}, json.dumps(body, ensure_ascii=False).encode()


def _env(tmp_path, mode="live"):
    return {"MIYAR_LLM_MODEL_JUDGE": "fixture-judge-model", "MIYAR_LLM_MODEL_ASSISTANT": "fixture-assistant-model",
            "MIYAR_LLM_MODEL_JUDGE_FALLBACK": "", "MIYAR_RUN_MODE": mode, "MIYAR_LLM_CACHE_DIR": str(tmp_path),
            "MIYAR_LIVE_MAX_CALLS_PER_DAY": "5", "GEMINI_API_KEY": FAKE_KEY}


V_2_255 = IDX.verse(2, 255).text_simple.split()[:6]  # مطلع آية الكرسي من البيانات
QUOTE = " ".join(V_2_255)
ANSWER = f"إجابة FIXTURE: قال تعالى «{QUOTE}» (البقرة: 255). وهذا شرح عام."


def test_valid_quote_and_location_are_kept():
    raw = [{"kind": "quran", "quote": QUOTE, "cited": "البقرة: 255", "sura": 2, "aya": 255, "aya_end": None}]
    kept, rejected = validate(raw, ANSWER, IDX)
    assert rejected == [] and len(kept) == 1
    c = kept[0]
    assert (c.kind, c.sura, c.aya, c.cited, c.notes) == (KIND_QURAN, 2, 255, "البقرة: 255", [])
    assert c.as_citation() == Citation(kind="quran", quote=QUOTE, cited="البقرة: 255", sura=2, aya=255)


def test_quote_not_in_answer_is_rejected_extractor_cannot_correct_or_invent():
    # المستخرِج «صحّح» الآية أو أضاف آية لم ترد في الإجابة: يُرفض
    answer = "إجابة FIXTURE: قال تعالى «وقل رب زدني فهما» (طه: 114)."
    raw = [{"kind": "quran", "quote": "وقل رب زدني علما", "cited": "طه: 114", "sura": 20, "aya": 114},
           {"kind": "quran", "quote": "إن مع العسر يسرا", "cited": None, "sura": None, "aya": None}]
    kept, rejected = validate(raw, answer, IDX)
    assert kept == [] and [r["reason"] for r in rejected] == ["quote_not_in_answer", "quote_not_in_answer"]
    # والنص المحرّف كما ورد في الإجابة يُستخرج كما هو (والحكم عليه لاحقاً لـ quran_match)
    kept, _ = validate([{"kind": "quran", "quote": "وقل رب زدني فهما", "cited": "طه: 114", "sura": 20, "aya": 114}], answer, IDX)
    assert kept[0].quote == "وقل رب زدني فهما" and (kept[0].sura, kept[0].aya) == (20, 114)


def test_diacritics_hamza_and_digit_forms_still_match():
    answer = "FIXTURE: ﴿قُلْ هُوَ اللَّهُ أَحَدٌ﴾ [الإخلاص: ١]"
    raw = [{"kind": "quran", "quote": "قل هو الله أحد", "cited": "الإخلاص: ١", "sura": 112, "aya": 1}]
    kept, rejected = validate(raw, answer, IDX)
    assert rejected == [] and (kept[0].sura, kept[0].aya) == (112, 1)


def test_location_the_assistant_did_not_state_is_dropped():
    answer = f"FIXTURE: قال تعالى «{QUOTE}» وهي آية عظيمة."
    raw = [{"kind": "quran", "quote": QUOTE, "cited": "البقرة: 255", "sura": 2, "aya": 255}]
    kept, _ = validate(raw, answer, IDX)
    assert kept[0].cited is None and not kept[0].has_location and kept[0].notes == ["cited_not_in_answer"]


def test_location_inconsistent_with_cited_text_is_dropped():
    # الاسم المذكور لا يطابق رقم السورة، أو رقم الآية ليس في نص الموضع
    raw1 = [{"kind": "quran", "quote": QUOTE, "cited": "البقرة: 255", "sura": 3, "aya": 255}]
    raw2 = [{"kind": "quran", "quote": QUOTE, "cited": "البقرة: 255", "sura": 2, "aya": 256}]
    k1, _ = validate(raw1, ANSWER, IDX)
    k2, _ = validate(raw2, ANSWER, IDX)
    assert k1[0].notes == ["sura_name_mismatch"] and not k1[0].has_location and k1[0].cited == "البقرة: 255"
    assert k2[0].notes == ["aya_number_not_in_cited"] and not k2[0].has_location


def test_numeric_location_and_invalid_numbers():
    answer = f"FIXTURE: «{QUOTE}» (2:255)"
    kept, _ = validate([{"kind": "quran", "quote": QUOTE, "cited": "(2:255)", "sura": 2, "aya": 255}], answer, IDX)
    assert (kept[0].sura, kept[0].aya) == (2, 255)
    kept, _ = validate([{"kind": "quran", "quote": QUOTE, "cited": "(2:255)", "sura": 200, "aya": 255}], answer, IDX)
    assert kept[0].notes == ["location_incomplete_or_invalid"]


def test_non_quran_items_are_set_aside_for_day_2():
    raw = [{"kind": "hadith", "quote": "إجابة FIXTURE", "cited": None}]
    kept, rejected = validate(raw, ANSWER, IDX)
    assert kept == [] and rejected[0]["reason"] == "kind_not_supported_yet"


def test_parse_output_accepts_fences_and_rejects_bad_shapes():
    assert parse_output('```json\n{"citations": []}\n```') == []
    for bad in ("ليس JSON", '{"items": []}', '{"citations": ["x"]}', "[]"):
        with pytest.raises(ExtractionError):
            parse_output(bad)


def test_extract_uses_mi_yar_judge_model_not_the_assistant(tmp_path):
    payload = {"citations": [{"kind": "quran", "quote": QUOTE, "cited": "البقرة: 255", "sura": 2, "aya": 255, "aya_end": None}]}
    t = FakeTransport(ok(payload))
    client, model = client_from_env(_env(tmp_path), t, role="judge")
    ex = extract(ANSWER, client, model, IDX)
    assert model == "fixture-judge-model" and "fixture-judge-model" in t.calls[0]["url"]
    body = t.calls[0]["body"]
    assert body["generationConfig"].get("responseMimeType") == "application/json"
    assert ANSWER in body["contents"][0]["parts"][0]["text"]
    assert len(ex.citations) == 1 and ex.citations[0].aya == 255 and ex.model == "fixture-judge-model"
    # الإعادة من المخزن دون استدعاء ثانٍ
    again = extract(ANSWER, client_from_env(_env(tmp_path, "cached"), t, role="judge")[0], model, IDX)
    assert len(t.calls) == 1 and again.from_cache is True


def test_extract_empty_answer_never_calls_and_cached_miss_raises(tmp_path):
    t = FakeTransport()
    client, model = client_from_env(_env(tmp_path, "cached"), t, role="judge")
    assert extract("   ", client, model, IDX).citations == []
    with pytest.raises(CacheMiss):
        extract(ANSWER, client, model, IDX)
    assert t.calls == []


def test_request_is_deterministic_and_extractor_never_imports_assistants():
    assert build_request(ANSWER, "m").key() == build_request(ANSWER, "m").key()
    text = (ROOT / "miyar/extract.py").read_text(encoding="utf-8")
    assert "assistants" not in text.split('"""', 2)[2]
