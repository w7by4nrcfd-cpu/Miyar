"""اختبار دخان لنموذجي الدورين (الحَكَم والمساعد). تشغيل تطوير DEV_RUN، لا يُنشر كنتيجة.

- المساعد: طلب قصير واحد («Reply with exactly one word: OK»).
- الحَكَم: طلب حكم حقيقي قصير على مثال اصطناعي موسوم FIXTURE، يُرجع JSON صغيراً مثل {"verdict":"supported"}.
  يُستدعى النموذج المطلوب مرة واحدة (بلا إعادة)، فإن أخفق جُرّب الاحتياطي بالطلب نفسه مرة واحدة فقط.
- يفشل صراحةً (رمز خروج 1) عند أي إخراج فارغ أو JSON غير صالح أو حكم خارج التصنيفات الثلاثة.
- يسجّل لكل محاولة: النموذج المطلوب والذي أجاب، وfinishReason، ورموز التفكير، ورموز الإخراج.
- الاستجابات الصالحة تُخزَّن في evaluation/dev/llm_cache، والملخص في evaluation/dev/smoke_<الوقت>.json.
- لا يطبع قيمة أي متغير بيئة. الاستخدام: ``python scripts/llm_smoke_test.py [--role judge|assistant]``.

الطلبان لا علاقة لهما بالمحتوى الشرعي، فاختبار الدخان لا يولّد نصاً دينياً.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from miyar.llm import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    DEV_RUN,
    ROLE_MODEL_VARS,
    IncompleteOutput,
    LLMError,
    LLMRequest,
    LLMResponse,
    ResponseStore,
    client_from_env,
)

ASSISTANT_PROMPT = "Reply with exactly one word: OK"
ASSISTANT_MAX_OUTPUT_TOKENS = 16

# مثال اصطناعي بالكامل (FIXTURE): لا مصدر حقيقي ولا محتوى شرعي
JUDGE_PROMPT = (
    "⚠️ FIXTURE — synthetic test data, not a real source.\n"
    'Source text: "The FIXTURE river is 12 km long."\n'
    'Claim: "The FIXTURE river is 12 km long."\n'
    "Does the source text support the claim? Reply ONLY with JSON of the form "
    '{"verdict": "supported" | "needs_review" | "wrong_or_missing"}.'
)
JUDGE_EXPECTED = "supported"
VERDICTS = {"supported", "needs_review", "wrong_or_missing"}


def _describe(resp: LLMResponse) -> dict:
    return {
        "answered_by": resp.model,
        "from_cache": resp.from_cache,
        "text": resp.text,
        "finish_reason": resp.finish_reason,
        "thoughts_tokens": resp.thoughts_tokens,
        "output_tokens": resp.output_tokens,
        "usage": resp.usage,
        "request_key": resp.request_key,
    }


def _check_json(text: str) -> tuple[bool, str]:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        return False, f"JSON غير صالح: {e}"
    if not isinstance(obj, dict) or obj.get("verdict") not in VERDICTS:
        return False, f"حكم خارج التصنيفات الثلاثة: {obj!r}"
    return True, obj["verdict"]


def _attempt(client, model: str, prompt: str, max_tokens: int, json_mode: bool) -> dict:
    """محاولة واحدة على نموذج واحد. تعيد سجلاً فيه status: ok / empty_output / invalid_json / error."""
    entry: dict = {"requested_model": model}
    req = LLMRequest(
        "gemini", model, prompt, max_output_tokens=max_tokens,
        response_mime_type="application/json" if json_mode else None,
    )
    try:
        resp = client.complete(req)
    except IncompleteOutput as e:
        entry.update(_describe(e.response), status="empty_output", error=str(e))
        return entry
    except LLMError as e:
        entry.update(status="error", error_type=type(e).__name__, error=str(e)[:500])
        return entry
    entry.update(_describe(resp))
    if not resp.text.strip():
        entry.update(status="empty_output")
    elif json_mode:
        valid, detail = _check_json(resp.text)
        if valid:
            entry.update(status="ok", verdict=detail, matches_expected=detail == JUDGE_EXPECTED)
        else:
            entry.update(status="invalid_json", error=detail)
    else:
        entry.update(status="ok")
    return entry


def _print(role: str, e: dict) -> None:
    line = f"{role}: طُلب {e['requested_model']} → {e['status']}"
    if "answered_by" in e:
        line += (f" | أجاب: {e['answered_by']} | finishReason={e['finish_reason']}"
                 f" | تفكير={e['thoughts_tokens']} | إخراج={e['output_tokens']} | text={e['text']!r}")
    if e.get("error"):
        line += f" | {e['error'][:300]}"
    print(line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=list(ROLE_MODEL_VARS), help="دور واحد فقط (افتراضياً الدوران)")
    args = ap.parse_args()
    roles = [args.role] if args.role else list(ROLE_MODEL_VARS)

    store = ResponseStore(os.environ.get("MIYAR_LLM_CACHE_DIR") or DEFAULT_CACHE_DIR)
    budget = sum(2 if r == "judge" else 1 for r in roles)  # الحَكَم: المطلوب مرة + الاحتياطي مرة
    cap = store.live_calls_today() + budget
    env = {**os.environ, "MIYAR_RUN_MODE": "live", "MIYAR_LIVE_MAX_CALLS_PER_DAY": str(cap)}

    results = []
    for role in roles:
        client, model = client_from_env(env, role=role)
        fallbacks = list(client.fallback_models)
        # محاولة واحدة لكل نموذج: الاحتياطي يُدار هنا صراحةً لا داخل العميل
        client.fallback_models, client.max_attempts = (), 1
        if role == "judge":
            # 16 عمداً: العميل يرفعه إلى حد الحَكَم الأدنى (1024) ويضبط التفكير
            attempts = [_attempt(client, model, JUDGE_PROMPT, 16, json_mode=True)]
            if attempts[0]["status"] != "ok" and fallbacks:
                attempts.append(_attempt(client, fallbacks[0], JUDGE_PROMPT, 16, json_mode=True))
        else:
            attempts = [_attempt(client, model, ASSISTANT_PROMPT, ASSISTANT_MAX_OUTPUT_TOKENS, json_mode=False)]
        for a in attempts:
            _print(role, a)
        last = attempts[-1]
        results.append({
            "role": role,
            "model_var": ROLE_MODEL_VARS[role],
            "status": last["status"],
            "answered_by": last.get("answered_by") if last["status"] == "ok" else None,
            "attempts": attempts,
        })

    now = datetime.now(timezone.utc)
    out = ROOT / "evaluation" / "dev" / f"smoke_{now.strftime('%Y-%m-%dT%H%M%SZ')}.json"
    record = {
        "run_label": DEV_RUN,
        "note": "DEV_RUN: اختبار دخان للاتصال فقط، ليس نتيجة تقييم ولا يُنشر.",
        "ran_at": now.isoformat(timespec="seconds"),
        "prompts": {"judge": JUDGE_PROMPT, "assistant": ASSISTANT_PROMPT},
        "results": results,
    }
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"حُفظ: {out.relative_to(ROOT)}")
    failed = [r["role"] for r in results if r["status"] != "ok"]
    if failed:
        print(f"فشل: {failed} (إخراج فارغ أو JSON غير صالح أو خطأ)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
