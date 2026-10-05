"""صفحة تفصيل الحالة (S2): بيانات web/data/testcases.json من testsets/ والبيانات المعتمدة وحدها، بلا نتائج.

لا نموذج ولا شبكة. النتائج تأتي لاحقاً من web/data/cases/<id>.json الذي يكتبه scripts/publish_results.py وحده.
"""

import importlib.util
import json
from pathlib import Path

from miyar.hadith_manual import entry_status, load_manual
from miyar.quran_match import QuranIndex

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DATA = json.loads((WEB / "data/testcases.json").read_text(encoding="utf-8"))
CASES = {c["id"]: c for c in DATA["cases"]}
TESTSET = {c["id"]: c for f in ("official_v0.json", "extended_v1.json")
           for c in json.loads((ROOT / "testsets" / f).read_text(encoding="utf-8"))["cases"]}


def _builder():
    spec = importlib.util.spec_from_file_location("build_web_pages", ROOT / "scripts/build_web_pages.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_case_data_in_sync_with_generator():
    assert (WEB / "data/testcases.json").read_text(encoding="utf-8") == _builder().render_case_data(), \
        "شغّل scripts/build_web_pages.py"


def test_every_case_present_with_expected_behavior_and_no_results():
    assert set(CASES) == set(TESTSET)
    for cid, c in CASES.items():
        assert c["expected_behavior"] == TESTSET[cid]["expected_behavior"]
        assert c["prompt"] in (None, TESTSET[cid]["prompt"])
        assert not {"judgement", "answer", "score", "runs"} & set(c)  # لا نتيجة في بيانات الحالة


def test_traps_flagged_and_misquote_shows_correct_text_from_data():
    idx = QuranIndex.load()
    c = CASES["OFF-11"]
    assert c["trap"] and DATA["trap_warning"]
    (ref,) = c["references"]
    assert ref["text"] == idx.verse(20, 114).text_simple and ref["ref"].startswith("طه 20:114")
    assert not CASES["OFF-05"]["trap"] and CASES["OFF-05"]["references"] == []


def test_every_displayed_religious_text_exists_in_data():
    """BUILD_SPEC S2.3: لا نص شرعي يعرضه مِعيار إلا من data/ (القرآن) أو الملف اليدوي (الحديث)."""
    idx = QuranIndex.load()
    all_quran = " ".join(v.text_simple for s in range(1, 115) for v in idx.verses_range(s, 1, idx.sura_length(s)))
    manual = {e["id"]: e for e in load_manual()["entries"]}
    for c in CASES.values():
        for r in c["references"]:
            if r["kind"] == "quran":
                assert r["text"] in all_quran, c["id"]
            elif not r["pending"] and r["entry_kind"] == "found":
                assert (r["text"], r["grade"], r["grade_by"]) == (manual[r["ref"]]["text"], manual[r["ref"]]["grade"],
                                                                   manual[r["ref"]]["grade_by"])


def test_pending_manual_entries_show_no_text_or_grade():
    manual = {e["id"]: e for e in load_manual()["entries"]}
    for c in CASES.values():
        for r in c["references"]:
            if r["kind"] == "hadith":
                assert r["pending"] == (entry_status(manual[r["ref"]]) != "complete")
                if r["pending"]:
                    assert "text" not in r and "grade" not in r


def test_masked_prompts_follow_manual_entries():
    for cid in ("EXT-029", "EXT-030", "EXT-031", "EXT-032"):
        c = CASES[cid]
        assert c["prompt_masked"] == (c["prompt"] is None)


def test_case_page_shell_and_links():
    html = (WEB / "case.html").read_text(encoding="utf-8")
    assert 'src="assets/case.js"' in html and 'id="case"' in html
    assert '<a href="cases.html" aria-current="page">' in html  # القائمة تُبرز «حالات الاختبار»
    cases_html = (WEB / "cases.html").read_text(encoding="utf-8")
    assert all(f'href="case.html?id={cid}"' in cases_html for cid in CASES)
    js = (WEB / "assets/case.js").read_text(encoding="utf-8") + (WEB / "assets/case-core.js").read_text(encoding="utf-8")
    for needle in ("ليست ضمن الحالات الاثنتي عشرة المُشغَّلة رسمياً", "إجابة المساعد المُختبَر — ليست من مِعيار", "أُحيلت إلى مراجعة بشرية", "ثقة الحَكَم", "سبب الحكم"):
        assert needle in js, needle
    assert ".innerHTML" not in js and "insertAdjacentHTML" not in js  # نص فقط، لا HTML من البيانات
