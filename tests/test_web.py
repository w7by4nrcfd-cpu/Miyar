import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
PAGES = ["index.html", "levels.html", "sources.html", "cases.html", "status.html", "transparency.html", "results.html", "project.html"]


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


@pytest.mark.parametrize("page", [*PAGES, "case.html", "check.html", "replay.html"])
def test_status_card_only_on_status_page_and_no_live_button(page):
    """البطاقة الجانبية (وضع العرض «نتائج محفوظة» والأساس ونواة التقييم مع الشريطين) في صفحة الحالة وحدها؛
    ولا زر «تشغيل حي» ولا عبارة «معطّل حالياً» في أي صفحة."""
    html = (WEB / page).read_text(encoding="utf-8")
    if page == "status.html":
        assert 'class="status-card"' in html and "نتائج محفوظة" in html and 'class="mode on"' in html
        assert html.count("<progress") >= 2
    else:
        assert 'class="status-card"' not in html and 'class="sc-progress"' not in html
    assert "تشغيل حي — معطّل" not in html and "معطّل حالياً" not in html
    assert not re.search(r'<button[^>]*class="mode"', html)


def test_transparency_states_live_mode_is_cli_only():
    t = _text("transparency.html")
    assert ("وضع التشغيل الحي موجود في المحرك عبر سطر الأوامر وغير متاح من الموقع؛ "
            "الموقع يعرض نتائج محفوظة من تشغيلات رسمية.") in t


def test_redteam_item_is_deferred_not_counted_and_cites_verified_cases():
    """Red Teaming: «مؤجَّل خارج نطاق التسليم: لا وحدة تشغيل مستقلة»، لا يُحتسب مكتملاً، وأعداد الحالات العدائية محسوبة من testsets/."""
    status = _text("status.html")
    assert "مؤجَّل خارج نطاق التسليم: لا وحدة تشغيل مستقلة." in status
    # اسم الملف ودليله في طبقة «التفاصيل التقنية» المطوية لا في نص البند الظاهر
    tech = _page("status.html")
    tech = tech[tech.index('<details class="tech">', tech.index("وحدة Red Teaming") - 4000):]
    assert "miyar/redteam.py" in tech
    visible = re.search(r'<li><span class="badge[^>]*>.*?مؤجَّل.*?وحدة Red Teaming.*?</li>', _page("status.html"), re.S).group(0)
    assert "miyar/redteam.py" not in visible
    f = _load_builder().facts()
    _, p1 = _load_builder().status_items(f)
    item = next(i for i in p1 if i[2] == "miyar/redteam.py")
    assert item[1] is False
    assert f"{sum(1 for i in p1 if i[1])} من {len(p1)}" in status
    # الأعداد من الملفات مباشرة (لا من المولّد)
    rt = [c for name in ("official_v0", "extended_v1") for c in json.loads((ROOT / f"testsets/{name}.json").read_text(encoding="utf-8"))["cases"]
          if c.get("red_team") is True]
    in_ctx = sum(1 for c in rt if c.get("injected_context"))
    off = json.loads((ROOT / "testsets/official_v0.json").read_text(encoding="utf-8"))["cases"]
    assert not any(c.get("red_team") for c in off)
    assert f"{len(rt)} حالات بصيغة حقن أوامر ({rt[0]['id']} إلى {rt[-1]['id']}: {len(rt) - in_ctx} في السؤال و{in_ctx} في نص مرفق مدسوس)" in status
    assert "لم تدخل التشغيلات الرسمية (كلها على official_v0)" in status


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


def _published_runs() -> list:
    return json.loads((WEB / "data/results.json").read_text(encoding="utf-8"))["runs"]


def test_published_results_are_empty_or_backed_by_records():
    """فارغ إن لم تُنشر سجلات رسمية، وإلا فلكل تشغيل منشور سجل موجود في evaluation/official/ (والمزامنة التفصيلية في test_publish)."""
    data = json.loads((WEB / "data/results.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    for run in data["runs"]:
        rec = run["evaluation_record"]
        assert re.fullmatch(r"evaluation/official/[^/]+\.json", rec), rec
        assert (ROOT / rec).is_file(), rec


def _page(name):
    return (WEB / name).read_text(encoding="utf-8")


def _text(name):
    """نص الصفحة المرئي تقريباً (بلا وسوم)."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _page(name)))


def test_old_about_page_removed_and_nav_has_four_items():
    """القائمة أربعة عناصر: جرّب والنتائج والحالات وعن المشروع؛ و«عن المشروع» تضم المستويات والمصادر والشفافية والحالة."""
    assert not (WEB / "about.html").exists() and (WEB / "project.html").is_file()
    nav_hrefs = ["check.html", "results.html", "cases.html", "project.html"]
    about = {"levels.html", "sources.html", "transparency.html", "status.html", "project.html"}
    for page in [*PAGES, "case.html", "check.html", "replay.html"]:
        html = _page(page)
        assert "about.html" not in html
        nav = html[html.index('<nav class="main"'):html.index("</nav>")]
        assert [h for h in re.findall(r'href="([^"]+)"', nav)] == nav_hrefs, page
        current = re.findall(r'href="([^"]+)" aria-current="page"', nav)
        expected = {"project.html": "project.html", "case.html": "cases.html", "index.html": None}
        want = expected.get(page, page if page in nav_hrefs else ("project.html" if page in about else None))
        assert current == ([want] if want else []), (page, current)
    for page in about - {"project.html"}:
        assert _page(page).count('aria-current="location"') == 1, page  # الشريط الفرعي
    for page in about:  # صفحة المشروع تصل الصفحات الأربع
        for target in about - {"project.html"}:
            if page == "project.html":
                assert f'href="{target}"' in _page(page), target


def test_home_defines_miyar_in_one_sentence_and_track_four():
    t = _text("index.html")
    assert "يختبر المساعد الذكي نفسه" in t and "لا يولّد آية ولا حديثاً ولا حكماً" in t
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


def test_sources_registry_shows_only_used_sources_and_states_scope():
    """السجل يعرض المستخدم فقط (القرآن والحديث)؛ والمجالات الأخرى خارج النطاق وتفاصيلها في SOURCES.md. المولّد يحتفظ بالتسعة داخلياً."""
    rows = _registry_rows()
    assert [name for name, _ in rows] == ["القرآن الكريم", "الحديث"]
    assert len(_load_builder().domains(_load_builder().facts())) == 9  # العدّاد في صفحة الحالة يبقى محسوباً من التسعة
    page = re.sub(r"\s+\)", ")", _text("sources.html"))
    for gone in ("الموضوعات الدعوية", "dorar.net/tafseer", "dorar.net/aqeeda", "dorar.net/feqhia", "dorar.net/history", "dawa.center",
                 "islamic-content.com", "الترجمة والمصطلحات", "لم يُستخدم بعد"):
        assert gone not in _page("sources.html").split("أصناف الحكم")[0], gone
    assert ("المرجعية المعتمدة أوسع مما نستخدمه؛ مِعيار يغطي القرآن والحديث فقط، وباقي مجالاتها خارج النطاق الحالي (التفاصيل في SOURCES.md).") in page
    for name, body in rows:
        # كل صف: رابط رسمي للمرجع ورابط إثبات في المستودع، والأعمدة السبعة
        for label in ("المرجع المعتمد في الحزمة", "الحالة", "كيف استُخدم", "كيف يُتحقق منه", "الترخيص والحقوق", "القيود والحدود", "الإثبات في المستودع"):
            assert f'data-label="{label}"' in body, (name, label)
        assert 'href="https://' in body and "github.com/w7by4nrcfd-cpu/Miyar/blob/main/" in body, name


def test_transparency_ai_table_matches_reality():
    t = _text("transparency.html")
    assert "gemini-3.5-flash-lite" in t and "المساعد المُختبَر" in t
    assert "openai/gpt-oss-120b" in t and "استخراج الإسنادات وحكم السلوك" in t and "بلا نموذج احتياط" in t
    assert "Anthropic" not in t  # تبقى في README لا في الموقع
    assert "مخطط استخدامه" not in t and "اختبارات اتصال تطويرية فقط" not in t


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
        assert f'<a class="mono case-link" href="case.html?id={c["id"]}">{c["id"]}</a>' in body  # رابط صفحة التفصيل
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
    assert all(item[1] for item in p0)
    # كل بند في أيام التحدي يطابق حالة وحدته في الكود (هيكل NotImplementedError = لم يُنفَّذ)
    by_evidence = {item[2]: item[1] for item in p1 if item[2] != "evaluation/official/"}
    assert by_evidence["miyar/runner.py"] == (f["state"]["runner"] == "built")
    assert by_evidence["miyar/judge.py"] == (f["state"]["judge"] == "built")
    assert by_evidence["miyar/scoring.py"] == (f["state"]["scoring"] == "built")
    assert f["state"]["quran_match"] == "built"
    # «المساعدان المرجعيان» لا يكتمل بأحدهما
    assert f["state"]["assistants"] == ("built" if (ROOT / "miyar/assistants/rag.py").exists() else "todo")
    # الاستخراج لا «يكتمل» بالآيات وحدها: جزئي حتى يشمل الأحاديث
    ex = (ROOT / "miyar/extract.py").read_text(encoding="utf-8") if (ROOT / "miyar/extract.py").exists() else ""
    if "KIND_HADITH" not in ex:
        assert f["state"]["extract"] != "built" and by_evidence["miyar/extract.py"] is False
    # والحكم لا «يكتمل» قبل الأحاديث وأصناف الحكم الستة
    jd = (ROOT / "miyar/judge.py").read_text(encoding="utf-8")
    if "def classify_error" not in jd or "hadith_matching_not_built" in jd:
        assert f["state"]["judge"] != "built" and by_evidence["miyar/judge.py"] is False


def test_accuracy_item_is_partial_not_counted_complete():
    """الدليل المكتوب (evaluation/official/) لا يشمل قياس اتفاق الحَكَم مع الوسوم البشرية: البند «جاهز جزئياً» ولا يُحتسب مكتملاً."""
    mod = _load_builder()
    f = mod.facts()
    _, p1 = mod.status_items(f)
    text, done, evidence, partial = next(i for i in p1 if i[2] == "evaluation/official/")
    assert done is False
    assert partial is (f["official_runs"] > 0)
    status_text = _text("status.html")
    if f["official_runs"]:
        assert f"التشغيل الرسمي مسجّل ({mod._rounds(f['official_runs'])} مكتملة)" in text
        assert "قياس اتفاق أحكام الحَكَم مع الوسوم البشرية لم يُنفَّذ" in text
        assert "المراجعة البشرية: حالة واحدة من 12 (تحقق مصادر) و0 مراجعة شرعية متخصصة" in text
        assert text in status_text and "جاهز جزئياً" in _page("status.html")
    assert f"{sum(1 for i in p1 if i[1])} من {len(p1)}" in status_text


def test_home_how_it_works_and_results_glance_from_data():
    """الرئيسية: ثلاث بطاقات «كيف يعمل»، ولمحة نتائج من web/data/results.json (لا أرقام مكتوبة يدوياً)."""
    html = _page("index.html")
    assert html.count('class="card how"') == 3 and html.count('class="how-icon"') == 3
    runs = _published_runs()
    t = _text("index.html")
    if runs:
        assert f"الجولات الرسمية {len(runs)}" in t
        gate = json.loads((WEB / "data/results.json").read_text(encoding="utf-8")).get("gate")
        if gate:
            assert ("نشر rag" if gate["allow"] else "منع rag") in t and "حساس لاختيار الجولة المرجعية" in t

def test_transparency_page_disclosures():
    t = _text("transparency.html")
    for needle in ("مدعومة بالذكاء الاصطناعي", "ليس عالماً ولا مفتياً", "لا تُصدر فتوى", "لا نجمع بياناتك الشخصية",
                   "Claude Code", "Gemini", "لا يستدعيه الموقع", "استُخدم فعلاً"):
        assert needle in t, needle


@pytest.mark.parametrize("page", ["status.html"])  # البطاقة الجانبية في صفحة الحالة وحدها
def test_mode_bar_says_display_only_not_official(page):
    t = _text(page)
    if _published_runs():
        assert "نتائج محفوظة من تشغيلات رسمية مسجّلة في المستودع، كل رقم مع N." in t
        assert "لا توجد نتائج تقييم رسمية بعد" not in t
    else:
        assert "للعرض فقط: لا توجد نتائج تقييم رسمية بعد؛ التشغيل الرسمي في أيام التحدي 4–6 أكتوبر 2026." in t


def test_results_page_says_demo_not_official():
    t = _text("results.html")
    if _published_runs():
        # بطاقة واحدة فقط (يصنعها results.js بعدد الجولات)، لا بطاقة ثابتة مكررة قبلها
        assert "نتائج من تشغيلات رسمية مسجّلة" not in t
        assert "فارغ حالياً" not in t
    else:
        for needle in ("للعرض فقط: هذه ليست نتائج تقييم رسمية", "فارغ حالياً", "التقييم الرسمي يبدأ 4 أكتوبر 2026"):
            assert needle in t, needle
    js = (WEB / "assets/results.js").read_text(encoding="utf-8")
    assert "officialRunsHeadline" in js and 'id: "results-notice"' in js
    assert "لم يُشغَّل أي تقييم رسمي بعد" in js and "التقييم الرسمي يبدأ 4 أكتوبر 2026" in js


def test_status_page_is_honest():
    t = _text("status.html")
    runs = _published_runs()
    if runs:
        assert f"سجلات التشغيل الرسمية: {len(runs)}." in t
        assert "لا توجد نتائج تقييم رسمية بعد" not in t
    else:
        assert "لا توجد نتائج تقييم رسمية بعد" in t
    assert SPECIALIST_NOTE in t and "تحقق مصادر" in t and "Quranpedia" in t
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
    # يشغّل كل ملفات tests/web (منها اختبارات المتصفح)؛ فرسالة الفشل تسمّي الاختبارات الفاشلة وأخطاءها،
    # لا ذيل المخرجات وحده (الذيل قد يكون اسم اختبار ناجح مثل «run_id مكرر» فيضلّل)
    lines = r.stdout.splitlines()
    failed = []
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("not ok"):
            failed.append(ln.strip())
        elif ln.strip().startswith("error:") and any("not ok" in x for x in lines[max(0, i - 6):i]):
            failed.extend(x.strip() for x in lines[i:i + 3])  # السطر الأول من نص الخطأ متعدد الأسطر
    assert r.returncode == 0, "\n".join(failed[:40]) + "\n--- stderr ---\n" + r.stderr[-1500:]


SPECIALIST_NOTE = ("المراجعة الشرعية: مراجعة واحدة لحالة واحدة من 12 (OFF-06) أجراها خريج شريعة هو قريب لصاحب المشروع؛ "
                   "لا مراجعة من لجنة مستقلة.")


@pytest.mark.parametrize("page", ["status.html", "transparency.html"])
def test_specialist_review_stated_honestly(page):
    """النص الثابت لحال المراجعة الشرعية (evaluation/review/SPECIALIST_REVIEW_2026-10-05.md)، ولا شارة «معتمدة شرعياً» لأي حالة
    (ملفات الحالات المجمّدة لم تتغير)."""
    assert SPECIALIST_NOTE in _text(page)
    assert "لم تُجرَ مراجعة شرعية متخصصة" not in _page(page)
    assert "معتمدة شرعياً</span>" not in _page(page)
    assert (ROOT / "evaluation/review/SPECIALIST_REVIEW_2026-10-05.md").is_file()


def test_comparison_caveat_on_methodology_and_results():
    """تنبيه ميل المقارنة لصالح rag وصغر N: ثابت في المنهجية وبجوار المقارنة وقرار البوابة، والنص واحد في المولّد والصفحة."""
    COMPARISON_CAVEAT = _load_builder().COMPARISON_CAVEAT
    assert "أُعدّت لحالات الاختبار نفسها" in COMPARISON_CAVEAT and "تميل لصالح rag" in COMPARISON_CAVEAT
    assert COMPARISON_CAVEAT in _text("sources.html")
    core = (WEB / "assets/results-core.js").read_text(encoding="utf-8")
    m = re.search(r'export const COMPARISON_CAVEAT =\s*"([^"]+)"', core)
    assert m and m.group(1) == COMPARISON_CAVEAT
    js = (WEB / "assets/results.js").read_text(encoding="utf-8")
    assert '"compare-caveat"' in js and '"gate-caveat"' in js
    assert "تميل لصالح rag" in (ROOT / "docs/METHODOLOGY.md").read_text(encoding="utf-8")


def test_noise_removed_and_specialist_phrase_only_where_kept():
    """قرارات التنظيف: لا فقرة «ست مراحل» ولا مفتاح الرسم في الرئيسية، ولا سطر «مجالات الحزمة التسعة» في الحالة،
    ونص المراجعة الشرعية الثابت في الشفافية والحالة (والنتائج من results.js) فقط."""
    home = _page("index.html")
    assert "ست مراحل" not in home and 'class="legend"' not in home and "لم يُبنَ بعد" not in home
    status = _text("status.html")
    assert "مجالات الحزمة التسعة" not in status and "وحدة Red Teaming" in status
    assert "كل بند أدناه محسوب من ملفات المستودع عند توليد الصفحة." in status
    for page in ("levels.html", "sources.html", "cases.html", "index.html", "project.html", "check.html"):
        assert "لم تُجرَ مراجعة شرعية متخصصة" not in _page(page) and "قريب لصاحب المشروع" not in _page(page), page
    js = (WEB / "assets/results.js").read_text(encoding="utf-8")
    assert "لم تُجرَ مراجعة شرعية متخصصة" not in js
    assert ("مراجعة واحدة لحالة واحدة من 12 (OFF-06) أجراها خريج شريعة هو قريب لصاحب المشروع، لا لجنة مستقلة؛ "
            "وما عداها تحقق مصادر (source_check) يجريه المشارك وليس مراجعة شرعية.") in js.replace('"\n    + "', "")


def test_cases_list_review_line_and_badges_from_data():
    cases = [c for name in ("official_v0", "extended_v1")
             for c in json.loads((ROOT / f"testsets/{name}.json").read_text(encoding="utf-8"))["cases"]]
    approved = [c for c in cases if c.get("review_status") == "approved"]
    html = _page("cases.html")
    assert f"المراجعة البشرية: {len(approved)} من {len(cases)} حالة" in _text("cases.html")
    assert "لم يُتحقق منها بعد" not in html
    src = sum(1 for c in approved if c.get("reviewer_role") == "source_check")
    assert html.count("راجعها صاحب المشروع (تحقق مصادر)") == src


@pytest.mark.parametrize("page", [*PAGES, "case.html", "check.html", "replay.html"])
def test_footer_states_saved_results_on_every_page(page):
    foot = _page(page)
    foot = foot[foot.index('<footer class="site">'):]
    assert "يعرض الموقع نتائج محفوظة من تشغيلات رسمية؛ لا يشغّل التقييم من المتصفح" in foot


def test_case_page_review_badge_only_for_reviewed():
    js = (WEB / "assets/case.js").read_text(encoding="utf-8")
    assert "لم يُتحقق منها بعد" not in js and "لم تُراجَع بعد" not in js
    assert "راجعها صاحب المشروع (تحقق مصادر)" in js


def test_specialist_review_file_quotes_reviewer_with_header():
    doc = (ROOT / "evaluation/review/SPECIALIST_REVIEW_2026-10-05.md").read_text(encoding="utf-8")
    for needle in ("خريج شريعة (بحسب قوله)", "أخو صاحب المشروع", "الاسم:** غير مذكور", "5 أكتوبر 2026", "OFF-06 وحدها",
                   "رواه مسلم (2699)", "«لا يصح، وليس في الصحيحين»", "فانا خريج شريعة"):
        assert needle in doc, needle


def test_review_wording_relative_not_brother_on_site_and_snapshot_explained():
    """«قريب لصاحب المشروع» في الموقع كله، و«أخو» في ملف المراجعة وحده؛ وصفر المراجعة المتخصصة موصوف بأنه لقطة وقت التشغيل."""
    for p in [*WEB.glob("*.html"), *(WEB / "assets").glob("*.js")]:
        assert "أخو صاحب المشروع" not in p.read_text(encoding="utf-8"), p.name
    assert "أخو صاحب المشروع" in (ROOT / "evaluation/review/SPECIALIST_REVIEW_2026-10-05.md").read_text(encoding="utf-8")
    status = _text("status.html")
    assert "(لقطة وقت التشغيل؛ وجرت بعده مراجعة شرعية لاحقة لحالة واحدة: OFF-06)" in status
    assert "وجرت بعده مراجعة شرعية لاحقة لحالة واحدة (OFF-06)" in status
    case_js = (WEB / "assets/case.js").read_text(encoding="utf-8")
    assert "راجعها بعد التشغيل خريج شريعة (قريب لصاحب المشروع)، والسجل الرسمي نفسه لم يتغير." in case_js
    assert "لم تُجرَ مراجعة شرعية لهذه الحالة." in case_js  # لبقية الحالات


@pytest.mark.parametrize("page", [*PAGES, "case.html", "check.html", "replay.html"])
def test_page_identity_metadata_inline_and_static(page):
    """وصف وعنوان لكل صفحة، وtheme-color، وأيقونتان مضمّنتان (data:)، وOpen Graph ثابت بلا صور خارجية."""
    h = _page(page)
    head = h[:h.index("</head>")]
    assert re.search(r'<meta name="description" content="[^"]{20,}">', head)
    assert head.count('name="theme-color"') == 2
    assert '<link rel="icon" href="data:image/svg+xml,' in head and '<link rel="apple-touch-icon" href="data:image/png;base64,' in head
    for prop in ("og:title", "og:description", "og:url", "og:type"):
        assert f'property="{prop}"' in head, prop
    assert "og:image" not in head


def test_page_descriptions_are_distinct():
    descs = {p: re.search(r'<meta name="description" content="([^"]+)">', _page(p)).group(1) for p in [*PAGES, "case.html", "check.html", "replay.html"]}
    assert len(set(descs.values())) == len(descs)


@pytest.mark.parametrize("page", [*PAGES, "case.html", "check.html", "replay.html"])
def test_footer_one_line_with_repo_and_license(page):
    foot = _page(page)
    foot = foot[foot.index('<footer class="site">'):foot.index("</footer>")]
    assert 'class="foot-line"' in foot and "github.com/w7by4nrcfd-cpu/Miyar" in foot and "LICENSE" in foot and "MIT" in foot


def test_cases_lead_counts_from_data():
    b = _load_builder()
    f = b.facts()
    assert f"{f['n']} حالة اختُبرت منها {f['n_tested']} رسمياً" in _text("cases.html")
    assert f["n_tested"] == max(r["n_cases"] for r in f["results"]["runs"])


def test_review_counts_are_described_as_case_definition_review():
    """أعداد source_check مراجعة لتعريف الحالات وسلوكها المتوقع، لا لأحكام مِعيار؛ ولا نسبة اتفاق في الموقع."""
    assert "مراجعة لتعريف الحالات وسلوكها المتوقع (تحقق مصادر)، لا لأحكام مِعيار" in _text("cases.html")
    st = _text("status.html")
    assert "لا لأحكام مِعيار على إجابات المساعد" in st and "وتحقق المصادر مراجعة لتعريف الحالة لا لأحكام مِعيار" in st
    for page in ["index.html", "results.html", "status.html", "cases.html"]:
        assert not re.search(r"(اتفاق|Agreement)[^.؛\n]{0,40}\d+(\.\d+)?\s*[%٪]", _text(page)), page


def test_discovered_section_numbers_recomputed_from_official_records():
    """«ماذا اكتشف مِعيار؟»: كل رقم يُعاد حسابه هنا مستقلاً من evaluation/official/ ويُطابق الصفحة؛ بلا نسب ولا «أفضل/أسوأ»."""
    from collections import Counter
    if not _published_runs():
        return
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "evaluation/official").glob("official-*.json")]
    answers = sum(len(r["cases"]) for r in recs)
    cits = [x for r in recs for c in r["cases"] for x in (c.get("judgement") or {}).get("citations") or []]
    st = Counter((x["citation"]["kind"], x["status"]) for x in cits)
    with_cit = sum(bool((c.get("judgement") or {}).get("citations")) for r in recs for c in r["cases"])
    refer = sum(bool((c.get("judgement") or {}).get("needs_human_review")) for r in recs for c in r["cases"])
    h = _page("results.html")
    sec = h[h.index('id="discovered"'):h.index("</section>", h.index('id="discovered"'))]
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", sec))
    assert f"{answers} إجابة مُقيَّمة" in t
    assert f"{len(cits)} استشهاداً استخرجها مِعيار من {with_cit} إجابة فيها استشهاد (من {answers})" in t
    nq = sum(v for (k, _), v in st.items() if k == "quran")
    assert (f"الآيات ({nq}): {st[('quran', 'supported')]} مؤيَّد" in t and f"و{st[('quran', 'needs_review')]} يحتاج تحقق" in t
            and f"و{st[('quran', 'wrong_or_missing')]} خاطئ أو غير موجود" in t)
    nh = sum(v for (k, _), v in st.items() if k == "hadith")
    assert f"الأحاديث ({nh}): {st[('hadith', 'supported')]} مؤيَّد، و{st[('hadith', 'needs_review')]} يحتاج تحقق" in t
    assert f"{refer} إجابات من {answers} أُحيلت إلى مراجعة بشرية ولم تدخل في الدرجة الآلية" in t
    assert "«يحتاج تحقق» لا يعني أن الحديث خاطئ" in t
    assert ("تحقق بشري نصي للآيات" in t) if (ROOT / "evaluation/gold/quran/agreement.json").exists() else ("لم يُقَس بعد" in t)
    assert not re.search(r"[%٪]", t) and "أسوأ" not in t and "فرق رسم" not in t and "تحريف" not in t
    # كل حالة في القسم رابط إلى صفحتها
    for cid in re.findall(r'href="case.html\?id=([A-Z]+-\d+)"', sec):
        assert any(c["id"] == cid for r in recs for c in r["cases"]), cid


def test_discovered_neutral_wording_for_single_letter_rulings():
    """حكم wrong_or_missing بفرق حرف واحد يُعرض بصياغة محايدة: لا تفسير غير مراجع بشرياً."""
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", _page("results.html")))
    if "في سجلي OFF-03" in t:
        assert ("في سجلي OFF-03 صُنّف الفرق wrong_or_missing / altered_text؛ والفرق المرصود حرف واحد (س/ص). "
                "وأكّده التحقق البشري النصي دون حسم أهو خطأ أم وجه رسم أو قراءة.") in t


def test_gold_line_from_locked_agreement():
    """سطر Gold Set في النتائج محسوب من evaluation/gold/quran/agreement.json المقفل، بالأعداد والمقامات وحدوده، بلا نسب."""
    g = json.loads((ROOT / "evaluation/gold/quran/agreement.json").read_text(encoding="utf-8"))["by_automated_verdict"]
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", _page("results.html")))
    assert (f"وافق {g['supported']['agree']} من {g['supported']['of']} «مؤيَّد»، و{g['wrong_or_missing']['agree']} من "
            f"{g['wrong_or_missing']['of']} «خاطئ»، و{g['needs_review']['agree']} من {g['needs_review']['of']} «يحتاج تحقق»") in t
    assert "تحقق بشري نصي للآيات" in t and "صاحب المشروع، غير مستقل، ليس مراجعة شرعية" in t


def test_replay_banner_same_in_page_and_js():
    """شريط إعادة العرض نصه واحد في الصفحة المولّدة وفي replay-core.js، ولا يوحي بتشغيل حي."""
    b = _load_builder()
    js = (WEB / "assets/replay-core.js").read_text(encoding="utf-8")
    m = re.search(r'export const BANNER = "([^"]+)"', js)
    assert m and m.group(1) == b.REPLAY_BANNER == "إعادة عرض لتشغيل رسمي محفوظ — ليس تشغيلاً حياً"
    assert b.REPLAY_BANNER in _page("replay.html")
