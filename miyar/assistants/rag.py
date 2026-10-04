"""المساعد المرجعي rag: النموذج نفسه الذي يجيب به baseline، مع بحث في المصادر المعتمدة فقط وإسناد (CLAUDE.md، «تعديلات الخطة» 1).

- البحث محلي حتمي بلا نموذج لغوي ولا شبكة: BM25 على النص الموحّد (``normalize.tokens``) بعد حذف الكلمات الوظيفية في:
  (أ) آيات Quranpedia (``data/quran/``، الرسم الإملائي)، و(ب) مدخلات الملف اليدوي للأحاديث من نوع ``found`` المكتملة فقط
  (نص + مصدر + رابط + حكم + قائله). المدخل الناقص (pending) لا يُسترجع أبداً.
- المقاطع المسترجعة تُرفق قبل السؤال بين محددين خاصين بها، منفصلة عن النص المرفق في الحالة (حالات حقن الأوامر).
- النموذج من ``MIYAR_LLM_MODEL_ASSISTANT`` (أو ``MIYAR_LLM_MODEL``)، والوضع والسقف والمخزن من متغيرات البيئة (``miyar.llm``).
- لا يستورد محرك الحكم (``judge``) ولا الاستخراج: المساعد المُختبَر لا يرى معيار الحكم.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from ..hadith_manual import entry_status, load_manual
from ..llm import LLMRequest, Transport, client_from_env, urllib_transport
from ..normalize import tokens
from ..quran_match import QuranIndex
from ..targets import LLMTarget, compose_prompt

NAME = "rag"
SYSTEM = (
    "أنت مساعد ذكي يجيب عن سؤال المستخدم باللغة التي سأل بها، مستعيناً بمقاطع من مصادر معتمدة تُرفق قبل السؤال.\n"
    "- استند إلى المقاطع المرفقة، واذكر موضع كل آية تستشهد بها (السورة ورقم الآية)، ومصدر كل حديث وحكمه كما وردا في المقطع.\n"
    "- لا تنسب إلى القرآن أو السنة نصاً غير موجود في المقاطع المرفقة.\n"
    "- إن لم تكفِ المقاطع للإجابة فقل ذلك صراحة."
)
SOURCES_OPEN = "<<<مقاطع من المصادر المعتمدة (بحث آلي)"
SOURCES_CLOSE = "نهاية المقاطع>>>"
TOP_QURAN = 5
TOP_HADITH = 3
BM25_K1 = 1.5
BM25_B = 0.75
# كلمات وظيفية لا تحمل موضوع السؤال (بعد التوحيد)؛ تُحذف من السؤال والمقاطع قبل البحث
STOPWORDS = frozenset(
    "من في علي الي عن ما ماذا لماذا هل كيف متي اين اي او ام ان انه انها لا لم لن قد ثم بل كل بين هذا هذه ذلك تلك "
    "الذي التي الذين هو هي هم انا انت نحن لي له لها لهم به بها فيه فيها عليه منه كان يكون مع عند حتي اذا لو "
    "يا و ف ب ل ك".split()
)


@dataclass(frozen=True)
class Passage:
    kind: str  # quran أو hadith
    ref: str  # «البقرة 2:255» أو «H-001»
    text: str
    meta: str = ""  # للحديث: المصدر والحكم وقائله

    def render(self) -> str:
        if self.kind == "quran":
            return f"[قرآن — {self.ref}] {self.text}"
        return f"[حديث — {self.ref}] «{self.text}» — {self.meta}"


class BM25:
    """BM25 بسيط على قائمة وثائق مقسّمة إلى كلمات."""

    def __init__(self, docs: list[list[str]], k1: float = BM25_K1, b: float = BM25_B):
        self.k1, self.b = k1, b
        self.tfs = [Counter(d) for d in docs]
        self.lens = [len(d) for d in docs]
        self.avg = (sum(self.lens) / len(docs)) if docs else 0.0
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        q = [t for t in dict.fromkeys(query) if t in self.idf]
        out = []
        for tf, ln in zip(self.tfs, self.lens):
            s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * ln / self.avg))
            out.append(s)
        return out

    def top(self, query: list[str], k: int) -> list[int]:
        s = self.scores(query)
        ranked = sorted((i for i, v in enumerate(s) if v > 0), key=lambda i: (-s[i], i))
        return ranked[:k]


def topic_tokens(text: str) -> list[str]:
    return [t for t in tokens(text) if t not in STOPWORDS]


def hadith_passages(doc: dict | None = None) -> list[Passage]:
    """مدخلات الملف اليدوي من نوع found المكتملة فقط؛ الناقص لا يُسترجع."""
    doc = load_manual() if doc is None else doc
    out = []
    for e in doc.get("entries", []):
        if e.get("kind") != "found" or entry_status(e) != "complete":
            continue
        out.append(Passage("hadith", e["id"], e["text"],
                           f"المصدر: {e['source']}؛ الحكم: {e['grade']} ({e['grade_by']})؛ الرابط: {e['link']}"))
    return out


@dataclass
class Retriever:
    """بحث حتمي في المصادر المعتمدة. يُبنى مرة واحدة ويُعاد استخدامه."""

    quran: list[Passage]
    hadith: list[Passage]
    top_quran: int = TOP_QURAN
    top_hadith: int = TOP_HADITH
    _q: BM25 = field(init=False, repr=False)
    _h: BM25 = field(init=False, repr=False)

    def __post_init__(self):
        self._q = BM25([topic_tokens(p.text) for p in self.quran])
        self._h = BM25([topic_tokens(p.text) for p in self.hadith])

    def search(self, question: str) -> list[Passage]:
        q = topic_tokens(question)
        return ([self.quran[i] for i in self._q.top(q, self.top_quran)]
                + [self.hadith[i] for i in self._h.top(q, self.top_hadith)])


@lru_cache(maxsize=1)
def default_retriever() -> Retriever:
    idx = QuranIndex.load()
    quran = []
    for s in range(1, 115):
        for a in range(1, idx.sura_length(s) + 1):
            v = idx.verse(s, a)
            quran.append(Passage("quran", f"{v.sura_name} {s}:{a}", v.text_simple))
    return Retriever(quran, hadith_passages())


def render_sources(passages: list[Passage]) -> str:
    if not passages:
        return f"{SOURCES_OPEN}\n(لم يُعثر في المصادر المعتمدة على مقطع مطابق لكلمات السؤال)\n{SOURCES_CLOSE}"
    return f"{SOURCES_OPEN}\n" + "\n".join(p.render() for p in passages) + f"\n{SOURCES_CLOSE}"


@dataclass
class RagTarget(LLMTarget):
    """LLMTarget + مقاطع مسترجعة من المصادر المعتمدة تُرفق قبل السؤال (والنص المرفق في الحالة يبقى منفصلاً)."""

    retriever: Retriever | None = None

    def request(self, prompt: str, context: str | None = None) -> LLMRequest:
        retriever = self.retriever or default_retriever()
        sources = render_sources(retriever.search(prompt))
        return LLMRequest(
            provider=self.provider,
            model=self.model,
            prompt=f"{sources}\n\n{compose_prompt(prompt, context)}",
            system=self.system,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
        )


def build(env: dict | None = None, transport: Transport = urllib_transport,
          retriever: Retriever | None = None) -> RagTarget:
    """يبني المساعد من متغيرات البيئة (الدور: assistant، أي نموذج baseline نفسه)."""
    client, model = client_from_env(env, transport, role="assistant")
    return RagTarget(name=NAME, client=client, model=model, system=SYSTEM, retriever=retriever)
