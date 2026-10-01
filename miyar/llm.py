"""طبقة مزوّد النماذج اللغوية — بنية تحتية فقط، بلا أي منطق حكم أو استخراج.

المبادئ:
- **لا استدعاء مكرر:** كل استجابة تُخزَّن بمفتاح = بصمة SHA-256 للطلب (المزوّد، النموذج، النص، الإعدادات).
  إن وُجدت الاستجابة في المخزن أُعيدت منه دائماً، حتى في الوضع الحي.
- **وضعان:** ``cached`` يعيد من المخزن فقط ويرفع ``CacheMiss`` عند غيابه (لا استدعاء مدفوع أبداً)؛
  ``live`` يستدعي النموذج عند الغياب، بسقف يومي ``MIYAR_LIVE_MAX_CALLS_PER_DAY``.
- **حد الاستخدام (429):** يُرفع ``RateLimited`` مع مدة الانتظار إن عُرفت، ليتراجع المستدعي إلى النتائج المحفوظة.
- **احتياط الحَكَم:** عند 503 أو 429 يُعاد الطلب حتى 3 محاولات بتأخير تصاعدي، ثم يُجرَّب النموذج الاحتياطي
  (افتراضياً ``gemini-3.5-flash``) بالطريقة نفسها. كل استجابة تسجّل النموذج الذي أجاب فعلاً (``model``)
  والمطلوب (``requested_model``) وسجل المحاولات (``attempts``).
- **لا أسرار في الملفات:** المفتاح يُقرأ من متغير بيئة ولا يُكتب في المخزن ولا في رسائل الخطأ.
- **وسم التشغيل:** كل ملف في المخزن يحمل ``run_label`` (افتراضياً ``DEV_RUN``)، ومخزن التطوير في ``evaluation/dev/``.

المزوّدات المنفّذة: Gemini (REST ``generateContent``). Anthropic وواجهات OpenAI المتوافقة تُضاف عند الحاجة.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import time
import urllib.request
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE_DIR = ROOT / "evaluation" / "dev" / "llm_cache"
DEV_RUN = "DEV_RUN"
MODES = ("cached", "live")


# ---------- الأخطاء ----------
class LLMError(Exception):
    """خطأ عام من طبقة النموذج."""


class MissingCredentials(LLMError):
    pass


class CacheMiss(LLMError):
    """الوضع cached ولا توجد استجابة محفوظة لهذا الطلب."""


class CallBudgetExceeded(LLMError):
    """تجاوز السقف اليومي للاستدعاءات الحية."""


class ServiceUnavailable(LLMError):
    """المزوّد مشغول مؤقتاً (HTTP 503)."""


class RateLimited(LLMError):
    """رفض المزوّد الطلب لتجاوز الحد (HTTP 429)."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


# ---------- الطلب والاستجابة ----------
@dataclass(frozen=True)
class LLMRequest:
    provider: str
    model: str
    prompt: str
    system: str = ""
    temperature: float = 0.0
    max_output_tokens: int = 1024

    def key(self) -> str:
        canonical = json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str  # النموذج الذي أجاب فعلاً
    finish_reason: str | None = None
    usage: dict = field(default_factory=dict)
    from_cache: bool = False
    request_key: str = ""
    requested_model: str = ""  # النموذج المطلوب (يختلف عن model إن أجاب الاحتياطي)
    attempts: list = field(default_factory=list)  # [{"model", "status"}] لكل محاولة حية في هذا الاستدعاء


# ---------- النقل ----------
# (url, headers, body) -> (status, headers, body)
Transport = Callable[[str, dict, bytes, float], tuple[int, dict, bytes]]


def urllib_transport(url: str, headers: dict, body: bytes, timeout: float) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()


def _redact(text: str, secret: str | None) -> str:
    return text.replace(secret, "***") if secret else text


# ---------- المزوّدات ----------
class Provider(Protocol):
    name: str

    def call(self, req: LLMRequest) -> LLMResponse: ...


class GeminiProvider:
    """Gemini عبر REST: POST /v1beta/models/{model}:generateContent مع الترويسة x-goog-api-key."""

    name = "gemini"
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, transport: Transport = urllib_transport, timeout: float = 120.0):
        if not api_key:
            raise MissingCredentials("GEMINI_API_KEY غير مضبوط")
        self._key = api_key
        self._transport = transport
        self._timeout = timeout

    def call(self, req: LLMRequest) -> LLMResponse:
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": req.prompt}]}],
            "generationConfig": {"temperature": req.temperature, "maxOutputTokens": req.max_output_tokens},
        }
        if req.system:
            body["systemInstruction"] = {"parts": [{"text": req.system}]}
        url = f"{self.BASE_URL}/models/{req.model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": self._key}
        status, resp_headers, raw = self._transport(url, headers, json.dumps(body).encode("utf-8"), self._timeout)
        text = _redact(raw.decode("utf-8", errors="replace"), self._key)
        if status == 429:
            raise RateLimited(f"Gemini 429: {text[:300]}", _retry_after(resp_headers, text))
        if status == 503:
            raise ServiceUnavailable(f"Gemini 503: {text[:300]}")
        if status != 200:
            raise LLMError(f"Gemini HTTP {status}: {text[:300]}")
        data = json.loads(text)
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise LLMError(f"Gemini: لا توجد مرشّحات في الاستجابة (blockReason={reason})")
        cand = candidates[0]
        parts = (cand.get("content") or {}).get("parts") or []
        return LLMResponse(
            text="".join(p.get("text", "") for p in parts),
            provider=self.name,
            model=req.model,
            finish_reason=cand.get("finishReason"),
            usage=data.get("usageMetadata") or {},
        )


def _retry_after(headers: dict, body_text: str) -> float | None:
    for k, v in headers.items():
        if k.lower() == "retry-after":
            try:
                return float(v)
            except ValueError:
                pass
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', body_text)
    return float(m.group(1)) if m else None


# ---------- المخزن ----------
class ResponseStore:
    """ملف JSON لكل استجابة: <key>.json، مع وسم التشغيل. لا يُخزَّن أي مفتاح أو ترويسة."""

    def __init__(self, directory: str | Path, run_label: str = DEV_RUN):
        self.dir = Path(directory)
        self.run_label = run_label

    def _path(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    def get(self, req: LLMRequest) -> LLMResponse | None:
        p = self._path(req.key())
        if not p.exists():
            return None
        rec = json.loads(p.read_text(encoding="utf-8"))
        r = rec["response"]
        return LLMResponse(
            text=r["text"],
            provider=r["provider"],
            model=r["model"],
            finish_reason=r.get("finish_reason"),
            usage=r.get("usage") or {},
            from_cache=True,
            request_key=req.key(),
        )

    def put(self, req: LLMRequest, resp: LLMResponse) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        rec = {
            "run_label": self.run_label,
            "stored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "request_key": req.key(),
            "request": asdict(req),
            "response": {
                "text": resp.text,
                "provider": resp.provider,
                "model": resp.model,  # النموذج الذي أجاب فعلاً
                "requested_model": resp.requested_model or req.model,
                "finish_reason": resp.finish_reason,
                "usage": resp.usage,
            },
        }
        p = self._path(req.key())
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(p)
        return p

    # عدّاد الاستدعاءات الحية لليوم (UTC)
    def _usage_path(self) -> Path:
        return self.dir / "usage.json"

    def live_calls_today(self) -> int:
        p = self._usage_path()
        if not p.exists():
            return 0
        u = json.loads(p.read_text(encoding="utf-8"))
        return u.get("live_calls", 0) if u.get("date") == _today() else 0

    def record_live_call(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        u = {"run_label": self.run_label, "date": _today(), "live_calls": self.live_calls_today() + 1}
        self._usage_path().write_text(json.dumps(u, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ---------- العميل ----------
RETRYABLE = (RateLimited, ServiceUnavailable)
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_SECONDS = 2.0  # 2ث ثم 4ث بين المحاولات الثلاث
MAX_WAIT_SECONDS = 60.0


class LLMClient:
    def __init__(
        self,
        provider: Provider | None,
        store: ResponseStore,
        mode: str = "cached",
        max_live_calls_per_day: int = 0,
        fallback_models: tuple[str, ...] = (),
        max_attempts: int = 1,
        backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if mode not in MODES:
            raise ValueError(f"وضع غير معروف: {mode}")
        if mode == "live" and provider is None:
            raise MissingCredentials("الوضع الحي يحتاج مزوّداً مضبوطاً")
        self.provider = provider
        self.store = store
        self.mode = mode
        self.max_live_calls_per_day = max_live_calls_per_day
        self.fallback_models = tuple(fallback_models)
        self.max_attempts = max(1, max_attempts)
        self.backoff_seconds = backoff_seconds
        self.sleep = sleep

    def complete(self, req: LLMRequest) -> LLMResponse:
        """النموذج المطلوب أولاً، ثم الاحتياطيات بالترتيب عند 503/429 بعد استنفاد المحاولات."""
        chain = [req] + [replace(req, model=m) for m in self.fallback_models if m != req.model]
        attempts: list[dict] = []
        # المخزن أولاً عبر السلسلة كلها: إن أجاب الاحتياطي سابقاً أُعيدت إجابته ولا يُعاد أي استدعاء
        for r in chain:
            hit = self.store.get(r)
            if hit is not None:
                return self._finish(hit, req, attempts)
        if self.mode == "cached":
            raise CacheMiss(f"لا استجابة محفوظة للطلب {req.key()[:12]}")
        for i, r in enumerate(chain):
            last = i == len(chain) - 1
            try:
                resp = self._call_with_retries(r, attempts)
            except RETRYABLE:
                if last:
                    raise
                continue
            resp.requested_model = req.model
            self.store.put(r, resp)
            resp.request_key = r.key()
            return self._finish(resp, req, attempts)
        raise AssertionError("unreachable")

    def _call_with_retries(self, req: LLMRequest, attempts: list[dict]) -> LLMResponse:
        for n in range(1, self.max_attempts + 1):
            if self.store.live_calls_today() >= self.max_live_calls_per_day:
                raise CallBudgetExceeded(f"بلغ السقف اليومي للاستدعاءات الحية ({self.max_live_calls_per_day})")
            self.store.record_live_call()  # يُحتسب قبل الإرسال: المحاولة المرفوضة تستهلك من الحصة أيضاً
            try:
                resp = self.provider.call(req)
            except RETRYABLE as e:
                attempts.append({"model": req.model, "status": 429 if isinstance(e, RateLimited) else 503})
                if n == self.max_attempts:
                    raise
                wait = self.backoff_seconds * 2 ** (n - 1)
                if isinstance(e, RateLimited) and e.retry_after:
                    wait = max(wait, e.retry_after)
                self.sleep(min(wait, MAX_WAIT_SECONDS))
                continue
            attempts.append({"model": req.model, "status": 200})
            return resp
        raise AssertionError("unreachable")

    @staticmethod
    def _finish(resp: LLMResponse, original: LLMRequest, attempts: list[dict]) -> LLMResponse:
        resp.requested_model = original.model
        resp.attempts = attempts
        return resp


# متغير النموذج لكل دور. الحَكَم والمساعد المُختبَر نموذجان مختلفان عمداً لتجنب تحيّز النموذج لإجاباته.
ROLE_MODEL_VARS = {"judge": "MIYAR_LLM_MODEL_JUDGE", "assistant": "MIYAR_LLM_MODEL_ASSISTANT"}
# احتياط الحَكَم وحده: 3 محاولات بتأخير تصاعدي عند 503/429، ثم النموذج الاحتياطي.
JUDGE_FALLBACK_VAR = "MIYAR_LLM_MODEL_JUDGE_FALLBACK"
DEFAULT_JUDGE_FALLBACK = "gemini-3.5-flash"


def model_for_role(env: dict, role: str | None) -> tuple[str, str]:
    """يعيد (اسم المتغير، اسم النموذج): متغير الدور إن ضُبط، وإلا MIYAR_LLM_MODEL."""
    if role is not None and role not in ROLE_MODEL_VARS:
        raise ValueError(f"دور غير معروف: {role}")
    if role is not None and env.get(ROLE_MODEL_VARS[role]):
        return ROLE_MODEL_VARS[role], env[ROLE_MODEL_VARS[role]]
    return "MIYAR_LLM_MODEL", env.get("MIYAR_LLM_MODEL", "")


def client_from_env(
    env: dict | None = None, transport: Transport = urllib_transport, role: str | None = None
) -> tuple[LLMClient, str]:
    """يبني العميل من متغيرات البيئة. يعيد (العميل، اسم النموذج). ``role``: judge أو assistant."""
    env = os.environ if env is None else env
    provider_name = env.get("MIYAR_LLM_PROVIDER", "gemini")
    var, model = model_for_role(env, role)
    mode = env.get("MIYAR_RUN_MODE", "cached")
    if not model:
        raise LLMError(f"{var} غير مضبوط")
    store = ResponseStore(env.get("MIYAR_LLM_CACHE_DIR") or DEFAULT_CACHE_DIR, env.get("MIYAR_RUN_LABEL", DEV_RUN))
    provider: Provider | None = None
    if provider_name != "gemini":
        raise LLMError(f"المزوّد {provider_name} غير منفّذ بعد (المتاح: gemini)")
    key = env.get("GEMINI_API_KEY", "")
    if key:
        provider = GeminiProvider(key, transport)
    elif mode == "live":
        raise MissingCredentials("GEMINI_API_KEY غير مضبوط")
    max_calls = int(env.get("MIYAR_LIVE_MAX_CALLS_PER_DAY", "0") or 0)
    if role == "judge":
        fallback = env.get(JUDGE_FALLBACK_VAR, DEFAULT_JUDGE_FALLBACK)
        fallbacks = tuple(m for m in [fallback] if m)
        return LLMClient(provider, store, mode, max_calls, fallbacks, DEFAULT_MAX_ATTEMPTS), model
    return LLMClient(provider, store, mode, max_calls), model
