"""تشغيل مجموعة الاختبار على مساعد وحفظ الإجابات في سجل تشغيل (اليوم 1، docs/BUILD_PLAN.md).

- ``load_cases``: يقرأ الحالات من ملفات testsets/ بترتيبها، ويُلحق بكل حالة اسم مجموعتها.
- ``run_testset``: يطرح كل حالة على المساعد (``Target``) ويجمع الإجابات. الحالة التي يتعذّر جوابها
  (مثل غياب إجابة مخزنة في وضع cached، أو بلوغ السقف اليومي) تُسجَّل بخطئها ولا تُحذف؛ فـ N = عدد الحالات المطروحة.
- ``save_run``: DEV_RUN إلى evaluation/dev/، وOFFICIAL_RUN إلى evaluation/official/<run_id>.json، بلا كتابة فوق سجل موجود.

لا يحكم هذا الملف على أي إجابة (ذلك عمل judge)، ولا يستورده.
التشغيل من سطر الأوامر: ``python -m miyar.runner --assistant baseline --testset official_v0`` (انظر ``main``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol

from .review import ROLES, review_summary

ROOT = Path(__file__).resolve().parent.parent
TESTSETS_DIR = ROOT / "testsets"
DEV_DIR = ROOT / "evaluation" / "dev"
OFFICIAL_DIR = ROOT / "evaluation" / "official"
DEV_RUN = "DEV_RUN"
OFFICIAL_RUN = "OFFICIAL_RUN"
LABELS = (DEV_RUN, OFFICIAL_RUN)
RIYADH = timezone(timedelta(hours=3))
_RUN_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class Target(Protocol):
    """المساعد المُختبَر (miyar/targets.py وmiyar/assistants/)."""

    name: str  # مثل baseline أو rag

    def answer(self, prompt: str, context: str | None = None) -> "Answer": ...


@dataclass
class Answer:
    text: str
    model: str  # النموذج الذي أجاب فعلاً
    from_cache: bool = False


@dataclass
class CaseResult:
    case_id: str
    testset: str
    prompt: str
    answer: Answer | None  # None إن تعذّر الجواب، والسبب في error
    level: str = ""
    error: str | None = None


@dataclass
class RunRecord:
    run_id: str
    run_label: str  # DEV_RUN أو OFFICIAL_RUN
    executed_at: str  # ISO 8601 بمنطقة زمنية
    assistant: str
    model: str
    testsets: list[str]
    cases: list[CaseResult] = field(default_factory=list)  # N = len(cases)
    human_reviewed: dict = field(default_factory=dict)

    @property
    def n_cases(self) -> int:
        return len(self.cases)

    def to_dict(self) -> dict:
        d = asdict(self)
        cases = d.pop("cases")
        d["n_cases"] = self.n_cases
        d["n_errors"] = sum(1 for c in self.cases if c.error)
        d["cases"] = [{"id": c.pop("case_id"), **c} for c in cases]
        return d


def load_cases(testset_paths: list[Path]) -> list[dict]:
    """يقرأ حالات الاختبار من ملفات testsets/ بترتيبها، ويُلحق بكل حالة ``testset`` (اسم المجموعة). المعرّفات فريدة."""
    cases, seen = [], set()
    for path in testset_paths:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        name = doc.get("name") or Path(path).stem
        for c in doc["cases"]:
            if c["id"] in seen:
                raise ValueError(f"معرّف حالة مكرر: {c['id']}")
            seen.add(c["id"])
            cases.append({**c, "testset": name})
    return cases


def _target_run_id(target: Target) -> str | None:
    client = getattr(target, "client", None)
    return getattr(client, "run_id", None)


def run_testset(
    cases: list[dict],
    target: Target,
    run_label: str,
    *,
    run_id: str | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(RIYADH),
) -> RunRecord:
    """يطرح كل حالة على المساعد ويجمع الإجابات في سجل تشغيل.

    ``run_id``: معرّف التشغيل؛ إن لم يُعطَ أُخذ من عميل المساعد (``MIYAR_RUN_ID``). وفي OFFICIAL_RUN هو إلزامي
    ويجب أن يطابق معرّف عميل المساعد، حتى يستدعي كل تشغيل رسمي النماذج من جديد (docs/BUILD_PLAN.md).
    """
    if run_label not in LABELS:
        raise ValueError(f"وسم تشغيل غير معروف: {run_label}")
    if not cases:
        raise ValueError("لا حالات للتشغيل")
    client_run_id = _target_run_id(target)
    if run_id is not None and client_run_id is not None and run_id != client_run_id:
        raise ValueError(f"run_id ({run_id}) لا يطابق معرّف عميل المساعد ({client_run_id})")
    started = now()
    run_id = run_id or client_run_id
    if run_label == OFFICIAL_RUN and (not run_id or (hasattr(target, "client") and client_run_id != run_id)):
        raise ValueError("OFFICIAL_RUN يحتاج run_id جديداً مضبوطاً في عميل المساعد (MIYAR_RUN_ID)")
    run_id = run_id or f"dev-{target.name}-{started.strftime('%Y%m%dT%H%M%S')}"
    if not _RUN_ID.match(run_id):
        raise ValueError(f"run_id غير صالح: {run_id!r}")

    results = []
    for c in cases:
        try:
            ans = target.answer(c["prompt"], c.get("injected_context"))
            results.append(CaseResult(c["id"], c.get("testset", ""), c["prompt"], ans, c.get("level", "")))
        except Exception as e:  # noqa: BLE001 — يُسجَّل الخطأ في الحالة ولا تُحذف
            results.append(CaseResult(c["id"], c.get("testset", ""), c["prompt"], None, c.get("level", ""),
                                      error=f"{type(e).__name__}: {e}"))

    models = sorted({r.answer.model for r in results if r.answer})
    s = review_summary(cases)
    by_role = {r: s["approved"][r] for r in ROLES}
    return RunRecord(
        run_id=run_id,
        run_label=run_label,
        executed_at=started.isoformat(timespec="seconds"),
        assistant=target.name,
        model=", ".join(models) or getattr(target, "model", "") or "unknown",
        testsets=list(dict.fromkeys(c.get("testset", "") for c in cases)),
        cases=results,
        human_reviewed={"approved": sum(by_role.values()), "total": len(cases), "by_role": by_role},
    )


def save_run(record: RunRecord, directory: Path) -> Path:
    """يحفظ السجل: DEV_RUN في مجلد تطوير، وOFFICIAL_RUN في evaluation/official/<run_id>.json. لا يكتب فوق سجل موجود."""
    directory = Path(directory)
    official_dir = directory.name == "official"
    if record.run_label == OFFICIAL_RUN and not official_dir:
        raise ValueError("سجل OFFICIAL_RUN لا يُحفظ إلا في evaluation/official/")
    if record.run_label == DEV_RUN and official_dir:
        raise ValueError("سجل DEV_RUN لا يُحفظ في evaluation/official/")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record.run_id}.json"
    if path.exists():
        raise FileExistsError(f"سجل التشغيل موجود: {path.name}")
    path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    """تشغيل من سطر الأوامر. الوضع والنموذج والسقف و``MIYAR_RUN_ID`` من متغيرات البيئة (miyar.llm).

    الافتراضي DEV_RUN إلى evaluation/dev/. التشغيل الرسمي يحتاج ``--label OFFICIAL_RUN`` و``MIYAR_RUN_ID`` جديداً.
    """
    p = argparse.ArgumentParser(prog="python -m miyar.runner")
    p.add_argument("--assistant", default="baseline", choices=["baseline"])
    p.add_argument("--testset", action="append", default=None, help="official_v0 أو extended_v1 (يتكرر)")
    p.add_argument("--label", default=DEV_RUN, choices=list(LABELS))
    args = p.parse_args(argv)
    from .assistants import baseline  # استيراد متأخر: لا حاجة لطبقة النموذج في load_cases/save_run

    target = baseline.build()
    names = args.testset or ["official_v0"]
    cases = load_cases([TESTSETS_DIR / f"{n}.json" for n in names])
    record = run_testset(cases, target, args.label)
    path = save_run(record, OFFICIAL_DIR if args.label == OFFICIAL_RUN else DEV_DIR)
    errors = sum(1 for c in record.cases if c.error)
    shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    print(f"{record.run_label} {record.run_id}: N={record.n_cases}، أخطاء={errors} → {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
