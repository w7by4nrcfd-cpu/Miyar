---
name: miyar-test-cases
description: العمل على حالات اختبار مِعيار (testsets/official_v0.json وtestsets/extended_v1.json). استخدمها عند إضافة حالة أو تعديل سؤالها أو مستواها أو سلوكها المتوقع أو فحوصها، أو عند عرض الحالات في الموقع، أو عند ربطها بالملف اليدوي للأحاديث.
---

# حالات الاختبار — مِعيار

المرجع: `testsets/README.md`، `CLAUDE.md` («أمثلة الحزمة العلمية» و«إضافات مطلوبة» 1 و3)، `scripts/build_testset_v1.py`، `miyar/review.py`.

## الملفان
- `official_v0.json`: **أمثلة الحزمة العلمية الاثنا عشر**، نصها الرسمي في `official_prompt`، والمستوى والسلوك المتوقع من إعداد المشروع.
- `extended_v1.json`: الحالات الإضافية، **مولَّدة** من `scripts/build_testset_v1.py`. عدّل المولّد ثم شغّله؛ **لا تعدّل JSON يدوياً**.
  المولّد يحفظ المراجعات المسجّلة ما دام محتوى الحالة لم يتغير، وأي تعديل يعيدها `pending`.

## بنية الحالة
`id`، `prompt`، `level` (A–D)، `category`، `critical`، `expected_behavior`، `checks`، `reference_hints`، وحقول المراجعة
(`review_status`، `reviewed_by`، `reviewer_role`، `reviewed_at`، `review_notes`). وفي `extended_v1`: `risk_type` و`handling`،
وعند الحاجة `data_check` (ومنه `manual_ref` إلى مدخل `H-…` في `data/hadith/manual_hadith.json`) و`misquote` و`injected_context`.

## خطة اختبار الموثوقية (إلزامية في CLAUDE.md)
يجب أن تشمل المجموعة صراحةً:
- **(أ) التعارض:** خلاف العلماء (`conflict_scholars`) ومصدران يختلفان (`conflict_sources`).
- **(ب) غياب المرجع** (`absent_reference`).
- **(ج) الأخطاء المتوقعة من المساعد:** آية محرّفة (`misquoted_verse`)، إحالة خاطئة (`wrong_reference`)، مرجع غير موجود (`invalid_reference`)،
  منسوب للصحيحين وليس فيهما (`hadith_absent`)، حديث لا يصح يُقدَّم كصحيح (`hadith_fabricated`).
- **(د) آلية المعالجة** لكل نوع عبر `handling`: `direct_answer`، `sourced_answer`، `state_disagreement`، `abstain_or_refer`،
  `correct_and_answer`، `refuse_fabrication`، `general_info_and_referral`، `hold_rules`.
- وحالات المستوى D (`personal_fatwa`)، وحقن الأوامر (`prompt_injection`) **كبيانات فقط** حتى تُبنى وحدة Red Teaming بعد النواة.

## قواعد عند الكتابة والتعديل
- الفخ في السؤال **متعمد** (آية محرّفة، حديث لا يصح)؛ النص الصحيح في السلوك المتوقع يأتي من البيانات فقط (Quranpedia أو الملف اليدوي)، لا من عندك.
- حالة الحديث مربوطة بمدخل يدوي (`manual_ref`)، وحكم الحديث في السلوك المتوقع منسوب لقائله كما في المدخل.
- المستوى D يقتضي إحالة وعدم فتوى (يفرضه `test_level_d_requires_referral_and_no_fatwa`).
- بعد أي تعديل: `python scripts/build_testset_v1.py` ثم `python scripts/review_sheet.py export` ثم `python -m pytest -q`،
  ثم `python scripts/build_web_pages.py` إن تغيّر ما يُعرض.

## في الموقع
- صفحة «حالات الاختبار» تُقرأ من الملفات عند التوليد، وتعرض المعرّف والمستوى والنوع وآلية المعالجة والسلوك المتوقع والحرجة والمراجعة، دون حكم أو نتيجة.
- **لا يُعرض نص السؤال**، لأن بعض الأسئلة تتضمن عمداً آيات منقولة بخطأ أو أحاديث لا تصح؛ ومقطع أي حالة حديث مدخلها اليدوي غير مكتمل
  محجوب عن الموقع (يفرضه `test_pending_hadith_fragments_stay_hidden_from_site`).
- الأعداد (الكلي، ولكل مستوى، والمراجَعة) محسوبة من الملفات؛ لا تكتبها يدوياً. والعدد الفعلي للمراجعات: `python scripts/review_sheet.py status`.
