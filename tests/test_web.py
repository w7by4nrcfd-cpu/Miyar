import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
PAGES = ["index.html", "levels.html", "sources.html", "cases.html", "status.html", "transparency.html", "results.html"]


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


def _registry_rows():
    html = _page("sources.html")
    table = html.split('class="stack registry"', 1)[1].split("</table>", 1)[0]
    return re.findall(r'<tr><th scope="row">([^<]*)</th>(.*?)</tr>', table, re.S)


def test_sources_registry_nine_domains_only_quran_and_hadith_used():
    rows = _registry_rows()
    assert len(rows) == 9
    used = [name for name, body in rows if "b-todo" not in body.split('data-label="الحالة">', 1)[1].split("</td>", 1)[0]]
    assert used == ["القرآن الكريم", "الحديث"]
    for name, body in rows:
        # كل صف: رابط رسمي للمرجع ورابط إثبات في المستودع، والأعمدة السبعة
        for label in ("المرجع المعتمد في الحزمة", "الحالة", "كيف استُخدم", "كيف يُتحقق منه", "الترخيص والحقوق", "القيود والحدود", "الإثبات في المستودع"):
            assert f'data-label="{label}"' in body, (name, label)
        assert 'href="https://' in body and "github.com/w7by4nrcfd-cpu/Miyar/blob/main/" in body, name


@pytest.mark.parametrize("page", PAGES)
def test_repo_links_point_to_existing_files(page):
    for path in re.findall(r'github\.com/w7by4nrcfd-cpu/Miyar/blob/main/([^"]+)"', _page(page)):
        assert (ROOT / path).exists(), path


def test_sources_used_claims_backed_by_repo():
    mod = _load_builder()
    f = mod.facts()
    for d in mod.domains(f):
        if d["used"]:
            assert all((ROOT / p).exists() for p, _ in d["proof"]), d["name"]


def test_sources_page_has_judgements_and_attribution():
    t = _text("sources.html")
    mod = _load_builder()
    cats = mod.judgement_categories()
    assert len(cats) == 6
    for name, _ in cats:
        assert name in t
    for needle in ("تحديد النص المنسوب", "المطابقة مع المصدر", "متى يمتنع النظام أو يُحيل"):
        assert needle in t


def test_cases_page_lists_every_case_from_repo():
    html = _page("cases.html")
    cases = [c for f in ("official_v0.json", "extended_v1.json")
             for c in json.loads((ROOT / "testsets" / f).read_text(encoding="utf-8"))["cases"]]
    body = html.split('id="cases"', 1)[1]
    assert len(re.findall(r"<tr data-level=", body)) == len(cases)
    for c in cases:
        assert f'<span class="mono">{c["id"]}</span>' in body
    # لا نص سؤال (بعض الأسئلة فيها آيات منقولة بخطأ أو أحاديث لا تصح عمداً)، ولا حكم ولا نتيجة
    for c in cases:
        for q in re.findall(r"«([^»]{8,})»", c["prompt"]):
            if q not in c["expected_behavior"]:
                assert q not in html, (c["id"], q)
    assert 'id="q"' in html and 'id="lv"' in html and 'id="ty"' in html
    assert 'src="assets/cases.js"' in html


def test_status_items_are_computed_from_repo():
    mod = _load_builder()
    f = mod.facts()
    p0, p1 = mod.status_items(f)
    # قبل 4 أكتوبر: نواة التقييم كلها لم تُبنَ
    assert not any(done for _, done, _ in p1)
    assert all(done for _, done, _ in p0)
    assert f["state"]["runner"] == f["state"]["judge"] == f["state"]["scoring"] == "todo"
    assert f["state"]["quran_match"] == "built"


def test_home_flow_svg_marks_built_and_unbuilt():
    html = _page("index.html")
    svg = html.split('aria-labelledby="flow-title flow-desc"', 1)[1].split("</svg>", 1)[0]
    for step in ("سؤال موسوم", "إجابة المساعد", "استخراج الاستشهاد", "مطابقة المصدر", "حكم", "درجة وقرار"):
        assert step in svg
    assert "لم يُبنَ بعد" in svg and "جاهز" in svg
    for card in ("ماذا نختبر", "لماذا", "ما الذي يميّزنا"):
        assert card in _text("index.html")


def test_transparency_page_disclosures():
    t = _text("transparency.html")
    for needle in ("مدعومة بالذكاء الاصطناعي", "ليس عالماً ولا مفتياً", "لا تُصدر فتوى", "لا نجمع بياناتك الشخصية",
                   "Claude Code", "Gemini", "لا يستدعيه الموقع", "استُخدم فعلاً"):
        assert needle in t, needle


@pytest.mark.parametrize("page", PAGES)
def test_mode_bar_says_display_only_not_official(page):
    t = _text(page)
    assert "للعرض فقط: لا توجد نتائج تقييم رسمية؛ التقييم الرسمي يبدأ 4 أكتوبر 2026." in t


def test_results_page_says_demo_not_official():
    t = _text("results.html")
    for needle in ("للعرض فقط: هذه ليست نتائج تقييم رسمية", "فارغ حالياً", "التقييم الرسمي يبدأ 4 أكتوبر 2026"):
        assert needle in t, needle
    js = (WEB / "assets/results.js").read_text(encoding="utf-8")
    assert "لم يُشغَّل أي تقييم رسمي بعد" in js and "التقييم الرسمي يبدأ 4 أكتوبر 2026" in js


def test_status_page_is_honest():
    t = _text("status.html")
    assert "لا توجد نتائج تقييم رسمية بعد" in t
    assert "لم تُجرَ مراجعة شرعية متخصصة" in t and "تحقق مصادر" in t and "Quranpedia" in t
    assert "قبل أيام التحدي" in t and "أيام التحدي: 4–6 أكتوبر 2026" in t
    assert "<progress" in _page("status.html")


def test_site_free_of_external_hadith_set_and_secrets():
    # «ابن ماجه» لم يعد محظوراً: صار موضع حديث في السلوك المتوقع لـEXT-030 من بحث صاحب المشروع في الدرر (لا من المجموعة الخارجية)؛
    # والمجموعة الخارجية نفسها محظورة بأسماء ملفاتها ومستودعها هنا وفي tests/test_hadith_manual.py
    banned = ("fawazahmed", "hadith-api", "sahihayn", "weak_fabricated", "unapproved", "مجموعة أحاديث خارجية", "Tanzil")
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


@pytest.mark.parametrize("page", ["status.html", "levels.html", "sources.html", "cases.html"])
def test_no_specialist_review_is_stated_honestly(page):
    """ما دامت لا توجد مراجعة specialist مسجّلة: تقول الصفحة صراحة إنها لم تُجرَ، ولا تعرض «معتمدة شرعياً» شارةً لأي حالة."""
    f = _load_builder().facts()
    if f["review"]["approved"]["specialist"] == 0:
        assert "لم تُجرَ مراجعة شرعية متخصصة" in _text(page)
        assert "معتمدة شرعياً</span>" not in _page(page)
