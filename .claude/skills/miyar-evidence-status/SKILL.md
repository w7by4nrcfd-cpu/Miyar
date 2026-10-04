---
name: miyar-evidence-status
description: حالات الأدلة والتحقق في مِعيار وكيف تُحدَّث. استخدمها عند تعبئة أو تعديل الملف اليدوي للأحاديث (data/hadith/manual_hadith.json)، أو تسجيل مراجعات حالات الاختبار (source_check / specialist)، أو عرض أعداد المدخلات والمراجعات وحالات الإسناد في الموقع أو الوثائق.
---

# حالات الأدلة والتحقق — مِعيار

المرجع: `miyar/hadith_manual.py`، `data/hadith/README.md`، `miyar/review.py`، `docs/REVIEWER_GUIDE.md`، `docs/METHODOLOGY.md`.

## 1. حكم الإسناد (ثلاثة فقط)
| الحالة | المعنى |
|---|---|
| `supported` مؤيَّد | وُجد النص فعلاً في المصدر المذكور بمطابقة في البيانات. لا يصدر دون مطابقة فعلية |
| `needs_review` يحتاج تحقق | لا دليل كافٍ: لا مرجع، أو مدخل حديث ناقص، أو نص قصير، أو ثقة حَكَم منخفضة. **ليس «خطأ»** |
| `wrong_or_missing` خاطئ أو غير موجود | موضع غير موجود، أو النص في موضع آخر، أو منقول محرّفاً |

## 2. مدخلات الملف اليدوي للأحاديث
- **أنواع المدخل وحقولها المطلوبة** (`KINDS` في `miyar/hadith_manual.py`) + `entered_by` و`entered_at` (YYYY-MM-DD) لكل نوع:
  - `found`: `text`، `source`، `link`، `grade`، `grade_by`.
  - `not_found`: `query`، `searched_in`، `link`.
  - `collection_range`: `source`، `max_number` (عدد صحيح)، `link`.
- **complete** إن امتلأت كل الحقول المطلوبة لنوعه، وإلا **pending**؛ والحالة المرتبطة بمدخل pending تُحكم «يحتاج تحقق» دون حكم آلي.
- **الروابط من `dorar.net` أو `shamela.ws` فقط.** والدرجة لا تُقبل بلا قائلها (`grade_by`)، فإن غاب القائل تُكتب الدرجة في `notes` ويبقى المدخل pending.
- لا جلب آلي. **لا تعدّل بيانات الحديث إلا بطلب صريح** من صاحب المشروع، وبالنتائج التي يرسلها فقط.
- تحقق بعد التعديل: `manual_errors(load_manual())` فارغ، و`pytest tests/test_hadith_manual.py tests/test_testsets_v1.py`.

## 3. مراجعة حالات الاختبار
- `review_status`: `pending` / `approved` / `rejected`. مع القرار إلزامي: `reviewed_by` و`reviewer_role` و`reviewed_at`؛ ومع الرفض `review_notes`.
- `reviewer_role`:
  - `source_check` — **النوع المعتمد الآن**: تحقق المشارك من المصادر (Quranpedia، الدرر، الشاملة). **ليس مراجعة شرعية متخصصة**، ولا يحكم بصحة السلوك المتوقع شرعاً.
  - `specialist` — **اختياري ومعلّق** حتى يتوفر مراجع متخصص؛ وحده يجعل الحالة «معتمدة شرعياً». ملاحظات جلسة إرشاد دون مراجعة مسجّلة لا تُحتسب `specialist`.
- الحالة التي مدخلها اليدوي ناقص تبقى `pending`. ولا يحلّ `source_check` محل `specialist` مسجّل.
- أي تعديل على محتوى حالة مراجَعة يعيدها `pending`.
- **طريقة التسجيل الوحيدة:** `python scripts/review_sheet.py export` ← تعبئة `docs/review_sheet.csv` ← `python scripts/review_sheet.py apply <الورقة>`
  (يرفض الورقة كلها عند أي خطأ). العدد الحالي: `python scripts/review_sheet.py status`.

## 4. عرض الأعداد بصدق
- لا تكتب عدداً يدوياً؛ الموقع يحسب عدد المدخلات المكتملة والمراجعات من الملفات عند التوليد (`scripts/build_web_pages.py`).
- عند تحديث الوثائق اذكر العدد الفعلي وأسماء المدخلات المكتملة وسبب نقص كل مدخل غير مكتمل.
- ما دام عدد `specialist` صفراً تقول الصفحات صراحة «لم تُجرَ مراجعة شرعية متخصصة».
- مقاييس الدقة تحتسب الحالات `approved` فقط، وتُذكر مع نوع المراجعة التي قيست مقابلها.
