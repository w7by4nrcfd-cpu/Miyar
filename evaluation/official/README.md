# evaluation/official/ — OFFICIAL_RUN

سجلات **التشغيل الرسمي** لمِعيار خلال أيام التحدي (4–6 أكتوبر 2026، بتوقيت الرياض). هذا المجلد وحده مصدر أي رقم
يظهر في الموقع (`web/data/results.json`) أو التقرير أو العرض.

**حالياً: أربعة سجلات رسمية** بتاريخ 4 أكتوبر 2026 (توقيت الرياض): `official-2026-10-04-baseline-1` و`-baseline-2` و`-baseline-3` و`-rag-2`، كلها على الحالات الاثنتي عشرة `official_v0` وعلى الـ commit `e9facf4ca04bdbaefb6121fa0d3ff9ebfd4490a1` (آخر commit في `main` وقت التشغيل؛ بلا وسم `v1.0` لتعذّر دفع الوسوم من بيئة العمل، فالتجميد موثّق بهذا الـ commit).
جولتا `rag-1` و`rag-3` لم تكتملا (خطأ حكم واحد في `rag-1` بقطع `MAX_TOKENS` في الحالة OFF-09، وحدّ يومي 429 من Groq في `rag-3`) فلم تُحفظ كسجلين رسميين؛ استجاباتهما المخزّنة موجودة في `evaluation/official_llm_cache/` فقط. `evaluation/official_llm_cache/` استجابات التشغيل الرسمي (دون عدّاد الاستدعاءات)، منفصلة عن مخزن التطوير.

## القواعد (يفرضها `tests/test_official_runs.py`)
1. كل سجل ملف JSON واحد لكل تشغيل، بالحقول الإلزامية (المخطط: `official_run.schema.json`):
   - `run_label`: `"OFFICIAL_RUN"` حرفياً.
   - `run_id`: معرّف فريد، ويطابق اسم الملف (`<run_id>.json`).
   - `executed_at`: وقت التشغيل الفعلي ISO 8601 بمنطقة زمنية، **داخل 2026-10-04 00:00 – 2026-10-06 23:59:59 بتوقيت الرياض**.
   - `n_cases`: عدد الحالات N (≥ 1)، ويساوي عدد عناصر `cases`.
   - `testsets`، `assistant`، `model`، و`cases` (نتيجة كل حالة بمعرّفها).
   - `human_reviewed`: `{approved, total, by_role: {specialist, source_check}}`، حيث `total` = N و`approved` = مجموع النوعين.
     **`source_check` تحقق من المصادر بواسطة المشارك، وليس مراجعة شرعية متخصصة**، ويُعرض في التقرير منفصلاً عنها.
2. `web/data/results.json` لا يشير إلا إلى سجلات داخل `evaluation/official/`، والسجل المشار إليه موجود، ويطابقه
   في `executed_at` و`n_cases` و`human_reviewed` (لكل نوع مراجعة).
3. لا يُنقل إلى هنا أي سجل من تشغيلات التطوير، ولا يُعدَّل سجل رسمي بعد كتابته؛ أي إعادة تشغيل = سجل جديد بمعرّف جديد.
4. لا مفاتيح ولا ترويسات طلبات في أي سجل.
5. **الكاتب:** `python -m miyar.evaluate --label OFFICIAL_RUN --assistant baseline|rag --cases <الاختيار>` مع `MIYAR_RUN_ID` جديد.
   يكتب السجل بالحقول أعلاه، ومعها لكل حالة `judgement` أو `judge_error`، و`commit` و`case_selection` و`judge_model` و`min_confidence`.
6. **للنشر:** لكل حالة حقل `judgement` اختياري بصيغة `miyar.publish.judgement_to_dict` (حكم السلوك والثقة وأحكام الإسناد).
   الدرجة لا تُكتب في السجل يدوياً؛ يحسبها `python scripts/publish_results.py` من هذه الأحكام بـ `scoring.score_run`،
   ويكتب `web/data/results.json` و`web/data/cases/<id>.json`، ويرفض أي سجل يخالف القواعد أعلاه أو يحمل وسماً غير وسم التشغيل الرسمي.
