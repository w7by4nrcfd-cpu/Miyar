"""مسودتا الفيديو والعرض (docs/submission/): بلا أي رقم نتائج حتى يُنشر تشغيل رسمي، وكل رقم لاحق من evaluation/official/."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRAFTS = [ROOT / "docs/submission/VIDEO_SCRIPT.md", ROOT / "docs/submission/DECK_OUTLINE.md"]
# أنماط رقم نتائج: نسبة مئوية، أو N بعدد، أو درجة أو دقة أو استدعاء يليها عدد، أو «X من N» بأعداد
RESULT_NUMBER = re.compile(r"\d+(?:\.\d+)?\s*[%٪]|N\s*=\s*\d|(?:درجة|الدقة|الاستدعاء|score)\D{0,12}\d|\b\d+\s+من\s+\d+\s+حالة")


def test_drafts_exist_and_have_no_result_numbers():
    for p in DRAFTS:
        text = p.read_text(encoding="utf-8")
        assert not RESULT_NUMBER.findall(text), f"{p.name}: رقم نتائج مكتوب"
        assert "[" in text and "evaluation/official/" in text  # خانات تُملأ من السجل الرسمي


def test_drafts_state_no_specialist_review_and_placeholders():
    video = DRAFTS[0].read_text(encoding="utf-8")
    deck = DRAFTS[1].read_text(encoding="utf-8")
    assert "لم تُجرَ مراجعة شرعية متخصصة" in video and "لم تُجرَ مراجعة شرعية متخصصة" in deck
    assert "≤ 2:00" in video
    for item in ("المشكلة", "الحل", "آلية العمل", "القيمة", "التقنيات", "خطة الاستمرار", "حالات التعارض", "صور من المنتج", "الفريق"):
        assert item in deck, item
