"""المزوّد المتوافق مع OpenAI في miyar/llm.py بنقل وهمي — لا اتصال بالشبكة ولا استهلاك للحصة.

⚠️ FIXTURE: المفاتيح والعناوين والنماذج والإجابات هنا مصطنعة للاختبار، وليست بيانات حقيقية.
"""

import json

import pytest

from miyar import llm
from miyar.llm import (
    CacheMiss, LLMError, LLMRequest, MissingCredentials, OpenAICompatibleProvider, RateLimited, ServiceUnavailable,
    client_from_env,
)

FAKE_KEY = "FAKE-OPENAI-KEY-for-tests-only-321"  # ليس مفتاحاً حقيقياً
BASE = "https://llm.fixture.example/v1"


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(body)})
        return self.responses.pop(0)


def ok(text="جواب FIXTURE", finish="stop", model="fixture-model", reasoning=0):
    body = {"model": model, "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 5 + reasoning,
                      "completion_tokens_details": {"reasoning_tokens": reasoning}}}
    return 200, {}, json.dumps(body, ensure_ascii=False).encode()


def _env(tmp_path, mode="live", **extra):
    env = {
        "MIYAR_LLM_PROVIDER": "openai",
        "MIYAR_OPENAI_BASE_URL": BASE,
        "MIYAR_OPENAI_API_KEY": FAKE_KEY,
        "MIYAR_LLM_MODEL_ASSISTANT": "fixture-assistant",
        "MIYAR_LLM_MODEL_JUDGE": "fixture-judge",
        "MIYAR_RUN_MODE": mode,
        "MIYAR_LLM_CACHE_DIR": str(tmp_path),
        "MIYAR_LIVE_MAX_CALLS_PER_DAY": "5",
    }
    env.update(extra)
    return env


def test_request_shape_and_parse():
    t = FakeTransport(ok(reasoning=3))
    p = OpenAICompatibleProvider(FAKE_KEY, BASE + "/", t)
    resp = p.call(LLMRequest("openai", "fixture-model", "سؤال", system="تعليمات", temperature=0.0,
                             max_output_tokens=64, response_mime_type="application/json", thinking_level="low"))
    sent = t.calls[0]
    assert sent["url"] == f"{BASE}/chat/completions"  # الشرطة الأخيرة لا تتكرر
    assert sent["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"
    assert sent["body"] == {
        "model": "fixture-model",
        "messages": [{"role": "system", "content": "تعليمات"}, {"role": "user", "content": "سؤال"}],
        "temperature": 0.0, "max_tokens": 64, "response_format": {"type": "json_object"},
    }  # إعدادات التفكير الخاصة بـ Gemini لا تُرسل
    assert (resp.text, resp.provider, resp.model, resp.finish_reason) == ("جواب FIXTURE", "openai", "fixture-model", "STOP")
    assert (resp.output_tokens, resp.thoughts_tokens, resp.usage["promptTokenCount"]) == (5, 3, 7)


def test_no_system_message_when_empty():
    t = FakeTransport(ok())
    OpenAICompatibleProvider(FAKE_KEY, BASE, t).call(LLMRequest("openai", "m", "سؤال"))
    assert t.calls[0]["body"]["messages"] == [{"role": "user", "content": "سؤال"}]
    assert "response_format" not in t.calls[0]["body"]


def test_length_maps_to_max_tokens_and_is_incomplete():
    resp = OpenAICompatibleProvider(FAKE_KEY, BASE, FakeTransport(ok(finish="length"))).call(LLMRequest("openai", "m", "x"))
    assert resp.finish_reason == "MAX_TOKENS" and resp.is_incomplete()


def test_errors_map_to_layer_exceptions_and_never_leak_key():
    body429 = json.dumps({"error": {"message": f"slow down {FAKE_KEY}"}}).encode()
    p = OpenAICompatibleProvider(FAKE_KEY, BASE, FakeTransport(
        (429, {"Retry-After": "12"}, body429), (503, {}, b"busy"), (401, {}, f"bad key {FAKE_KEY}".encode()),
        (200, {}, b'{"choices": []}'),
    ))
    req = LLMRequest("openai", "m", "x")
    with pytest.raises(RateLimited) as e:
        p.call(req)
    assert e.value.retry_after == 12.0 and FAKE_KEY not in str(e.value)
    with pytest.raises(ServiceUnavailable):
        p.call(req)
    with pytest.raises(LLMError) as e:
        p.call(req)
    assert "401" in str(e.value) and FAKE_KEY not in str(e.value)
    with pytest.raises(LLMError):
        p.call(req)


@pytest.mark.parametrize("url", ["http://llm.fixture.example/v1", "ftp://x", "https://x/v1?k=1", "", "not a url"])
def test_base_url_must_be_https(url):
    with pytest.raises(LLMError):
        llm.validate_base_url(url)


def test_localhost_http_is_allowed_for_local_servers():
    assert llm.validate_base_url("http://localhost:8000/v1/") == "http://localhost:8000/v1"


def test_missing_key_or_base_url(tmp_path):
    with pytest.raises(MissingCredentials):
        OpenAICompatibleProvider("", BASE)
    with pytest.raises(MissingCredentials):
        client_from_env(_env(tmp_path, MIYAR_OPENAI_API_KEY=""), role="assistant")
    with pytest.raises(LLMError):
        client_from_env(_env(tmp_path, MIYAR_OPENAI_BASE_URL=""), role="assistant")
    # وضع cached يعمل بلا مفتاح (يقرأ المخزن فقط)
    client, _ = client_from_env(_env(tmp_path, mode="cached", MIYAR_OPENAI_API_KEY=""), role="assistant")
    assert client.provider is None and client.provider_name == "openai"


def test_unknown_provider_is_rejected(tmp_path):
    with pytest.raises(LLMError):
        client_from_env(_env(tmp_path, MIYAR_LLM_PROVIDER="anthropic"), role="assistant")


def test_client_from_env_stores_with_openai_key_and_replays_in_cached_mode(tmp_path):
    t = FakeTransport(ok("مرة واحدة"))
    client, model = client_from_env(_env(tmp_path), t, role="assistant")
    assert model == "fixture-assistant" and isinstance(client.provider, OpenAICompatibleProvider)
    # الطلب يُبنى بمزوّد gemini افتراضياً (targets/extract/judge)، والعميل يضع اسم مزوّده في البصمة
    first = client.complete(LLMRequest("gemini", model, "سؤال"))
    assert first.provider == "openai" and len(t.calls) == 1
    stored = json.loads(next(p for p in tmp_path.glob("*.json") if p.name not in ("usage.json",)).read_text())
    assert stored["request"]["provider"] == "openai" and FAKE_KEY not in json.dumps(stored, ensure_ascii=False)

    cached, _ = client_from_env(_env(tmp_path, mode="cached", MIYAR_OPENAI_API_KEY=""), t, role="assistant")
    again = cached.complete(LLMRequest("gemini", model, "سؤال"))
    assert again.text == "مرة واحدة" and again.from_cache and len(t.calls) == 1


def test_gemini_cache_entries_are_not_served_to_openai(tmp_path):
    t = FakeTransport(ok("من openai"))
    gem_env = {"MIYAR_LLM_PROVIDER": "gemini", "MIYAR_LLM_MODEL_ASSISTANT": "fixture-assistant",
               "MIYAR_RUN_MODE": "cached", "MIYAR_LLM_CACHE_DIR": str(tmp_path)}
    gem, _ = client_from_env(gem_env, t, role="assistant")
    with pytest.raises(CacheMiss):
        gem.complete(LLMRequest("gemini", "fixture-assistant", "سؤال"))
    oa, _ = client_from_env(_env(tmp_path), t, role="assistant")
    oa.complete(LLMRequest("gemini", "fixture-assistant", "سؤال"))
    with pytest.raises(CacheMiss):  # مخزن openai لا يُعاد لعميل gemini بالسؤال نفسه
        gem.complete(LLMRequest("gemini", "fixture-assistant", "سؤال"))


def test_judge_on_openai_has_no_implicit_gemini_fallback(tmp_path):
    client, model = client_from_env(_env(tmp_path), FakeTransport(), role="judge")
    assert model == "fixture-judge" and client.fallback_models == ()
    explicit, _ = client_from_env(_env(tmp_path, MIYAR_LLM_MODEL_JUDGE_FALLBACK="fixture-judge-2"), FakeTransport(),
                                  role="judge")
    assert explicit.fallback_models == ("fixture-judge-2",)


def test_gemini_default_fallback_and_keys_unchanged(tmp_path):
    env = {"MIYAR_LLM_PROVIDER": "gemini", "MIYAR_LLM_MODEL_JUDGE": "fixture-judge", "MIYAR_RUN_MODE": "cached",
           "MIYAR_LLM_CACHE_DIR": str(tmp_path)}
    client, _ = client_from_env(env, FakeTransport(), role="judge")
    assert client.fallback_models == (llm.DEFAULT_JUDGE_FALLBACK,)
    req = LLMRequest("gemini", "fixture-judge", "سؤال")
    assert client._prepare(req).provider == "gemini"
