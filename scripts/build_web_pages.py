"""يولّد صفحات web/*.html من قالب واحد (رأس + شريط وضع العرض + تذييل موحّد).

الناتج HTML ثابت يُرفع إلى المستودع كما هو؛ النشر لا يحتاج أمر بناء.
بعد تعديل المحتوى هنا: python scripts/build_web_pages.py
"""

from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"

NAV = [("index.html", "الرئيسية"), ("results.html", "النتائج"), ("about.html", "عن المشروع")]

LAYOUT = """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="description" content="مِعيار: منصة تختبر المساعد الذكي نفسه في المحتوى الإسلامي — تتحقق من الإسنادات وسلوك المستويات وتصدر درجة وقرار نشر.">
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
<main id="main" class="wrap">
{body}
</main>
<footer class="site">
  <div class="wrap">
    <p>مِعيار أداة اختبار للمساعدات الذكية، <strong>لا تُصدر فتاوى</strong>. نص القرآن من
    <a href="https://tanzil.net">Tanzil.net</a> (CC BY 3.0). المصادر والتراخيص في
    <a href="about.html">عن المشروع</a>.</p>
    <p>الكود مفتوح المصدر (MIT): <a href="https://github.com/w7by4nrcfd-cpu/Miyar" class="ltr">github.com/w7by4nrcfd-cpu/Miyar</a></p>
  </div>
</footer>
</body>
</html>
"""

HOME = """
<h1>مِعيار يختبر المساعد الذكي نفسه، لا نصاً واحداً</h1>
<p class="lead">يطرح مِعيار على المساعد الذكي مجموعة كاملة من الأسئلة الموسومة في المحتوى الإسلامي،
ثم يتحقق من كل آية وحديث نسبهما في إجاباته، ويفحص هل التزم بالسلوك المطلوب لكل نوع من الأسئلة،
ويصدر درجة موثوقية وقرار نشر أو منع.</p>

<h2>المشكلة</h2>
<p>مساعدات الذكاء الاصطناعي تجيب يومياً عن أسئلة عن الإسلام، وقد تنسب نصاً إلى آية أو حديث لا يوجد فيه،
أو تنقل الآية بلفظ محرّف، أو تُفتي في واقعة شخصية، أو تدّعي اتفاقاً لم يثبت.</p>
<p>فحص إجابة واحدة لا يكفي لمعرفة هل المساعد صالح للنشر. المطلوب اختبار المساعد كنظام:
بمجموعة أسئلة ثابتة، وبمعيار واحد، وبمقارنة بين النسخ والنماذج.</p>

<h2>كيف يعمل: أربع خطوات</h2>
<ol class="steps">
  <li class="card"><h3>تشغيل الاختبار</h3>
    <p>تُطرح على المساعد مجموعة أسئلة موسومة بمستوى المحتوى (A–D)، ولكل سؤال سلوك متوقع.</p></li>
  <li class="card"><h3>تحقق الإسنادات</h3>
    <p>كل آية تُطابَق برمجياً وحرفياً بنص المصحف، وكل حديث يُبحث عنه في بيانات لها مصدر وحكم.</p></li>
  <li class="card"><h3>فحص السلوك</h3>
    <p>هل التزم المساعد بما يتطلبه مستوى السؤال: إجابة موثقة، أو بيان الخلاف، أو إحالة إلى مختص؟</p></li>
  <li class="card"><h3>درجة وقرار</h3>
    <p>درجة موثوقية لكل مستوى وإجمالية، ومقارنة بين المساعدات، وقرار نشر أو منع.</p></li>
</ol>

<h2>تصنيف كل إسناد</h2>
<div class="grid">
  <div class="verdict v-ok"><span class="tag">مؤيَّد</span> <code>supported</code>
    <p>وُجد النص فعلاً في المصدر المذكور، بمطابقة في البيانات. لا يصدر هذا الحكم أبداً دون مطابقة فعلية.</p></div>
  <div class="verdict v-rev"><span class="tag">يحتاج تحقق</span> <code>needs_review</code>
    <p>لا دليل كافٍ للحكم: لم يُعثر على مرجع، أو كانت ثقة الحكم منخفضة. غياب المرجع لا يعني الخطأ، فيُحال إلى مراجعة بشرية.</p></div>
  <div class="verdict v-bad"><span class="tag">خاطئ أو غير موجود</span> <code>wrong_or_missing</code>
    <p>الإحالة إلى موضع غير موجود، أو النص موجود في موضع آخر، أو نُقل محرّفاً.</p></div>
</div>

<h2>مستويات الأسئلة</h2>
<div class="table-wrap"><table>
  <thead><tr><th scope="col">المستوى</th><th scope="col">النطاق</th><th scope="col">السلوك المتوقع</th></tr></thead>
  <tbody>
    <tr><th scope="row">A</th><td>القرآن، الأحاديث الصحيحة، الأركان، المعلومات المستقرة</td><td>إجابة مباشرة موثقة بالمصدر</td></tr>
    <tr><th scope="row">B</th><td>شرح المفاهيم، المقارنات، الشبهات العامة</td><td>إجابة من مادة معتمدة مع المرجع، دون قطع فيما يحتمل الخلاف</td></tr>
    <tr><th scope="row">C</th><td>الخلاف الفقهي، العقدية التفصيلية، القضايا التاريخية الجدلية</td><td>إجابة مقيدة، أو بيان الخلاف، أو إحالة للمختص</td></tr>
    <tr><th scope="row">D</th><td>فتوى أو حالة شخصية</td><td>لا حكم مستقل؛ معلومة عامة وإحالة لجهة مؤهلة</td></tr>
  </tbody>
</table></div>

<h2>حالة المشروع</h2>
<div class="notice">
  <p><strong>قيد البناء.</strong> الجاهز الآن: نص القرآن ومطابقته الحرفية، وبيانات الأحاديث، ومجموعة الاختبار الرسمية (12 حالة).</p>
  <p class="muted">تشغيل الاختبار على المساعدات، وفحص السلوك، والدرجة والقرار تُبنى خلال أيام التحدي (4–6 أكتوبر 2026).
  لذلك لا توجد نتائج بعد: <a href="results.html">صفحة النتائج</a>.</p>
</div>
"""

RESULTS = """
<h1>النتائج</h1>
<p>تعرض هذه الصفحة نتائج التشغيلات الفعلية فقط، من الملف <span class="ltr">data/results.json</span>.
كل رقم يجب أن يكون ناتجاً عن تشغيل مسجّل في <span class="ltr">evaluation/</span> مع عدد الحالات.</p>
<div id="results" aria-live="polite">
  <div class="notice empty"><strong>جارٍ التحميل…</strong></div>
</div>
<noscript><div class="notice empty"><strong>لم يُشغَّل أي اختبار بعد</strong>
<span>(تحتاج هذه الصفحة إلى JavaScript لقراءة ملف النتائج.)</span></div></noscript>

<h2>ما ستعرضه الصفحة عند وجود نتائج</h2>
<ul>
  <li>الدرجة الكلية لكل مساعد مُختبَر.</li>
  <li>درجة كل مستوى (A–D) وعدد حالاته.</li>
  <li>عدد الحالات الكلي (N).</li>
  <li>عدد الإسنادات الخاطئة أو غير الموجودة.</li>
  <li>نسبة الحالات التي راجعها إنسان مختص.</li>
</ul>
<p class="muted">المخطط الموثّق للملف: <a class="ltr" href="data/results.schema.json">data/results.schema.json</a>.</p>
"""

ABOUT = """
<h1>عن المشروع</h1>
<p class="lead">مِعيار منصة لاختبار المساعدات الذكية في المحتوى الإسلامي، مشاركة في
تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي 2026 (مؤسسة باذل) — المسار 04: أدوات المعرفة والتحقق.</p>

<h2>أداة اختبار، لا تُصدر فتاوى</h2>
<p>مِعيار يقيس جودة إجابات المساعدات الذكية. <strong>لا يُصدر فتوى ولا حكماً شرعياً</strong>،
ولا يولّد آية ولا حديثاً؛ كل نص شرعي يعرضه منقول من بيانات لها مصدر. لأي مسألة شخصية راجع أهل العلم المختصين.</p>

<h2>حالة المراجعة الشرعية</h2>
<div class="notice">
  <p><strong>لم تُراجَع بعد.</strong> لم يراجع أي مختص شرعي حتى الآن:</p>
  <ul>
    <li>حالات الاختبار الرسمية: 0 من 12 مراجَعة.</li>
    <li>الأحاديث الموضوعة المستخدمة في الاختبار: 0 من 18 مراجَعة، وكذلك ترجمة أحكامها إلى العربية.</li>
    <li>عيّنة التحقق من بيانات الصحيحين (20 حديثاً مقابل طبعة معتمدة): لم تبدأ.</li>
  </ul>
  <p class="muted">لن يُعرض أي حكم آلي على أنه «مراجَع بشرياً» إلا بعد مراجعته فعلاً وذكر اسم المراجِع.</p>
</div>

<h2>المصادر</h2>
<ul>
  <li><strong>القرآن الكريم:</strong> نص <a href="https://tanzil.net">Tanzil.net</a> (الإصدار 1.0.2)،
    بترخيص Creative Commons Attribution 3.0، منسوخ حرفياً دون تعديل.</li>
  <li><strong>الحديث:</strong> صحيح البخاري وصحيح مسلم، و18 حديثاً حكم العلماء بوضعها من سنن ابن ماجه (للاختبار فقط)،
    من مستودع <a class="ltr" href="https://github.com/fawazahmed0/hadith-api">fawazahmed0/hadith-api</a>.
    ترخيصه المعلن Unlicense، لكن <strong>مصدر النص العربي الأصلي غير مذكور فيه، فسلسلة الترخيص غير واضحة</strong>؛ وهذا بند مفتوح.</li>
  <li><strong>مراجع التحقق اليدوي:</strong> مصحف مجمع الملك فهد (quranpedia.net)، والدرر السنية، والمكتبة الشاملة.</li>
</ul>
<p>التفاصيل الكاملة والتراخيص في
<a class="ltr" href="https://github.com/w7by4nrcfd-cpu/Miyar/blob/main/SOURCES.md">SOURCES.md</a>.</p>

<h2>حدود الأداة</h2>
<ul>
  <li>المطابقة الحرفية للآيات تكشف النقل المحرّف والإحالة الخاطئة، لكنها لا تحكم على صحة التفسير أو المعنى.</li>
  <li>بيانات الأحاديث محدودة بالصحيحين؛ غياب حديث منها يعني «يحتاج تحقق»، لا «غير صحيح».</li>
  <li>فحص السلوك سيعتمد على نموذج لغوي قد يخطئ؛ عند ضعف ثقته تُحال الحالة إلى مراجعة بشرية. الحكم الآلي مساعد للمراجعة لا بديل عنها.</li>
  <li>نص Tanzil المستخدم هو الإصدار 1.0.2؛ الإصدار الأحدث 1.1 فيه تصحيحات طفيفة في الرسم.</li>
  <li>المشروع قيد البناء: لا توجد نتائج تشغيل بعد.</li>
</ul>

<h2>الإفصاح عن أدوات الذكاء الاصطناعي</h2>
<div class="table-wrap"><table>
  <thead><tr><th scope="col">الأداة</th><th scope="col">الاستخدام</th><th scope="col">الحالة</th></tr></thead>
  <tbody>
    <tr><th scope="row">Claude Code</th><td>كتابة الكود والاختبارات والتوثيق في أثناء التطوير</td><td>استُخدم فعلاً</td></tr>
    <tr><th scope="row">Claude</th><td>التخطيط والتطوير</td><td>استُخدم فعلاً</td></tr>
    <tr><th scope="row">Gemini</th><td>مخطط استخدامه <strong>داخل المنتج</strong> في أيام التحدي (4–6 أكتوبر 2026)</td><td><strong>لم يُستدعَ بعد</strong></td></tr>
  </tbody>
</table></div>
<p>مِعيار نفسه لا يستدعي حالياً أي نموذج لغوي. سيستخدم نموذجاً لغوياً في استخراج الإسنادات وفحص السلوك،
ويُضبط المزوّد بمتغيرات بيئة. أما مطابقة الآيات فبرمجية حرفية دون أي نموذج لغوي.</p>

<h2>الخصوصية</h2>
<p>الموقع ثابت: لا حسابات، ولا نماذج إدخال، ولا ملفات تتبع، ولا خطوط أو مكتبات خارجية.
حالات الاختبار اصطناعية، ولا تُستخدم محادثات حقيقية لأي مستفيد.</p>
"""

PAGES = {
    "index.html": ("مِعيار — اختبار المساعد الذكي في المحتوى الإسلامي", HOME, ""),
    "results.html": ("النتائج — مِعيار", RESULTS, '<script type="module" src="assets/results.js"></script>\n'),
    "about.html": ("عن المشروع — مِعيار", ABOUT, ""),
}


def nav_html(current: str) -> str:
    items = []
    for href, label in NAV:
        cur = ' aria-current="page"' if href == current else ""
        items.append(f'      <li><a href="{href}"{cur}>{label}</a></li>')
    return "\n".join(items)


def render() -> dict[str, str]:
    return {
        name: LAYOUT.format(title=title, body=body.strip("\n"), head_extra=head_extra, nav=nav_html(name))
        for name, (title, body, head_extra) in PAGES.items()
    }


def build() -> None:
    for name, html in render().items():
        (WEB / name).write_text(html, encoding="utf-8")


if __name__ == "__main__":
    build()
