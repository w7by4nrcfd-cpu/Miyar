"""حارس: بيانات الاختبار المصطنعة (FIXTURE) لا تتسرب إلى البيانات أو الموقع المنشور."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER = "FIXTURE"
PUBLISHED = [ROOT / "data", ROOT / "web", ROOT / "testsets", ROOT / "evaluation"]


def test_no_fixture_marker_in_published_or_data_files():
    leaks = []
    for base in PUBLISHED:
        for p in base.rglob("*"):
            if p.is_file() and p.suffix in {".json", ".jsonl", ".html", ".js", ".md", ".txt", ".xml", ".csv"}:
                if MARKER in p.read_text(encoding="utf-8", errors="ignore"):
                    leaks.append(str(p.relative_to(ROOT)))
    assert leaks == [], f"بيانات FIXTURE في ملفات منشورة: {leaks}"


def test_synthetic_test_data_is_labelled_fixture():
    # كل ملف اختبار فيه بيانات مصطنعة يحمل الوسم صراحةً
    for rel in ("tests/web/results-core.test.mjs", "tests/test_hadith_data_loader.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "⚠️ FIXTURE" in text and "ليس" in text, rel
