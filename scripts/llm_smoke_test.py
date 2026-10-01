"""اختبار دخان لنموذجي الدورين (الحَكَم والمساعد): طلب توليد قصير واحد لكل نموذج.

- يمر عبر miyar/llm.py: كل استجابة تُخزَّن في evaluation/dev/llm_cache بوسم DEV_RUN، ولا يتكرر استدعاء أُجري.
- يكتب ملخصاً في evaluation/dev/smoke_<الوقت>.json بوسم DEV_RUN. تشغيل تطوير، لا يُنشر كنتيجة.
- السقف: محاولة واحدة لكل دور، وللحَكَم حتى 3 محاولات ثم 3 للنموذج الاحتياطي (عند 503/429 فقط).
- يسجّل لكل دور النموذج المطلوب والنموذج الذي أجاب فعلاً وكل المحاولات. لا يطبع قيمة أي متغير بيئة.
- الاستخدام: ``python scripts/llm_smoke_test.py [--role judge|assistant]`` (افتراضياً الدوران).

الطلب سؤال عام لا علاقة له بالمحتوى الشرعي، فاختبار الدخان لا يولّد نصاً دينياً.
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
    DEFAULT_MAX_ATTEMPTS,
    DEV_RUN,
    ROLE_MODEL_VARS,
    LLMError,
    LLMRequest,
    RateLimited,
    ResponseStore,
    client_from_env,
)

PROMPT = "Reply with exactly one word: OK"
MAX_OUTPUT_TOKENS = 16


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", choices=list(ROLE_MODEL_VARS), help="دور واحد فقط (افتراضياً الدوران)")
    args = ap.parse_args()
    roles = [args.role] if args.role else list(ROLE_MODEL_VARS)
    store = ResponseStore(os.environ.get("MIYAR_LLM_CACHE_DIR") or DEFAULT_CACHE_DIR)
    budget = sum(2 * DEFAULT_MAX_ATTEMPTS if r == "judge" else 1 for r in roles)
    cap = store.live_calls_today() + budget  # لا يتجاوز هذا التشغيل ميزانية محاولاته
    env = {**os.environ, "MIYAR_RUN_MODE": "live", "MIYAR_LIVE_MAX_CALLS_PER_DAY": str(cap)}
    results = []
    for role in roles:
        entry: dict = {"role": role, "model_var": ROLE_MODEL_VARS[role]}
        try:
            client, model = client_from_env(env, role=role)
            entry["requested_model"] = model
            entry["fallback_models"] = list(client.fallback_models)
            resp = client.complete(LLMRequest("gemini", model, PROMPT, max_output_tokens=MAX_OUTPUT_TOKENS))
            entry.update(
                # 200 بلا نص (مثلاً MAX_TOKENS بعد رموز التفكير) ليس نجاحاً للتوليد
                status="ok" if resp.text.strip() else "empty_output",
                answered_by=resp.model,
                attempts=resp.attempts,
                from_cache=resp.from_cache,
                text=resp.text,
                finish_reason=resp.finish_reason,
                usage=resp.usage,
                request_key=resp.request_key,
            )
        except RateLimited as e:
            entry.update(status="rate_limited", error=str(e), retry_after=e.retry_after)
        except LLMError as e:
            entry.update(status="error", error_type=type(e).__name__, error=str(e))
        results.append(entry)
        print(f"{role}: طُلب {entry.get('requested_model', '?')} → {entry['status']}"
              + (f" | أجاب: {entry['answered_by']} | المحاولات: {entry['attempts']} | text={entry['text']!r}"
                 if entry["status"] == "ok" else f" | {entry.get('error', '')[:300]}"))

    now = datetime.now(timezone.utc)
    out = ROOT / "evaluation" / "dev" / f"smoke_{now.strftime('%Y-%m-%dT%H%M%SZ')}.json"
    record = {
        "run_label": DEV_RUN,
        "note": "DEV_RUN: اختبار دخان للاتصال فقط، ليس نتيجة تقييم ولا يُنشر.",
        "ran_at": now.isoformat(timespec="seconds"),
        "prompt": PROMPT,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "results": results,
    }
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"حُفظ: {out.relative_to(ROOT)}")
    return 0 if all(r["status"] == "ok" for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
