"""ورقة المراجعة الشرعية لحالات الاختبار (انظر docs/REVIEWER_GUIDE.md).

    python scripts/review_sheet.py export             # يكتب docs/review_sheet.csv لإرساله إلى المراجع
    python scripts/review_sheet.py apply <ملف.csv>    # يسجّل قرارات المراجع في ملفات testsets/
    python scripts/review_sheet.py status             # عدد الحالات المراجَعة لكل نوع مراجعة

الورقة بترميز UTF-8 مع BOM، أول أعمدتها «الأولوية» ومرتبة بها:
  1 = الحديث الموضوع، والمنسوب إلى الصحيحين وهو غير موجود فيهما (risk_type: hadith_fabricated / hadith_absent)
  2 = الخلاف الفقهي (category: fiqh_disagreement) وحالات المستوى D
  3 = باقي الحالات

قواعد التسجيل (miyar/review.py):
- decision: approved أو rejected، أو فارغ (تبقى الحالة pending).
- approved/rejected يتطلبان reviewer_name وreviewer_role (specialist أو source_check) وreview_date (YYYY-MM-DD)؛
  وrejected يتطلب notes بسبب الرفض. source_check تحقق من المصادر بواسطة المشارك وليس مراجعة شرعية متخصصة.
- يُرفض تسجيل قرار على حالة تغيّر نصها منذ تصدير الورقة (المراجع راجع نصاً آخر).
- لا يُكتب أي شيء إن وُجد خطأ واحد في الورقة.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from miyar.review import ROLES, review_errors, review_summary  # noqa: E402

TESTSETS = {"official_v0": ROOT / "testsets/official_v0.json", "extended_v1": ROOT / "testsets/extended_v1.json"}
SHEET = ROOT / "docs" / "review_sheet.csv"
PRIORITY = "الأولوية"
COLUMNS = [PRIORITY, "id", "testset", "level", "critical", "risk_type", "prompt", "injected_context",
           "expected_behavior", "decision", "reviewer_name", "reviewer_role", "review_date", "notes"]


def priority(case: dict) -> int:
    if case.get("risk_type") in ("hadith_fabricated", "hadith_absent"):
        return 1
    if case.get("category") == "fiqh_disagreement" or case["level"] == "D":
        return 2
    return 3


def _load() -> dict[str, dict]:
    return {name: json.loads(p.read_text(encoding="utf-8")) for name, p in TESTSETS.items()}


def export(path: Path = SHEET) -> int:
    rows = []
    for name, doc in _load().items():
        for c in doc["cases"]:
            rows.append({
                PRIORITY: priority(c),
                "id": c["id"], "testset": name, "level": c["level"], "critical": "نعم" if c["critical"] else "لا",
                "risk_type": c.get("risk_type", c["category"]), "prompt": c["prompt"],
                "injected_context": c.get("injected_context", ""), "expected_behavior": c["expected_behavior"],
                "decision": "" if c["review_status"] == "pending" else c["review_status"],
                "reviewer_name": c.get("reviewed_by") or "", "reviewer_role": c.get("reviewer_role") or "",
                "review_date": c.get("reviewed_at") or "",
                "notes": c.get("review_notes") or "",
            })
    rows.sort(key=lambda r: r[PRIORITY])  # فرز مستقر: يحفظ ترتيب الحالات داخل كل أولوية
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:  # BOM: يفتحه Excel بالعربية صحيحاً
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def apply(sheet: Path) -> tuple[int, list[str]]:
    """يعيد (عدد القرارات المسجّلة، الأخطاء). لا يكتب شيئاً إن وُجد خطأ."""
    docs = _load()
    index = {(name, c["id"]): c for name, doc in docs.items() for c in doc["cases"]}
    errors, updates = [], []
    with sheet.open(encoding="utf-8-sig", newline="") as f:
        for n, row in enumerate(csv.DictReader(f), start=2):
            decision = (row.get("decision") or "").strip().lower()
            if not decision:
                continue
            key = ((row.get("testset") or "").strip(), (row.get("id") or "").strip())
            case = index.get(key)
            if case is None:
                errors.append(f"سطر {n}: حالة غير معروفة {key}")
                continue
            if (row.get("prompt") or "").strip() != case["prompt"].strip():
                errors.append(f"سطر {n} ({key[1]}): نص الحالة تغيّر منذ تصدير الورقة؛ صدّر ورقة جديدة")
                continue
            fields = {
                "review_status": decision,
                "reviewed_by": (row.get("reviewer_name") or "").strip() or None,
                "reviewer_role": (row.get("reviewer_role") or "").strip().lower() or None,
                "reviewed_at": (row.get("review_date") or "").strip() or None,
                "review_notes": (row.get("notes") or "").strip() or None,
            }
            errs = review_errors({**case, **fields}) if decision != "pending" else ["القرار يجب أن يكون approved أو rejected"]
            if case.get("reviewer_role") == "specialist" and fields["reviewer_role"] == "source_check":
                errs.append("لا يحلّ تحقق المصادر (source_check) محل مراجعة شرعية متخصصة مسجّلة")
            if errs:
                errors.append(f"سطر {n} ({key[1]}): " + "؛ ".join(errs))
                continue
            updates.append((case, fields))
    if errors:
        return 0, errors
    for case, fields in updates:
        case.update(fields)
    for name, doc in docs.items():
        TESTSETS[name].write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(updates), []


def status() -> dict:
    cases = [c for doc in _load().values() for c in doc["cases"]]
    return review_summary(cases)


def status_lines(s: dict) -> list[str]:
    lines = [f"حالات الاختبار: {s['total']}، لم تُراجَع: {s['pending']}"]
    for role, label in ROLES.items():
        lines.append(f"- {role} ({label}): مقبولة {s['approved'][role]}، مرفوضة {s['rejected'][role]} من {s['total']}")
    return lines


def main(argv: list[str]) -> int:
    if argv[:1] == ["status"]:
        print("\n".join(status_lines(status())))
        return 0
    if argv[:1] == ["export"]:
        print(f"{SHEET.relative_to(ROOT)}: {export()} حالة")
        return 0
    if len(argv) == 2 and argv[0] == "apply":
        count, errors = apply(Path(argv[1]))
        for e in errors:
            print(e)
        if not errors:
            # الصفحات تعرض عدد المراجعات لكل نوع، فتُعاد كتابتها مع كل تسجيل
            sys.path.insert(0, str(ROOT / "scripts"))
            import build_web_pages
            build_web_pages.build()
            export()
            print("\n".join(status_lines(status())))
        print(f"سُجّل {count} قراراً" if not errors else "لم يُسجَّل شيء بسبب الأخطاء أعلاه")
        return 1 if errors else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
