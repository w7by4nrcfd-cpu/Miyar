"""سكربت الدخان يفشل صراحةً عند الإخراج الفارغ أو JSON غير الصالح — بنقل وهمي، بلا شبكة."""

import importlib.util
import json
from pathlib import Path

from miyar.llm import GeminiProvider, LLMClient, ResponseStore

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("llm_smoke_test", ROOT / "scripts" / "llm_smoke_test.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)

FAKE_KEY = "FAKE-KEY-for-tests-only-123"  # ليس مفتاحاً حقيقياً


def _client(tmp_path, text, finish="STOP"):
    body = {
        "candidates": [{"content": {"parts": [{"text": text}] if text else []}, "finishReason": finish}],
        "usageMetadata": {"thoughtsTokenCount": 3, "candidatesTokenCount": 5},
    }
    transport = lambda *a: (200, {}, json.dumps(body).encode())  # noqa: E731
    return LLMClient(GeminiProvider(FAKE_KEY, transport), ResponseStore(tmp_path), "live", 5)


def test_check_json():
    assert smoke._check_json('{"verdict": "supported"}') == (True, "supported")
    assert smoke._check_json("not json")[0] is False
    assert smoke._check_json('{"verdict": "maybe"}')[0] is False
    assert smoke._check_json("[]")[0] is False


def test_attempt_statuses(tmp_path):
    p = smoke.JUDGE_PROMPT
    ok = smoke._attempt(_client(tmp_path / "a", '{"verdict": "supported"}'), "m", p, 1024, True)
    assert ok["status"] == "ok" and ok["matches_expected"] is True and ok["output_tokens"] == 5
    assert smoke._attempt(_client(tmp_path / "b", ""), "m", p, 1024, True)["status"] == "empty_output"
    assert smoke._attempt(_client(tmp_path / "c", "x", "MAX_TOKENS"), "m", p, 1024, True)["status"] == "empty_output"
    assert smoke._attempt(_client(tmp_path / "d", "نص"), "m", p, 1024, True)["status"] == "invalid_json"
    assert smoke._attempt(_client(tmp_path / "e", "OK"), "m", "q", 16, False)["status"] == "ok"
