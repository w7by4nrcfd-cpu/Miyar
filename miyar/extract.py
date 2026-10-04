"""استخراج الاستشهادات من إجابة المساعد (اليوم 1: الآيات فقط — نص + موضع؛ docs/BUILD_PLAN.md).

الاستخراج بنموذج لغوي (نموذج مِعيار، دور judge، لا نموذج المساعد)، ثم **تحقق برمجي حتمي** يمنع المستخرِج من التأليف:
1. النص المستخرج يجب أن يكون موجوداً حرفياً في الإجابة (بعد توحيد التشكيل والهمزات والأرقام والترقيم)، وإلا يُرفض.
   فالمستخرِج لا «يصحح» آية ولا يضيف آية لم ترد في الإجابة.
2. الموضع (السورة والآية) يُقبل فقط إن ذكره المساعد فعلاً في الإجابة: نص الموضع كما ورد موجود في الإجابة،
   ورقم الآية مذكور فيه، واسم السورة (إن ذُكر اسم) يطابق اسمها في بيانات Quranpedia. وإلا يُحذف الموضع (= «لم يذكر موضعاً»).
لا يحكم هذا الملف على صحة أي آية: ذلك عمل quran_match (المطابقة الحرفية) ثم judge.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .judge import Citation
from .llm import LLMClient, LLMRequest
from .normalize import normalize
from .quran_match import TOTAL_SURAS, QuranIndex

KIND_QURAN = "quran"

SYSTEM = (
    "أنت أداة استخراج لا تجيب ولا تصحح. مهمتك: استخراج كل نص قدّمته الإجابة على أنه آية من القرآن الكريم.\n"
    "- انسخ نص الآية كما ورد في الإجابة حرفياً، دون تصحيح ولا إكمال ولا تشكيل زائد.\n"
    "- cited: الموضع كما كتبه المساعد حرفياً (مثل «البقرة: 255» أو «(2:255)»)، أو null إن لم يذكر موضعاً.\n"
    "- sura وaya وaya_end: أرقام الموضع الذي ذكره المساعد، أو null. لا تستنتج موضعاً لم يُذكر.\n"
    "- لا تستخرج الأحاديث ولا أقوال العلماء ولا الشرح.\n"
    'أعد JSON فقط بالشكل: {"citations": [{"kind": "quran", "quote": "...", "cited": "..." أو null, '
    '"sura": عدد أو null, "aya": عدد أو null, "aya_end": عدد أو null}]}. وإن لم توجد آيات: {"citations": []}.'
)
EXTRACT_MAX_OUTPUT_TOKENS = 2048


class ExtractionError(ValueError):
    """إخراج المستخرِج ليس JSON صالحاً بالشكل المطلوب؛ فلا تُبنى عليه أحكام (الحالة تُحال: يحتاج تحقق)."""


@dataclass
class ExtractedCitation:
    kind: str
    quote: str
    cited: str | None = None  # الموضع كما كتبه المساعد
    sura: int | None = None
    aya: int | None = None
    aya_end: int | None = None
    notes: list[str] = field(default_factory=list)  # ما حُذف من الموضع ولماذا

    @property
    def has_location(self) -> bool:
        return self.sura is not None and self.aya is not None

    def as_citation(self) -> Citation:
        """الصيغة التي يستقبلها judge."""
        return Citation(kind=self.kind, quote=self.quote, cited=self.cited)


@dataclass
class Extraction:
    citations: list[ExtractedCitation]
    rejected: list[dict]  # ما ردّه التحقق البرمجي مع سببه (للتدقيق، لا للحكم)
    model: str = ""  # النموذج الذي استخرج فعلاً
    from_cache: bool = False


def build_request(answer_text: str, model: str, provider: str = "gemini") -> LLMRequest:
    prompt = f"<<<الإجابة\n{answer_text}\nنهاية الإجابة>>>"
    return LLMRequest(provider=provider, model=model, prompt=prompt, system=SYSTEM, temperature=0.0,
                      max_output_tokens=EXTRACT_MAX_OUTPUT_TOKENS, response_mime_type="application/json")


def parse_output(text: str) -> list[dict]:
    """يقرأ JSON المستخرِج (ويقبل إحاطته بسياج ```). يرفع ExtractionError عند أي شكل آخر."""
    t = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.S)
    if m:
        t = m.group(1)
    try:
        data = json.loads(t)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"إخراج المستخرِج ليس JSON: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("citations"), list):
        raise ExtractionError("الإخراج يجب أن يكون كائناً فيه citations قائمة")
    if not all(isinstance(c, dict) for c in data["citations"]):
        raise ExtractionError("كل عنصر في citations يجب أن يكون كائناً")
    return data["citations"]


def _int_or_none(v) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, str) and normalize(v).isdigit():
        return int(normalize(v))
    return None


def _strip_al(name: str) -> str:
    return name[2:] if name.startswith("ال") else name


def _location_notes(cited: str | None, sura: int | None, aya: int | None, aya_end: int | None,
                    answer_norm: str, index: QuranIndex) -> list[str]:
    """أسباب رفض الموضع (قائمة فارغة = الموضع مقبول)."""
    if sura is None and aya is None:
        return []
    if not cited or not normalize(cited) or normalize(cited) not in answer_norm:
        return ["cited_not_in_answer"]
    if sura is None or aya is None or not (1 <= sura <= TOTAL_SURAS) or aya < 1 or (aya_end is not None and aya_end < aya):
        return ["location_incomplete_or_invalid"]
    cited_norm = normalize(cited)
    numbers = set(re.findall(r"\d+", cited_norm))
    if str(aya) not in numbers:
        return ["aya_number_not_in_cited"]
    words = re.sub(r"[\d\s]+", " ", cited_norm).split()
    named = [w for w in words if w not in {"سوره", "سورة", "ايه", "اية", "الايه", "الاية", "رقم", "اي", "ايات"}]
    if named:
        name = normalize(index.sura_name(sura) or "")
        if not name or _strip_al(name) not in cited_norm:
            return ["sura_name_mismatch"]
    elif str(sura) not in numbers:
        return ["sura_number_not_in_cited"]
    return []


def validate(raw: list[dict], answer_text: str, index: QuranIndex) -> tuple[list[ExtractedCitation], list[dict]]:
    """التحقق البرمجي الحتمي على ما أعاده المستخرِج."""
    answer_norm = normalize(answer_text)
    kept, rejected = [], []
    for item in raw:
        kind = item.get("kind")
        quote = item.get("quote") if isinstance(item.get("quote"), str) else ""
        if kind != KIND_QURAN:
            rejected.append({"item": item, "reason": "kind_not_supported_yet"})  # الأحاديث: اليوم 2
            continue
        q = normalize(quote)
        if len(q.split()) < 2 or q not in answer_norm:
            rejected.append({"item": item, "reason": "quote_not_in_answer"})
            continue
        cited = item.get("cited") if isinstance(item.get("cited"), str) else None
        sura, aya, aya_end = (_int_or_none(item.get(k)) for k in ("sura", "aya", "aya_end"))
        notes = _location_notes(cited, sura, aya, aya_end, answer_norm, index)
        if notes:
            cited_ok = cited if cited and normalize(cited) and normalize(cited) in answer_norm else None
            kept.append(ExtractedCitation(KIND_QURAN, quote.strip(), cited_ok, None, None, None, notes))
        else:
            kept.append(ExtractedCitation(KIND_QURAN, quote.strip(), cited, sura, aya, aya_end))
    return kept, rejected


def extract(answer_text: str, client: LLMClient, model: str, index: QuranIndex | None = None) -> Extraction:
    """يستخرج الآيات المستشهد بها من إجابة المساعد. الإجابة الفارغة لا تستدعي أي نموذج."""
    if not answer_text or not answer_text.strip():
        return Extraction([], [], model="", from_cache=False)
    resp = client.complete(build_request(answer_text, model))
    kept, rejected = validate(parse_output(resp.text), answer_text, index or QuranIndex.load())
    return Extraction(kept, rejected, model=resp.model, from_cache=resp.from_cache)
