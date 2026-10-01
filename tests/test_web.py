import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
PAGES = ["index.html", "results.html", "about.html"]


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_web_pages", ROOT / "scripts/build_web_pages.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("page", PAGES)
def test_page_is_arabic_rtl_mobile(page):
    html = (WEB / page).read_text(encoding="utf-8")
    assert '<html lang="ar" dir="rtl">' in html
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in html
    assert 'href="assets/style.css"' in html


@pytest.mark.parametrize("page", PAGES)
def test_mode_bar_cached_on_live_disabled(page):
    html = (WEB / page).read_text(encoding="utf-8")
    assert "نتائج محفوظة" in html and 'class="mode on"' in html
    assert re.search(r'<button[^>]*aria-disabled="true"[^>]*disabled[^>]*>[^<]*تشغيل حي', html)


@pytest.mark.parametrize("page", PAGES)
def test_no_external_resources_or_inline_scripts(page):
    html = (WEB / page).read_text(encoding="utf-8")
    # لا سكربتات أو أنماط أو خطوط خارجية (الخصوصية + CSP: default-src 'self')
    assert not re.search(r'<(script|link|img|iframe)[^>]+(src|href)="(https?:)?//', html)
    # لا سكربت مضمّن (CSP تمنعه)
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html)
    assert "style=" not in html


def test_pages_in_sync_with_generator():
    rendered = _load_builder().render()
    for name in PAGES:
        assert (WEB / name).read_text(encoding="utf-8") == rendered[name], f"{name}: شغّل scripts/build_web_pages.py"


def test_published_results_are_empty():
    data = json.loads((WEB / "data/results.json").read_text(encoding="utf-8"))
    assert data == {"schema_version": 1, "runs": []}


def test_about_page_disclosures():
    html = (WEB / "about.html").read_text(encoding="utf-8")
    for needle in (
        "لا تُصدر فتاوى",
        "لا يُصدر فتوى",
        "لم تُراجَع بعد",
        "Claude Code",
        "Gemini",
        "Quranpedia.net",
        "سلسلة الترخيص غير واضحة",
        "لا يستدعي حالياً أي نموذج لغوي",
        "لم يُستدعَ بعد",
        "استُخدم فعلاً",
    ):
        assert needle in html, needle


def test_cloudflare_headers_file():
    h = (WEB / "_headers").read_text(encoding="utf-8")
    assert "Content-Security-Policy: default-src 'self'" in h
    assert "/data/*" in h and "no-store" in h


@pytest.mark.skipif(shutil.which("node") is None, reason="node غير متوفر")
def test_results_core_js():
    files = sorted(str(p) for p in (ROOT / "tests/web").glob("*.test.mjs"))
    r = subprocess.run(["node", "--test", *files], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
