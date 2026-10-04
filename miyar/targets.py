"""محولات المساعد المُختبَر (Target): ما يطرح عليه مِعيار أسئلة مجموعة الاختبار.

كل محوّل يحقق واجهة ``runner.Target``: ``name`` و``answer(prompt, context) -> Answer``.
- ``LLMTarget``: مساعد مبني على نموذج لغوي عبر ``miyar.llm`` (المخزن، والوضعان cached/live، والسقف اليومي، و``run_id``).
- ``PastedAnswersTarget``: إجابات ملصقة مسبقاً لمساعد خارجي، بلا أي استدعاء.

لا يستورد هذا الملف محرك الحكم (``judge``): المساعد المُختبَر لا يرى معيار الحكم (CLAUDE.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .llm import LLMClient, LLMRequest
from .runner import Answer

# إخراج المساعد: سقف يتسع لإجابة شرح كاملة ولتفكير نماذج Gemini 3 (الإجابة الناقصة لا تُخزَّن أبداً: IncompleteOutput)
ASSISTANT_MAX_OUTPUT_TOKENS = 2048

CONTEXT_OPEN = "<<<النص المرفق"
CONTEXT_CLOSE = "نهاية النص المرفق>>>"


def compose_prompt(prompt: str, context: str | None = None) -> str:
    """السؤال كما هو؛ وإن كان معه نص مرفق (حالات حقن الأوامر في النص المسترجع) يُقدَّم قبله بين محددين صريحين."""
    if not context:
        return prompt
    return f"{CONTEXT_OPEN}\n{context}\n{CONTEXT_CLOSE}\n\n{prompt}"


@dataclass
class LLMTarget:
    """مساعد = نموذج لغوي + تعليمات نظام ثابتة. الإجابة تُخزَّن بمفتاح الطلب (ومنه run_id) فلا يتكرر الاستدعاء."""

    name: str
    client: LLMClient
    model: str
    system: str
    provider: str = "gemini"
    max_output_tokens: int = ASSISTANT_MAX_OUTPUT_TOKENS
    temperature: float = 0.0

    def request(self, prompt: str, context: str | None = None) -> LLMRequest:
        return LLMRequest(
            provider=self.provider,
            model=self.model,
            prompt=compose_prompt(prompt, context),
            system=self.system,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
        )

    def answer(self, prompt: str, context: str | None = None) -> Answer:
        resp = self.client.complete(self.request(prompt, context))
        return Answer(text=resp.text, model=resp.model, from_cache=resp.from_cache)


@dataclass
class PastedAnswersTarget:
    """إجابات مساعد خارجي ملصقة مسبقاً، مفتاحها نص السؤال كما في مجموعة الاختبار. لا استدعاء لأي نموذج."""

    name: str
    answers: dict[str, str] = field(default_factory=dict)
    model: str = "pasted"

    def answer(self, prompt: str, context: str | None = None) -> Answer:
        if prompt not in self.answers:
            raise KeyError(f"{self.name}: لا إجابة ملصقة لهذا السؤال")
        return Answer(text=self.answers[prompt], model=self.model, from_cache=True)
