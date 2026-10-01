"""قاعدة المراجعة لحالات الاختبار (مشتركة بين official_v0 وextended_v1)، وموثقة في docs/REVIEWER_GUIDE.md.

- pending: لم تُراجع؛ reviewed_by وreviewed_at وreviewer_role فارغة.
- approved: راجعها مراجِع مسمّى؛ reviewed_by وreviewed_at (YYYY-MM-DD) وreviewer_role إلزامية.
- rejected: رفضها مراجِع مسمّى (بالحقول نفسها)، ومعها review_notes بسبب الرفض. لا تُستخدم في المقاييس حتى تُصحَّح.

reviewer_role (نوع المراجعة):
- specialist: مراجعة شرعية متخصصة.
- source_check: تحقق من المصادر بواسطة المشارك، وهو غير متخصص شرعياً. **ليست مراجعة شرعية متخصصة**،
  ولا تُعرض على أنها كذلك في أي تقرير أو واجهة.
"""

import re

REVIEW_FIELDS = ("review_status", "reviewed_by", "reviewer_role", "reviewed_at", "review_notes")
# الحقول التي إن تغيّرت بعد المراجعة سقطت المراجعة وعادت الحالة pending
REVIEWED_CONTENT = ("prompt", "level", "expected_behavior", "checks", "reference_hints", "injected_context", "critical")
STATUSES = ("pending", "approved", "rejected")
ROLES = {
    "specialist": "مراجعة شرعية متخصصة",
    "source_check": "تحقق من المصادر بواسطة المشارك (غير متخصص شرعياً) — ليس مراجعة شرعية متخصصة",
}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def review_errors(case: dict) -> list[str]:
    status = case.get("review_status")
    if status not in STATUSES:
        return [f"review_status غير معروف: {status!r}"]
    by, at, role = case.get("reviewed_by"), case.get("reviewed_at"), case.get("reviewer_role")
    if status == "pending":
        ok = not by and not at and not role
        return [] if ok else ["حالة pending لا تحمل اسم مراجِع ولا نوع مراجعة ولا تاريخ"]
    errs = []
    if not (isinstance(by, str) and by.strip()):
        errs.append(f"{status} بلا اسم مراجِع (reviewed_by)")
    if role not in ROLES:
        errs.append(f"{status} بلا نوع مراجعة صالح (reviewer_role: specialist أو source_check)")
    if not (isinstance(at, str) and _DATE.match(at)):
        errs.append(f"{status} بلا تاريخ مراجعة صالح (reviewed_at بصيغة YYYY-MM-DD)")
    notes = case.get("review_notes")
    if status == "rejected" and not (isinstance(notes, str) and notes.strip()):
        errs.append("rejected بلا سبب (review_notes)")
    return errs


def review_summary(cases: list[dict]) -> dict:
    """عدد الحالات لكل حالة مراجعة ونوع: {"total", "pending", "approved": {role: n}, "rejected": {role: n}}."""
    out = {"total": len(cases), "pending": 0,
           "approved": {r: 0 for r in ROLES}, "rejected": {r: 0 for r in ROLES}}
    for c in cases:
        if c.get("review_status") in ("approved", "rejected") and c.get("reviewer_role") in ROLES:
            out[c["review_status"]][c["reviewer_role"]] += 1
        else:
            out["pending"] += 1
    return out


def same_content(a: dict, b: dict) -> bool:
    """هل محتوى الحالة المراجَع نفسه في النسختين؟"""
    return all(a.get(k) == b.get(k) for k in REVIEWED_CONTENT)
