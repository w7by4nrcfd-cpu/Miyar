"""اختبارات طبقة النموذج اللغوي بنقل وهمي — لا اتصال بالشبكة ولا استهلاك للحصة."""

import json

import pytest

from miyar.llm import (
    DEV_RUN,
    CacheMiss,
    CallBudgetExceeded,
    GeminiProvider,
    IncompleteOutput,
    LLMClient,
    LLMError,
    LLMRequest,
    MissingCredentials,
    RateLimited,
    ResponseStore,
    ServiceUnavailable,
    client_from_env,
)

FAKE_KEY = "FAKE-KEY-for-tests-only-123"  # ليس مفتاحاً حقيقياً


class FakeTransport:
    """يسجّل الطلبات ويعيد استجابات معدّة مسبقاً بالترتيب."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": headers, "body": json.loads(body)})
        return self.responses.pop(0)


def ok(text="جواب", finish="STOP"):
    body = {
        "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}],
        "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2},
    }
    return 200, {}, json.dumps(body, ensure_ascii=False).encode()


REQ = LLMRequest(provider="gemini", model="test-model", prompt="سؤال", system="تعليمات")


def test_request_key_is_stable_and_sensitive():
    assert REQ.key() == LLMRequest("gemini", "test-model", "سؤال", "تعليمات").key()
    assert REQ.key() != LLMRequest("gemini", "test-model", "سؤال آخر", "تعليمات").key()
    assert REQ.key() != LLMRequest("gemini", "other-model", "سؤال", "تعليمات").key()


def test_gemini_request_shape_and_parse():
    t = FakeTransport(ok("نص الإجابة"))
    resp = GeminiProvider(FAKE_KEY, t).call(REQ)
    call = t.calls[0]
    assert call["url"].endswith("/v1beta/models/test-model:generateContent")
    assert call["headers"]["x-goog-api-key"] == FAKE_KEY
    assert call["body"]["contents"][0]["parts"][0]["text"] == "سؤال"
    assert call["body"]["systemInstruction"]["parts"][0]["text"] == "تعليمات"
    assert call["body"]["generationConfig"] == {"temperature": 0.0, "maxOutputTokens": 1024}
    assert resp.text == "نص الإجابة" and resp.finish_reason == "STOP" and resp.usage["promptTokenCount"] == 3


def test_gemini_429_retry_after_header_and_body():
    t = FakeTransport((429, {"Retry-After": "12"}, b"{}"))
    with pytest.raises(RateLimited) as e:
        GeminiProvider(FAKE_KEY, t).call(REQ)
    assert e.value.retry_after == 12.0
    body = b'{"error":{"code":429,"status":"RESOURCE_EXHAUSTED","details":[{"retryDelay":"30s"}]}}'
    with pytest.raises(RateLimited) as e:
        GeminiProvider(FAKE_KEY, FakeTransport((429, {}, body))).call(REQ)
    assert e.value.retry_after == 30.0


def test_errors_never_leak_the_key():
    body = f'{{"error":{{"message":"bad key {FAKE_KEY}"}}}}'.encode()
    with pytest.raises(LLMError) as e:
        GeminiProvider(FAKE_KEY, FakeTransport((400, {}, body))).call(REQ)
    assert FAKE_KEY not in str(e.value) and "***" in str(e.value)


def test_blocked_prompt_without_candidates():
    body = json.dumps({"promptFeedback": {"blockReason": "SAFETY"}}).encode()
    with pytest.raises(LLMError, match="SAFETY"):
        GeminiProvider(FAKE_KEY, FakeTransport((200, {}, body))).call(REQ)


def test_missing_key():
    with pytest.raises(MissingCredentials):
        GeminiProvider("")


def _client(tmp_path, transport, mode="live", cap=5):
    return LLMClient(GeminiProvider(FAKE_KEY, transport), ResponseStore(tmp_path), mode, cap)


def test_live_call_is_stored_and_never_repeated(tmp_path):
    t = FakeTransport(ok("مرة واحدة"))
    c = _client(tmp_path, t)
    first = c.complete(REQ)
    second = c.complete(REQ)
    assert len(t.calls) == 1
    assert first.from_cache is False and second.from_cache is True and second.text == "مرة واحدة"


def test_stored_file_is_labelled_and_has_no_secret(tmp_path):
    _client(tmp_path, FakeTransport(ok())).complete(REQ)
    files = list(tmp_path.glob("*.json"))
    assert {f.name for f in files} == {f"{REQ.key()}.json", "usage.json"}
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert DEV_RUN in text and FAKE_KEY not in text


def test_cached_mode_never_calls(tmp_path):
    t = FakeTransport()
    c = LLMClient(None, ResponseStore(tmp_path), "cached")
    with pytest.raises(CacheMiss):
        c.complete(REQ)
    assert t.calls == []


def test_cached_mode_replays_stored(tmp_path):
    _client(tmp_path, FakeTransport(ok("محفوظ"))).complete(REQ)
    assert LLMClient(None, ResponseStore(tmp_path), "cached").complete(REQ).text == "محفوظ"


def test_daily_cap(tmp_path):
    t = FakeTransport(ok("1"), ok("2"))
    c = _client(tmp_path, t, cap=1)
    c.complete(REQ)
    with pytest.raises(CallBudgetExceeded):
        c.complete(LLMRequest("gemini", "test-model", "سؤال جديد"))
    assert len(t.calls) == 1


def test_rate_limited_attempt_counts_and_is_not_stored(tmp_path):
    t = FakeTransport((429, {}, b"{}"))
    c = _client(tmp_path, t, cap=5)
    with pytest.raises(RateLimited):
        c.complete(REQ)
    assert c.store.get(REQ) is None and c.store.live_calls_today() == 1


def test_client_from_env(tmp_path):
    base = {"MIYAR_LLM_CACHE_DIR": str(tmp_path), "MIYAR_LLM_MODEL": "m"}
    c, model = client_from_env(base)
    assert model == "m" and c.mode == "cached" and c.provider is None
    with pytest.raises(LLMError, match="MIYAR_LLM_MODEL"):
        client_from_env({"MIYAR_LLM_CACHE_DIR": str(tmp_path)})
    with pytest.raises(MissingCredentials):
        client_from_env({**base, "MIYAR_RUN_MODE": "live"})
    with pytest.raises(LLMError, match="غير منفّذ"):
        client_from_env({**base, "MIYAR_LLM_PROVIDER": "anthropic"})
    c, _ = client_from_env({**base, "MIYAR_RUN_MODE": "live", "GEMINI_API_KEY": FAKE_KEY, "MIYAR_LIVE_MAX_CALLS_PER_DAY": "7"})
    assert c.mode == "live" and c.max_live_calls_per_day == 7 and c.store.run_label == DEV_RUN


def test_client_from_env_role_models(tmp_path):
    base = {
        "MIYAR_LLM_CACHE_DIR": str(tmp_path),
        "MIYAR_LLM_MODEL_JUDGE": "judge-m",
        "MIYAR_LLM_MODEL_ASSISTANT": "assistant-m",
    }
    assert client_from_env(base, role="judge")[1] == "judge-m"
    assert client_from_env(base, role="assistant")[1] == "assistant-m"
    # بلا متغير الدور: يُرجع إلى MIYAR_LLM_MODEL
    assert client_from_env({"MIYAR_LLM_CACHE_DIR": str(tmp_path), "MIYAR_LLM_MODEL": "m"}, role="judge")[1] == "m"
    with pytest.raises(LLMError, match="MIYAR_LLM_MODEL"):
        client_from_env({"MIYAR_LLM_CACHE_DIR": str(tmp_path)}, role="assistant")
    with pytest.raises(ValueError):
        client_from_env(base, role="other")


# ---------- احتياط الحَكَم: 3 محاولات بتأخير تصاعدي ثم النموذج الاحتياطي ----------
BUSY = (503, {}, b'{"error": {"code": 503, "status": "UNAVAILABLE"}}')
LIMITED = (429, {}, b'{"error": {"code": 429}}')


def _judge_client(tmp_path, transport, cap=20):
    slept = []
    c = LLMClient(
        GeminiProvider(FAKE_KEY, transport), ResponseStore(tmp_path), "live", cap,
        fallback_models=("fallback-model",), max_attempts=3, sleep=slept.append,
    )
    return c, slept


def test_retry_then_success_on_primary(tmp_path):
    t = FakeTransport(BUSY, LIMITED, ok("نجح"))
    c, slept = _judge_client(tmp_path, t)
    r = c.complete(REQ)
    assert r.text == "نجح" and r.model == r.requested_model == "test-model"
    assert slept == [2.0, 4.0]  # تأخير تصاعدي
    assert [a["status"] for a in r.attempts] == [503, 429, 200]


def test_fallback_after_three_failures_records_answering_model(tmp_path):
    t = FakeTransport(BUSY, BUSY, BUSY, ok("من الاحتياطي"))
    c, slept = _judge_client(tmp_path, t)
    r = c.complete(REQ)
    assert r.model == "fallback-model" and r.requested_model == "test-model"
    assert t.calls[-1]["url"].endswith("/models/fallback-model:generateContent")
    assert slept == [2.0, 4.0]
    assert [(a["model"], a["status"]) for a in r.attempts] == [
        ("test-model", 503), ("test-model", 503), ("test-model", 503), ("fallback-model", 200)]
    stored = json.loads((tmp_path / f"{r.request_key}.json").read_text(encoding="utf-8"))
    assert stored["response"]["model"] == "fallback-model"
    assert stored["response"]["requested_model"] == "test-model"
    # الإعادة من المخزن: لا استدعاء جديد، والنموذج المسجّل هو الذي أجاب فعلاً
    again = c.complete(REQ)
    assert len(t.calls) == 4 and again.from_cache
    assert again.model == "fallback-model" and again.requested_model == "test-model"
    cached = LLMClient(None, ResponseStore(tmp_path), "cached", fallback_models=("fallback-model",)).complete(REQ)
    assert cached.model == "fallback-model"


def test_all_fail_raises_last_error(tmp_path):
    t = FakeTransport(BUSY, BUSY, BUSY, LIMITED, LIMITED, LIMITED)
    c, _ = _judge_client(tmp_path, t)
    with pytest.raises(RateLimited):
        c.complete(REQ)
    assert len(t.calls) == 6 and c.store.live_calls_today() == 6


def test_retries_respect_daily_cap(tmp_path):
    t = FakeTransport(BUSY, BUSY)
    c, _ = _judge_client(tmp_path, t, cap=2)
    with pytest.raises(CallBudgetExceeded):
        c.complete(REQ)
    assert len(t.calls) == 2


def test_non_retryable_error_is_not_retried(tmp_path):
    t = FakeTransport((404, {}, b'{"error": {"code": 404}}'))
    c, slept = _judge_client(tmp_path, t)
    with pytest.raises(LLMError, match="404"):
        c.complete(REQ)
    assert len(t.calls) == 1 and slept == []


def test_503_raises_service_unavailable():
    with pytest.raises(ServiceUnavailable):
        GeminiProvider(FAKE_KEY, FakeTransport(BUSY)).call(REQ)


def test_judge_role_has_fallback_assistant_does_not(tmp_path):
    base = {"MIYAR_LLM_CACHE_DIR": str(tmp_path), "MIYAR_LLM_MODEL_JUDGE": "j", "MIYAR_LLM_MODEL_ASSISTANT": "a"}
    judge, _ = client_from_env(base, role="judge")
    assert judge.fallback_models == ("gemini-3.5-flash",) and judge.max_attempts == 3
    assistant, _ = client_from_env(base, role="assistant")
    assert assistant.fallback_models == () and assistant.max_attempts == 1
    custom, _ = client_from_env({**base, "MIYAR_LLM_MODEL_JUDGE_FALLBACK": "x"}, role="judge")
    assert custom.fallback_models == ("x",)


# ---------- الإجابات الناقصة، وإعداد التفكير، وسقف الحَكَم ----------
def _resp(text, finish="STOP", thoughts=0, out=0):
    body = {
        "candidates": [{"content": {"parts": [{"text": text}] if text else []}, "finishReason": finish}],
        "usageMetadata": {"thoughtsTokenCount": thoughts, "candidatesTokenCount": out},
    }
    return 200, {}, json.dumps(body).encode()


def test_old_request_keys_are_unchanged():
    # البصمة القديمة (قبل الحقول الاختيارية) يجب أن تبقى كما هي حتى لا يضيع المخزن
    old = json.dumps(
        {"provider": "gemini", "model": "test-model", "prompt": "سؤال", "system": "تعليمات",
         "temperature": 0.0, "max_output_tokens": 1024},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    import hashlib
    assert REQ.key() == hashlib.sha256(old.encode("utf-8")).hexdigest()
    assert REQ.key() != LLMRequest("gemini", "test-model", "سؤال", "تعليمات", thinking_level="low").key()


def test_empty_or_max_tokens_output_is_never_stored(tmp_path):
    for i, r in enumerate([_resp("", "MAX_TOKENS", 13, 0), _resp("مقطوع", "MAX_TOKENS", 5, 3), _resp("  ")]):
        c = _client(tmp_path / str(i), FakeTransport(r))
        with pytest.raises(IncompleteOutput) as e:
            c.complete(REQ)
        assert c.store.get(REQ) is None
        assert not list((tmp_path / str(i)).glob("[0-9a-f]*.json"))
    assert e.value.response.finish_reason == "STOP"


def test_invalid_for_replay_record_is_skipped(tmp_path):
    _client(tmp_path, FakeTransport(ok("قديم"))).complete(REQ)
    f = tmp_path / f"{REQ.key()}.json"
    rec = json.loads(f.read_text(encoding="utf-8"))
    rec["invalid_for_replay"] = True
    f.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CacheMiss):
        LLMClient(None, ResponseStore(tmp_path), "cached").complete(REQ)


def test_usage_fields_are_recorded(tmp_path):
    c = _client(tmp_path, FakeTransport(_resp('{"verdict":"supported"}', "STOP", 40, 7)))
    r = c.complete(REQ)
    assert (r.finish_reason, r.thoughts_tokens, r.output_tokens) == ("STOP", 40, 7)
    stored = json.loads((tmp_path / f"{REQ.key()}.json").read_text(encoding="utf-8"))["response"]
    assert stored["thoughts_tokens"] == 40 and stored["output_tokens"] == 7


def test_judge_floor_thinking_and_json_mime(tmp_path):
    t = FakeTransport(_resp("{}", "STOP", 1, 1))
    c, _ = client_from_env(
        {"MIYAR_LLM_CACHE_DIR": str(tmp_path), "MIYAR_LLM_MODEL_JUDGE": "gemini-3.8-flash",
         "MIYAR_RUN_MODE": "live", "GEMINI_API_KEY": FAKE_KEY, "MIYAR_LIVE_MAX_CALLS_PER_DAY": "5"},
        transport=t, role="judge")
    c.complete(LLMRequest("gemini", "gemini-3.8-flash", "س", max_output_tokens=16, response_mime_type="application/json"))
    cfg = t.calls[0]["body"]["generationConfig"]
    assert cfg["maxOutputTokens"] == 1024
    assert cfg["thinkingConfig"] == {"thinkingLevel": "low"}
    assert cfg["responseMimeType"] == "application/json"


def test_thinking_config_by_family():
    from miyar.llm import JUDGE_THINKING, thinking_config_for
    assert thinking_config_for("gemini-3.8-flash", JUDGE_THINKING) == {"thinking_level": "low"}
    assert thinking_config_for("gemini-2.5-flash", JUDGE_THINKING) == {"thinking_budget": 256}
    assert thinking_config_for("gemma-4-31b-it", JUDGE_THINKING) == {}


def test_incomplete_primary_falls_back(tmp_path):
    t = FakeTransport(_resp("", "MAX_TOKENS", 13, 0), ok("من الاحتياطي"))
    c, slept = _judge_client(tmp_path, t)
    r = c.complete(REQ)
    assert r.model == "fallback-model" and slept == []
    assert [a["status"] for a in r.attempts] == ["incomplete", 200]


# ---------- معرّف التشغيل في مفتاح الطلب، وسجل 429 لكل تشغيل ----------
def _run_client(tmp_path, transport, run_id, cap=20):
    return LLMClient(GeminiProvider(FAKE_KEY, transport), ResponseStore(tmp_path), "live", cap, run_id=run_id)


def test_different_run_ids_call_the_model_again(tmp_path):
    t = FakeTransport(ok("تشغيل 1"), ok("تشغيل 2"))
    r1 = _run_client(tmp_path, t, "official-1").complete(REQ)
    r2 = _run_client(tmp_path, t, "official-2").complete(REQ)
    assert len(t.calls) == 2  # استدعاءان فعليان: لا إعادة من المخزن بين تشغيلين
    assert (r1.from_cache, r2.from_cache) == (False, False)
    assert (r1.text, r2.text) == ("تشغيل 1", "تشغيل 2")
    assert r1.request_key != r2.request_key
    assert "run_id" not in json.dumps(t.calls[0]["body"])  # المعرّف في البصمة فقط، لا يُرسل إلى المزوّد


def test_same_run_id_replays_from_store(tmp_path):
    t = FakeTransport(ok("مرة واحدة"))
    first = _run_client(tmp_path, t, "official-1").complete(REQ)
    again = _run_client(tmp_path, t, "official-1").complete(REQ)  # إعادة التشغيل نفسه (عميل جديد، المخزن نفسه)
    assert len(t.calls) == 1 and again.from_cache and again.text == first.text
    cached = LLMClient(None, ResponseStore(tmp_path), "cached", run_id="official-1").complete(REQ)
    assert cached.text == "مرة واحدة"
    with pytest.raises(CacheMiss):
        LLMClient(None, ResponseStore(tmp_path), "cached", run_id="official-2").complete(REQ)


def test_run_id_from_env(tmp_path):
    base = {"MIYAR_LLM_CACHE_DIR": str(tmp_path), "MIYAR_LLM_MODEL_JUDGE": "j", "MIYAR_LLM_MODEL_ASSISTANT": "a",
            "MIYAR_RUN_ID": "official-3"}
    assert client_from_env(base, role="judge")[0].run_id == "official-3"
    assert client_from_env(base, role="assistant")[0].run_id == "official-3"
    assert client_from_env({**base, "MIYAR_RUN_ID": ""}, role="assistant")[0].run_id is None


def test_rate_limits_are_counted_per_run(tmp_path):
    limited = (429, {"Retry-After": "7"}, b'{"error": {"code": 429}}')
    t = FakeTransport(limited, ok("بعد الانتظار"), limited)
    slept = []
    c = LLMClient(GeminiProvider(FAKE_KEY, t), ResponseStore(tmp_path), "live", 20, max_attempts=3,
                  sleep=slept.append, run_id="official-1")
    assert c.complete(REQ).text == "بعد الانتظار"
    c2 = LLMClient(GeminiProvider(FAKE_KEY, t), ResponseStore(tmp_path), "live", 20, run_id="official-2")
    with pytest.raises(RateLimited):
        c2.complete(REQ)
    store = ResponseStore(tmp_path)
    assert store.rate_limit_count("official-1") == 1 and store.rate_limit_count("official-2") == 1
    assert store.rate_limit_count("official-3") == 0
    log = json.loads((tmp_path / "rate_limits.json").read_text(encoding="utf-8"))
    assert log["run_label"] == DEV_RUN
    assert log["runs"]["official-1"]["events"][0]["retry_after"] == 7.0 and slept == [7.0]
