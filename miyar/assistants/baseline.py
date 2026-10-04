"""المساعد المرجعي baseline: نموذج لغوي عادي يجيب مباشرة (CLAUDE.md، «تعديلات الخطة» 1).

- بلا بحث في المصادر وبلا إسناد مُعان؛ هذا ما يميّزه عن ``rag``.
- تعليمات النظام عامة عمداً: لا تحوي معيار الحكم ولا قواعد المستويات، حتى يُقاس سلوك النموذج كما هو.
- النموذج من ``MIYAR_LLM_MODEL_ASSISTANT`` (أو ``MIYAR_LLM_MODEL``)، والوضع والسقف والمخزن من متغيرات البيئة (``miyar.llm``).
- لا يستورد محرك الحكم (``judge``).
"""

from __future__ import annotations

from ..llm import Transport, client_from_env, urllib_transport
from ..targets import LLMTarget

NAME = "baseline"
SYSTEM = "أنت مساعد ذكي. أجب عن سؤال المستخدم باللغة التي سأل بها."


def build(env: dict | None = None, transport: Transport = urllib_transport) -> LLMTarget:
    """يبني المساعد من متغيرات البيئة (الدور: assistant)."""
    client, model = client_from_env(env, transport, role="assistant")
    return LLMTarget(name=NAME, client=client, model=model, system=SYSTEM)
