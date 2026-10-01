"""فحص الاتصال بـ Gemini دون طباعة المفتاح ودون استهلاك حصة التوليد.

يستدعي GET /v1beta/models (قائمة النماذج) فقط، ولا يولّد أي نص.
الاستخدام: python scripts/check_llm_connectivity.py
"""

import json
import os
import sys
import urllib.error
import urllib.request

URL = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=100"


def main() -> int:
    key = os.environ.get("GEMINI_API_KEY", "")
    print(f"GEMINI_API_KEY: {'موجود' if key else 'غير موجود'}")
    req = urllib.request.Request(URL, headers={"x-goog-api-key": key} if key else {})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, body = r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        status, body = e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"تعذّر الوصول إلى الخادم (قد يكون محظوراً من الشبكة): {type(e).__name__}")
        return 2
    if key:
        body = body.replace(key, "***")
    print(f"HTTP {status}")
    if status == 200:
        models = [m["name"].removeprefix("models/") for m in json.loads(body).get("models", [])
                  if "generateContent" in m.get("supportedGenerationMethods", [])]
        print(f"الاتصال يعمل. نماذج تدعم generateContent ({len(models)}):")
        for name in models:
            print(f"  {name}")
        return 0
    try:
        msg = json.loads(body)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        msg = body[:200]
    print(f"الخادم وصل لكنه رفض الطلب: {msg}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
