import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
PAGES = ["index.html", "levels.html", "sources.html", "transparency.html", "status.html", "results.html"]


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


def _page(name):
    return (WEB / name).read_text(encoding="utf-8")


def _text(name):
    """نص الصفحة المرئي تقريباً (بلا وسوم)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _page(name)))


def test_old_about_page_removed_and_nav_complete():
    assert not (WEB / "about.html").exists()
    for page in PAGES:
        html = _page(page)
        assert "about.html" not in html
        for other in PAGES:
            assert f'href="{other}"' in html, (page, other)
        assert html.count('aria-current="page"') == 1


def test_home_defines_miyar_in_one_sentence_and_track_four():
    t = _text("index.html")
    assert "يختبر المساعد الذكي نفسه ويحكم على إجاباته" in t
    assert "ولا يجيب هو" in t
    assert "المسار الرابع: أدوات المعرفة والتحقق" in t


def test_levels_page_has_four_levels_with_behaviour():
    t = _text("levels.html")
    for code, short in (("A", "إجابة موثقة"), ("B", "شرح مع مرجع"), ("C", "بيان الخلاف أو إحالة"), ("D", "لا فتوى")):
        assert re.search(rf"\b{code}\b {short}", t), code
    for behaviour in ("إجابة مباشرة موثقة بالمصدر", "لا حكم مستقل؛ معلومة عامة + إحالة لجهة مؤهلة"):
        assert behaviour in t


def test_sources_page_nine_domains_only_quran_and_hadith_used():
    html = _page("sources.html")
    rows = re.findall(r'<tr><th scope="row">(.*?)</th>.*?</tr>', html)
    assert len(rows) == 9
    used = re.findall(r'<tr><th scope="row">([^<]*)</th>(?:(?!</tr>).)*class="yes"', html)
    assert used == ["القرآن الكريم", "الحديث"]
    assert html.count('class="no"') == 7
    assert "Quranpedia" in html and "ملف يدوي" in html


def test_transparency_page_disclosures():
    t = _text("transparency.html")
    for needle in ("مدعومة بالذكاء الاصطناعي", "ليس عالماً ولا مفتياً", "لا تُصدر فتوى", "لا نجمع بياناتك الشخصية",
                   "Claude Code", "Gemini", "لا يستدعيه الموقع", "استُخدم فعلاً"):
        assert needle in t, needle


def test_status_page_is_honest():
    t = _text("status.html")
    assert "لا توجد نتائج تقييم رسمية بعد" in t
    assert "المراجعة الشرعية لم تكتمل" in t
    assert "ما تمّ فعلاً" in t and "ما لم يتم بعد" in t


def test_site_free_of_external_hadith_set_and_secrets():
    banned = ("fawazahmed", "hadith-api", "sahihayn", "unapproved", "ابن ماجه", "مجموعة أحاديث خارجية", "Tanzil")
    for p in WEB.rglob("*"):
        if p.is_file() and p.suffix in (".html", ".js", ".css", ".json", ".md", ""):
            s = p.read_text(encoding="utf-8", errors="ignore")
            for b in banned:
                assert b not in s, (p.name, b)
            assert not re.search(r"AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9]{20,}|API_KEY\s*=", s), p.name


def test_cloudflare_headers_file():
    h = (WEB / "_headers").read_text(encoding="utf-8")
    assert "Content-Security-Policy: default-src 'self'" in h
    assert "/data/*" in h and "no-store" in h


@pytest.mark.skipif(shutil.which("node") is None, reason="node غير متوفر")
def test_results_core_js():
    files = sorted(str(p) for p in (ROOT / "tests/web").glob("*.test.mjs"))
    r = subprocess.run(["node", "--test", *files], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
