"""مزوّد Anthropic في miyar/llm.py للحَكَم والاستخراج، بنقل وهمي — لا اتصال بالشبكة ولا استهلاك للحصة.

⚠️ FIXTURE: المفاتيح والنماذج والإجابات هنا مصطنعة للاختبار، وليست بيانات حقيقية.
"""

import json

import pytest

from miyar import llm
from miyar.llm import (
    AnthropicProvider, CacheMiss, GeminiProvider, IncompleteOutput, LLMError, LLMRequest, MissingCredentials,
    RateLimited, ServiceUnavailable, client_from_env,
)

FAKE_KEY = "FAKE-ANTHROPIC-KEY-for-tests-only-654"  # ليس مفتاحاً حقيقياً
FAKE_GEMINI_KEY = "FAKE-GEMINI-KEY-for-tests-only-987"


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(body)})
        return self.responses.pop(0)


def ok(text="جواب FIXTURE", stop="end_turn", model="fixture-claude"):
    body = {"id": "msg_fixture", "type": "message", "role": "assistant", "model": model,
            "content": [{"type": "text", "text": text}], "stop_reason": stop,
            "usage": {"input_tokens": 9, "output_tokens": 4}}
    return 200, {}, json.dumps(body, ensure_ascii=False).encode()


def _env(tmp_path, mode="live", **extra):
    env = {
        "MIYAR_LLM_PROVIDER": "gemini",
        "MIYAR_LLM_PROVIDER_JUDGE": "anthropic",
        "ANTHROPIC_API_KEY": FAKE_KEY,
        "GEMINI_API_KEY": FAKE_GEMINI_KEY,
        "MIYAR_LLM_MODEL_ASSISTANT": "gemini-fixture-assistant",
        "MIYAR_LLM_MODEL_JUDGE": "fixture-claude",
        "MIYAR_RUN_MODE": mode,
        "MIYAR_LLM_CACHE_DIR": str(tmp_path),
        "MIYAR_LIVE_MAX_CALLS_PER_DAY": "5",
    }
    env.update(extra)
    return env


def test_request_shape_and_parse():
    t = FakeTransport(ok())
    resp = AnthropicProvider(FAKE_KEY, t).call(LLMRequest(
        "anthropic", "fixture-claude", "سؤال", system="تعليمات", temperature=0.0, max_output_tokens=64,
        response_mime_type="application/json", thinking_level="low"))
    sent = t.calls[0]
    assert sent["url"] == "https://api.anthropic.com/v1/messages"
    assert sent["headers"]["x-api-key"] == FAKE_KEY and sent["headers"]["anthropic-version"] == "2023-06-01"
    assert sent["body"] == {
        "model": "fixture-claude", "max_tokens": 64, "temperature": 0.0, "system": "تعليمات",
        "messages": [{"role": "user", "content": "سؤال"}],
    }  # إعدادات Gemini (التفكير وresponseMimeType) لا تُرسل
    assert (resp.text, resp.provider, resp.model, resp.finish_reason) == ("جواب FIXTURE", "anthropic", "fixture-claude", "STOP")
    assert (resp.output_tokens, resp.thoughts_tokens, resp.usage["promptTokenCount"]) == (4, 0, 9)


def test_no_system_field_when_empty_and_only_text_blocks():
    body = {"model": "m", "stop_reason": "end_turn", "usage": {},
            "content": [{"type": "thinking", "thinking": "داخلي"}, {"type": "text", "text": "أ"}, {"type": "text", "text": "ب"}]}
    t = FakeTransport((200, {}, json.dumps(body, ensure_ascii=False).encode()))
    resp = AnthropicProvider(FAKE_KEY, t).call(LLMRequest("anthropic", "m", "سؤال"))
    assert "system" not in t.calls[0]["body"] and resp.text == "أب"


@pytest.mark.parametrize("stop,mapped", [("max_tokens", "MAX_TOKENS"), ("refusal", "SAFETY"), ("stop_sequence", "STOP")])
def test_stop_reason_mapping(stop, mapped):
    resp = AnthropicProvider(FAKE_KEY, FakeTransport(ok(stop=stop))).call(LLMRequest("anthropic", "m", "x"))
    assert resp.finish_reason == mapped
    assert resp.is_incomplete() == (mapped == "MAX_TOKENS")


def test_errors_map_to_layer_exceptions_and_never_leak_key():
    body429 = json.dumps({"type": "error", "error": {"type": "rate_limit_error", "message": f"slow {FAKE_KEY}"}}).encode()
    p = AnthropicProvider(FAKE_KEY, FakeTransport(
        (429, {"retry-after": "7"}, body429), (529, {}, b'{"type":"error","error":{"type":"overloaded_error"}}'),
        (503, {}, b"busy"), (401, {}, f"bad key {FAKE_KEY}".encode()),
    ))
    req = LLMRequest("anthropic", "m", "x")
    with pytest.raises(RateLimited) as e:
        p.call(req)
    assert e.value.retry_after == 7.0 and FAKE_KEY not in str(e.value)
    for _ in range(2):
        with pytest.raises(ServiceUnavailable):
            p.call(req)
    with pytest.raises(LLMError) as e:
        p.call(req)
    assert "401" in str(e.value) and FAKE_KEY not in str(e.value)


def test_judge_uses_anthropic_while_assistant_stays_on_gemini(tmp_path):
    env = _env(tmp_path)
    judge, jmodel = client_from_env(env, FakeTransport(), role="judge")
    assistant, amodel = client_from_env(env, FakeTransport(), role="assistant")
    assert isinstance(judge.provider, AnthropicProvider) and judge.provider_name == "anthropic"
    assert jmodel == "fixture-claude"  # اسم النموذج من MIYAR_LLM_MODEL_JUDGE، بلا قيمة افتراضية في الكود
    assert isinstance(assistant.provider, GeminiProvider) and amodel == "gemini-fixture-assistant"


def test_model_name_comes_from_env_only(tmp_path):
    _, model = client_from_env(_env(tmp_path, MIYAR_LLM_MODEL_JUDGE="fixture-claude-2"), FakeTransport(), role="judge")
    assert model == "fixture-claude-2"
    with pytest.raises(LLMError, match="MIYAR_LLM_MODEL غير مضبوط"):  # ولا MIYAR_LLM_MODEL الاحتياطي
        client_from_env(_env(tmp_path, MIYAR_LLM_MODEL_JUDGE=""), FakeTransport(), role="judge")


def test_gemini_model_name_with_anthropic_is_rejected_before_any_call(tmp_path):
    t = FakeTransport()
    with pytest.raises(LLMError, match="Claude"):
        client_from_env(_env(tmp_path, MIYAR_LLM_MODEL_JUDGE="gemini-3.8-flash"), t, role="judge")
    assert t.calls == []


def test_anthropic_is_judge_only(tmp_path):
    with pytest.raises(LLMError, match="للحَكَم وحده"):
        client_from_env(_env(tmp_path, MIYAR_LLM_PROVIDER="anthropic"), FakeTransport(), role="assistant")
    with pytest.raises(LLMError):  # والمزوّد غير المعروف مرفوض
        client_from_env(_env(tmp_path, MIYAR_LLM_PROVIDER_JUDGE="fixture-unknown"), FakeTransport(), role="judge")


def test_missing_key(tmp_path):
    with pytest.raises(MissingCredentials):
        AnthropicProvider("")
    with pytest.raises(MissingCredentials):
        client_from_env(_env(tmp_path, ANTHROPIC_API_KEY=""), role="judge")
    # وضع cached يعمل بلا مفتاح (يقرأ المخزن فقط)
    client, _ = client_from_env(_env(tmp_path, mode="cached", ANTHROPIC_API_KEY=""), role="judge")
    assert client.provider is None and client.provider_name == "anthropic"


def test_no_implicit_gemini_fallback_for_anthropic_judge(tmp_path):
    client, _ = client_from_env(_env(tmp_path), FakeTransport(), role="judge")
    assert client.fallback_models == ()
    # احتياط Gemini المضبوط من إعداد سابق لا يُرسل إلى Anthropic
    stale, _ = client_from_env(_env(tmp_path, MIYAR_LLM_MODEL_JUDGE_FALLBACK="gemini-3.5-flash"), FakeTransport(),
                               role="judge")
    assert stale.fallback_models == ()
    explicit, _ = client_from_env(_env(tmp_path, MIYAR_LLM_MODEL_JUDGE_FALLBACK="fixture-claude-small"),
                                  FakeTransport(), role="judge")
    assert explicit.fallback_models == ("fixture-claude-small",)


def test_judge_settings_apply_without_gemini_thinking(tmp_path):
    t = FakeTransport(ok())
    client, model = client_from_env(_env(tmp_path), t, role="judge")
    resp = client.complete(LLMRequest("gemini", model, "سؤال", max_output_tokens=100))
    body = t.calls[0]["body"]
    assert body["max_tokens"] == llm.JUDGE_MIN_OUTPUT_TOKENS  # سقف الحَكَم الأدنى يبقى مطبَّقاً
    assert "thinking" not in body and resp.provider == "anthropic"


def test_stores_once_and_replays_in_cached_mode_without_key(tmp_path):
    t = FakeTransport(ok("مرة واحدة"))
    client, model = client_from_env(_env(tmp_path), t, role="judge")
    first = client.complete(LLMRequest("gemini", model, "سؤال"))
    assert first.provider == "anthropic" and len(t.calls) == 1
    stored = json.loads(next(p for p in tmp_path.glob("*.json") if p.name != "usage.json").read_text())
    assert stored["request"]["provider"] == "anthropic" and FAKE_KEY not in json.dumps(stored, ensure_ascii=False)

    cached, _ = client_from_env(_env(tmp_path, mode="cached", ANTHROPIC_API_KEY=""), t, role="judge")
    again = cached.complete(LLMRequest("gemini", model, "سؤال"))
    assert again.text == "مرة واحدة" and again.from_cache and len(t.calls) == 1


def test_gemini_judge_cache_is_not_served_to_anthropic_judge(tmp_path):
    gem_env = _env(tmp_path, mode="cached", MIYAR_LLM_PROVIDER_JUDGE="", MIYAR_LLM_MODEL_JUDGE="fixture-claude")
    gem, _ = client_from_env(gem_env, FakeTransport(), role="judge")
    assert gem.provider_name == "gemini"
    client, model = client_from_env(_env(tmp_path), FakeTransport(ok()), role="judge")
    client.complete(LLMRequest("gemini", model, "سؤال"))
    with pytest.raises(CacheMiss):  # مخزن anthropic لا يُعاد لحَكَم gemini بالسؤال نفسه
        gem.complete(LLMRequest("gemini", model, "سؤال"))


def test_truncated_answer_is_not_stored(tmp_path):
    t = FakeTransport(ok("نصف", stop="max_tokens"))
    client, model = client_from_env(_env(tmp_path), t, role="judge")
    with pytest.raises(IncompleteOutput):
        client.complete(LLMRequest("gemini", model, "سؤال"))
    assert not [p for p in tmp_path.glob("*.json") if p.name not in ("usage.json", "rate_limits.json")]
