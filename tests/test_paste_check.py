"""وضع «الصق نصاً وتحقق» (miyar/paste_check.py) وبيانات صفحته — بلا نموذج لغوي ولا شبكة.

⚠️ النصوص الموسومة FIXTURE اصطناعية للاختبار. الآيات فيها منقولة من بيانات Quranpedia نفسها.
"""

import json
from pathlib import Path

import pytest

from miyar import paste_check as pc
from miyar.hadith_manual import entry_status, load_manual
from miyar.quran_match import QuranIndex
from scripts import build_web_pages as b

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


@pytest.fixture(scope="module")
def idx():
    return QuranIndex.load()


def test_parity_fixture_is_in_sync_with_python():
    stored = json.loads(pc.PARITY_FILE.read_text(encoding="utf-8"))
    assert stored == json.loads(json.dumps(pc.parity_fixture(), ensure_ascii=False)), \
        "شغّل: python -m miyar.paste_check --write-parity"


def test_web_data_is_in_sync_with_generator():
    for name, body in b.render_check_data().items():
        assert (WEB / "assets/check" / name).read_text(encoding="utf-8") == body, f"شغّل scripts/build_web_pages.py ({name})"


def test_web_quran_data_carries_attribution_and_all_verses():
    q = json.loads((WEB / "assets/check/quran.json").read_text(encoding="utf-8"))
    src = json.loads((ROOT / "data/quran/source.json").read_text(encoding="utf-8"))
    assert q["source"]["url"] == "https://quranpedia.net" and q["source"]["dump_version"] == src["dump_version"]
    assert len(q["simple"]) == len(q["uthmani"]) == 6236 and sum(q["lens"]) == 6236


def test_web_hadith_data_is_complete_entries_only_and_unchanged():
    h = json.loads((WEB / "assets/check/hadith.json").read_text(encoding="utf-8"))
    manual = {e["id"]: e for e in load_manual()["entries"]}
    assert h["entries"] and all(entry_status(e) == "complete" for e in h["entries"])
    assert all(e == manual[e["id"]] for e in h["entries"])  # منقولة كما هي، بلا تعديل
    assert {e["id"] for e in h["entries"]} == {i for i, e in manual.items() if entry_status(e) == "complete"}


def test_supported_only_with_actual_match_and_every_shown_text_is_in_data(idx):
    """لا «مؤيَّد» بلا مطابقة في البيانات، وكل نص آية معروض منقول من البيانات حرفياً."""
    simple = {v.ref: v.text_simple for v in idx.verses}
    for case in json.loads(pc.PARITY_FILE.read_text(encoding="utf-8"))["cases"]:
        for r in case["result"]:
            if r["kind"] == "quran":
                if r["status"] == "supported":
                    assert r["found_at"], case["text"]
                    if r["cited"]:  # بموضع: التحقق الحرفي في الموضع نفسه
                        s, rest = r["cited"].split(":")
                        a1, _, a2 = rest.partition("-")
                        assert idx.verify(r["quote"], int(s), int(a1), int(a2 or a1)).status == "supported"
                    else:  # بلا موضع: النص موجود حرفياً في المصحف
                        assert [loc.ref for loc in idx.find(r["quote"])] == [v["ref"] for v in r["found_at"]]
                shown = r["found_at"] + ([r["cited_verse"]] if r["cited_verse"] else []) + r["suggestions"]
                for v in shown:
                    s, rest = v["ref"].split(":")
                    a1, _, a2 = rest.partition("-")
                    assert v["text"] == " ".join(simple[f"{s}:{a}"] for a in range(int(a1), int(a2 or a1)+1))
            else:
                if r["status"] == "supported":
                    assert r["entry"] and r["entry"]["kind"] == "found"
                assert r["status"] in ("supported", "needs_review", "wrong_or_missing")


@pytest.mark.parametrize("text,expected", [
    ("FIXTURE: ﴿قل هو الله أحد﴾ (الإخلاص: 1)", ("supported", "exact_match", "112:1")),
    ("FIXTURE: ﴿قل هو الله أحد﴾ (البقرة: 1)", ("wrong_or_missing", "wrong_reference", "2:1")),
    ("FIXTURE: ﴿قل هو الله أحد﴾ (الإخلاص: 9)", ("wrong_or_missing", "invalid_reference", "112:9")),
    ("FIXTURE: ﴿قل هو الله أحد﴾ (112:1)", ("supported", "exact_match", "112:1")),
    ("FIXTURE: ﴿قل هو الله أحد﴾ (١١٢:١)", ("supported", "exact_match", "112:1")),
    ("FIXTURE: «قل هو الله أحد» [سورة الإخلاص، الآية 1]", ("supported", "exact_match", "112:1")),
    ("FIXTURE: ﴿قل هو الله أحد﴾", ("supported", "exact_match_unreferenced", None)),
    ("FIXTURE: ﴿الحمد لله رب الناس﴾", ("wrong_or_missing", "altered_text_unreferenced", None)),
    ("FIXTURE: ﴿نص اصطناعي لا يوجد في المصحف أبداً﴾", ("needs_review", "not_found", None)),
])
def test_quran_rules(idx, text, expected):
    [r] = pc.check_text(text, idx)
    assert (r["status"], r["reason"], r["cited"]) == expected


def test_hadith_only_complete_manual_entries_and_absent_reference_is_needs_review(idx):
    manual = pc.complete_manual()
    h = next(e for e in manual["entries"] if e["kind"] == "found")
    [r] = pc.check_text(f"FIXTURE: قال رسول الله ﷺ: «{h['text']}»", idx, manual)
    assert r["entry_id"] == h["id"] and r["status"] == "needs_review"
    [r] = pc.check_text("FIXTURE: قال رسول الله ﷺ: «نص اصطناعي ليس في الملف اليدوي إطلاقاً» رواه البخاري 1", idx, manual)
    assert (r["status"], r["reason"]) == ("needs_review", "no_manual_entry")  # غياب المرجع ليس «خطأ»
    # مدخل ناقص لا يُستعمل: الملف كاملاً فيه مدخلات pending، والوضع لا يراها
    assert all(entry_status(e) == "complete" for e in manual["entries"])


def test_plain_quotes_without_markers_are_not_extracted(idx):
    assert pc.check_text("FIXTURE: «نص عادي بين علامتي تنصيص» ثم كلام.", idx) == []
    assert pc.check_text("", idx) == []


def test_page_states_its_limits_and_is_secondary():
    page = (WEB / "check.html").read_text(encoding="utf-8")
    for needle in ("وضع ثانوي", "ليست تقييماً لمساعد", "لا فتوى ولا حكم شرعي", "الأحاديث محدودة جداً",
                   "«يحتاج تحقق»", "لا يُرسل النص إلى أي خادم", "Quranpedia.net"):
        assert needle in page, needle
    assert 'src="assets/check.js"' in page
    assert ("check.html", "تحقق من نص") == b.NAV[0]  # أول القائمة (بقرار صاحب المشروع)، والصفحة نفسها تبقى معنونة «وضع ثانوي»


def test_browser_code_has_no_inner_html_or_external_fetch():
    for name in ("check.js", "check-core.js"):
        src = (WEB / "assets" / name).read_text(encoding="utf-8")
        assert ".innerHTML" not in src and "insertAdjacentHTML" not in src
        assert "http://" not in src and "https://" not in src


def test_check_link_is_first_in_nav_on_every_page_and_home_has_try_button():
    pages = sorted(WEB.glob("*.html"))
    assert len(pages) >= 9
    for page in pages:
        html = page.read_text(encoding="utf-8")
        nav = html[html.index('<nav class="main"'):html.index("</nav>")]
        assert nav.index('href="check.html"') < nav.index('href="index.html"'), page.name
        assert nav.count("<li>") == len(b.NAV), page.name
    home = (WEB / "index.html").read_text(encoding="utf-8")
    assert '<a class="btn btn-try" href="check.html">جرّب مِعيار بنفسك</a>' in home
    hero = home[home.index('<header class="hero">'):home.index("</header>")]
    assert hero.index("btn-try") < hero.index("<h1>"), "الزر قبل عنوان الصفحة في أعلاها"
    assert "وضع ثانوي" in home and "ليس تقييماً لمساعد" in home  # الصدق عند باب الدخول نفسه
    check = (WEB / "check.html").read_text(encoding="utf-8")
    assert "وضع ثانوي" in check and "ليست تقييماً لمساعد" in check  # وسم الصفحة وحدودها باقيان


def test_try_button_only_links_and_adds_no_external_resource():
    home = (WEB / "index.html").read_text(encoding="utf-8")
    assert "http://" not in home.replace("http://www.w3.org/2000/svg", "")


# ---------- «لم يُطابَق حرفياً، أقرب مدخل» وإبراز الكلمة المختلفة والتلميح ----------
H1 = "اطلبوا العلم ولو بالصين"  # نص H-001 (مكتمل)


def _hadith(quote, cited=""):
    return pc.check_text(f"قال رسول الله ﷺ: «{quote}» {cited}".strip(), QuranIndex.load())


@pytest.mark.parametrize("quote,q_word,entry_word", [
    ("اطلبوا العلم ولو بالصن", "بالصن", "بالصين"),  # حذف حرف في آخر كلمة
    ("اطبوا العلم ولو بالصين", "اطبوا", "اطلبوا"),  # حذف حرف في أول كلمة
    ("اطلبوا العم ولو بالصين", "العم", "العلم"),  # حذف حرف في وسط كلمة
    ("اطلبوا العلمم ولو بالصين", "العلمم", "العلم"),  # إضافة حرف
    ("اطلبوا العلم ولو بالصيد", "بالصيد", "بالصين"),  # استبدال حرف
    ("العلم ولو بالصن", "بالصن", "بالصين"),  # مقطع من المدخل (ثلاث كلمات) بحرف ناقص: يقارَن بنافذة منه
])
def test_near_match_one_letter_in_one_word(quote, q_word, entry_word):
    [r] = _hadith(quote)
    assert (r["status"], r["reason"]) == ("needs_review", "near_match_not_literal")
    assert (r["near"]["entry_id"], r["near"]["q_word"], r["near"]["entry_word"]) == ("H-001", q_word, entry_word)
    assert r["entry_id"] is None and r["entry"] is None  # لا يُعرض كأنه المدخل المطابَق


@pytest.mark.parametrize("quote", [
    "اطبوا العم ولو بالصين",  # حرفان في كلمتين
    "اطلبوا العلم ولو بالن",  # حذف حرفين في كلمة واحدة
    "ولو بالصين اطلبوا العلم",  # تبديل ترتيب الكلمات
    "العلم بالصن",  # أقل من ثلاث كلمات
    "نص اصطناعي آخر تماماً لا يقارب",
])
def test_near_match_is_conservative(quote):
    [r] = _hadith(quote)
    assert r["near"] is None and r["reason"] in ("no_manual_entry",)


def test_near_match_needs_words_of_three_letters_or_more():
    # «من» كلمة من حرفين: حذف حرف منها لا يُعرض اقتراباً (الكلمات القصيرة ملتبسة)
    [r] = _hadith("حب الوطن م الايمان")
    assert r["near"] is None and r["reason"] == "no_manual_entry"
    [r] = _hadith("حب الوطن من الايمن")  # كلمة طويلة: يُعرض
    assert r["near"]["entry_id"] == "H-002" and r["near"]["entry_word"] == "الايمان"


def test_near_match_never_overrides_a_literal_match_and_is_never_supported():
    [r] = _hadith(H1)  # حرفي
    assert r["near"] is None and r["entry_id"] == "H-001" and r["reason"] != "near_match_not_literal"
    # حتى مع تخريج يطابق مصدر مدخل آخر: الاقتراب لا يرفع إلى «مؤيَّد»
    [r] = _hadith("اطلبوا العلم ولو بالصن", "رواه ابن ماجه 248")
    assert r["status"] == "needs_review" and r["near"]["entry_id"] == "H-001"


def test_near_match_ambiguity_shows_nothing():
    manual = {"entries": [
        {"id": "A", "kind": "found", "text": "اطلبوا العلم ولو بالصين"},
        {"id": "B", "kind": "found", "text": "اطلبوا العلم ولو بالصيد"},
    ]}
    assert pc.near_entry("اطلبوا العلم ولو بالصيف", manual) is None  # يوافق مدخلين
    assert pc.near_entry("اطلبوا العلم ولو بالصيف", {"entries": manual["entries"][:1]})["entry_id"] == "A"
    assert pc.near_entry("اطلبوا العلم ولو بالصن", {"entries": [{"id": "N", "kind": "not_found", "query": H1}]}) is None  # found فقط


def test_near_match_does_not_touch_the_judge_path():
    """الاقتراب لـ paste_check وحدها: hadith_match.verify (ومنه judge) لا يعرفه ولا يتغير حكمه."""
    from miyar import hadith_match

    c = hadith_match.verify("اطلبوا العلم ولو بالصن", None, pc.complete_manual())
    assert (c.status, c.reason) == ("needs_review", "no_manual_entry")
    import inspect

    assert "near_entry" not in inspect.getsource(hadith_match)


def test_one_letter_deletion_fuzz_over_all_entries_never_supported():
    """كل حذف لحرف واحد داخل كل كلمة من كل مدخل found: لا «مؤيَّد» أبداً، والمقترَب منه هو مدخله."""
    manual = pc.complete_manual()
    idx = QuranIndex.load()
    entries = {e["id"]: e for e in manual["entries"] if e["kind"] == "found"}
    near = literal = rest = 0
    for text in pc.near_fuzz_texts(manual):
        [r] = pc.check_text(text, idx, manual)
        assert r["status"] == "needs_review", text  # لا «مؤيَّد» ولا «خاطئ»
        if r["reason"] == "near_match_not_literal":
            near += 1
            assert r["near"]["entry_id"] in entries and r["entry_id"] is None
            e = entries[r["near"]["entry_id"]]
            assert r["near"]["similarity"] >= pc.NEAR_MIN_RATIO and len(r["near"]["q_word"]) >= 3
            assert r["near"]["entry_word"] in pc.normalize(e["text"]).split()
        elif r["entry_id"]:
            literal += 1  # حذف الحرف الأول أو الأخير يبقى ضمن النص حرفياً (احتواء حرفي قائم في hadith_match)
        else:
            rest += 1
            assert r["near"] is None
    assert near > 150 and near + literal + rest > 200


def test_word_diff_and_quran_diff():
    assert pc.word_diff("a b c d".split(), "a x c".split()) == [
        {"q": [1, 2], "w": [1, 2], "q_words": ["b"], "w_words": ["x"]},
        {"q": [3, 4], "w": [3, 3], "q_words": ["d"], "w_words": []}]
    assert pc.word_diff(["a", "b"], ["a", "b"]) == []
    idx = QuranIndex.load()
    [r] = pc.check_text("﴿قل هو الله أح﴾ (الإخلاص: 1)", idx)
    assert r["status"] == "wrong_or_missing" and r["reason"] == "altered_text"
    d = r["diff"]
    assert d["ref"] == "112:1" and d["script"] == "simple" and d["offset"] == 0
    assert d["chunks"] == [{"q": [3, 4], "w": [3, 4], "q_words": ["اح"], "w_words": ["احد"]}]
    [r] = pc.check_text("﴿ذلك من أنباء الغيب نوحيه إليك وما كنت لديهم إذ ألقوا أقلامهم أيهم يكفل مريم﴾", idx)
    assert r["reason"] == "altered_text_unreferenced" and r["diff"]["ref"] == "3:44"
    assert r["diff"]["chunks"][0]["q_words"] == ["القوا"] and r["diff"]["chunks"][0]["w_words"] == ["يلقون"]
    [r] = pc.check_text("﴿قل هو الله أحد﴾ (الإخلاص: 1)", idx)
    assert r["status"] == "supported" and r["diff"] is None  # لا فرق مع المطابق ولا إبراز


def test_hints_for_unextracted_quotes():
    idx = QuranIndex.load()
    lit = pc.hints_for("قال رسول اله: «اطلبوا العلم ولو بالصين»", idx)
    assert [(h["match"], h["entry_id"]) for h in lit] == [("literal", "H-001")] and lit[0]["near"] is None
    near = pc.hints_for("قال رسول اله: «اطلبوا العلم ولو بالصن»", idx)
    assert [(h["match"], h["entry_id"]) for h in near] == [("near", "H-001")] and near[0]["near"]["entry_word"] == "بالصين"
    assert pc.hints_for("قال رسول اله: «نص اصطناعي لا يقارب أي مدخل في الملف اليدوي»", idx) == []
    # النص المستخرج (علامة النسبة سليمة) لا يُلمَّح إليه: يُفحص كحديث
    assert pc.hints_for("قال رسول الله ﷺ: «اطلبوا العلم ولو بالصين»", idx) == []
    # ولا يُنتج التلميح أي حكم: لا status في التلميح
    assert all("status" not in h for h in lit + near)


def test_page_explains_near_match_is_not_a_match():
    page = (WEB / "check.html").read_text(encoding="utf-8")
    assert "القريب ليس مطابقاً" in page and "ولا يصدر معه «مؤيَّد» أبداً" in page
