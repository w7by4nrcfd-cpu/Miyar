"""حارس: تشغيلات التطوير موسومة DEV_RUN ولا تُنشر كنتائج رسمية."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV_DIR = ROOT / "evaluation" / "dev"
DEV_PATH = "evaluation/dev"


def test_every_dev_file_is_labelled_dev_run():
    files = [p for p in DEV_DIR.rglob("*") if p.is_file()]
    assert files, "evaluation/dev/README.md يجب أن يوجد"
    unlabelled = [str(p.relative_to(ROOT)) for p in files if "DEV_RUN" not in p.read_text(encoding="utf-8", errors="ignore")]
    assert unlabelled == [], f"ملفات تطوير بلا وسم DEV_RUN: {unlabelled}"


def test_published_results_do_not_reference_dev_runs():
    text = (ROOT / "web/data/results.json").read_text(encoding="utf-8")
    assert DEV_PATH not in text


def test_no_published_file_references_dev_runs():
    # كل ما في web/ منشور على Cloudflare Pages: صفحات، بيانات، سكربتات، أنماط، README
    leaks = [
        str(p.relative_to(ROOT))
        for p in (ROOT / "web").rglob("*")
        if p.is_file() and DEV_PATH in p.read_text(encoding="utf-8", errors="ignore")
    ]
    assert leaks == [], f"ملفات منشورة تشير إلى {DEV_PATH}: {leaks}"


def test_page_generator_does_not_reference_dev_runs():
    assert DEV_PATH not in (ROOT / "scripts/build_web_pages.py").read_text(encoding="utf-8")
