# Benefit Benchmark v2

**الحالة:** مسجّلة مسبقاً ومقفلة. لم تُجرَ أي جلسة، ولا بيانات خام، ولا نتائج.

البروتوكول: [PROTOCOL.md](PROTOCOL.md). سبب v2: [../benefit/DEVIATIONS.md](../benefit/DEVIATIONS.md).

| الملف | المحتوى |
|---|---|
| `PREREGISTRATION.json` | البذرة، وبصمات البروتوكول والعناصر والتوزيع والمخرجات والأداتين والكود، وبصمات `evaluation/official/` وGold Set وسجل v1، وبصمة المفتاح، وبصمة بيانات العرض لكل مراجع |
| `items_blind.json` | 28 عنصراً جديداً (24 + 4 إحماء) لا تتقاطع مع v1 |
| `assignment.json` | التوزيع المقفل لـ`ind1`، و`ind2` الاختياري بالتوزيع المعكوس، ووصف كل مراجع |
| `miyar_outputs.json` | مخرجات `judge_citation` الحقيقية |
| `tool/review_ind1.html`، `tool/review_ind2.html` | أداة الجلسة: إقرار إلزامي، وبصمة بيانات العرض تُحسب في المتصفح وتُصدَّر |
| `provenance_<r>.json` | يُكتب قبل الجلسة بعد نشر الأداة: الملف المقدَّم = غلاف المنصة + الأداة المسجّلة بايتاً ببايت |
| `key.json` | **غير موجود**: يُكتب بعد قفل البيانات الخام فقط |

```
python scripts/benefit_benchmark_v2.py verify
python scripts/benefit_benchmark_v2.py provenance ind1 <served.html> <artifact_url> <version_id>   # قبل الجلسة
python scripts/benefit_benchmark_v2.py lock ind1         # بعد الجلسة
python scripts/benefit_benchmark_v2.py reveal-key
python scripts/benefit_benchmark_v2.py compute ind1
```
