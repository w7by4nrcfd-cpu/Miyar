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
    assert ("check.html", "تحقق من نص") == b.NAV[-1]  # آخر القائمة: ليست الميزة الرئيسية


def test_browser_code_has_no_inner_html_or_external_fetch():
    for name in ("check.js", "check-core.js"):
        src = (WEB / "assets" / name).read_text(encoding="utf-8")
        assert ".innerHTML" not in src and "insertAdjacentHTML" not in src
        assert "http://" not in src and "https://" not in src
