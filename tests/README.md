# tests/

| الملف | ما يختبره | بيانات مصطنعة؟ |
|---|---|---|
| `test_normalize.py` | توحيد النص العربي | أمثلة نصية قصيرة |
| `test_quran_match.py` | المطابقة الحرفية | نص القرآن الحقيقي من `data/quran` (للقراءة فقط)، ومقاطع محرّفة عمداً لاختبار الكشف |
| `test_hadith_data.py` | سلامة ملفات `data/hadith` | لا |
| `test_hadith_data_loader.py` | طبقة تحميل الأحاديث | **نعم: `FIXTURE_HADITH`** في مجلد مؤقت |
| `test_testsets.py` | أمثلة الحزمة العلمية | لا |
| `test_api.py` | `GET /health` | لا |
| `test_web.py` | صفحات الموقع | لا |
| `test_fixtures.py` | منع تسرب الـfixtures إلى `data/` و`web/` | لا |
| `web/results-core.test.mjs` | منطق صفحة النتائج (`node --test`) | **نعم: `FIXTURE_RUN`** |

## قاعدة الـfixtures
كل بيانات مصطنعة في الاختبارات **ليست نتائج ولا بيانات حقيقية**: لم يُشغَّل بها أي مساعد ولم يُستدعَ أي نموذج.
تُسمّى `FIXTURE_*`، وقيمها تحمل الكلمة `FIXTURE`، ويبدأ موضعها بتعليق `⚠️ FIXTURE`.
`test_fixtures.py` يفشل إن ظهرت الكلمة `FIXTURE` في أي ملف داخل `data/` أو `web/` أو `testsets/` أو `evaluation/`.
