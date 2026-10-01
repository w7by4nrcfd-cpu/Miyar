# النشر

## 1) الموقع الثابت `web/` على Cloudflare Pages (من الجوال)
الموقع HTML/CSS/JS فقط، **بلا أمر بناء**.

1. افتح https://dash.cloudflare.com وسجّل الدخول (الخطة المجانية تكفي).
2. **Workers & Pages** ← **Create** ← تبويب **Pages** ← **Connect to Git**.
3. اربط حساب GitHub واختر المستودع `w7by4nrcfd-cpu/Miyar`.
4. الإعدادات:
   | الحقل | القيمة |
   |---|---|
   | Production branch | `main` |
   | Framework preset | `None` |
   | Build command | **اتركه فارغاً** |
   | Build output directory | `web` |
   | Root directory | اتركه فارغاً (جذر المستودع) |
5. **Save and Deploy**. بعد دقيقة يظهر رابط مثل `https://miyar.pages.dev`.
6. كل دفع إلى `main` يعيد النشر تلقائياً.

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
