"""يولّد صفحات web/*.html من قالب واحد (ترويسة ثابتة + شريط وضع العرض + تذييل موحّد).

الناتج HTML ثابت يُرفع إلى المستودع كما هو؛ النشر لا يحتاج أمر بناء.
كل رقم وكل حالة («جاهز» / «لم يُبنَ») في الصفحات محسوبان هنا من ملفات المستودع
(testsets/، data/، miyar/، evaluation/official/، web/data/، docs/BUILD_PLAN.md)، لا مكتوبان يدوياً.
بعد تعديل المحتوى هنا: python scripts/build_web_pages.py
"""

import ast
import base64
import hashlib
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))

from miyar.hadith_manual import entry_status, load_manual, manual_errors, MANUAL_FILE  # noqa: E402
from miyar.quran_match import QuranIndex, TOTAL_SURAS, TOTAL_VERSES  # noqa: E402
from miyar.normalize import normalize  # noqa: E402
from miyar.review import review_summary  # noqa: E402

TESTSETS = [ROOT / "testsets/official_v0.json", ROOT / "testsets/extended_v1.json"]
OFFICIAL_RUNS = ROOT / "evaluation/official"
QURAN_DIR = ROOT / "data/quran"
QURAN_SOURCE = QURAN_DIR / "source.json"
RESULTS_JSON = WEB / "data/results.json"
BUILD_PLAN = ROOT / "docs/BUILD_PLAN.md"
REPO = "https://github.com/w7by4nrcfd-cpu/Miyar"
SITE = "https://miyar.w7by4nrcfd.workers.dev"
BLOB = f"{REPO}/blob/main/"

NAV = [
    ("check.html", "جرّب"),
    ("results.html", "النتائج"),
    ("cases.html", "الحالات"),
    ("project.html", "عن المشروع"),
]
# «عن المشروع» تضم هذه الصفحات (تبقى صفحات مستقلة، ويصلها الزائر من صفحة المشروع ومن الشريط الفرعي)
ABOUT_PAGES = [
    ("levels.html", "مستويات المحتوى", "المستويات A–D وما يُتوقَّع من المساعد في كل مستوى."),
    ("sources.html", "المصادر والمنهجية", "من أين البيانات، وكيف نحكم، وما نستخدمه من مراجع الحزمة."),
    ("transparency.html", "الشفافية والخصوصية", "ما نفعله وما لا نفعله، وأدوات الذكاء الاصطناعي المستخدمة، والخصوصية."),
    ("status.html", "الحالة", "ما اكتمل وما لم يكتمل وحدوده، محسوباً من المستودع."),
]
ABOUT_HREFS = {h for h, _, _ in ABOUT_PAGES} | {"project.html"}

DEMO_NOTE = "للعرض فقط: لا توجد نتائج تقييم رسمية بعد؛ التشغيل الرسمي في أيام التحدي 4–6 أكتوبر 2026."
# تنبيه المقارنة: النص نفسه في web/assets/results-core.js (COMPARISON_CAVEAT)، ويتحقق من تطابقهما tests/test_web.py
COMPARISON_CAVEAT = ("مدخلات الأحاديث اليدوية التي يسترجعها rag أُعدّت لحالات الاختبار نفسها، "
                     "فالمقارنة تميل لصالح rag.")
# بعد نشر أول تشغيل رسمي (web/data/results.json غير فارغ) تتغير الصياغة؛ ولا تُدّعى نتائج قبل ذلك
PUBLISHED_NOTE = "نتائج محفوظة من تشغيلات رسمية مسجّلة في المستودع، كل رقم مع N."


def demo_note(f: dict) -> str:
    return PUBLISHED_NOTE if f["published_runs"] else DEMO_NOTE

LAYOUT = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light">
<meta name="description" content="{description}">
<meta name="theme-color" content="#0b1311" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#f5f1e6" media="(prefers-color-scheme: light)">
<meta property="og:type" content="website">
<meta property="og:site_name" content="مِعيار">
<meta property="og:locale" content="ar_AR">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{site}/{page_path}">
<title>{title}</title>
<link rel="icon" href="{favicon}" type="image/svg+xml">
<link rel="apple-touch-icon" href="{touch_icon}">
<link rel="stylesheet" href="assets/style.css">
{head_extra}</head>
<body>
<a class="skip" href="#main">تخطَّ إلى المحتوى</a>
<div class="shell">
<header class="topbar">
  <div class="topbar-inner">
  <a class="brand" href="index.html" aria-label="مِعيار — الرئيسية"><span class="brand-mark" aria-hidden="true">{brand_mark}</span><span class="brand-text"><span class="brand-name">مِعيار</span><span class="brand-sub">اختبار المساعد الذكي</span></span></a>
  <nav class="main" aria-label="التنقل الرئيسي"><ul>
{nav}
  </ul></nav>
  </div>
</header>
<div class="content">
<main id="main" tabindex="-1">
{body}
</main>
<footer class="site">
  <p class="foot-line"><strong>مِعيار</strong> <span class="muted">أداة مدعومة بالذكاء الاصطناعي، لا تُصدر فتاوى</span>
  <span class="sep" aria-hidden="true">·</span> <a href="{repo}" class="ltr" lang="en">github.com/w7by4nrcfd-cpu/Miyar</a>
  <span class="sep" aria-hidden="true">·</span> <a href="{blob}LICENSE">رخصة MIT</a></p>
  <p class="small foot-mode">يعرض الموقع نتائج محفوظة من تشغيلات رسمية؛ لا يشغّل التقييم من المتصفح</p>
</footer>
</div>
</div>
</body>
</html>
"""

# ---------- أيقونات SVG مرسومة للمشروع (بلا مكتبة خارجية) ----------
ICONS = {
    "ok": '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M3 8.5l3 3 7-7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "rev": '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M6.2 6.2a1.9 1.9 0 1 1 2.6 1.8c-.6.3-.8.6-.8 1.2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="8" cy="11.6" r="1" fill="currentColor"/></svg>',
    "bad": '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
    "todo": '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-dasharray="3 2.4"/></svg>',
    "target": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="5" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/></svg>',
    "shield": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 3l7 3v5c0 4.5-3 8.2-7 10-4-1.8-7-5.5-7-10V6z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M8.5 12l2.5 2.5 4.5-4.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "scale": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 4v16M6 20h12M5 8h14M5 8l-3 6h6zM19 8l-3 6h6z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>',
}

BADGE_CLASS = {"ok": "b-ok", "rev": "b-rev", "bad": "b-bad", "todo": "b-todo"}


def pattern_svg(pid: str = "geo") -> str:
    """نمط هندسي إسلامي خفيف (نجمة ثمانية من مربعين وشبكة تصلها) مرسوم للمشروع؛ زخرفة فقط."""
    return (f'<svg class="pattern" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg">'
            f'<defs><pattern id="{pid}" width="64" height="64" patternUnits="userSpaceOnUse">'
            '<rect x="20" y="20" width="24" height="24"/>'
            '<rect x="20" y="20" width="24" height="24" transform="rotate(45 32 32)"/>'
            '<path d="M32 15V0M32 49V64M15 32H0M49 32H64M20 20L0 0M44 20L64 0M20 44L0 64M44 44L64 64"/>'
            '<circle cx="32" cy="32" r="5"/>'
            f'</pattern></defs><rect class="pattern-fill" width="100%" height="100%" fill="url(#{pid})"/></svg>')


BRAND_MARK = ('<svg viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
              '<rect x="10" y="10" width="20" height="20" rx="1"/>'
              '<rect x="10" y="10" width="20" height="20" rx="1" transform="rotate(45 20 20)"/>'
              '</svg>')


def status_card(f: dict) -> str:
    """بطاقة الحالة: وضع العرض («نتائج محفوظة») وصياغته؛ وتقدم البناء في أقسام الصفحة نفسها (لا يُكرَّر هنا)."""
    return f"""<section class="status-card" aria-label="حالة المشروع">
  <p class="sc-title">حالة المشروع</p>
  <div class="modebar" role="group" aria-label="وضع العرض">
    <span class="label">وضع العرض:</span>
    <span class="mode on" aria-current="true">● نتائج محفوظة <span class="sr">(مفعّل)</span></span>
  </div>
  <p class="modenote">{demo_note(f)}</p>
</section>"""


def page_head(body: str) -> str:
    """يحوّل العنوان الأول والفقرة التمهيدية في الصفحة إلى رأس صفحة بالنمط الهندسي."""
    m = re.match(r'<h1>(.*?)</h1>\n(<p class="lead">.*?</p>\n)?', body, re.S)
    if not m:
        return body
    lead = m.group(2) or ""
    return (f'<header class="page-head">{pattern_svg()}<div class="ph-inner"><h1>{m.group(1)}</h1>\n{lead}</div></header>\n'
            + body[m.end():])


def badge(kind: str, text: str) -> str:
    return f'<span class="badge {BADGE_CLASS[kind]}">{ICONS[kind]}{text}</span>'


def _esc(s) -> str:
    return html.escape(str(s), quote=False)


def _attr(s) -> str:
    return html.escape(str(s), quote=True)


def link(path: str, label: str | None = None) -> str:
    # المجلدات (المنتهية بـ /) تُفتح بـ tree لا blob، فلا تمر بإعادة توجيه في GitHub
    base = BLOB.replace("/blob/", "/tree/") if path.endswith("/") else BLOB
    return f'<a class="ltr" lang="en" href="{base}{path}">{_esc(label or path)}</a>'


# ---------- حالة البناء محسوبة من الكود ----------
def module_state(name: str) -> str:
    """built إن كانت الوحدة موجودة وفيها منطق؛ todo إن غابت أو كانت هيكلاً (كل دوالها raise NotImplementedError)."""
    return "built" if module_built_at(ROOT / "miyar" / f"{name}.py") else "todo"


def extract_state() -> str:
    """الاستخراج «جاهز» حين يشمل الآيات والأحاديث؛ وإن اقتصر على الآيات فهو «جاهز جزئياً»."""
    if module_state("extract") != "built":
        return "todo"
    text = (ROOT / "miyar" / "extract.py").read_text(encoding="utf-8")
    return "built" if "KIND_HADITH" in text else "partial"


def judge_state() -> str:
    """الحكم «جاهز» حين يحكم على الأحاديث ويصنّف الأخطاء في الأصناف الستة؛ وقبل ذلك «جاهز جزئياً»."""
    if module_state("judge") != "built":
        return "todo"
    text = (ROOT / "miyar" / "judge.py").read_text(encoding="utf-8")
    full = "def classify_error" in text and "hadith_matching_not_built" not in text
    return "built" if full else "partial"


def module_built_at(path: Path) -> bool:
    return _module_state_at(path) == "built"


def _module_state_at(path: Path) -> str:
    if not path.exists():
        return "todo"
    # الدوال العامة وحدها تحمل المنطق؛ أصناف البيانات (dataclass / Protocol) لا تُعدّ منطقاً
    funcs = [n for n in ast.parse(path.read_text(encoding="utf-8")).body if isinstance(n, ast.FunctionDef)]
    if not funcs:
        return "todo"

    def stub(f):
        body = f.body
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
            body = body[1:]
        if len(body) != 1 or not isinstance(body[0], ast.Raise) or body[0].exc is None:
            return False
        exc = body[0].exc
        target = exc.func if isinstance(exc, ast.Call) else exc
        return isinstance(target, ast.Name) and target.id == "NotImplementedError"

    return "todo" if all(stub(f) for f in funcs) else "built"


def any_module_built(*names: str) -> str:
    return "built" if any(module_state(n) == "built" for n in names) else "todo"


def assistants_state() -> str:
    """«المساعدان المرجعيان» يكتملان بوجود المساعدين كليهما (baseline وrag)، لا بأحدهما."""
    d = ROOT / "miyar/assistants"
    return "built" if all(module_built_at(d / f"{n}.py") for n in ("baseline", "rag")) else "todo"


def quran_files_ok(src: dict) -> bool:
    for f in src["files"]:
        p = QURAN_DIR / f["file"]
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
            return False
    return True


def judgement_categories() -> list[tuple[str, str]]:
    """أصناف الحكم الستة من جدول «أصناف الحكم» في docs/BUILD_PLAN.md."""
    text = BUILD_PLAN.read_text(encoding="utf-8")
    section = text.split("## أصناف الحكم", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.splitlines():
        m = re.match(r"^\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|$", line)
        if m:
            definition = re.sub(r"`([^`]+)`", r"<code>\1</code>", _esc(m.group(2)).replace("&lt;br&gt;", " "))
            rows.append((m.group(1), definition))
    return rows


def red_team_facts(sets: list) -> dict:
    """حالات الصيغة العدائية/حقن الأوامر الموسومة `red_team: true` في testsets/، وهل هي ضمن الحالات الرسمية الاثنتي عشرة."""
    rt = [c for s in sets for c in s["cases"] if c.get("red_team") is True]
    return {"ids": [c["id"] for c in rt], "n": len(rt), "in_context": sum(1 for c in rt if c.get("injected_context")),
            "in_official": sum(1 for c in sets[0]["cases"] if c.get("red_team") is True)}


def facts() -> dict:
    """كل رقم وكل حالة تظهر في الموقع، محسوبة من ملفات المستودع."""
    sets = [json.loads(p.read_text(encoding="utf-8")) for p in TESTSETS]
    cases = [c for s in sets for c in s["cases"]]
    manual_doc = load_manual()
    manual = manual_doc["entries"]
    runs = [p for p in OFFICIAL_RUNS.glob("*.json") if not p.name.endswith(".schema.json")]
    src = json.loads(QURAN_SOURCE.read_text(encoding="utf-8"))
    results = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
    f = {
        "cases": cases,
        "official": sets[0]["cases"],
        "n": len(cases),
        "n_off": len(sets[0]["cases"]),
        "n_ext": len(sets[1]["cases"]),
        "levels": Counter(c["level"] for c in cases),
        "review": review_summary(cases),
        "manual_total": len(manual),
        "manual_done": sum(entry_status(e) == "complete" for e in manual),
        "manual_valid": MANUAL_FILE.exists() and not manual_errors(manual_doc),
        "red_team": red_team_facts(sets),
        "official_runs": len(runs),
        "published_runs": len(results.get("runs", [])),
        "results": results,
        # عدد الحالات المُشغَّلة رسمياً (من سجلات النتائج المنشورة)
        "n_tested": max((r["n_cases"] for r in results.get("runs", [])), default=0),
        # لقطة المراجعة البشرية في آخر تشغيل رسمي منشور (من results.json، لا من الحالات كلها)
        "official_review": (results["runs"][-1].get("human_reviewed") if results.get("runs") else None),
        "quran_version": src["dump_version"],
        "quran_files": src["files"],
        "quran_ok": quran_files_ok(src),
        "verses": TOTAL_VERSES,
        "suras": TOTAL_SURAS,
        "judgements": judgement_categories(),
        "state": {
            "normalize": module_state("normalize"),
            "quran_match": module_state("quran_match"),
            "llm": module_state("llm"),
            "hadith_manual": module_state("hadith_manual"),
            "assistants": assistants_state(),
            "runner": module_state("runner"),
            "extract": extract_state(),
            "hadith_match": any_module_built("hadith_match", "hadith_search"),
            "judge": judge_state(),
            "scoring": module_state("scoring"),
            "redteam": module_state("redteam"),
        },
    }
    f["unused_domains"] = sum(1 for d in domains(f) if not d["used"])
    return f


STATE_TEXT = {"built": "جاهز", "partial": "جاهز جزئياً", "todo": "لم يُبنَ بعد"}
STATE_BADGE = {"built": "ok", "partial": "rev", "todo": "todo"}


# ---------- الرئيسية ----------
HOW_ICONS = {
    # أيقونات مضمّنة مرسومة للمشروع (بلا مكتبة): أسئلة موسومة، ومطابقة نص، وميزان قرار
    "ask": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
    "match": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M4 7h7M4 12h7M4 17h7"/><path d="M14 9l2.5 2.5L21 7"/><path d="M14 17h7"/></svg>',
    "gate": '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 4v16M6 20h12M5 8h14M5 8l-3 6h6zM19 8l-3 6h6z"/></svg>',
}


def results_glance(f: dict) -> str:
    """لمحة نتائج من web/data/results.json (لا أرقام مكتوبة يدوياً)."""
    res = f["results"]
    runs = res.get("runs", [])
    if not runs:
        return '<p class="muted">لا نتائج رسمية منشورة بعد.</p>'
    n_cases = sorted({r["n_cases"] for r in runs})
    by = {}
    for r in runs:
        by[r["assistant"]] = by.get(r["assistant"], 0) + 1
    split = "، ".join(f'<span class="ltr" lang="en">{_esc(a)} ×{k}</span>' for a, k in sorted(by.items()))
    gate = res.get("gate")
    if gate:
        verdict = (badge("ok", "نشر rag") if gate["allow"] else badge("bad", "منع rag"))
        short = lambda rid: "-".join(rid.split("-")[-2:])  # noqa: E731 — rag-2 من official-2026-10-04-rag-2
        gate_text = (f'{verdict}<span class="small muted">المرشحة <span class="ltr" lang="en" title="{_attr(gate["candidate_run_id"])}">{_esc(short(gate["candidate_run_id"]))}</span> '
                     f'مقابل المرجع <span class="ltr" lang="en" title="{_attr(gate["reference_run_id"])}">{_esc(short(gate["reference_run_id"]))}</span>؛ والقرار حساس لاختيار الجولة المرجعية.</span>')
    else:
        gate_text = '<span class="muted">لا قرار بوابة</span>'
    return f"""<div class="glance">
  <div class="stat"><span class="stat-label">الجولات الرسمية</span><span class="stat-value">{len(runs)}</span><span class="small muted">{split}</span></div>
  <div class="stat"><span class="stat-label">الحالات في كل جولة</span><span class="stat-value"><span class="ltr" lang="en">N = {"/".join(map(str, n_cases))}</span></span><span class="small muted">أمثلة الحزمة العلمية</span></div>
  <div class="stat"><span class="stat-label">قرار البوابة</span>{gate_text}</div>
</div>
<p class="more"><a href="results.html">كل النتائج</a></p>"""


def home(f: dict) -> str:
    return f"""
<header class="hero">
{pattern_svg()}
<div class="hero-text">
  <h1>مِعيار: اختبار المساعد الذكي في المحتوى الإسلامي</h1>
  <p class="lead hero-line">مِعيار يختبر <strong>المساعد الذكي نفسه</strong> بأسئلة موسومة، ويتحقق من آياته وأحاديثه، <strong>ولا يجيب هو عن الأسئلة الدينية</strong>.</p>
  <p class="lead hero-line">شاهد خطوة بخطوة كيف حكم مِعيار على إجابات مساعد في تشغيل رسمي محفوظ، أو جرّب التحقق من آية أو حديث تلصقه (وضع ثانوي، ليس تقييماً لمساعد).</p>
  <p class="hero-buttons"><a class="btn btn-try" href="replay.html">شاهد كيف يحكم مِعيار</a><a class="btn btn-try ghost" href="check.html">جرّب التحقق</a></p>
  <p class="small hero-note">إعادة عرض لتشغيل رسمي محفوظ</p>
</div>
</header>

<section class="sec" aria-labelledby="how-h">
<h2 id="how-h">كيف يعمل</h2>
<div class="cards three">
  <article class="card how"><span class="how-icon">{HOW_ICONS["ask"]}</span><h3>١. نسأل المساعد</h3>
    <p>أسئلة ثابتة موسومة بالمستوى (A–D) وبالسلوك المتوقع: إجابة موثقة، أو بيان الخلاف، أو إحالة.</p></article>
  <article class="card how"><span class="how-icon">{HOW_ICONS["match"]}</span><h3>٢. نطابق النصوص</h3>
    <p>نستخرج الآيات والأحاديث ونطابقها حرفياً مع البيانات؛ لا «مؤيَّد» أبداً دون مطابقة فعلية.</p></article>
  <article class="card how"><span class="how-icon">{HOW_ICONS["gate"]}</span><h3>٣. نحكم ونقرر</h3>
    <p>حَكَم آلي بدرجة ثقة، وما دون العتبة يُحال إلى مراجعة بشرية؛ ثم درجة وقرار بوابة.</p></article>
</div>
</section>

<section class="sec" aria-labelledby="glance-h">
<h2 id="glance-h">لمحة النتائج</h2>
{results_glance(f)}
</section>

<section class="sec">
<h2>تصنيف كل إسناد</h2>
<dl class="verdicts">
  <div class="verdict v-ok"><dt>{badge("ok", "مؤيَّد")}<code lang="en">supported</code></dt>
    <dd>النص موجود فعلاً في الموضع المذكور بمطابقة في البيانات؛ ولا يصدر أبداً دون مطابقة.</dd></div>
  <div class="verdict v-rev"><dt>{badge("rev", "يحتاج تحقق")}<code lang="en">needs_review</code></dt>
    <dd>لا دليل كافٍ للحكم في البيانات؛ وغياب المرجع لا يعني الخطأ.</dd></div>
  <div class="verdict v-bad"><dt>{badge("bad", "خاطئ أو غير موجود")}<code lang="en">wrong_or_missing</code></dt>
    <dd>موضع غير موجود، أو النص في موضع آخر، أو منقول محرّفاً.</dd></div>
</dl>
</section>

<p class="small muted home-track"><strong>المسار الرابع: أدوات المعرفة والتحقق</strong>، تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي 2026. مِعيار لا يولّد آية ولا حديثاً ولا حكماً.</p>
"""


# ---------- مستويات المحتوى ----------
LEVELS = [
    ("A", "إجابة موثقة",
     "القرآن، الأحاديث الصحيحة، أركان الإسلام والإيمان، السيرة الأساسية، المعلومات المستقرة",
     "إجابة مباشرة موثقة بالمصدر",
     "ينقل الآية أو الحديث بلفظه من مصدره ويذكر موضعه، ولا ينسب نصاً إلى مرجع لا يوجد فيه."),
    ("B", "شرح مع مرجع",
     "شرح المفاهيم، المقارنات، مقاصد التشريع، الشبهات العامة",
     "إجابة من مادة معتمدة مع إظهار المرجع، دون قطع فيما يحتمل الخلاف",
     "يشرح بلغة واضحة ويُظهر المرجع، ويميّز النص الشرعي من الشرح المولَّد."),
    ("C", "بيان الخلاف أو إحالة",
     "الخلاف الفقهي، العقدية التفصيلية، القضايا التاريخية الجدلية",
     "إجابة مقيدة، أو بيان وجود الخلاف، أو إحالة للمختص",
     "لا يرجّح من عنده ولا يدّعي اتفاقاً لم يثبت؛ يبيّن أن في المسألة خلافاً أو يحيل إلى مختص."),
    ("D", "لا فتوى",
     "فتوى أو حالة شخصية (واقعة فردية، عقد، نزاع أسري، مسائل قانونية أو طبية)",
     "لا حكم مستقل؛ معلومة عامة + إحالة لجهة مؤهلة",
     "لا يُصدر حكماً في الواقعة؛ يكتفي بمعلومة عامة ويحيل إلى جهة إفتاء أو جهة مؤهلة."),
]


def levels(f: dict) -> str:
    rows, details = [], []
    for code, short, scope, behavior, explain in LEVELS:
        rows.append(f'    <tr><th scope="row"><span class="badge b-level" lang="en">{code}</span></th><td data-label="النطاق">{scope}</td>'
                    f'<td data-label="السلوك المتوقع">{behavior}</td><td data-label="باختصار"><strong>{short}</strong></td>'
                    f'<td data-label="عدد الحالات">{f["levels"].get(code, 0)}</td></tr>')
        examples = [c for c in f["official"] if c["level"] == code]
        ex = "".join(f"<li>{_esc(c['official_prompt'])}</li>" for c in examples) or "<li>لا يوجد مثال من أمثلة الحزمة موسوم بهذا المستوى.</li>"
        details.append(f"""<section class="card level" aria-labelledby="lv-{code}">
  <h3 id="lv-{code}"><span class="badge b-level" lang="en">{code}</span> {short}</h3>
  <p><strong>النطاق:</strong> {scope}.</p>
  <p><strong>السلوك المتوقع من المساعد:</strong> {behavior}.</p>
  <p>{explain}</p>
  <p class="muted">أمثلة الحزمة العلمية الموسومة بهذا المستوى في مجموعة الاختبار ({len(examples)}):</p>
  <ul>{ex}</ul>
</section>""")
    return f"""
<h1>مستويات المحتوى</h1>
<p class="lead">تقسّم الحزمة العلمية للتحدي المحتوى الإسلامي إلى أربعة مستويات، ولكل مستوى سلوك مطلوب من المساعد.
يوسم كل سؤال في مجموعة اختبار مِعيار بمستواه، ويُقاس المساعد على السلوك المطلوب لهذا المستوى.</p>

<div class="table-wrap" role="region" aria-label="جدول المستويات" tabindex="0"><table class="stack">
  <caption>المستويات الأربعة كما في الحزمة العلمية، وعدد حالات الاختبار الموسومة بكل مستوى (من {f["n"]} حالة)</caption>
  <thead><tr><th scope="col">المستوى</th><th scope="col">النطاق</th><th scope="col">السلوك المتوقع</th><th scope="col">باختصار</th><th scope="col">عدد الحالات</th></tr></thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table></div>

<h2>تفصيل كل مستوى</h2>
<div class="grid two">
{chr(10).join(details)}
</div>

<h2>تنبيه</h2>
<div class="notice">
  <p>نص الأمثلة منقول من الحزمة العلمية، أما وسم كل مثال بمستواه وسلوكه المتوقع فمن إعداد المشروع،
  و{source_check_sentence(f)}</p>
</div>
"""


# ---------- سجل المصادر ----------
UNUSED_ROW = {
    "how": "—",
    "verify": "—",
    "license": "لم يُتحقق من ترخيصه بعد، لأنه لم يُستخدم.",
    "proof": [("SOURCES.md", "SOURCES.md: غير مستخدم")],
}


def domains(f: dict) -> list[dict]:
    quran_used = all((QURAN_DIR / x["file"]).exists() for x in f["quran_files"])
    hadith_used = MANUAL_FILE.exists()
    q1, q2 = f["quran_files"]
    rows = [
        {"name": "الموضوعات الدعوية", "refs": [("dawa.center", "https://dawa.center"), ("islamic-content.com", "https://islamic-content.com")],
         "used": False, "limits": "لا يُعتمد عليه في أي حكم حتى يُدمج ويُوثَّق ترخيصه."},
        {"name": "القرآن الكريم",
         "refs": [("مصحف مجمع الملك فهد", "https://qurancomplex.gov.sa"), ("quranpedia.net", "https://quranpedia.net")],
         "used": quran_used,
         "how": f"نص القرآن ({f['suras']} سورة، {f['verses']} آية) من التنزيلات الرسمية لـ Quranpedia.net، النسخة {f['quran_version']}، رواية حفص: "
                "ملف بالرسم الإملائي للمطابقة، وملف بالرسم العثماني للمطابقة والعرض. لم ننزّل من موقع المجمع.",
         "verify": ("بصمة SHA-256 لكل ملف " + ("مطابقة" if f["quran_ok"] else "<strong>غير مطابقة</strong>") +
                    " لما في manifest المصدر (فحص عند توليد هذه الصفحة)؛ ومطابقة الآيات حرفية برمجية بعد توحيد التشكيل والهمزات، دون نموذج لغوي، مع اختبارات وحدات."),
         "license": "رخصة بيانات Quranpedia: الاستعمال داخل التطبيقات مجاني؛ وإعادة نشر البيانات نفسها تستلزم ذكر Quranpedia.net مع رابطه ورقم النسخة.",
         "limits": f"وصف الملف العثماني في المصدر: «{_esc(q2['description_in_file'])}». ووصف الإملائي: «{_esc(q1['description_in_file'])}». "
                   "الوصفان من المصدر، ولم نطابق النص مع الطبعة المطبوعة مستقلاً. والمطابقة الحرفية لا تحكم على صحة التفسير.",
         "proof": [("data/quran/source.json", None), ("data/quran/LICENSE-quranpedia.md", None),
                   ("miyar/quran_match.py", None), ("tests/test_quran_match.py", None)]},
        {"name": "التفسير", "refs": [("dorar.net/tafseer", "https://dorar.net/tafseer")], "used": False,
         "limits": "مِعيار لا يعرض تفسيراً ولا يحكم على صحة معنى."},
        {"name": "الحديث",
         "refs": [("الصحيحان", None), ("dorar.net/hadith", "https://dorar.net/hadith"), ("shamela.ws", "https://shamela.ws")],
         "used": hadith_used, "partial": f["manual_done"] < f["manual_total"],
         "how": "ملف يدوي يُدخله صاحب المشروع من الدرر السنية أو المكتبة الشاملة: نص الحديث، والمصدر، والرابط، والدرجة منسوبة لقائلها. لا جلب آلي.",
         "verify": "يتحقق برمجياً من بنية كل مدخل: الرابط مقصور على dorar.net أو shamela.ws، والدرجة لا تُقبل بلا قائلها، والمدخل الناقص يبقى «غير مكتمل»؛ مع اختبارات." +
                   ("" if f["manual_valid"] else " <strong>(في الملف أخطاء بنية حالياً)</strong>"),
         "license": "يُنقل نص الحديث مقتبساً مع رابط موضعه في المصدر؛ ولا تُعاد بناء بيانات الموقعين أو تُجلب آلياً.",
         "limits": f"{f['manual_done']} من {f['manual_total']} مدخلات مكتملة حتى الآن. التحقق محدود بهذه المدخلات؛ وغياب المدخل أو نقصه يعني «يحتاج تحقق» لا «خطأ». ومِعيار لا يحكم على حديث بالصحة أو الضعف من عنده.",
         "proof": [("data/hadith/manual_hadith.json", None), ("data/hadith/README.md", None),
                   ("miyar/hadith_manual.py", None), ("tests/test_hadith_manual.py", None)]},
        {"name": "العقيدة", "refs": [("dorar.net/aqeeda", "https://dorar.net/aqeeda")], "used": False,
         "limits": "لا يُعتمد عليه في أي حكم حتى يُدمج ويُوثَّق ترخيصه."},
        {"name": "الفقه", "refs": [("dorar.net/feqhia", "https://dorar.net/feqhia")], "used": False,
         "limits": "لا يُعتمد عليه في أي حكم حتى يُدمج ويُوثَّق ترخيصه."},
        {"name": "السيرة والتاريخ", "refs": [("dorar.net/history", "https://dorar.net/history")], "used": False,
         "limits": "لا يُعتمد عليه في أي حكم حتى يُدمج ويُوثَّق ترخيصه."},
        {"name": "الشبهات", "refs": [("بيّنات dawa.center/file/7937", "https://dawa.center/file/7937")], "used": False,
         "limits": "لا يُعتمد عليه في أي حكم حتى يُدمج ويُوثَّق ترخيصه."},
        {"name": "الترجمة والمصطلحات", "refs": [("موسوعة الجمهرة islamic-content.com/dictionary", "https://islamic-content.com/dictionary")],
         "used": False, "limits": "حالة ترجمة «التوحيد» (OFF-08) لا تستند إليها بعد."},
    ]
    for r in rows:
        if not r["used"]:
            for k, v in UNUSED_ROW.items():
                r.setdefault(k, v)
    return rows


def cell(label: str, value: str) -> str:
    """خلية في سجل المصادر؛ الفارغة («—») تُخفى في عرض البطاقات ويبقى معناها في الجدول."""
    na = ' class="na"' if value == "—" else ""
    return f'<td data-label="{label}"{na}>{value}</td>'


def sources(f: dict) -> str:
    rows = []
    for d in (x for x in domains(f) if x["used"]):  # المجالات غير المستخدمة تُذكر في SOURCES.md لا هنا
        refs = "<br>".join(f'<a class="ltr-mixed" href="{u}">{_esc(t)}</a>' if u else _esc(t) for t, u in d["refs"])
        if not d["used"]:
            status = badge("todo", "لم يُستخدم بعد")
        elif d.get("partial"):
            status = badge("rev", "مستخدم يدوياً — المدخلات غير مكتملة")
        else:
            status = badge("ok", "مستخدم فعلاً")
        proof = "".join(f"<li>{link(p, label)}</li>" for p, label in d["proof"])
        rows.append(
            f'    <tr><th scope="row">{d["name"]}</th><td data-label="المرجع المعتمد في الحزمة">{refs}</td>'
            f'<td data-label="الحالة">{status}</td>{cell("كيف استُخدم", d["how"])}'
            f'{cell("كيف يُتحقق منه", d["verify"])}<td data-label="الترخيص والحقوق">{d["license"]}</td>'
            f'<td data-label="القيود والحدود">{d["limits"]}</td><td data-label="الإثبات في المستودع"><ul class="proof">{proof}</ul></td></tr>')
    n_used = sum(1 for d in domains(f) if d["used"])
    cats = "\n".join(f'    <tr><th scope="row">{name}</th><td data-label="التعريف">{definition}</td></tr>' for name, definition in f["judgements"])
    st = f["state"]
    extract_badge = badge(STATE_BADGE[st["extract"]], STATE_TEXT[st["extract"]])
    quran_badge = badge(STATE_BADGE[st["quran_match"]], STATE_TEXT[st["quran_match"]])
    hadith_badge = badge(STATE_BADGE[st["hadith_match"]], STATE_TEXT[st["hadith_match"]])
    judge_badge = badge(STATE_BADGE[st["judge"]], STATE_TEXT[st["judge"]])
    return f"""
<h1>المصادر والمنهجية</h1>
<p class="lead">المعيار الذي يُقاس عليه المساعد هو <strong>الحزمة العلمية للتحدي</strong>، لا رأي المشروع.
وهذا سجل المصادر التي يستخدمها مِعيار فعلاً: المرجع المعتمد، وكيف استُخدم، ومع رابط الملف الذي يثبت ذلك في المستودع.</p>

<h2 id="registry">سجل المصادر</h2>
<div class="table-wrap" role="region" aria-label="سجل المصادر" tabindex="0"><table class="stack registry">
  <caption>المصادر المستخدمة فعلاً: القرآن والحديث</caption>
  <thead><tr><th scope="col">المجال</th><th scope="col">المرجع المعتمد في الحزمة</th><th scope="col">الحالة</th><th scope="col">كيف استُخدم</th>
  <th scope="col">كيف يُتحقق منه</th><th scope="col">الترخيص والحقوق</th><th scope="col">القيود والحدود</th><th scope="col">الإثبات في المستودع</th></tr></thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table></div>
<p class="notice demo" role="note" id="sources-scope">المرجعية المعتمدة أوسع مما نستخدمه؛ مِعيار يغطي القرآن والحديث فقط، وباقي مجالاتها خارج النطاق الحالي (التفاصيل في {link("SOURCES.md")}).</p>
<p class="muted">«مستخدم» لا يُكتب إلا لما له ملف بيانات وكود في المستودع؛ ويُفحص ذلك عند توليد هذه الصفحة.
وأمثلة الحزمة العلمية ({f["n_off"]} أسئلة) منقولة نصاً في مجموعة الاختبار. التراخيص التفصيلية في {link("SOURCES.md")} و{link("SOURCES_LICENSES.md")}.</p>

<h2 id="judgements">أصناف الحكم ({len(f["judgements"])})</h2>
<p class="section-intro">كل خطأ يرصده مِعيار في إجابة المساعد يُصنَّف في واحد من هذه الأصناف (من {link("docs/BUILD_PLAN.md")}).
الحكم الآلي نفسه {judge_badge}.</p>
<div class="table-wrap" role="region" aria-label="أصناف الحكم" tabindex="0"><table class="stack">
  <caption>أصناف الحكم</caption>
  <thead><tr><th scope="col">الصنف</th><th scope="col">التعريف</th></tr></thead>
  <tbody>
{cats}
  </tbody>
</table></div>

<h2 id="attribution">الإسناد: من النص إلى الحكم</h2>
<div class="grid">
  <section class="card">
    <h3>١. تحديد النص المنسوب {extract_badge}</h3>
    <p>يُستخرج من إجابة المساعد كل نص يُنسب إلى القرآن أو السنة، مع الموضع الذي ذكره المساعد (سورة وآية، أو كتاب ورقم).
    النص الشرعي يُميَّز من الشرح المولَّد، ولا يُحكم على الشرح كأنه نص.</p>
  </section>
  <section class="card">
    <h3>٢. المطابقة مع المصدر</h3>
    <p><strong>الآيات</strong> {quran_badge}: مطابقة برمجية حرفية مع نص Quranpedia بعد توحيد التشكيل والهمزات، دون نموذج لغوي.
    النتيجة واحدة من: مطابقة في الموضع المذكور (<code lang="en">supported</code>)، أو النص في موضع آخر، أو موضع غير موجود،
    أو لفظ محرّف عن الآية المذكورة (<code lang="en">wrong_or_missing</code>)، أو لا تطابق كافٍ (<code lang="en">needs_review</code>).</p>
    <p><strong>الأحاديث</strong> {hadith_badge}: المقارنة مع مدخل الملف اليدوي المعتمد فقط (النص والمصدر والدرجة وقائلها).</p>
  </section>
  <section class="card">
    <h3>٣. متى يمتنع النظام أو يُحيل</h3>
    <ul class="plain">
      <li>لا يصدر «مؤيَّد» أبداً دون مطابقة فعلية في البيانات.</li>
      <li>غياب المرجع، أو مدخل حديث ناقص، أو نص قصير لا يكفي للمطابقة: «يحتاج تحقق»، لا «خطأ».</li>
      <li>عند ضعف ثقة الحَكَم الآلي: لا حكم آلي، وتُحال الحالة إلى مراجعة بشرية.</li>
      <li>في المستوى C يُنتظر من المساعد بيان الخلاف أو الإحالة، وفي D معلومة عامة وإحالة؛ ومِعيار نفسه لا يفتي ولا يرجّح.</li>
    </ul>
  </section>
</div>

<h2 id="method">مبادئ المنهجية</h2>
<ol class="plain">
  <li><strong>مِعيار لا يولّد نصاً شرعياً:</strong> لا آية ولا حديثاً ولا حكماً. كل نص شرعي يعرضه منقول من بيانات لها مصدر مسجّل.</li>
  <li><strong>السلوك حسب المستوى:</strong> يُقارن سلوك المساعد بالسلوك المطلوب لمستوى السؤال في <a href="levels.html">الحزمة العلمية</a>.</li>
  <li><strong>الحَكَم الآلي يطبّق معياراً مكتوباً ولا يضعه</strong>، ونموذج الحكم يختلف عن نموذج المساعد المُختبَر.</li>
  <li><strong>المراجعة:</strong> النوع المعتمد الآن <strong>تحقق المصادر</strong> (<span lang="en" class="ltr">source_check</span>) يجريه المشارك،
    وهو غير متخصص شرعياً، مقابل Quranpedia والدرر السنية والمكتبة الشاملة؛ وهذا <strong>ليس</strong> مراجعة شرعية.
    والمراجعة الشرعية (<span lang="en" class="ltr">specialist</span>) اختيارية؛ وجرت بعد التشغيل الرسمي مراجعة واحدة غير مستقلة لحالة واحدة (OFF-06)، ولا تُحسب حالة «معتمدة شرعياً» إلا بمراجعة مختص مستقل.</li>
  <li><strong>حدود المقارنة بين baseline وrag:</strong> {COMPARISON_CAVEAT}
    والأرقام من عدد محدود من الحالات (N مذكور بجانب كل رقم)، فلا تُعمَّم. والتنبيه نفسه ثابت بجوار المقارنة وقرار البوابة في <a href="results.html">النتائج</a>.</li>
</ol>
<p>التفاصيل في {link("docs/METHODOLOGY.md")}.</p>
"""


# ---------- حالات الاختبار ----------
TYPE_LABELS = {
    None: "مثال من الحزمة العلمية",
    "none": "بلا فخ",
    "conflict_scholars": "خلاف علماء",
    "conflict_sources": "مصدران متعارضان",
    "absent_reference": "غياب المرجع",
    "misquoted_verse": "آية منقولة بخطأ",
    "wrong_reference": "إحالة قرآنية خاطئة",
    "invalid_reference": "مرجع غير موجود",
    "hadith_absent": "منسوب للصحيحين وليس فيهما",
    "hadith_fabricated": "حديث لا يصح يُقدَّم كصحيح",
    "personal_fatwa": "واقعة شخصية",
    "prompt_injection": "حقن أوامر",
}
HANDLING_LABELS = {
    None: "حسب المستوى",
    "direct_answer": "إجابة مباشرة موثقة",
    "sourced_answer": "إجابة مع المرجع",
    "state_disagreement": "بيان الخلاف أو إحالة",
    "abstain_or_refer": "امتناع أو إحالة",
    "correct_and_answer": "تصحيح ثم إجابة",
    "refuse_fabrication": "رفض الاختلاق",
    "general_info_and_referral": "معلومة عامة + إحالة",
    "hold_rules": "الثبات على القواعد",
}


# نص ثابت لحال المراجعة الشرعية (evaluation/review/SPECIALIST_REVIEW_2026-10-05.md)؛ لا يغيّر عدّادات الحالات المجمّدة
SPECIALIST_REVIEW_NOTE = ("المراجعة الشرعية: مراجعة واحدة لحالة واحدة من 12 (OFF-06) أجراها خريج شريعة هو قريب لصاحب المشروع؛ "
                          "لا مراجعة من لجنة مستقلة.")

def source_check_sentence(f: dict) -> str:
    return f"تحقق المصادر (ليس مراجعة شرعية): مقبول {f['review']['approved']['source_check']} من {f['n']}."


def review_badge(c: dict) -> str:
    status, role = c.get("review_status"), c.get("reviewer_role")
    if status == "approved" and role == "specialist":
        return badge("ok", "معتمدة شرعياً")
    if status == "approved" and role == "source_check":
        return badge("rev", "راجعها صاحب المشروع (تحقق مصادر)")
    if status == "rejected":
        return badge("bad", "مرفوضة")
    return ""  # غير المراجَعة بلا شارة؛ وعدد المراجَعة في أعلى القائمة


def cases_page(f: dict) -> str:
    rows = []
    for c in f["cases"]:
        t = c.get("risk_type")
        tl = TYPE_LABELS.get(t, t)
        hl = HANDLING_LABELS.get(c.get("handling"), c.get("handling"))
        search = _attr(f'{hl} {c["expected_behavior"]}')
        # فهرس: يُعرض ما يلزم لاختيار الحالة؛ والسلوك المتوقع وآلية المعالجة في صفحة الحالة، ويبقيان قابلين للبحث (data-search)
        rows.append(
            f'    <tr data-level="{_attr(c["level"])}" data-type="{_attr(tl)}" data-search="{search}">'
            f'<th scope="row"><a class="mono case-link" href="case.html?id={_attr(c["id"])}">{_esc(c["id"])}</a></th>'
            f'<td data-label="المستوى"><span class="badge b-level" lang="en">{_esc(c["level"])}</span></td>'
            f'<td data-label="نوع الحالة">{_esc(tl)}</td>'
            f'<td data-label="حرجة">{"نعم" if c.get("critical") else "لا"}</td>'
            f'<td data-label="المراجعة">{review_badge(c)}</td></tr>')
    types = sorted({TYPE_LABELS.get(c.get("risk_type"), c.get("risk_type")) for c in f["cases"]})
    type_opts = "".join(f'<option value="{_attr(t)}">{_esc(t)}</option>' for t in types)
    lvl_opts = "".join(f'<option value="{k}">{k}</option>' for k in sorted(f["levels"]))
    s = f["review"]
    return f"""
<h1>حالات الاختبار</h1>
<p class="lead">{f["n"]} حالة اختُبرت منها {f["n_tested"]} رسمياً <span class="muted">({f["n_off"]} من أمثلة الحزمة العلمية + {f["n_ext"]} إضافية)</span>.</p>
<details class="tech"><summary>مصدر البيانات (ملفات المستودع)</summary>
  <p>تُقرأ الحالات من {link("testsets/official_v0.json")} و{link("testsets/extended_v1.json")} عند توليد هذه الصفحة.</p>
</details>
<div class="notice">
  <p><strong>لا حكم ولا نتيجة هنا.</strong> فهرس الحالات وما يُنتظر من المساعد، لا ما أجاب به. اضغط معرّف الحالة لسؤالها وسلوكها المتوقع وما سُجّل لها.</p>
  <details class="tech"><summary>لماذا لا يظهر نص السؤال هنا؟</summary>
  <p>بعض الأسئلة تتضمن عمداً آيات منقولة بخطأ أو أحاديث لا تصح لاختبار المساعد؛ فتعرضها صفحة الحالة مع تنبيه الفخ والنص الصحيح من البيانات.
  والسلوك المتوقع مسودة من إعداد المشروع.</p>
  </details>
</div>

<form class="filters" role="search" aria-label="بحث وتصفية الحالات">
  <div><label for="q">بحث</label><input id="q" type="search" placeholder="بالمعرّف أو السلوك المتوقع…" autocomplete="off"></div>
  <div><label for="lv">المستوى</label><select id="lv"><option value="">كل المستويات</option>{lvl_opts}</select></div>
  <div><label for="ty">نوع الحالة</label><select id="ty"><option value="">كل الأنواع</option>{type_opts}</select></div>
</form>
<p class="review-line" id="review-line"><strong>المراجعة البشرية: {s["approved"]["source_check"] + s["approved"]["specialist"]} من {f["n"]} حالة</strong>
<span class="muted small">— مراجعة لتعريف الحالات وسلوكها المتوقع (تحقق مصادر)، لا لأحكام مِعيار.</span></p>
<p class="count" id="count" aria-live="polite">يُعرض {f["n"]} من {f["n"]} حالة.</p>

<div class="table-wrap" role="region" aria-label="جدول حالات الاختبار" tabindex="0"><table class="stack" id="cases" data-total="{f["n"]}">
  <caption>حالات الاختبار</caption>
  <thead><tr><th scope="col">المعرّف</th><th scope="col">المستوى</th><th scope="col">نوع الحالة</th><th scope="col">حرجة</th><th scope="col">المراجعة</th></tr></thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table></div>
<div class="notice empty" id="no-match" role="status" hidden><strong>لا حالات تطابق البحث أو التصفية</strong>
<span>جرّب كلمة أخرى، أو اختر «كل المستويات» و«كل الأنواع».</span></div>
"""


# ---------- تفصيل الحالة (S2) ----------
CASES_JSON = WEB / "data/testcases.json"
# فخاخ مقصودة: يُسبق نص السؤال بتنبيه، ويُعرض بجانبه النص الصحيح من البيانات (BUILD_SPEC S2)
TRAP_TYPES = {"misquoted_verse", "wrong_reference", "invalid_reference", "hadith_absent", "hadith_fabricated"}
TRAP_WARNING = "هذا السؤال يتضمن عمداً نصاً محرّفاً أو لا يصح، لاختبار المساعد."
CITATION_STATUS_LABELS = {"supported": "مؤيَّد", "needs_review": "يحتاج تحقق", "wrong_or_missing": "خاطئ أو غير موجود"}


def _quran_reference(ref: dict, index) -> dict | None:
    if ref.get("type") != "quran":
        return None
    verses = index.verses_range(ref["sura"], ref["aya"], ref.get("aya_end") or ref["aya"])
    if not verses:
        return None
    aya = str(ref["aya"]) if not ref.get("aya_end") or ref["aya_end"] == ref["aya"] else f'{ref["aya"]}–{ref["aya_end"]}'
    # الرسم الإملائي المضبوط (mushafs-1) للعرض هنا: علامات الرسم العثماني الصغيرة لا تظهر في كثير من خطوط الجوال
    return {"kind": "quran", "ref": f'{verses[0].sura_name} {ref["sura"]}:{aya}', "text": " ".join(v.text_simple for v in verses),
            "source": "Quranpedia.net (النسخة 2026-10-01، mushafs-1 بالرسم الإملائي)"}


def _hadith_reference(entry_id: str, manual: dict) -> dict:
    e = manual.get(entry_id) or {}
    if not e or entry_status(e) != "complete":
        return {"kind": "hadith", "ref": entry_id, "pending": True,
                "note": "مدخل الملف اليدوي ناقص؛ لا يُعرض نص ولا حكم حتى يكتمل من الدرر السنية أو المكتبة الشاملة."}
    out = {"kind": "hadith", "ref": entry_id, "pending": False, "entry_kind": e["kind"], "link": e.get("link")}
    if e["kind"] == "found":
        out.update(text=e["text"], source=e["source"], grade=e["grade"], grade_by=e["grade_by"])
    elif e["kind"] == "not_found":
        out.update(query=e["query"], searched_in=e["searched_in"])
    else:
        out.update(source=e["source"], max_number=e["max_number"])
    return out


def case_records(f: dict) -> dict:
    """بيانات صفحة تفصيل الحالة: من testsets/ والبيانات المعتمدة فقط، بلا أي نتيجة (النتائج من web/data/cases/ وحدها)."""
    from miyar.hadith_match import pending_entries_for_case
    from miyar.judge import CATEGORIES
    from miyar.publish import MASK_WHILE_PENDING, MASKED_TEXT
    from miyar.quran_match import QuranIndex

    index = QuranIndex.load()
    manual_doc = load_manual()
    manual = {e["id"]: e for e in manual_doc["entries"]}
    check_desc, level_desc = {}, {}
    for p in TESTSETS:
        doc = json.loads(p.read_text(encoding="utf-8"))
        check_desc.update(doc.get("checks", {}))
        level_desc.update(doc.get("levels", {}))
    cases = []
    for c in f["cases"]:
        masked = c["id"] in MASK_WHILE_PENDING and bool(pending_entries_for_case(c["id"], manual_doc))
        refs = []
        if c.get("misquote"):
            refs.append(_quran_reference(c["misquote"]["correct_ref"], index))
        elif c.get("risk_type") in ("wrong_reference",):
            refs += [_quran_reference(r, index) for r in c.get("reference_hints", [])]
        if (c.get("data_check") or {}).get("manual_ref"):
            refs.append(_hadith_reference(c["data_check"]["manual_ref"], manual))
        cases.append({
            "id": c["id"], "testset": "official_v0" if c["id"].startswith("OFF-") else "extended_v1",
            "level": c["level"], "level_behavior": level_desc.get(c["level"], ""),
            "type": TYPE_LABELS.get(c.get("risk_type"), c.get("risk_type")),
            "handling": HANDLING_LABELS.get(c.get("handling"), c.get("handling")),
            "critical": bool(c.get("critical")),
            "prompt": None if masked else c["prompt"], "prompt_masked": masked,
            "trap": bool({c.get("risk_type"), c.get("category"), (c.get("data_check") or {}).get("type")} & TRAP_TYPES),
            "injected_context": c.get("injected_context"),
            "expected_behavior": c["expected_behavior"],
            "checks": [{"name": k, "description": check_desc.get(k, "")} for k in c.get("checks", [])],
            "review": {"status": c.get("review_status"), "role": c.get("reviewer_role")},
            "references": [r for r in refs if r],
        })
    return {
        "schema_version": 1,
        "note": "حالات الاختبار كما في testsets/، والنص الصحيح من البيانات المعتمدة؛ لا نتائج هنا.",
        "trap_warning": TRAP_WARNING, "masked_text": MASKED_TEXT,
        "specialist_reviews": f["review"]["approved"]["specialist"],
        "citation_status_labels": CITATION_STATUS_LABELS, "categories": dict(CATEGORIES),
        "cases": cases,
    }


CASE_PAGE = """
<h1>تفصيل الحالة</h1>
<p class="lead">السؤال، والسلوك المتوقع، وما سجّله التشغيل الرسمي. كل نص شرعي منقول من البيانات المعتمدة، وكل حكم من سجل رسمي.</p>
<p class="back"><a href="cases.html">← كل الحالات</a> · <a href="results.html">النتائج والمقارنة</a></p>
<div id="case" aria-live="polite">
  <div class="notice empty"><strong>جارٍ التحميل…</strong></div>
</div>
<noscript><div class="notice empty"><strong>تحتاج هذه الصفحة إلى JavaScript لقراءة بيانات الحالة.</strong></div></noscript>
"""


# ---------- الحالة ----------
def _rounds(n: int) -> str:
    return {1: "جولة واحدة", 2: "جولتان"}.get(n, f"{n} جولات" if n <= 10 else f"{n} جولة")


def redteam_item(f: dict) -> tuple:
    """Red Teaming: لا وحدة تشغيل مستقلة (miyar/redteam.py)، فلا يُحتسب مكتملاً. «مؤجَّل خارج نطاق التسليم»؛ والحالات العدائية
    الموجودة فعلاً في testsets/ تُذكر بأعدادها المحسوبة منها، وتُقاس بالمشغّل والحَكَم كباقي الحالات عند اختيارها."""
    if f["state"]["redteam"] == "built":
        return ("وحدة Red Teaming", True, "miyar/redteam.py")
    rt = f["red_team"]
    text = "مؤجَّل خارج نطاق التسليم: لا وحدة تشغيل مستقلة."
    if rt["n"]:
        in_prompt = rt["n"] - rt["in_context"]
        official = ("لم تدخل التشغيلات الرسمية (كلها على official_v0)" if rt["in_official"] == 0
                    else f"منها {rt['in_official']} في official_v0")
        text += (f" في مجموعة الاختبار الموسّعة {rt['n']} حالات بصيغة حقن أوامر ({rt['ids'][0]} إلى {rt['ids'][-1]}: "
                 f"{in_prompt} في السؤال و{rt['in_context']} في نص مرفق مدسوس) تُقاس بالمشغّل والحَكَم كباقي الحالات؛ {official}.")
    return ("وحدة Red Teaming", False, "miyar/redteam.py", False, {"badge": "مؤجَّل", "evidence": text})


def accuracy_item(f: dict) -> tuple:
    """«تشغيل رسمي مسجّل وقياس الدقة»: الدليل المكتوب (evaluation/official/) لا يشمل قياس اتفاق الحَكَم مع الوسوم البشرية،
    فلا يُحتسب مكتملاً: «جاهز جزئياً» بصياغة تذكر ما سُجّل وما لم يُنفَّذ. وقبل أي تشغيل رسمي: «لم يُنفَّذ بعد»."""
    if f["official_runs"] == 0:
        return ("تشغيل رسمي مسجّل وقياس اتفاق أحكام الحَكَم مع الوسوم البشرية", False, "evaluation/official/", False)
    hr = f.get("official_review") or {}
    roles, total = hr.get("by_role") or {}, hr.get("total")
    sc, sp = roles.get("source_check", 0), roles.get("specialist", 0)
    reviewed = (f"المراجعة البشرية: {'حالة واحدة' if sc == 1 else f'{sc} حالات'} من {total} (تحقق مصادر) و{sp} مراجعة شرعية متخصصة (لقطة وقت التشغيل؛ وجرت بعده مراجعة شرعية لاحقة لحالة واحدة: OFF-06)"
                if total else "المراجعة البشرية: لا بيانات")
    text = (f"التشغيل الرسمي مسجّل ({_rounds(f['official_runs'])} مكتملة)؛ قياس اتفاق أحكام الحَكَم مع الوسوم البشرية لم يُنفَّذ، "
            f"وقيس التحقق النصي للاستشهادات القرآنية فقط (Gold Set، غير مستقل)، و{reviewed}؛ وتحقق المصادر مراجعة لتعريف الحالة لا لأحكام مِعيار")
    return (text, False, "evaluation/official/", True)


def status_items(f: dict) -> tuple[list, list]:
    st = f["state"]
    phase0 = [
        ("نص القرآن من Quranpedia ببصمات ملفاته", f["quran_ok"], "data/quran/source.json"),
        ("توحيد النص العربي", st["normalize"] == "built", "miyar/normalize.py"),
        ("مطابقة الآيات حرفياً", st["quran_match"] == "built", "miyar/quran_match.py"),
        ("مجموعة الاختبار موسومة بالمستوى والسلوك المتوقع", f["n"] > 0, "testsets/"),
        ("قالب الملف اليدوي للأحاديث (البنية والتحقق)", f["manual_valid"] and st["hadith_manual"] == "built", "miyar/hadith_manual.py"),
        ("طبقة مزوّد النماذج: نتائج محفوظة وتشغيل حي بسقف", st["llm"] == "built", "miyar/llm.py"),
        ("الموقع الثابت ونظام التصميم", (WEB / "assets/style.css").exists(), "web/"),
    ]
    phase1 = [
        ("المساعدان المرجعيان (baseline و rag)", st["assistants"] == "built", "miyar/assistants/"),
        ("وحدة تشغيل مجموعة الاختبار وحفظ سجل التشغيل (runner)", st["runner"] == "built", "miyar/runner.py"),
        ("استخراج الاستشهادات من الإجابات" + (" (الآيات جاهزة؛ الأحاديث لم تُبنَ)" if st["extract"] == "partial" else ""),
         st["extract"] == "built", "miyar/extract.py"),
        ("مطابقة الأحاديث مع الملف اليدوي", st["hadith_match"] == "built", "miyar/hadith_match.py"),
        ("حكم السلوك حسب المستوى A–D" + (("" if st["judge"] != "partial" else
                                          " (حكم إسناد الآيات والأحاديث وحكم السلوك الأولي بالثقة والإحالة جاهزة؛ "
                                          "أصناف الحكم الستة لم تُبنَ)" if st["hadith_match"] == "built" else
                                          " (حكم إسناد الآيات وحكم السلوك الأولي بالثقة والإحالة جاهزان؛ "
                                          "الأحاديث وأصناف الحكم الستة لم تُبنَ)")),
         st["judge"] == "built", "miyar/judge.py"),
        ("وحدة حساب الدرجة والمقارنة وقرار البوابة (scoring)", st["scoring"] == "built", "miyar/scoring.py"),
        ("لوحة النتائج والمقارنة (تشغيلات منشورة)", f["published_runs"] > 0, "web/data/results.json"),
        accuracy_item(f),
        redteam_item(f),
    ]
    return phase0, phase1


def checklist(items) -> str:
    """بنود الحالة: الشارة والنص ظاهران، وأسماء الملفات وأدلتها في طبقة مطوية «التفاصيل التقنية» (لا تُحذف).
    الصياغة المخصّصة لبند (مثل «مؤجَّل خارج نطاق التسليم…») تبقى ظاهرة لأنها جزء من معناه."""
    out, tech = [], []
    for text, done, evidence, *rest in items:
        partial = bool(rest and rest[0]) and not done
        custom = rest[1] if len(rest) > 1 else None  # صياغة مخصّصة للشارة والدليل (مثل «مؤجَّل»)
        b = (badge("ok", "اكتمل") if done else badge("todo", custom["badge"]) if custom else
             badge("rev", "جاهز جزئياً") if partial else badge("todo", "لم يُنفَّذ بعد"))
        shown = f'<span class="evidence">{_esc(custom["evidence"])}</span>' if custom else ""
        out.append(f'  <li>{b}<span class="what">{text}</span>{shown}</li>')
        ev = (f"الدليل: {link(evidence)}" if (ROOT / evidence).exists()
              else f'الملف <span class="mono">{_esc(evidence)}</span> غير موجود بعد')
        tech.append(f'    <li><span class="what">{text}</span><span class="evidence">{ev}</span></li>')
    return ('<ul class="checklist">\n' + "\n".join(out) + "\n</ul>\n"
            '<details class="tech"><summary>التفاصيل التقنية (الملفات والأدلة)</summary>\n'
            '  <ul class="checklist tech-list">\n' + "\n".join(tech) + "\n  </ul>\n</details>")


def progress(label: str, done: int, total: int, pid: str) -> str:
    return f"""<div class="progress-block">
  <div class="progress-head"><span id="{pid}">{label}</span><span>{done} من {total}</span></div>
  <progress value="{done}" max="{total}" aria-labelledby="{pid}">{done} من {total}</progress>
</div>"""


def status(f: dict) -> str:
    p0, p1 = status_items(f)
    d0, d1 = sum(1 for i in p0 if i[1]), sum(1 for i in p1 if i[1])
    s, n = f["review"], f["n"]
    runs = ("<strong>لا توجد نتائج تقييم رسمية بعد.</strong> لم يُسجَّل أي تشغيل رسمي في المستودع "
            f"(سجلات التشغيل الرسمية: {f['official_runs']})." if f["official_runs"] == 0 else
            f"سجلات التشغيل الرسمية: {f['official_runs']}.")
    return f"""
<h1>الحالة</h1>
{status_card(f)}
<div class="notice">
  <p>{runs} كل بند أدناه محسوب من ملفات المستودع عند توليد الصفحة.</p>
</div>

<section class="sec status-sec" aria-labelledby="st-base">
<h2 id="st-base">قبل أيام التحدي: الأساس</h2>
<div class="card">
{progress("الأساس (البنية التحتية والبيانات والموقع)", d0, len(p0), "pg0")}
{checklist(p0)}
</div>
</section>

<section class="sec status-sec" aria-labelledby="st-core">
<h2 id="st-core">أيام التحدي: 4–6 أكتوبر 2026</h2>
<p class="section-intro">بترتيب البناء الملزم: لا انتقال إلى بند قبل أن يعمل سابقه.</p>
<div class="card">
{progress("نواة التقييم والنتائج", d1, len(p1), "pg1")}
{checklist(p1)}
</div>
</section>

<section class="sec status-sec" aria-labelledby="st-data">
<h2 id="st-data">البيانات والمراجعة</h2>
<div class="card">
{progress("مدخلات الملف اليدوي للأحاديث المكتملة", f["manual_done"], f["manual_total"], "pg2")}
{progress("حالات تحقق المصادر المقبولة (النوع المعتمد الآن)", s["approved"]["source_check"], n, "pg3")}
<p>{SPECIALIST_REVIEW_NOTE} التحقق الحالي <strong>تحقق مصادر</strong> (<span lang="en" class="ltr">source_check</span>) يجريه المشارك،
وهو غير متخصص شرعياً، مقابل نص القرآن من Quranpedia.net والأحاديث من الدرر السنية أو المكتبة الشاملة (الملف اليدوي).
وهو مراجعة لتعريف الحالات (مصادرها ومستواها)، لا لأحكام مِعيار على إجابات المساعد.
<strong>وتحقق المصادر ليس مراجعة شرعية متخصصة.</strong> والمراجعة الشرعية المتخصصة اختيارية، ولم تُجرَ لبقية الحالات.</p>
</div>
</section>

<section class="sec status-sec" aria-labelledby="st-limits">
<h2 id="st-limits">حدود معروفة</h2>
<ul class="plain">
  <li>التحقق من الأحاديث محدود بما في الملف اليدوي؛ غياب المدخل أو نقصه يعني «يحتاج تحقق»، لا «غير صحيح».</li>
  <li>نص القرآن العثماني المعروض «غير موافق للمطبوع» بحسب وصف ملفه في المصدر؛ وتحديث النسخة يدوي مع تسجيله.</li>
  <li>الحكم الآلي قد يخطئ، وهو مساعد للمراجعة البشرية لا بديل عنها؛ والمراجعة البشرية المسجّلة وقت التشغيل تحقق مصادر فقط (0 مراجعة شرعية متخصصة في لقطة التشغيل)، وجرت بعده مراجعة شرعية لاحقة لحالة واحدة (OFF-06).</li>
</ul>
</section>
"""


# ---------- الشفافية والخصوصية ----------
def transparency(f: dict) -> str:
    return """
<h1>الشفافية والخصوصية</h1>

<h2>أداة مدعومة بالذكاء الاصطناعي، وليست مختصاً شرعياً</h2>
<div class="notice">
  <p><strong>مِعيار ليس عالماً ولا مفتياً.</strong> هو أداة برمجية مدعومة بالذكاء الاصطناعي تختبر المساعدات الذكية،
  و<strong>لا تُصدر فتوى ولا حكماً شرعياً</strong>، ولا تجيب عن الأسئلة الدينية. لأي مسألة شخصية راجع أهل العلم والجهات المختصة.</p>
</div>

<h2>حدود الأداة</h2>
<ul class="plain">
  <li>لا يولّد آية ولا حديثاً ولا حكماً، ولا يصحح نصاً من عنده.</li>
  <li>لا يرجّح في مسائل الخلاف، ولا يحكم على حديث بالصحة أو الضعف.</li>
  <li>المطابقة الحرفية تكشف النقل المحرّف والإحالة الخاطئة، لكنها لا تحكم على صحة التفسير أو المعنى.</li>
  <li>فحص السلوك يعتمد على نموذج لغوي <strong>قد يخطئ</strong>؛ لذلك الحكم الآلي مساعد للمراجعة البشرية لا بديل عنها.</li>
  <li>{SPECIALIST}</li>
</ul>

<h2>الإفصاح عن أدوات الذكاء الاصطناعي</h2>
<div class="table-wrap" role="region" aria-label="جدول أدوات الذكاء الاصطناعي" tabindex="0"><table class="stack">
  <caption>أدوات الذكاء الاصطناعي في المشروع</caption>
  <thead><tr><th scope="col">الأداة</th><th scope="col">الاستخدام</th><th scope="col">الحالة</th></tr></thead>
  <tbody>
    <tr><th scope="row" lang="en">Claude Code</th><td data-label="الاستخدام">كتابة الكود والاختبارات والتوثيق في أثناء التطوير</td><td data-label="الحالة">استُخدم فعلاً</td></tr>
    <tr><th scope="row" lang="en">Claude</th><td data-label="الاستخدام">التخطيط والتطوير</td><td data-label="الحالة">استُخدم فعلاً</td></tr>
    <tr><th scope="row" lang="en">Gemini <span class="mono">gemini-3.5-flash-lite</span></th><td data-label="الاستخدام"><strong>المساعد المُختبَر</strong> داخل المنتج (baseline وrag)</td><td data-label="الحالة">استُدعي فعلاً في التشغيل الرسمي وتشغيلات التطوير؛ <strong>لا يستدعيه الموقع</strong></td></tr>
    <tr><th scope="row" lang="en">Groq <span class="mono">openai/gpt-oss-120b</span></th><td data-label="الاستخدام"><strong>استخراج الإسنادات وحكم السلوك</strong> داخل المنتج، عبر واجهة متوافقة مع OpenAI، بلا نموذج احتياط</td><td data-label="الحالة">استُدعي فعلاً في التشغيل الرسمي؛ <strong>لا يستدعيه الموقع</strong></td></tr>
  </tbody>
</table></div>
<p>هذا الموقع ثابت ولا يستدعي أي نموذج لغوي. ومطابقة الآيات برمجية حرفية دون أي نموذج لغوي.</p>
<p>وضع التشغيل الحي موجود في المحرك عبر سطر الأوامر وغير متاح من الموقع؛ الموقع يعرض نتائج محفوظة من تشغيلات رسمية.</p>

<h2>الخصوصية</h2>
<ul class="plain">
  <li><strong>لا نجمع بياناتك الشخصية:</strong> لا حسابات، ولا نماذج إرسال، ولا ملفات تعريف ارتباط، ولا أدوات تحليلات أو تتبع.
    مربع البحث في صفحة الحالات يعمل داخل متصفحك فقط ولا يُرسل شيئاً.</li>
  <li>لا خطوط ولا مكتبات من مواقع خارجية؛ سياسة أمان المحتوى تمنع تحميل أي مورد من خارج الموقع.</li>
  <li>الموقع مستضاف على Cloudflare Workers، وقد يعالج مزوّد الاستضافة بيانات تقنية لازمة لتقديم الصفحات (مثل عنوان IP) وفق سياسته؛ ولم نفعّل أي أداة تحليلات.</li>
  <li>حالات الاختبار اصطناعية، ولا تُستخدم محادثات حقيقية لأي مستفيد.</li>
  <li>لا مفاتيح ولا أسرار في الموقع ولا في المستودع؛ إعدادات المزوّد في متغيرات بيئة على الخادم فقط.</li>
</ul>
"""


# ---------- «ماذا اكتشف مِعيار؟» (يُشتق آلياً من السجلات الرسمية، قراءة فقط) ----------
CIT_REASON_LABELS = {"exact_match": "مطابقة حرفية لموضعها", "location_not_stated": "لم يُذكر الموضع",
                     "no_manual_entry": "لا مدخل له في الملف اليدوي", "altered_text": "نص يختلف عن الموضع المذكور"}
REFERRAL_REASON_LABELS = {"hadith_unverified": "حديث لا بيانات تحسم وجوده", "low_confidence": "ثقة الحَكَم منخفضة",
                          "manual_entry_pending": "مدخل الحديث ناقص"}


def _run_short(run_id: str) -> str:
    return "-".join(run_id.split("-")[-2:])  # baseline-3 من official-2026-10-04-baseline-3


def _one_letter_diff(a: str, b: str) -> tuple[str, str] | None:
    """إن اختلف النصان بعد التوحيد في حرف واحد فقط (إبدال) يعيد الحرفين؛ وإلا None."""
    a, b = normalize(a), normalize(b)
    if len(a) != len(b):
        return None
    diffs = [(x, y) for x, y in zip(a, b) if x != y]
    return diffs[0] if len(diffs) == 1 else None


GOLD_QURAN = ROOT / "evaluation/gold/quran/agreement.json"


def gold_quran_facts() -> dict | None:
    """نتيجة Gold Set المقفلة (evaluation/gold/quran/agreement.json، قراءة فقط): تحقق بشري نصي للاستشهادات القرآنية."""
    if not GOLD_QURAN.exists():
        return None
    g = json.loads(GOLD_QURAN.read_text(encoding="utf-8"))
    by = g["by_automated_verdict"]
    return {"n": g["counts"]["n_items"], "cd": g["n_cannot_determine_excluded"],
            **{k: (by[k]["agree"], by[k]["of"]) for k in ("supported", "needs_review", "wrong_or_missing")},
            "off03_note": any("OFF-03" in n for n in g.get("notes", []))}


def gold_sentence(gf: dict | None) -> str:
    """جملة واحدة متسقة لحال اتفاق أحكام مِعيار مع تقييم بشري، بالأعداد والمقامات ودون نسب."""
    if not gf:
        return "صحة هذه الأحكام نفسها، أي اتفاقها مع تقييمات بشرية معتمدة: لم يُقَس بعد."
    s, w, r = gf["supported"], gf["wrong_or_missing"], gf["needs_review"]
    return (f"<a href=\"{BLOB}evaluation/gold/README.md\">تحقق بشري نصي للآيات</a> (صاحب المشروع، غير مستقل، ليس مراجعة شرعية): "
            f"وافق {s[0]} من {s[1]} «مؤيَّد»، و{w[0]} من {w[1]} «خاطئ»، و{r[0]} من {r[1]} «يحتاج تحقق».")


GOLD_KEY = ROOT / "evaluation/gold/quran/key.json"
GOLD_LABELS = ROOT / "evaluation/gold/quran/labels.json"
CRITICAL_PHRASE = "«مؤيَّد» خاطئ في الحالات الحرجة: {w} من {n} — تحقق نصي غير مستقل، للآيات فقط"


def critical_supported_facts() -> dict | None:
    """«مؤيَّد» خاطئ في الحالات الحرجة، محسوباً من الملفات المقفلة (قراءة فقط):
    الحالات الحرجة من web/data/testcases.json، وأحكام «مؤيَّد» من evaluation/official/، والتحقق البشري النصي
    من Gold Set (key.json وlabels.json). None إن لم يوجد Gold Set، أو وُجد «مؤيَّد» لحديث في حالة حرجة (لا تحقق بشري له)،
    أو كان أي «مؤيَّد» حرج غير مُراجَع."""
    if not (GOLD_KEY.exists() and GOLD_LABELS.exists()):
        return None
    critical = {c["id"] for c in json.loads(CASES_JSON.read_text(encoding="utf-8"))["cases"] if c.get("critical")}
    status = {}
    for p in sorted(OFFICIAL_RUNS.glob("official-*.json")):
        run = json.loads(p.read_text(encoding="utf-8"))
        for case in run["cases"]:
            for i, cit in enumerate((case.get("judgement") or {}).get("citations") or []):
                status[(run["run_id"], case["id"], i)] = (cit["citation"]["kind"], cit["status"])
    sup = {k for k, (kind, st) in status.items() if k[1] in critical and st == "supported"}
    if any(status[k][0] != "quran" for k in sup):
        return None
    key = {(k["run_id"], k["case_id"], k["citation_index"]): k["item_id"]
           for k in json.loads(GOLD_KEY.read_text(encoding="utf-8"))["items"]}
    labels = {x["item_id"]: x for x in json.loads(GOLD_LABELS.read_text(encoding="utf-8"))["labels"]}
    verdicts = [labels.get(key.get(k), {}) for k in sup]
    if any(v.get("review_status") != "approved" or v.get("human_verdict") == "cannot_determine" for v in verdicts):
        return None
    return {"wrong": sum(v["human_verdict"] != "matches_at_location" for v in verdicts), "n": len(verdicts)}


def critical_sentence(cf: dict | None) -> str:
    return CRITICAL_PHRASE.format(w=cf["wrong"], n=cf["n"]) + "." if cf else ""


def discovered_facts() -> dict:
    """أحكام مِعيار المسجلة في evaluation/official/ (لا تُعدَّل)، معدودة آلياً مع مقاماتها."""
    runs = sorted((json.loads(p.read_text(encoding="utf-8")) for p in OFFICIAL_RUNS.glob("*.json")
                   if not p.name.endswith(".schema.json")), key=lambda r: r["run_id"])
    out = {"runs": [], "answers": 0, "with_citations": 0, "cit": Counter(), "reasons": Counter(),
           "wrong": [], "referrals": [], "referral_reasons": Counter()}
    for r in runs:
        per = Counter()
        for c in r["cases"]:
            j = c.get("judgement") or {}
            out["answers"] += 1
            cits = j.get("citations") or []
            out["with_citations"] += bool(cits)
            per["with_citations"] += bool(cits)
            if j.get("needs_human_review"):
                out["referrals"].append((c["id"], _run_short(r["run_id"])))
                out["referral_reasons"][j.get("review_reason")] += 1
                per["referrals"] += 1
            for x in cits:
                k, st = x["citation"]["kind"], x["status"]
                out["cit"][(k, st)] += 1
                out["reasons"][(k, st, x.get("reason"))] += 1
                per[(k, st)] += 1
                if st == "wrong_or_missing":
                    out["wrong"].append({"case": c["id"], "run": _run_short(r["run_id"]), "reason": x.get("reason"),
                                         "letters": _one_letter_diff(x["citation"]["quote"], x.get("matched_text") or "")})
        out["runs"].append((_run_short(r["run_id"]), len(r["cases"]), per))
    return out


def _case_link(cid: str) -> str:
    return f'<a class="mono" href="case.html?id={_attr(cid)}">{_esc(cid)}</a>'


def _grouped(pairs: list) -> str:
    """OFF-03 (baseline-2، baseline-3)، OFF-02 (baseline-3) — مرتبة بالمعرّف."""
    by = {}
    for cid, run in pairs:
        by.setdefault(cid, []).append(run)
    runs = lambda rs: "، ".join(f'<span class="ltr" lang="en">{_esc(r)}</span>' for r in rs)  # noqa: E731 — كل اسم معزول الاتجاه
    return "، ".join(f"{_case_link(cid)} (في {runs(rs)})" for cid, rs in sorted(by.items()))


VERDICT_SEGMENTS = (("supported", "v-ok", "مؤيَّد"), ("needs_review", "v-rev", "يحتاج تحقق"), ("wrong_or_missing", "v-bad", "خاطئ أو غير موجود"))


def verdict_chart(q: dict, h: dict) -> str:
    """رسم أحكام الاستشهادات (الأعداد نفسها في القائمة فوقه): شريط لكل نوع، وعرض كل جزء بعدده (يضبطه results.js من data-n
    لأن سياسة CSP تمنع style المضمّن). الجزء الذي عدده صفر لا يُرسم."""
    def row(label: str, counts: dict) -> str:
        segs = "".join(f'<span class="{cls}" data-n="{counts[st]}" title="{name}: {counts[st]}">{counts[st]}</span>'
                       for st, cls, name in VERDICT_SEGMENTS if counts[st])
        return (f'<div class="verdict-row"><span class="chart-label">{label} ({sum(counts.values())})</span>'
                f'<div class="verdict-bar chart-plot-v" data-budget="data" role="img" aria-label="{label}: '
                + "، ".join(f"{counts[st]} {name}" for st, _, name in VERDICT_SEGMENTS) + f'">{segs}</div></div>')
    legend = "".join(f'<li class="{cls}">{name}</li>' for _, cls, name in VERDICT_SEGMENTS)
    return (f'<figure class="chart verdict-chart" id="verdict-chart">{row("الآيات", q)}{row("الأحاديث", h)}'
            f'<ul class="verdict-legend" aria-hidden="true">{legend}</ul></figure>')


def discovered_section(f: dict) -> str:
    d = discovered_facts()
    if not d["runs"]:
        return ""
    n_runs, total = len(d["runs"]), d["answers"]
    per_case = sorted({n for _, n, _ in d["runs"]})
    cit, rs = d["cit"], d["reasons"]
    q = {st: cit[("quran", st)] for st in ("supported", "needs_review", "wrong_or_missing")}
    h = {st: cit[("hadith", st)] for st in ("supported", "needs_review", "wrong_or_missing")}
    n_q, n_h = sum(q.values()), sum(h.values())

    def reasons_of(kind, st):
        items = [(why, n) for (k, s_, why), n in sorted(rs.items(), key=lambda kv: -kv[1]) if k == kind and s_ == st]
        return "، ".join(f"{n} {CIT_REASON_LABELS.get(why, why)}" for why, n in items)

    wrong_pairs = [(w["case"], w["run"]) for w in d["wrong"]]
    neutral = []
    for cid in sorted({w["case"] for w in d["wrong"]}):
        ws = [w for w in d["wrong"] if w["case"] == cid]
        letters = {w["letters"] for w in ws}
        if len(ws) > 1 and len(letters) == 1 and None not in letters:
            a, b = next(iter(letters))
            reason = ws[0]["reason"]
            neutral.append(f"في سجلي {_esc(cid)} صُنّف الفرق <span class=\"ltr\" lang=\"en\">wrong_or_missing / {_esc(reason)}</span>؛ "
                           f"والفرق المرصود حرف واحد ({_esc(a)}/{_esc(b)}). "
                           + ("وأكّده التحقق البشري النصي دون حسم أهو خطأ أم وجه رسم أو قراءة."
                              if (gold_quran_facts() or {}).get("off03_note")
                              else "لم يُراجع هذا الحكم بشريًا، لذلك لا يُستدل منه وحده على صحة الحكم أو خطئه."))
    neutral_html = "".join(f'<br><span class="muted small">{t}</span>' for t in neutral)

    ref_reasons = "، ".join(REFERRAL_REASON_LABELS.get(k, k) for k in d["referral_reasons"])
    rows = "".join(
        f'<tr><th scope="row" class="ltr" lang="en">{_esc(run)}</th><td data-label="إجابات فيها استشهاد">{per["with_citations"]} من {n}</td>'
        f'<td data-label="آيات: مؤيَّد / يحتاج تحقق / خاطئ أو غير موجود">{per[("quran", "supported")]} / {per[("quran", "needs_review")]} / {per[("quran", "wrong_or_missing")]}</td>'
        f'<td data-label="أحاديث: يحتاج تحقق">{per[("hadith", "needs_review")]}</td>'
        f'<td data-label="أُحيلت إلى مراجعة بشرية">{per["referrals"]} من {n}</td></tr>'
        for run, n, per in d["runs"])
    cases_of = lambda pairs: "، ".join(_case_link(cid) for cid in sorted({c for c, _ in pairs}))  # noqa: E731
    return f"""<section class="sec" id="discovered" aria-labelledby="disc-h">
<h2 id="disc-h">ماذا اكتشف مِعيار في التشغيلات الرسمية؟</h2>
<p class="muted small">{total} إجابة مُقيَّمة ({n_runs} جولات × {"/".join(map(str, per_case))} حالة).</p>
<ul class="disc-list">
  <li><strong>{sum(cit.values())} استشهاداً</strong> استخرجها مِعيار من {d["with_citations"]} إجابة فيها استشهاد (من {total}).</li>
  <li><strong>الآيات ({n_q}):</strong> {q["supported"]} مؤيَّد، و{q["needs_review"]} يحتاج تحقق، و{q["wrong_or_missing"]} خاطئ أو غير موجود في: {cases_of(wrong_pairs)}.{neutral_html}</li>
  <li><strong>الأحاديث ({n_h}):</strong> {h["supported"]} مؤيَّد، و{h["needs_review"]} يحتاج تحقق، و{h["wrong_or_missing"]} خاطئ أو غير موجود. «يحتاج تحقق» لا يعني أن الحديث خاطئ.</li>
  <li><strong>{len(d["referrals"])} إجابات من {total}</strong> أُحيلت إلى مراجعة بشرية ولم تدخل في الدرجة الآلية: {cases_of(d["referrals"])}.</li>
</ul>
{verdict_chart(q, h)}
<p class="muted small" id="gold-line">{gold_sentence(gold_quran_facts())}</p>
<details class="tech"><summary>التفصيل لكل جولة</summary>
<div class="tech-body">
<ul class="disc-list">
  {('<li id="critical-line">' + critical_sentence(critical_supported_facts()) + "</li>") if critical_supported_facts() else ""}
  <li>الآيات: {q["supported"]} مؤيَّد ({reasons_of("quran", "supported")})، و{q["needs_review"]} يحتاج تحقق ({reasons_of("quran", "needs_review")})، و{q["wrong_or_missing"]} خاطئ أو غير موجود ({reasons_of("quran", "wrong_or_missing")}) في: {_grouped(wrong_pairs)}.</li>
  <li>الأحاديث: {h["needs_review"]} يحتاج تحقق ({reasons_of("hadith", "needs_review")}).</li>
  <li>الإحالات ({ref_reasons}): {_grouped(d["referrals"])}.</li>
</ul>
<div class="table-wrap" role="region" aria-label="أحكام مِعيار لكل جولة" tabindex="0"><table class="stack">
  <caption>أحكام مِعيار المسجلة لكل جولة رسمية</caption>
  <thead><tr><th scope="col">الجولة</th><th scope="col">إجابات فيها استشهاد</th><th scope="col">آيات: مؤيَّد / يحتاج تحقق / خاطئ أو غير موجود</th><th scope="col">أحاديث: يحتاج تحقق</th><th scope="col">أُحيلت إلى مراجعة بشرية</th></tr></thead>
  <tbody>{rows}</tbody>
</table></div>
<p class="muted small">{COMPARISON_CAVEAT} فلا يُستدل بالفرق بين الجولات على أن أحد المساعدين أفضل.</p>
</div>
</details>
<p class="more"><a href="replay.html">أعد عرض حالة خطوة بخطوة</a></p>
</section>"""


RESULTS_EMPTY_NOTE = """<div class="notice demo" role="note">
  <p><strong>للعرض فقط: هذه ليست نتائج تقييم رسمية.</strong>
  وضع «نتائج محفوظة» يعرض ملف نتائج محفوظاً مسبقاً دون أي استدعاء لنموذج لغوي، وهو <strong>فارغ حالياً</strong>:
  لا نتائج تقييم رسمية فيه، ولا بيانات تجريبية مصطنعة.</p>
  <p><strong>التقييم الرسمي يبدأ 4 أكتوبر 2026</strong> (أيام التحدي 4–6 أكتوبر)، ولا يُعرض هنا بعده إلا ناتج تشغيل رسمي
  مسجّل في <span class="ltr" lang="en">evaluation/official/</span> مع عدد الحالات (N)، يحسبه سكربت النشر من سجلاته.</p>
</div>"""

# عند وجود نتائج منشورة تُعرض بطاقة واحدة يصنعها results.js بعدد الجولات (جولة/جولتان/جولات)؛ فلا بطاقة ثابتة هنا
RESULTS_PUBLISHED_NOTE = ""


def results_page(f: dict) -> str:
    note = RESULTS_PUBLISHED_NOTE if f["published_runs"] else RESULTS_EMPTY_NOTE
    return f"""
<h1>النتائج</h1>{note}
<div id="results" aria-live="polite">
  <div class="notice empty"><strong>جارٍ التحميل…</strong></div>
</div>
<noscript><div class="notice empty"><strong>لم يُشغَّل أي تقييم رسمي بعد</strong>
<span>(تحتاج هذه الصفحة إلى JavaScript لقراءة ملف النتائج.)</span></div></noscript>
{discovered_section(f) if f["published_runs"] else ""}
"""


def pages(f: dict) -> dict:
    return {
        "index.html": ("مِعيار — اختبار المساعد الذكي في المحتوى الإسلامي", home(f), ""),
        "levels.html": ("مستويات المحتوى — مِعيار", levels(f), ""),
        "sources.html": ("المصادر والمنهجية — مِعيار", sources(f), ""),
        "cases.html": ("حالات الاختبار — مِعيار", cases_page(f), '<script type="module" src="assets/cases.js"></script>\n'),
        "status.html": ("الحالة — مِعيار", status(f), ""),
        "transparency.html": ("الشفافية والخصوصية — مِعيار", transparency(f).replace("{SPECIALIST}", SPECIALIST_REVIEW_NOTE), ""),
        "results.html": ("النتائج — مِعيار", results_page(f), '<script type="module" src="assets/results.js"></script>\n'),
        "case.html": ("تفصيل الحالة — مِعيار", CASE_PAGE, '<script type="module" src="assets/case.js"></script>\n'),
        "project.html": ("عن المشروع — مِعيار", project_page(f), ""),
        "replay.html": ("إعادة عرض تشغيل رسمي — مِعيار", REPLAY_PAGE.replace("{banner}", REPLAY_BANNER),
                        '<script type="module" src="assets/replay.js"></script>\n'),
        "check.html": ("تحقق من نص — مِعيار", CHECK_PAGE.replace("{quran_version}", f["quran_version"]).replace("{examples}", check_examples(f))
                       .replace("{hadith_count}", str(f["manual_done"])),
                       '<script type="module" src="assets/check.js"></script>\n'),
    }


def subnav_html(current: str) -> str:
    """شريط فرعي في صفحات «عن المشروع»: الروابط الأربعة وصفحة المشروع، للتنقل بينها بنقرة."""
    items = [("project.html", "عن المشروع")] + [(h, label) for h, label, _ in ABOUT_PAGES]
    cur = ' aria-current="location"'
    lis = "".join(f'<li><a href="{h}"{cur if h == current else ""}>{label}</a></li>' for h, label in items)
    return f'<nav class="subnav" aria-label="أقسام «عن المشروع»"><ul>{lis}</ul></nav>\n'


def project_page(f: dict) -> str:
    cards = "".join(f'<li><a href="{h}">{label}</a><span>{desc}</span></li>' for h, label, desc in ABOUT_PAGES)
    return f"""
<h1>عن المشروع</h1>
<p class="lead">مِعيار يختبر المساعد الذكي في المحتوى الإسلامي. هذه الصفحات تشرح كيف يعمل وما حدوده وما اكتمل منه.</p>
<ul class="index-list about-list">{cards}</ul>
"""


def nav_html(current: str) -> str:
    current = "project.html" if current in ABOUT_HREFS else current
    items = []
    for href, label in NAV:
        cur = ' aria-current="page"' if href == current else ""
        items.append(f'    <li><a href="{href}"{cur}>{label}</a></li>')
    return "\n".join(items)


def _with_subnav(name: str, html: str) -> str:
    """يضع الشريط الفرعي مباشرة بعد رأس الصفحة في صفحات «عن المشروع» (عدا صفحة المشروع نفسها)."""
    if name not in ABOUT_HREFS or name == "project.html":
        return html
    head, sep, rest = html.partition("</header>\n")
    return head + sep + subnav_html(name) + rest


def page_descriptions(f: dict) -> dict:
    """وصف كل صفحة (meta description وOpen Graph)؛ الأرقام فيه محسوبة من البيانات."""
    about = {h: desc for h, _, desc in ABOUT_PAGES}
    return {
        "index.html": "مِعيار يختبر المساعد الذكي نفسه في المحتوى الإسلامي ويحكم على إجاباته، ولا يجيب هو عن الأسئلة. المسار الرابع: أدوات المعرفة والتحقق.",
        "results.html": "نتائج التشغيلات الرسمية المحفوظة: مقارنة المساعدَين baseline وrag، ودرجة كل مستوى، وقرار البوابة، مع عدد الحالات N.",
        "cases.html": f"{f['n']} حالة اختبار موسومة بمستوى المحتوى A–D والسلوك المتوقع، اختُبرت منها {f['n_tested']} رسمياً.",
        "case.html": "تفصيل حالة اختبار: السؤال، والسلوك المتوقع، وما سُجّل لها في التشغيل الرسمي إن وُجد.",
        "replay.html": "إعادة عرض خطوة بخطوة لتشغيل رسمي محفوظ: السؤال، وإجابة المساعد، والاستشهادات ومطابقتها، وحكم مِعيار وفحوص السلوك والقرار. ليس تشغيلاً حياً.",
        "check.html": "تحقق من آية أو حديث تلصقه: مطابقة حرفية داخل متصفحك مع نص القرآن والملف اليدوي للأحاديث، دون نموذج لغوي.",
        "project.html": "عن مِعيار: مستويات المحتوى، والمصادر والمنهجية، والشفافية والخصوصية، والحالة.",
        **about,
    }


# أيقونة الموقع مضمّنة (SVG بنجمة الشعار)، وأيقونة الشاشة الرئيسية PNG مضمّنة من scripts/apple-touch-icon.png
FAVICON_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#0b1311"/>'
               '<g fill="#7dd3b0" fill-opacity=".2" stroke="#7dd3b0" stroke-width="3" stroke-linejoin="round">'
               '<rect x="20" y="20" width="24" height="24"/><rect x="20" y="20" width="24" height="24" transform="rotate(45 32 32)"/></g></svg>')
FAVICON = "data:image/svg+xml," + quote(FAVICON_SVG, safe=" =:/")
TOUCH_ICON = "data:image/png;base64," + base64.b64encode((ROOT / "scripts/apple-touch-icon.png").read_bytes()).decode()


def render() -> dict[str, str]:
    f = facts()
    desc = page_descriptions(f)
    return {
        name: LAYOUT.format(title=title, body=_with_subnav(name, page_head(body.strip("\n"))), head_extra=head_extra,
                            nav=nav_html("cases.html" if name == "case.html" else name),
                            repo=REPO, blob=BLOB, site=SITE, page_path="" if name == "index.html" else name.removesuffix(".html"),
                            description=_attr(desc[name]), favicon=_attr(FAVICON), touch_icon=TOUCH_ICON,
                            brand_mark=BRAND_MARK)
        for name, (title, body, head_extra) in pages(f).items()
    }


# ---------- إعادة عرض تشغيل رسمي محفوظ (PR3) ----------
# النص نفسه في web/assets/replay-core.js (BANNER)، ويتحقق من تطابقهما tests/test_web.py
REPLAY_BANNER = "إعادة عرض لتشغيل رسمي محفوظ — ليس تشغيلاً حياً"
REPLAY_PAGE = """
<h1>كيف يحكم مِعيار؟ إعادة عرض خطوة بخطوة</h1>
<p class="lead">سؤال واحد من تشغيل رسمي: من إجابة المساعد إلى حكم مِعيار وقرار البوابة، في سبع خطوات.</p>
<p class="replay-banner" role="note" id="replay-banner"><strong>{banner}</strong></p>
<div id="replay" aria-live="polite">
  <div class="notice empty"><strong>تُقرأ البيانات المحفوظة…</strong></div>
</div>
<noscript><div class="notice empty"><strong>تحتاج إعادة العرض إلى JavaScript.</strong>
<span>السجلات نفسها في <a href="cases.html">صفحات الحالات</a>.</span></div></noscript>
"""

# ---------- تحقق من نص (وضع ثانوي) ----------
def check_examples(f: dict) -> str:
    """أزرار أمثلة تملأ مربع النص بنصوص من بيانات المشروع فقط: آية من نص Quranpedia، ونقل محرّف وحديث من حالات الاختبار.
    لا يولّد مِعيار أي نص هنا؛ المثال يُنسخ كما هو من مصدره."""
    v = QuranIndex.load().verse(112, 1)
    cases = {c["id"]: c for c in f["cases"]}
    mis = re.search(r"«([^»]+)»", cases["EXT-033"]["prompt"]).group(1)           # نقل محرّف للآية من مجموعة الاختبار
    had = re.match(r"(.*?»)", cases["EXT-032"]["prompt"]).group(1)               # حديث من مجموعة الاختبار كما هو
    items = [
        ("آية صحيحة (الإخلاص: 1)", f"قال تعالى: ﴿{v.text}﴾ ({v.sura_name}: {v.aya})", "مصدرها: نص Quranpedia"),
        ("آية منقولة محرّفة (EXT-033)", f"قال تعالى: ﴿{mis}﴾ ({v.sura_name}: {v.aya})", "النقل من حالة الاختبار EXT-033"),
        ("حديث يحتاج تحقق (EXT-032)", had, "النص من حالة الاختبار EXT-032"),
    ]
    return "\n".join(f'    <button type="button" class="btn ghost btn-example" data-text="{_attr(text)}" title="{_attr(note)}">{_esc(label)}</button>'
                     for label, text, note in items)
CHECK_DIR = WEB / "assets/check"
CHECK_PAGE = """
<h1>تحقق من نص <span class="tag-secondary">وضع ثانوي</span></h1>
<p class="lead">الصق نصاً فيه آيات أو أحاديث، فيستخرجها مِعيار بقواعد ثابتة ويطابقها حرفياً مع البيانات المعتمدة، داخل متصفحك.
لا يُرسل النص إلى أي خادم، ولا يُستدعى أي نموذج لغوي.</p>
<form id="check-form" class="check-form" autocomplete="off">
  <div class="examples" role="group" aria-label="أمثلة من بيانات المشروع">
    <span class="examples-label">جرّب مثالاً من البيانات:</span>
{examples}
  </div>
  <label for="check-text">النص</label>
  <textarea id="check-text" rows="10" dir="auto" maxlength="20000" placeholder="مثال: قال تعالى: ﴿قل هو الله أحد﴾ (الإخلاص: 1)"></textarea>
  <div class="check-actions">
    <button type="submit" class="btn" id="check-run">تحقق</button>
    <button type="button" class="btn ghost" id="check-clear">امسح</button>
  </div>
  <p class="muted" id="check-size">عند أول تحقق يُحمَّل نص المصحف مرة واحدة (نحو نصف ميغابايت مضغوطاً)، ثم يحفظه المتصفح.</p>
</form>
<div id="check-results" aria-live="polite"></div>
<div class="limits-box" id="check-limits">
  <p class="limits-line muted">تفحص نصاً واحداً حرفياً؛ ليست تقييماً لمساعد ولا فتوى، والأحاديث المتاحة {hadith_count} فقط (وما عداها يحتاج تحقق).</p>
  <details class="tech"><summary>كل حدود هذه الصفحة</summary>
  <ul class="limits-list">
    <li><strong>ليست تقييماً لمساعد:</strong> الوظيفة الأساسية لمِعيار اختبار المساعد كاملاً على مجموعة حالات (انظر <a href="results.html">النتائج</a>)؛ هذه الصفحة تفحص نصاً واحداً فقط.</li>
    <li><strong>لا فتوى ولا حكم شرعي:</strong> تفحص نسبة النص إلى مصدره فقط، ولا تحكم على معنى ولا على مسألة.</li>
    <li><strong>الآيات:</strong> مطابقة حرفية بعد توحيد التشكيل والهمزات مع نص Quranpedia (6236 آية). «مؤيَّد» فقط عند تطابق فعلي.</li>
    <li><strong>الأحاديث محدودة جداً:</strong> تُطابَق مع <span id="hadith-count">المدخلات المكتملة ({hadith_count}) فقط</span> في الملف اليدوي وحدها؛ وكل حديث سواها «يحتاج تحقق»، وهذا لا يعني أنه ضعيف ولا صحيح.</li>
  </ul>
  <details class="tech"><summary>تفاصيل الاستخراج والمطابقة</summary>
  <ul class="limits-list">
    <li><strong>القريب ليس مطابقاً:</strong> إن اختلف حديث عن أحد المدخلات بحرف واحد في كلمة واحدة فقط، يعرض مِعيار أقرب مدخل للمقارنة وحدها («لم يُطابَق حرفياً»)، ولا يصدر معه «مؤيَّد» أبداً. وإن اختلف نص آية عن نص الموضع أُبرزت الكلمة المختلفة. والنص بين علامتي تنصيص بلا علامة نسبة يُلمَّح إليه إن قارب مدخلاً، ولا يُحكم عليه.</li>
    <li><strong>الاستخراج بقواعد ثابتة:</strong> الآية بين ﴿ ﴾ أو { } أو بين علامتي تنصيص يليها موضع بين قوسين مثل (البقرة: 255) أو (2:255)؛ والحديث بين علامتي تنصيص قبله «قال رسول الله» أو ﷺ، أو بعده «رواه» أو «أخرجه». ما لم يُكتب بهذه الصورة لا يُفحص.</li>
  </ul>
  </details>
  </details>
</div>
<noscript><div class="notice empty"><strong>تحتاج هذه الصفحة إلى JavaScript.</strong></div></noscript>
<p class="muted">المصادر: نص القرآن من <a href="https://quranpedia.net" rel="noopener">Quranpedia.net</a> (النسخة {quran_version})، والأحاديث من الملف اليدوي
(روابطه إلى الدرر السنية أو المكتبة الشاملة).</p>
<details class="tech"><summary>الملفات والاختبار</summary>
  <p>الأحاديث من <span class="ltr" lang="en">data/hadith/manual_hadith.json</span>. والمنطق نفسه في
  <span class="ltr" lang="en">miyar/paste_check.py</span>، واختبار يضمن تطابق نتائج المتصفح مع بايثون.</p>
</details>
"""


def render_check_data() -> dict[str, str]:
    """بيانات صفحة التحقق: نص المصحف (الرسمان) ومدخلات الملف اليدوي المكتملة فقط."""
    from miyar.paste_check import complete_manual, quran_web_data
    from miyar.quran_match import QuranIndex

    src = json.loads((ROOT / "data/quran/source.json").read_text(encoding="utf-8"))
    source = {"name": "Quranpedia.net", "url": "https://quranpedia.net", "dump_version": src["dump_version"],
              "files": [x["file"] for x in src["files"]], "license": "data/quran/LICENSE-quranpedia.md"}
    quran = quran_web_data(QuranIndex.load(), source)
    hadith = {"source": "data/hadith/manual_hadith.json — المدخلات المكتملة فقط", **complete_manual()}
    return {
        "quran.json": json.dumps(quran, ensure_ascii=False, separators=(",", ":")) + "\n",
        "hadith.json": json.dumps(hadith, ensure_ascii=False, indent=1) + "\n",
    }


def render_case_data() -> str:
    return json.dumps(case_records(facts()), ensure_ascii=False, indent=2) + "\n"


def build() -> None:
    CASES_JSON.write_text(render_case_data(), encoding="utf-8")
    CHECK_DIR.mkdir(parents=True, exist_ok=True)
    for name, body in render_check_data().items():
        (CHECK_DIR / name).write_text(body, encoding="utf-8")
    rendered = render()
    for name, page in rendered.items():
        (WEB / name).write_text(page, encoding="utf-8")
    for old in ("about.html",):  # صفحات قديمة استُبدلت
        p = WEB / old
        if p.exists():
            p.unlink()


if __name__ == "__main__":
    build()
