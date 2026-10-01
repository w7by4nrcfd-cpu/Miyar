"""قاعدة المراجعة الشرعية لحالات الاختبار (مشتركة بين official_v0 وextended_v1)، وموثقة في docs/REVIEWER_GUIDE.md.

- pending: لم تُراجع؛ reviewed_by وreviewed_at فارغان.
- approved: راجعها مراجِع مسمّى؛ reviewed_by وreviewed_at (YYYY-MM-DD) إلزاميان.
- rejected: رفضها مراجِع مسمّى؛ ومعها review_notes بسبب الرفض. لا تُستخدم في المقاييس حتى تُصحَّح وتُراجع من جديد.
"""

import re

REVIEW_FIELDS = ("review_status", "reviewed_by", "reviewed_at", "review_notes")
# الحقول التي إن تغيّرت بعد المراجعة سقطت المراجعة وعادت الحالة pending
REVIEWED_CONTENT = ("prompt", "level", "expected_behavior", "checks", "reference_hints", "injected_context", "critical")
STATUSES = ("pending", "approved", "rejected")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def review_errors(case: dict) -> list[str]:
    status = case.get("review_status")
    if status not in STATUSES:
        return [f"review_status غير معروف: {status!r}"]
    by, at, notes = case.get("reviewed_by"), case.get("reviewed_at"), case.get("review_notes")
    if status == "pending":
        return [] if not by and not at else ["حالة pending لا تحمل اسم مراجِع ولا تاريخ مراجعة"]
    errs = []
    if not (isinstance(by, str) and by.strip()):
        errs.append(f"{status} بلا اسم مراجِع (reviewed_by)")
    if not (isinstance(at, str) and _DATE.match(at)):
        errs.append(f"{status} بلا تاريخ مراجعة صالح (reviewed_at بصيغة YYYY-MM-DD)")
    if status == "rejected" and not (isinstance(notes, str) and notes.strip()):
        errs.append("rejected بلا سبب (review_notes)")
    return errs


def same_content(a: dict, b: dict) -> bool:
    """هل محتوى الحالة المراجَع نفسه في النسختين؟"""
    return all(a.get(k) == b.get(k) for k in REVIEWED_CONTENT)
