"""خلفية مِعيار (FastAPI) — هيكل فقط.

المتاح الآن: GET /health. لا منطق حكم ولا استدعاء لأي نموذج لغوي هنا.
التشغيل: uvicorn miyar.api:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI

from . import __version__

app = FastAPI(title="Mi'yar API", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "miyar", "version": __version__}
