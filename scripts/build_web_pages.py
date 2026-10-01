"""يولّد صفحات web/*.html من قالب واحد (رأس + شريط وضع العرض + تذييل موحّد).

الناتج HTML ثابت يُرفع إلى المستودع كما هو؛ النشر لا يحتاج أمر بناء.
كل رقم في الصفحات محسوب هنا من ملفات المستودع (testsets/، data/، evaluation/official/)، لا مكتوب يدوياً.
بعد تعديل المحتوى هنا: python scripts/build_web_pages.py
"""

import html
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))

from miyar.hadith_manual import entry_status, load_manual  # noqa: E402
from miyar.quran_match import TOTAL_SURAS, TOTAL_VERSES  # noqa: E402
from miyar.review import review_summary  # noqa: E402

TESTSETS = [ROOT / "testsets/official_v0.json", ROOT / "testsets/extended_v1.json"]
OFFICIAL_RUNS = ROOT / "evaluation/official"
QURAN_SOURCE = ROOT / "data/quran/source.json"
REPO = "https://github.com/w7by4nrcfd-cpu/Miyar"

NAV = [
    ("index.html", "الرئيسية"),
    ("levels.html", "مستويات المحتوى"),
    ("sources.html", "المصادر والمنهجية"),
    ("transparency.html", "الشفافية والخصوصية"),
    ("status.html", "الحدود والحالة"),
    ("results.html", "النتائج"),
]

LAYOUT = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="description" content="مِعيار يختبر المساعد الذكي نفسه في المحتوى الإسلامي ويحكم على إجاباته، ولا يجيب هو عن الأسئلة. المسار الرابع: أدوات المعرفة والتحقق.">
<title>{title}</title>
<link rel="icon" href="assets/icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="assets/style.css">
{head_extra}</head>
<body>
<a class="skip" href="#main">تخطَّ إلى المحتوى</a>
<div class="modebar" role="region" aria-label="وضع العرض">
  <div class="wrap">
    <span class="label">وضع العرض:</span>
    <span class="mode on" aria-current="true">● نتائج محفوظة <span class="sr">(مفعّل)</span></span>
    <button class="mode" type="button" aria-disabled="true" disabled title="التشغيل الحي غير متاح حالياً">○ تشغيل حي — معطّل حالياً</button>
    <span class="modenote">للعرض فقط: لا توجد نتائج تقييم رسمية؛ التقييم الرسمي يبدأ 4 أكتوبر 2026.</span>
  </div>
</div>
<header class="site">
  <div class="wrap">
    <a class="brand" href="index.html">مِعيار</a>
    <nav aria-label="التنقل الرئيسي"><ul>
{nav}
    </ul></nav>
  </div>
</header>
<main id="main" class="wrap" tabindex="-1">
{body}
</main>
<footer class="site">
  <div class="wrap">
    <p>مِعيار أداة مدعومة بالذكاء الاصطناعي لاختبار المساعدات الذكية، <strong>ليست مختصاً شرعياً ولا تُصدر فتاوى</strong>.
    نص القرآن من تنزيلات <a href="https://quranpedia.net">Quranpedia.net</a> (النسخة {quran_version}).
    انظر <a href="sources.html">المصادر والمنهجية</a> و<a href="transparency.html">الشفافية والخصوصية</a>.</p>
    <p>الكود مفتوح المصدر (MIT): <a href="{repo}" class="ltr" lang="en">github.com/w7by4nrcfd-cpu/Miyar</a></p>
  </div>
</footer>
</body>
</html>
"""

# مستويات المحتوى الأربعة كما في الحزمة العلمية (النطاق والسلوك المتوقع)، مع وصف مختصر للسلوك
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

# المجالات التسعة في المرجعية العلمية للحزمة: (المجال، المرجع المعتمد، استُخدم فعلاً؟)
UNUSED = "لم يُستخدم بعد"
DOMAINS = [
    ("الموضوعات الدعوية", "dawa.center، وislamic-content.com", False),
    ("القرآن الكريم", "مصحف مجمع الملك فهد، أو quranpedia.net", True),
    ("التفسير", "dorar.net/tafseer", False),
    ("الحديث", "الصحيحان، والتحقق عبر dorar.net/hadith أو shamela.ws", True),
    ("العقيدة", "dorar.net/aqeeda", False),
    ("الفقه", "dorar.net/feqhia", False),
    ("السيرة والتاريخ", "dorar.net/history", False),
    ("الشبهات", "بيّنات dawa.center/file/7937", False),
    ("الترجمة والمصطلحات", "موسوعة الجمهرة islamic-content.com/dictionary", False),
]



def _esc(s) -> str:
    return html.escape(str(s), quote=False)


def facts() -> dict:
    """كل رقم يظهر في الموقع، محسوب من ملفات المستودع."""
    sets = [json.loads(p.read_text(encoding="utf-8")) for p in TESTSETS]
    cases = [c for s in sets for c in s["cases"]]
    manual = load_manual()["entries"]
    runs = [p for p in OFFICIAL_RUNS.glob("*.json") if not p.name.endswith(".schema.json")]
    return {
        "official": sets[0]["cases"],
        "n": len(cases),
        "n_off": len(sets[0]["cases"]),
        "n_ext": len(sets[1]["cases"]),
        "levels": Counter(c["level"] for c in cases),
        "review": review_summary(cases),
        "manual_total": len(manual),
        "manual_done": sum(entry_status(e) == "complete" for e in manual),
        "official_runs": len(runs),
        "unused_domains": sum(1 for d in DOMAINS if not d[2]),
        "quran_version": json.loads(QURAN_SOURCE.read_text(encoding="utf-8"))["dump_version"],
        "quran_files": json.loads(QURAN_SOURCE.read_text(encoding="utf-8"))["files"],
        "verses": TOTAL_VERSES,
        "suras": TOTAL_SURAS,
    }


def home(f: dict) -> str:
    return f"""
<h1>مِعيار: اختبار المساعد الذكي في المحتوى الإسلامي</h1>
<p class="lead">مِعيار يختبر <strong>المساعد الذكي نفسه</strong> ويحكم على إجاباته في المحتوى الإسلامي، <strong>ولا يجيب هو</strong> عن الأسئلة، وهو مشاركة في <strong>المسار الرابع: أدوات المعرفة والتحقق</strong> من تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي 2026.</p>

<h2>لماذا؟</h2>
<p>مساعدات الذكاء الاصطناعي قد تنسب نصاً إلى آية أو حديث لا يوجد فيه، أو تنقل الآية محرّفة، أو تُفتي في واقعة شخصية.
وفحص إجابة واحدة لا يكفي؛ المطلوب اختبار المساعد كنظام: بمجموعة أسئلة ثابتة موسومة، ومعيار واحد مكتوب.</p>

<h2>كيف سيعمل</h2>
<p class="muted">الخطوات التالية تصف التصميم؛ تشغيل الاختبار والحكم والدرجة <strong>لم تُبنَ بعد</strong> (انظر <a href="status.html">الحدود والحالة</a>).</p>
<ol class="steps">
  <li class="card"><h3>تشغيل الاختبار</h3>
    <p>تُطرح على المساعد أسئلة موسومة بمستوى المحتوى (A–D)، ولكل سؤال سلوك متوقع. انظر <a href="levels.html">مستويات المحتوى</a>.</p></li>
  <li class="card"><h3>تحقق الإسنادات</h3>
    <p>كل آية تُطابَق برمجياً وحرفياً بنص المصحف، وكل حديث يُقارن بمدخل يدوي من الدرر السنية أو المكتبة الشاملة.</p></li>
  <li class="card"><h3>فحص السلوك</h3>
    <p>هل التزم المساعد بما يتطلبه مستوى السؤال: إجابة موثقة، أو بيان الخلاف، أو إحالة إلى مختص؟</p></li>
  <li class="card"><h3>درجة وقرار</h3>
    <p>درجة لكل مستوى، ومقارنة بين المساعدات، وقرار نشر أو منع.</p></li>
</ol>

<h2>تصنيف كل إسناد</h2>
<div class="grid">
  <div class="verdict v-ok"><span class="tag">مؤيَّد</span> <code lang="en">supported</code>
    <p>وُجد النص فعلاً في المصدر المذكور، بمطابقة في البيانات. لا يصدر هذا الحكم أبداً دون مطابقة فعلية.</p></div>
  <div class="verdict v-rev"><span class="tag">يحتاج تحقق</span> <code lang="en">needs_review</code>
    <p>لا دليل كافٍ للحكم: لم يُعثر على مرجع، أو كانت ثقة الحكم منخفضة. غياب المرجع لا يعني الخطأ، فيُحال إلى مراجعة بشرية.</p></div>
  <div class="verdict v-bad"><span class="tag">خاطئ أو غير موجود</span> <code lang="en">wrong_or_missing</code>
    <p>الإحالة إلى موضع غير موجود، أو النص موجود في موضع آخر، أو نُقل محرّفاً.</p></div>
</div>

<h2>صفحات الموقع</h2>
<ul class="links">
  <li><a href="levels.html">مستويات المحتوى</a>: المستويات الأربعة A–D والسلوك المتوقع في كل منها.</li>
  <li><a href="sources.html">المصادر والمنهجية</a>: المرجع المعتمد لكل مجال، وهل استُخدم فعلاً.</li>
  <li><a href="transparency.html">الشفافية والخصوصية</a>: أداة مدعومة بالذكاء الاصطناعي، لا تجمع بياناتك.</li>
  <li><a href="status.html">الحدود والحالة</a>: ما تمّ وما لم يتم. <strong>لا توجد نتائج تقييم رسمية بعد.</strong></li>
</ul>
"""


def levels(f: dict) -> str:
    rows, details = [], []
    for code, short, scope, behavior, explain in LEVELS:
        rows.append(f'    <tr><th scope="row" lang="en">{code}</th><td data-label="النطاق">{scope}</td><td data-label="السلوك المتوقع">{behavior}</td>'
                    f'<td data-label="باختصار"><strong>{short}</strong></td><td data-label="عدد الحالات">{f["levels"].get(code, 0)}</td></tr>')
        examples = [c for c in f["official"] if c["level"] == code]
        ex = "".join(f'<li>{_esc(c["official_prompt"])}</li>' for c in examples) or "<li>لا يوجد مثال من أمثلة الحزمة موسوم بهذا المستوى.</li>"
        details.append(f"""<section class="card level" aria-labelledby="lv-{code}">
  <h3 id="lv-{code}"><span class="badge" lang="en">{code}</span> {short}</h3>
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
<div class="grid">
{chr(10).join(details)}
</div>

<div class="notice">
  <p><strong>تنبيه</strong> نص الأمثلة منقول من الحزمة العلمية، أما وسم كل مثال بمستواه وسلوكه المتوقع فمن إعداد المشروع،
  و<strong>لم يُراجَع شرعياً بعد</strong> ({f["review"]["approved"]["specialist"]} من {f["n"]} حالة مراجَعة مراجعة شرعية متخصصة).</p>
</div>
"""


def sources(f: dict) -> str:
    q1, q2 = f["quran_files"]
    notes = {
        "القرآن الكريم": f"Quranpedia.net: التنزيلات الرسمية، النسخة {f['quran_version']}. لم ننزّل من موقع المجمع.",
        "الحديث": f"ملف يدوي يُدخله صاحب المشروع من الدرر السنية أو المكتبة الشاملة ({f['manual_done']} من {f['manual_total']} مدخلات مكتملة حتى الآن).",
    }
    domains = [(name, ref, used, notes.get(name, "")) for name, ref, used in DOMAINS]
    rows = []
    for name, ref, used, note in domains:
        status = '<span class="yes">نعم</span>' if used else f'<span class="no">لا، {UNUSED}</span>'
        rows.append(f'    <tr><th scope="row">{name}</th><td data-label="المرجع المعتمد"><span class="ltr-mixed">{ref}</span></td>'
                    f'<td data-label="استُخدم فعلاً؟">{status}</td><td data-label="كيف استُخدم">{note or "—"}</td></tr>')
    n_used = sum(1 for d in domains if d[2])
    return f"""
<h1>المصادر والمنهجية</h1>
<p class="lead">المعيار الذي يُقاس عليه المساعد هو <strong>الحزمة العلمية للتحدي</strong>، لا رأي المشروع.
وهذا الجدول يبيّن لكل مجال من مجالاتها التسعة المرجعَ المعتمد فيها، وهل استخدمه مِعيار فعلاً.</p>

<div class="table-wrap" role="region" aria-label="جدول المصادر" tabindex="0"><table class="stack">
  <caption>المرجعية العلمية المعتمدة في الحزمة: المستخدم فعلاً {n_used} من {len(domains)} مجالات</caption>
  <thead><tr><th scope="col">المجال</th><th scope="col">المرجع المعتمد في الحزمة</th><th scope="col">استُخدم فعلاً؟</th><th scope="col">كيف استُخدم</th></tr></thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table></div>
<p>ما عدا القرآن والحديث <strong>لم يُستخدم بعد</strong>، ولم تُدمج منه أي بيانات.
وأمثلة الحزمة العلمية ({f["n_off"]} أسئلة) منقولة نصاً في مجموعة الاختبار.</p>

<h2>القرآن الكريم</h2>
<ul>
  <li>نص القرآن ({f["suras"]} سورة، {f["verses"]} آية) من <a href="https://quranpedia.net/dumps">التنزيلات الرسمية لـ Quranpedia.net</a>،
    النسخة {f["quran_version"]}، رواية حفص، منسوخاً كما نُزّل مع بصمة SHA-256 لكل ملف.</li>
  <li>ملفان: <span lang="en">mushafs-1</span> بالرسم الإملائي (للمطابقة)، ووصفه في ملفه: «{_esc(q1["description_in_file"])}»؛
    و<span lang="en">mushafs-2</span> بالرسم العثماني (للمطابقة والعرض)، ووصفه في ملفه: «{_esc(q2["description_in_file"])}».
    الوصفان من المصدر، ولم نتحقق منهما مستقلاً؛ و<strong>النص العثماني المعروض غير موافق للمطبوع</strong> بحسب وصف ملفه.</li>
  <li>ترخيص Quranpedia: الاستعمال داخل التطبيقات مجاني، وإعادة النشر تستلزم ذكر Quranpedia.net مع رابطه ورقم النسخة.</li>
</ul>

<h2>الحديث</h2>
<ul>
  <li>المصدر الوحيد للتحقق من الأحاديث في حالات الاختبار <strong>ملف يدوي</strong> يُدخله صاحب المشروع من
    <a href="https://dorar.net/hadith">الدرر السنية</a> أو <a href="https://shamela.ws">المكتبة الشاملة</a>:
    نص الحديث، والمصدر، والرابط، والدرجة منسوبة لقائلها. لا جلب آلي من أي موقع.</li>
  <li>حالته الآن: {f["manual_done"]} من {f["manual_total"]} مدخلات مكتملة.</li>
  <li>مِعيار لا يحكم على حديث بالصحة أو الضعف من عنده؛ والمدخل الناقص يجعل الحالة «يحتاج تحقق»، لا «خطأ».</li>
</ul>

<h2>المنهجية</h2>
<ol>
  <li><strong>مِعيار لا يولّد نصاً شرعياً:</strong> لا آية ولا حديثاً ولا حكماً. كل نص شرعي يعرضه منقول من بيانات لها مصدر مسجّل.</li>
  <li><strong>المطابقة البرمجية أولاً:</strong> نص الآية يُطابَق حرفياً بعد توحيد التشكيل والهمزات، دون نموذج لغوي.</li>
  <li><strong>لا «مؤيَّد» دون مطابقة فعلية في البيانات.</strong> غياب المرجع = «يحتاج تحقق»، لا «خطأ».</li>
  <li><strong>السلوك حسب المستوى:</strong> يُقارن سلوك المساعد بالسلوك المطلوب لمستوى السؤال في <a href="levels.html">الحزمة العلمية</a>.</li>
  <li><strong>الحَكَم الآلي يطبّق معياراً مكتوباً ولا يضعه.</strong> عند ضعف ثقته لا يصدر حكماً، وتُحال الحالة إلى مراجعة بشرية.
    ونموذج الحكم يختلف عن نموذج المساعد المُختبَر.</li>
  <li><strong>المراجعة نوعان:</strong> مراجعة شرعية متخصصة، وتحقق المشارك من المصادر (وهذا <strong>ليس</strong> مراجعة شرعية).
    لا تُحسب حالة «معتمدة شرعياً» إلا بمراجعة متخصصة.</li>
</ol>
<p>التفاصيل والتراخيص في <a class="ltr" lang="en" href="{REPO}/blob/main/SOURCES.md">SOURCES.md</a>
و<a class="ltr" lang="en" href="{REPO}/blob/main/docs/METHODOLOGY.md">METHODOLOGY.md</a>.</p>
"""


def transparency(f: dict) -> str:
    return f"""
<h1>الشفافية والخصوصية</h1>

<h2>أداة مدعومة بالذكاء الاصطناعي، وليست مختصاً شرعياً</h2>
<div class="notice">
  <p><strong>مِعيار ليس عالماً ولا مفتياً.</strong> هو أداة برمجية مدعومة بالذكاء الاصطناعي تختبر المساعدات الذكية،
  و<strong>لا تُصدر فتوى ولا حكماً شرعياً</strong>، ولا تجيب عن الأسئلة الدينية. لأي مسألة شخصية راجع أهل العلم والجهات المختصة.</p>
</div>

<h2>حدود الأداة</h2>
<ul>
  <li>لا يولّد آية ولا حديثاً ولا حكماً، ولا يصحح نصاً من عنده.</li>
  <li>لا يرجّح في مسائل الخلاف، ولا يحكم على حديث بالصحة أو الضعف.</li>
  <li>المطابقة الحرفية تكشف النقل المحرّف والإحالة الخاطئة، لكنها لا تحكم على صحة التفسير أو المعنى.</li>
  <li>فحص السلوك سيعتمد على نموذج لغوي <strong>قد يخطئ</strong>؛ لذلك الحكم الآلي مساعد للمراجعة البشرية لا بديل عنها.</li>
</ul>

<h2>الإفصاح عن أدوات الذكاء الاصطناعي</h2>
<div class="table-wrap" role="region" aria-label="جدول أدوات الذكاء الاصطناعي" tabindex="0"><table class="stack">
  <caption>أدوات الذكاء الاصطناعي في المشروع</caption>
  <thead><tr><th scope="col">الأداة</th><th scope="col">الاستخدام</th><th scope="col">الحالة</th></tr></thead>
  <tbody>
    <tr><th scope="row" lang="en">Claude Code</th><td data-label="الاستخدام">كتابة الكود والاختبارات والتوثيق في أثناء التطوير</td><td data-label="الحالة">استُخدم فعلاً</td></tr>
    <tr><th scope="row" lang="en">Claude</th><td data-label="الاستخدام">التخطيط والتطوير</td><td data-label="الحالة">استُخدم فعلاً</td></tr>
    <tr><th scope="row" lang="en">Gemini</th><td data-label="الاستخدام">مخطط استخدامه <strong>داخل المنتج</strong> (استخراج الإسنادات وفحص السلوك)، ومساعداً مرجعياً يُختبر</td><td data-label="الحالة">استُدعي في اختبارات اتصال تطويرية فقط؛ <strong>لا يستدعيه الموقع</strong></td></tr>
  </tbody>
</table></div>
<p>هذا الموقع ثابت ولا يستدعي أي نموذج لغوي. ومطابقة الآيات برمجية حرفية دون أي نموذج لغوي.</p>

<h2>الخصوصية</h2>
<ul>
  <li><strong>لا نجمع بياناتك الشخصية:</strong> لا حسابات، ولا نماذج إدخال، ولا ملفات تعريف ارتباط، ولا أدوات تحليلات أو تتبع.</li>
  <li>لا خطوط ولا مكتبات من مواقع خارجية؛ سياسة أمان المحتوى تمنع تحميل أي مورد من خارج الموقع.</li>
  <li>الموقع مستضاف على Cloudflare Workers، وقد يعالج مزوّد الاستضافة بيانات تقنية لازمة لتقديم الصفحات (مثل عنوان IP) وفق سياسته؛ ولم نفعّل أي أداة تحليلات.</li>
  <li>حالات الاختبار اصطناعية، ولا تُستخدم محادثات حقيقية لأي مستفيد.</li>
  <li>لا مفاتيح ولا أسرار في الموقع ولا في المستودع؛ إعدادات المزوّد في متغيرات بيئة على الخادم فقط.</li>
</ul>
"""


def review_status_html(f: dict) -> str:
    """حالة مراجعة حالات الاختبار لكل نوع، محسوبة من testsets/ (لا أرقام مكتوبة يدوياً)."""
    s, n = f["review"], f["n"]
    spec, src = s["approved"]["specialist"], s["approved"]["source_check"]
    head = ("<p><strong>المراجعة الشرعية لم تكتمل.</strong> لم يراجع أي مختص شرعي حتى الآن.</p>" if spec == 0 else
            "<p><strong>المراجعة الشرعية لم تكتمل.</strong> العدد الفعلي لكل نوع مراجعة:</p>")
    return f"""  {head}
  <ul>
    <li>مراجعة شرعية متخصصة (<span lang="en" class="ltr">specialist</span>): مقبولة {spec} من {n}، مرفوضة {s['rejected']['specialist']}.</li>
    <li>تحقق من المصادر بواسطة المشارك (<span lang="en" class="ltr">source_check</span>): مقبولة {src} من {n}، مرفوضة {s['rejected']['source_check']}.
      <strong>هذا ليس مراجعة شرعية متخصصة.</strong></li>
    <li>الملف اليدوي للأحاديث: {f["manual_done"]} من {f["manual_total"]} مدخلات مكتملة.</li>
  </ul>"""


def status(f: dict) -> str:
    lv = "، ".join(f'<span lang="en">{k}</span> {f["levels"].get(k, 0)}' for k in "ABCD")
    runs = ("<strong>لا توجد نتائج تقييم رسمية بعد.</strong> لم يُسجَّل أي تشغيل رسمي في المستودع "
            f"(عدد سجلات التشغيل الرسمية: {f['official_runs']})." if f["official_runs"] == 0 else
            f"عدد سجلات التشغيل الرسمية: {f['official_runs']}.")
    return f"""
<h1>الحدود والحالة</h1>
<div class="notice">
  <p>{runs} أي رقم تقييم سيُعرض لاحقاً يكون ناتجاً عن تشغيل فعلي مسجّل في المستودع مع عدد الحالات.</p>
</div>

<h2>ما تمّ فعلاً</h2>
<ul class="done">
  <li>نص القرآن ({f["suras"]} سورة، {f["verses"]} آية) من Quranpedia.net، النسخة {f["quran_version"]}، مع بصمات الملفات.</li>
  <li>توحيد النص العربي، ومطابقة الآيات حرفياً برمجياً، مع اختبارات وحدات.</li>
  <li>مجموعة اختبار من {f["n"]} حالة ({f["n_off"]} من أمثلة الحزمة العلمية + {f["n_ext"]} إضافية)، موسومة بالمستوى: {lv}. كلها مسودات لم تُراجَع شرعياً.</li>
  <li>قالب الملف اليدوي للأحاديث ({f["manual_total"]} مدخلات، المكتمل منها {f["manual_done"]}).</li>
  <li>طبقة مزوّد النماذج اللغوية بوضعين: نتائج محفوظة، وتشغيل حي بسقف استخدام (اختُبرت باتصال تطويري فقط).</li>
  <li>هذا الموقع الثابت (عربي، من اليمين لليسار، يعمل على الجوال).</li>
</ul>

<h2>ما لم يتم بعد</h2>
<ul class="todo">
  <li>المساعدان المرجعيان اللذان يُختبران (نموذج عادي، ونموذج مع مصادر معتمدة).</li>
  <li>تشغيل مجموعة الاختبار على المساعدين.</li>
  <li>استخراج الإسنادات من الإجابات، والتحقق من الأحاديث آلياً مقابل الملف اليدوي.</li>
  <li>فحص السلوك حسب المستوى (الحَكَم الآلي).</li>
  <li>الدرجة، والمقارنة بين المساعدين، وقرار النشر أو المنع.</li>
  <li>قياس دقة مِعيار مقابل الوسوم البشرية، واختبارات العداء (Red Teaming).</li>
</ul>
<p class="muted">تُبنى هذه خلال أيام التحدي (4–6 أكتوبر 2026).</p>

<h2>المراجعة الشرعية</h2>
<div class="notice">
{review_status_html(f)}
  <p class="muted">لن يُعرض أي حكم على أنه «مراجَع بشرياً» إلا بعد مراجعته فعلاً وذكر اسم المراجِع.</p>
</div>

<h2>حدود معروفة</h2>
<ul>
  <li>التحقق من الأحاديث محدود بما في الملف اليدوي؛ غياب المدخل أو نقصه يعني «يحتاج تحقق»، لا «غير صحيح».</li>
  <li>{f["unused_domains"]} من مجالات الحزمة التسعة لم تُستخدم مراجعها بعد (انظر <a href="sources.html">المصادر والمنهجية</a>).</li>
  <li>نص القرآن العثماني المعروض «غير موافق للمطبوع» بحسب وصف ملفه في المصدر؛ وتحديث النسخة يدوي مع تسجيله.</li>
  <li>الحكم الآلي قد يخطئ، وهو مساعد للمراجعة لا بديل عنها.</li>
</ul>
"""


RESULTS = """
<h1>النتائج</h1>
<div class="notice demo" role="note">
  <p><strong>للعرض فقط: هذه ليست نتائج تقييم رسمية.</strong>
  وضع «نتائج محفوظة» يعرض ملف نتائج محفوظاً مسبقاً دون أي استدعاء لنموذج لغوي، وهو <strong>فارغ حالياً</strong>:
  لا نتائج تقييم رسمية فيه، ولا بيانات تجريبية مصطنعة.</p>
  <p><strong>التقييم الرسمي يبدأ 4 أكتوبر 2026</strong> (أيام التحدي 4–6 أكتوبر)، ولا يُعرض هنا بعده إلا ناتج تشغيل رسمي
  مسجّل في <span class="ltr" lang="en">evaluation/official/</span> مع عدد الحالات (N).</p>
</div>
<div id="results" aria-live="polite">
  <div class="notice empty"><strong>جارٍ التحميل…</strong></div>
</div>
<noscript><div class="notice empty"><strong>لم يُشغَّل أي تقييم رسمي بعد</strong>
<span>(تحتاج هذه الصفحة إلى JavaScript لقراءة ملف النتائج.)</span></div></noscript>
<p>انظر <a href="status.html">الحدود والحالة</a> لما تمّ وما لم يتم.</p>
"""


def pages(f: dict) -> dict:
    return {
        "index.html": ("مِعيار — اختبار المساعد الذكي في المحتوى الإسلامي", home(f), ""),
        "levels.html": ("مستويات المحتوى — مِعيار", levels(f), ""),
        "sources.html": ("المصادر والمنهجية — مِعيار", sources(f), ""),
        "transparency.html": ("الشفافية والخصوصية — مِعيار", transparency(f), ""),
        "status.html": ("الحدود والحالة — مِعيار", status(f), ""),
        "results.html": ("النتائج — مِعيار", RESULTS, '<script type="module" src="assets/results.js"></script>\n'),
    }


def nav_html(current: str) -> str:
    items = []
    for href, label in NAV:
        cur = ' aria-current="page"' if href == current else ""
        items.append(f'      <li><a href="{href}"{cur}>{label}</a></li>')
    return "\n".join(items)


def render() -> dict[str, str]:
    f = facts()
    return {
        name: LAYOUT.format(title=title, body=body.strip("\n"), head_extra=head_extra, nav=nav_html(name),
                            quran_version=f["quran_version"], repo=REPO)
        for name, (title, body, head_extra) in pages(f).items()
    }


def build() -> None:
    rendered = render()
    for name, page in rendered.items():
        (WEB / name).write_text(page, encoding="utf-8")
    old = WEB / "about.html"  # استُبدلت بصفحات المصادر والشفافية والحالة
    if old.exists():
        old.unlink()


if __name__ == "__main__":
    build()
