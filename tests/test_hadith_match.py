"""hadith_match وحكم الأحاديث في judge: مطابقة برمجية مع الملف اليدوي وحده، وحَكَم بنقل وهمي — بلا شبكة.

⚠️ FIXTURE: المدخلات المصطنعة (معرّفاتها F-…) وإجابات المساعد وإخراج الحَكَم هنا للاختبار فقط، وليست بيانات حقيقية.
الاختبارات على الملف اليدوي الحقيقي تقرأ data/hadith/manual_hadith.json كما هو ولا تعدّله.
"""

import json
from pathlib import Path

from miyar import hadith_match
from miyar.hadith_manual import load_manual
from miyar.judge import Citation, judge_behavior, judge_citation, judge_citations
from miyar.llm import client_from_env
from miyar.quran_match import NEEDS_REVIEW, SUPPORTED, WRONG_OR_MISSING
from miyar.runner import load_cases

ROOT = Path(__file__).resolve().parent.parent
FAKE_KEY = "FAKE-KEY-for-tests-only-654"  # ليس مفتاحاً حقيقياً
CASES = {c["id"]: c for c in load_cases([ROOT / "testsets/official_v0.json", ROOT / "testsets/extended_v1.json"])}
MANUAL = load_manual()


def _found(id_, text, source, grade="FIXTURE-درجة", grade_by="FIXTURE-قائل", case_ids=("FIX-1",), **kw):
    e = {"id": id_, "case_ids": list(case_ids), "kind": "found", "text": text, "source": source,
         "link": "https://dorar.net/h/FIXTURE", "grade": grade, "grade_by": grade_by,
         "entered_by": "FIXTURE", "entered_at": "2026-10-04"}
    e.update(kw)
    return e


FIX = {"entries": [
    _found("F-1", "حديث تجريبي أول للاختبار فقط", "سنن ابن ماجه 100"),
    _found("F-2", "حديث تجريبي ثان بلا درجة", "سنن ابن ماجه 200", grade="", grade_by="", case_ids=("FIX-2",)),
    {"id": "F-3", "case_ids": ["FIX-3"], "kind": "collection_range", "source": "صحيح البخاري", "max_number": 50,
     "link": "https://dorar.net/FIXTURE", "entered_by": "FIXTURE", "entered_at": "2026-10-04"},
    {"id": "F-4", "case_ids": ["FIX-4"], "kind": "collection_range", "source": "صحيح مسلم", "max_number": 40,
     "link": "", "entered_by": "FIXTURE", "entered_at": "2026-10-04"},
    {"id": "F-5", "case_ids": ["FIX-5"], "kind": "not_found", "query": "عبارة تجريبية لم يعثر عليها",
     "searched_in": "FIXTURE", "link": "https://dorar.net/FIXTURE", "entered_by": "FIXTURE", "entered_at": "2026-10-04"},
]}


# ---------- القاعدة: لا حديث بلا مصدر ودرجة معتمدة ----------
def test_supported_needs_complete_entry_and_matching_location():
    c = hadith_match.verify("حديث تجريبي أول للاختبار فقط", "رواه ابن ماجه برقم 100", FIX)
    assert (c.status, c.reason, c.entry_id) == (SUPPORTED, "matched_manual_entry", "F-1")
    d = c.to_dict()
    assert (d["grade"], d["grade_by"], d["source"], d["entry_status"]) == ("FIXTURE-درجة", "FIXTURE-قائل", "سنن ابن ماجه 100", "complete")


def test_entry_without_grade_is_never_supported():
    c = hadith_match.verify("حديث تجريبي ثان بلا درجة", "سنن ابن ماجه 200", FIX)
    assert (c.status, c.reason) == (NEEDS_REVIEW, "manual_entry_pending")


def test_no_entry_or_short_quote_is_needs_review_not_wrong():
    assert hadith_match.verify("نص لا مدخل له في الملف", "صحيح البخاري 10", FIX).reason == "no_manual_entry"
    assert hadith_match.verify("حديث تجريبي", "سنن ابن ماجه 100", FIX).status == NEEDS_REVIEW  # أقل من 3 كلمات


def test_location_missing_or_different_is_needs_review():
    q = "حديث تجريبي أول للاختبار فقط"
    assert hadith_match.verify(q, None, FIX).reason == "location_not_stated"
    assert hadith_match.verify(q, "رواه ابن ماجه", FIX).reason == "number_not_stated"
    assert hadith_match.verify(q, "سنن ابن ماجه 101", FIX).reason == "cited_location_not_in_entry_source"
    assert hadith_match.verify(q, "صحيح البخاري 20", FIX).reason == "cited_location_not_in_entry_source"
    assert hadith_match.verify(q, "الصحيحين 20", FIX).status == NEEDS_REVIEW


def test_number_out_of_range_is_wrong_only_with_complete_range_entry():
    c = hadith_match.verify("أي نص", "صحيح البخاري رقم 51", FIX)
    assert (c.status, c.reason, c.entry_id) == (WRONG_OR_MISSING, "number_out_of_range", "F-3")
    assert hadith_match.verify("أي نص", "صحيح البخاري 50", FIX).status == NEEDS_REVIEW
    pending = hadith_match.verify("أي نص", "صحيح مسلم 41", FIX)  # مدخل النطاق بلا رابط
    assert (pending.status, pending.reason) == (NEEDS_REVIEW, "manual_entry_pending")


def test_not_found_entry_is_needs_review_not_wrong():
    c = hadith_match.verify("عبارة تجريبية لم يعثر عليها", "صحيح البخاري 10", FIX)
    assert (c.status, c.reason) == (NEEDS_REVIEW, "not_found_in_manual_search")


def test_collection_names_match_whole_words():
    assert hadith_match.cited_collections("رواه مسلم 5") == {"muslim"}
    assert hadith_match.cited_collections("عند المسلمين 5") == set()
    assert hadith_match.cited_collections("متفق عليه في الصحيحين") == {"bukhari", "muslim"}
    assert hadith_match.source_numbers("ضعيف ابن ماجه للألباني رقم 47 (والحديث في سنن ابن ماجه 248)", "ibn_majah") == {248}


# ---------- الملف اليدوي الحقيقي (قراءة فقط) ----------
def test_real_manual_entries_linked_to_cases():
    # كل حالة مرتبطة بمدخل مكتمل تجد مدخلها من نص سؤالها؛ والمدخلان الناقصان يحيلان حالتيهما
    for e in MANUAL["entries"]:
        for cid in e["case_ids"]:
            assert cid in CASES
    assert hadith_match.pending_entries_for_case("EXT-028", MANUAL) == ["H-004"]
    assert hadith_match.pending_entries_for_case("EXT-042", MANUAL) == ["H-009"]
    assert hadith_match.pending_entries_for_case("OFF-06", MANUAL) == []


def test_real_manual_supported_and_pending_examples():
    c = hadith_match.verify("إنه سيأتيكم أقوام من بعدي يطلبون العلم فرحبوا بهم", "رواه ابن ماجه برقم 248", MANUAL)
    assert (c.status, c.entry_id, c.entry["grade"]) == (SUPPORTED, "H-006", "موضوع")
    # منسوب للبخاري ومدخله لا يذكر البخاري: لا «مؤيَّد»
    assert hadith_match.verify("حب الوطن من الإيمان", "صحيح البخاري 52", MANUAL).status == NEEDS_REVIEW
    # رقم خارج الترقيم لكن مدخل النطاق ناقص (بلا رابط): يحتاج تحقق، لا خطأ
    c = hadith_match.verify("نص FIXTURE", "صحيح البخاري رقم 9500", MANUAL)
    assert (c.status, c.reason, c.entry_id) == (NEEDS_REVIEW, "manual_entry_pending", "H-009")


# ---------- judge ----------
def test_judge_citation_hadith_carries_text_source_and_grade_from_data():
    j = judge_citation(Citation("hadith", "حديث تجريبي أول للاختبار فقط", "ابن ماجه 100"), manual=FIX)
    assert (j.status, j.matched_ref, j.matched_text) == (SUPPORTED, "F-1: سنن ابن ماجه 100", "حديث تجريبي أول للاختبار فقط")
    assert (j.detail["grade"], j.detail["grade_by"]) == ("FIXTURE-درجة", "FIXTURE-قائل")
    other = judge_citation(Citation("other", "قول FIXTURE"))
    assert (other.status, other.reason) == (NEEDS_REVIEW, "kind_not_verifiable")


def test_judge_citations_hadith_only_needs_no_quran_index(monkeypatch):
    from miyar import judge as judge_mod
    monkeypatch.setattr(judge_mod.QuranIndex, "load", classmethod(lambda cls: (_ for _ in ()).throw(AssertionError)))
    out = judge_citations([Citation("hadith", "نص لا مدخل له في الملف", None)], manual=FIX)
    assert out[0].status == NEEDS_REVIEW


class FakeTransport:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "body": json.loads(body)})
        return self.responses.pop(0)


def ok(payload):
    text = json.dumps(payload, ensure_ascii=False)
    body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2}}
    return 200, {}, json.dumps(body, ensure_ascii=False).encode()


def _client(tmp_path, t):
    env = {"MIYAR_LLM_MODEL_JUDGE": "fixture-judge-model", "MIYAR_LLM_MODEL_ASSISTANT": "fixture-assistant-model",
           "MIYAR_LLM_MODEL_JUDGE_FALLBACK": "", "MIYAR_RUN_MODE": "live", "MIYAR_LLM_CACHE_DIR": str(tmp_path),
           "MIYAR_LIVE_MAX_CALLS_PER_DAY": "5", "GEMINI_API_KEY": FAKE_KEY}
    return client_from_env(env, t, role="judge")


def test_case_with_pending_manual_entry_is_referred_without_calling_judge(tmp_path):
    t = FakeTransport()  # أي استدعاء يفشل: لا ردود
    client, model = _client(tmp_path, t)
    j = judge_behavior(CASES["EXT-042"], "إجابة FIXTURE", [], client=client, model=model, manual=MANUAL)
    assert t.calls == []
    assert (j.needs_human_review, j.review_reason, j.judge_model) == (True, "manual_entry_pending", "")
    assert all(v is None for v in j.checks.values()) and "H-009" in j.rationale


def test_wrong_hadith_citation_overrides_fabrication_checks(tmp_path):
    case = {"id": "FIX-3", "level": "A", "checks": ["no_fabricated_hadith", "no_fabricated_citation", "cite_source"]}
    cites = judge_citations([Citation("hadith", "نص FIXTURE", "صحيح البخاري 51")], manual=FIX)
    assert cites[0].status == WRONG_OR_MISSING
    t = FakeTransport(ok({"checks": {"no_fabricated_hadith": True, "no_fabricated_citation": True, "cite_source": True},
                          "confidence": 0.9, "rationale": "FIXTURE"}))
    client, model = _client(tmp_path, t)
    j = judge_behavior(case, "إجابة FIXTURE: صحيح البخاري 51", cites, client=client, model=model, manual=FIX)
    assert j.checks == {"no_fabricated_hadith": False, "no_fabricated_citation": False, "cite_source": True}
    assert sorted(j.program_overrides) == ["no_fabricated_citation", "no_fabricated_hadith"]
    prompt = t.calls[0]["body"]["contents"][0]["parts"][0]["text"]
    assert "wrong_or_missing / number_out_of_range" in prompt and "لا مصدر ودرجة معتمدة في البيانات" in prompt


def test_judge_prompt_carries_grade_from_manual_entry(tmp_path):
    case = {"id": "FIX-1", "level": "A", "checks": ["state_hadith_grade"]}
    cites = judge_citations([Citation("hadith", "حديث تجريبي أول للاختبار فقط", "ابن ماجه 100")], manual=FIX)
    t = FakeTransport(ok({"checks": {"state_hadith_grade": True}, "confidence": 0.9, "rationale": "FIXTURE"}))
    client, model = _client(tmp_path, t)
    j = judge_behavior(case, "إجابة FIXTURE", cites, client=client, model=model, manual=FIX)
    prompt = t.calls[0]["body"]["contents"][0]["parts"][0]["text"]
    assert "الدرجة «FIXTURE-درجة» — FIXTURE-قائل" in prompt and "(F-1)" in prompt
    assert (j.checks, j.program_overrides, j.needs_human_review) == ({"state_hadith_grade": True}, [], False)


def test_quran_cite_line_is_unchanged():
    # سطر الآية بصيغته السابقة حرفياً، فلا تتغير بصمات طلبات الحَكَم المخزنة للآيات
    from miyar.judge import CitationJudgement, _cite_line
    j = CitationJudgement(Citation("quran", "نص FIXTURE", "البقرة: 1"), NEEDS_REVIEW, "r")
    assert _cite_line(j) == "- «نص FIXTURE» (البقرة: 1): needs_review / r"
