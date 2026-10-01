"""الملف اليدوي المعتمد للأحاديث (data/hadith/manual_hadith.json) — قراءة وتحقق فقط.

يُدخله صاحب المشروع يدوياً من الدرر السنية أو المكتبة الشاملة (مصدرا الحزمة العلمية). لا جلب آلي.
المدخل الناقص حالته pending: الحالات المرتبطة به تُحكم «يحتاج تحقق» ولا يصدر فيها حكم آلي.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
MANUAL_FILE = ROOT / "data" / "hadith" / "manual_hadith.json"
ALLOWED_HOSTS = ("dorar.net", "shamela.ws")
KINDS = {
    "found": ("text", "source", "link", "grade", "grade_by"),
    "not_found": ("query", "searched_in", "link"),
    "collection_range": ("source", "max_number", "link"),
}
COMMON = ("entered_by", "entered_at")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_manual(path: Path = MANUAL_FILE) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _filled(v) -> bool:
    return v not in (None, "") and not (isinstance(v, str) and not v.strip())


def entry_status(e: dict) -> str:
    """complete إن امتلأت كل الحقول المطلوبة لنوعه، وإلا pending."""
    required = KINDS.get(e.get("kind"), ()) + COMMON
    return "complete" if all(_filled(e.get(k)) for k in required) else "pending"


def link_allowed(url: str) -> bool:
    try:
        u = urlparse(url)
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return u.scheme in ("http", "https") and any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


def entry_errors(e: dict) -> list[str]:
    """أخطاء البنية دائماً، وأخطاء القيم لما امتلأ منها (ولو كان المدخل pending)."""
    errs = []
    if not e.get("id"):
        errs.append("مدخل بلا id")
    if e.get("kind") not in KINDS:
        errs.append(f"{e.get('id')}: نوع غير معروف {e.get('kind')!r}")
        return errs
    if not e.get("case_ids"):
        errs.append(f"{e['id']}: بلا case_ids")
    if _filled(e.get("link")) and not link_allowed(e["link"]):
        errs.append(f"{e['id']}: الرابط يجب أن يكون من dorar.net أو shamela.ws")
    if _filled(e.get("entered_at")) and not _DATE.match(str(e["entered_at"])):
        errs.append(f"{e['id']}: entered_at بصيغة YYYY-MM-DD")
    if e["kind"] == "found" and _filled(e.get("grade")) and not _filled(e.get("grade_by")):
        errs.append(f"{e['id']}: الدرجة بلا قائلها (grade_by)")
    if e["kind"] == "collection_range" and _filled(e.get("max_number")):
        if not isinstance(e["max_number"], int) or e["max_number"] < 1:
            errs.append(f"{e['id']}: max_number عدد صحيح موجب")
    return errs


def manual_errors(doc: dict) -> list[str]:
    errs, seen = [], set()
    for e in doc.get("entries", []):
        errs += entry_errors(e)
        if e.get("id") in seen:
            errs.append(f"id مكرر: {e.get('id')}")
        seen.add(e.get("id"))
    return errs


def entries_by_id(doc: dict | None = None) -> dict[str, dict]:
    doc = load_manual() if doc is None else doc
    return {e["id"]: e for e in doc["entries"]}
