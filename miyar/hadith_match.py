"""مطابقة الأحاديث مع الملف اليدوي المعتمد (data/hadith/manual_hadith.json) — برمجية حتمية، بلا نموذج لغوي.

المصدر الوحيد: الملف اليدوي (``miyar/hadith_manual.py``). لا مجموعة أحاديث خارجية، ولا بحث BM25 أو embeddings:
المدخلات قليلة ومُدخلة يدوياً، فالمطابقة حرفية بعد توحيد النص العربي (``normalize``) وبحدود الكلمات: مقطع يطابق
متتالية كلمات كاملة من نص المدخل (أو العكس)، ولا يُعدّ بتر حرف من أول كلمة أو آخرها مطابقة حرفية.

القاعدة المعتمدة: **لا حديث بلا مصدر ودرجة معتمدة في البيانات.**
- ``supported`` مؤيَّد: فقط إن طابق نص الاستشهاد مدخلاً ``found`` **مكتملاً** (نص، ومصدر، ورابط، ودرجة، وقائلها)،
  وذكر المساعد موضعاً (الكتاب ورقمه) والرقم نفسه ملاصق لاسم الكتاب في حقل ``source`` من المدخل.
- ``wrong_or_missing`` خاطئ أو غير موجود: فقط إن ذكر المساعد رقماً يتجاوز أعلى رقم في مدخل ``collection_range`` **مكتمل**
  للكتاب نفسه (رقم خارج الترقيم).
- ``needs_review`` يحتاج تحقق في كل ما عدا ذلك: لا مدخل مطابق، أو مدخل ناقص (pending)، أو موضع غير مذكور أو لا يطابق
  مصدر المدخل، أو عبارة سجّل الملف عدم العثور عليها. غياب المرجع ليس «خطأ».

لا يحكم هذا الملف على حديث بالصحة أو الضعف: الدرجة وقائلها تُنقل من المدخل كما هي.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .hadith_manual import entry_status, load_manual
from .normalize import normalize
from .quran_match import NEEDS_REVIEW, SUPPORTED, WRONG_OR_MISSING

# أسماء الكتب كما تظهر بعد التوحيد؛ «الصحيحين» تعني الكتابين معاً
COLLECTIONS = {
    "bukhari": ("البخاري",),
    "muslim": ("مسلم",),
    "ibn_majah": ("ابن ماجه",),
    "abu_dawud": ("ابو داود",),
    "tirmidhi": ("الترمذي",),
    "nasai": ("النسائي",),
}
BOTH_SAHIHS = ("الصحيحين", "الصحيحان")
MIN_MATCH_WORDS = 3  # أقل عدد كلمات يُقبل للمطابقة بين نص الاستشهاد ونص المدخل


@dataclass
class HadithCheck:
    status: str  # supported / needs_review / wrong_or_missing
    reason: str
    entry_id: str | None = None
    entry: dict = field(default_factory=dict)  # المدخل المطابَق كما في الملف اليدوي (للعرض: النص والمصدر والدرجة وقائلها والرابط)

    def to_dict(self) -> dict:
        keys = ("kind", "text", "query", "source", "grade", "grade_by", "link", "max_number")
        return {"status": self.status, "reason": self.reason, "entry_id": self.entry_id,
                "entry_status": entry_status(self.entry) if self.entry else None,
                **{k: self.entry[k] for k in keys if k in self.entry}}


def cited_collections(cited: str | None) -> set[str]:
    """الكتب التي ذكرها المساعد في الموضع."""
    n = f" {normalize(cited or '')} "  # مطابقة كلمات كاملة: «مسلم» لا تطابق «المسلمين»
    found = {key for key, names in COLLECTIONS.items() if any(f" {name} " in n for name in names)}
    if any(f" {b} " in n for b in BOTH_SAHIHS):
        found |= {"bukhari", "muslim"}
    return found


def cited_number(cited: str | None) -> int | None:
    """رقم الحديث الذي ذكره المساعد (إن كان رقماً واحداً)."""
    nums = re.findall(r"\d+", normalize(cited or ""))
    return int(nums[0]) if len(nums) == 1 else None


def source_numbers(source: str, collection: str) -> set[int]:
    """الأرقام الملاصقة لاسم الكتاب في حقل source من المدخل (مثل «سنن ابن ماجه 248» ← 248)."""
    n = normalize(source or "")
    out = set()
    for name in COLLECTIONS[collection]:
        out |= {int(m) for m in re.findall(r"(?<!\S)" + re.escape(name) + r"\s+(?:رقم\s+)?(\d+)", n)}
    return out


def _entry_phrase(e: dict) -> str:
    return normalize(e.get("text") or e.get("query") or "")


def _word_contains(whole: str, part: str) -> bool:
    """هل ``part`` متتالية كلمات متصلة داخل ``whole`` (بحدود الكلمات لا الأحرف)؟ كلاهما موحَّد ومفصول بمسافات مفردة.

    الاحتواء على مستوى الأحرف كان يعدّ حذف الحرف الأول أو الأخير من الكلمة الطرفية مطابقة حرفية
    («طلبوا العلم ولو بالصين» داخل «اطلبوا العلم ولو بالصين»)؛ والمقطع المبتور كلمةً لا يُعدّ حرفياً.
    """
    return f" {part} " in f" {whole} "


def find_entries(quote: str, doc: dict) -> list[dict]:
    """مدخلات found/not_found التي يحوي نصُّها نصَّ الاستشهاد أو العكس (بعد التوحيد، بحدود الكلمات، بحد أدنى من الكلمات)."""
    q = normalize(quote or "")
    if len(q.split()) < MIN_MATCH_WORDS:
        return []
    out = []
    for e in doc.get("entries", []):
        if e.get("kind") not in ("found", "not_found"):
            continue
        p = _entry_phrase(e)
        if len(p.split()) >= MIN_MATCH_WORDS and (_word_contains(q, p) or _word_contains(p, q)):
            out.append(e)
    return out


def _range_check(cited: str | None, doc: dict) -> HadithCheck | None:
    number, cols = cited_number(cited), cited_collections(cited)
    if number is None or not cols:
        return None
    for e in doc.get("entries", []):
        if e.get("kind") != "collection_range" or not (cited_collections(e.get("source")) & cols):
            continue
        if not isinstance(e.get("max_number"), int) or number <= e["max_number"]:
            continue
        if entry_status(e) != "complete":
            return HadithCheck(NEEDS_REVIEW, "manual_entry_pending", e["id"], e)
        return HadithCheck(WRONG_OR_MISSING, "number_out_of_range", e["id"], e)
    return None


def verify(quote: str, cited: str | None = None, doc: dict | None = None) -> HadithCheck:
    """يحكم على استشهاد حديثي واحد بالمقارنة مع الملف اليدوي وحده."""
    doc = load_manual() if doc is None else doc
    ranged = _range_check(cited, doc)
    if ranged is not None:
        return ranged
    entries = find_entries(quote, doc)
    if not entries:
        return HadithCheck(NEEDS_REVIEW, "no_manual_entry")
    complete = [e for e in entries if entry_status(e) == "complete"]
    if not complete:
        return HadithCheck(NEEDS_REVIEW, "manual_entry_pending", entries[0]["id"], entries[0])
    e = complete[0]
    if e["kind"] == "not_found":
        return HadithCheck(NEEDS_REVIEW, "not_found_in_manual_search", e["id"], e)
    cols, number = cited_collections(cited), cited_number(cited)
    if not cols:
        return HadithCheck(NEEDS_REVIEW, "location_not_stated", e["id"], e)
    if number is None:
        return HadithCheck(NEEDS_REVIEW, "number_not_stated", e["id"], e)
    if all(number in source_numbers(e["source"], c) for c in cols):
        return HadithCheck(SUPPORTED, "matched_manual_entry", e["id"], e)
    # الموضع المذكور لا يظهر في مصدر المدخل: لا دليل في البيانات على النسبة، ولا على نفيها
    return HadithCheck(NEEDS_REVIEW, "cited_location_not_in_entry_source", e["id"], e)


def pending_entries_for_case(case_id: str, doc: dict | None = None) -> list[str]:
    """معرّفات المدخلات الناقصة المرتبطة بالحالة: حالتها تُحكم «يحتاج تحقق» دون حكم آلي."""
    doc = load_manual() if doc is None else doc
    return [e["id"] for e in doc.get("entries", [])
            if case_id in (e.get("case_ids") or []) and entry_status(e) != "complete"]
