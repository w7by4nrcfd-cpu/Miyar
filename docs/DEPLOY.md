# النشر

## 1) الموقع الثابت `web/` على Cloudflare Workers (وليس Pages)
الرابط المنشور: <https://miyar.w7by4nrcfd.workers.dev>

النشر عبر **Cloudflare Workers** (أصول ثابتة Static Assets)، **وليس Cloudflare Pages**. الموقع HTML/CSS/JS فقط، **بلا أمر بناء**.
أمر النشر من جذر المستودع:

```bash
npx wrangler deploy --assets=./web --name miyar --compatibility-date=2026-10-01
```

- يحتاج تسجيل الدخول إلى حساب Cloudflare في wrangler (`npx wrangler login`) أو متغير البيئة `CLOUDFLARE_API_TOKEN`؛ **لا يُكتب أي مفتاح في المستودع**.
- بعد أي تعديل في `web/` يُعاد تشغيل أمر النشر؛ ولا تفترض أن الدفع إلى `main` ينشر تلقائياً.

الصفحات: `index.html` (الرئيسية)، `levels.html` (مستويات المحتوى)، `sources.html` (المصادر والمنهجية)،
`transparency.html` (الشفافية والخصوصية)، `status.html` (الحدود والحالة)، `results.html` (النتائج).
تُولَّد من `scripts/build_web_pages.py`؛ بعد أي تعديل شغّله وادفع الناتج.

ملاحظات:
- `web/_headers` يضبط رؤوس الأمان ويمنع التخزين المؤقت لملفات `web/data/`.
- الموقع لا يحمّل أي خط أو مكتبة خارجية (سياسة CSP: `default-src 'self'`).
- لتحديث النتائج: يُستبدل `web/data/results.json` بناتج تشغيل فعلي مطابق لـ `web/data/results.schema.json`، ثم دفع إلى `main`.

### معاينة محلية (اختياري، تحتاج كمبيوتر)
```bash
python -m http.server 8000 --directory web
# ثم افتح http://localhost:8000
```
(فتح الملفات مباشرة بـ file:// لا يكفي لصفحة النتائج، لأن المتصفح يمنع قراءة JSON منها.)

## 2) الخلفية FastAPI (اختياري الآن)
الخلفية حالياً هيكل فقط: نقطة `GET /health` لا غير، بلا حكم ولا استدعاء نموذج. الموقع الثابت لا يحتاجها.

التشغيل محلياً:
```bash
pip install -r requirements.txt
uvicorn miyar.api:app --host 0.0.0.0 --port 8000
# GET http://localhost:8000/health → {"status":"ok",...}
```

للنشر لاحقاً على Render (خطة مجانية): Web Service من المستودع نفسه،
Build: `pip install -r requirements.txt`، Start: `uvicorn miyar.api:app --host 0.0.0.0 --port $PORT`،
ومسار فحص الصحة `/health`. الأسرار تُضاف في إعدادات Render كمتغيرات بيئة، لا في الكود (انظر `.env.example`).
