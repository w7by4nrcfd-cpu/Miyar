"""كاتب السجل الكامل: المساعد ← الاستخراج ← حكم الإسناد البرمجي ← حكم السلوك، ثم سجل بالصيغة التي يقرؤها ``publish``.

- الإجابات من ``runner.run_testset`` (المساعد المُختبَر). ثم لكل حالة أُجيبت: ``extract`` بنموذج مِعيار (دور judge)،
  و``judge_citations`` (برمجي: القرآن والملف اليدوي للأحاديث)، و``judge_behavior`` (الحَكَم مع الثقة والإحالة).
- كل حالة تحمل ``judgement`` بصيغة ``publish.judgement_to_dict``، أو ``judge_error`` إن تعذّر الحكم (فلا تُحتسب في الدرجة)؛
  ولا تُحذف حالة: N = عدد الحالات المطروحة.
- ``OFFICIAL_RUN`` إلى ``evaluation/official/<run_id>.json`` فقط، ويشترط ``MIYAR_RUN_ID`` جديداً؛ و``DEV_RUN`` إلى ``evaluation/dev/``.
  لا كتابة فوق سجل موجود. ويُسجَّل الـcommit ونموذج الحَكَم وعتبة الثقة واختيار الحالات.
- الوضع (cached/live) والسقف اليومي والمخزن من متغيرات البيئة (``miyar.llm``)؛ هذا الملف لا يتجاوزها.

التشغيل: ``python -m miyar.evaluate --assistant baseline --cases official_v0+critical [--label OFFICIAL_RUN]``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .extract import extract
from .judge import judge_behavior, judge_citations, min_confidence_from_env
from .llm import LLMClient
from .publish import judgement_to_dict
from .runner import (
    DEV_DIR, DEV_RUN, LABELS, OFFICIAL_DIR, OFFICIAL_RUN, RIYADH, ROOT, TESTSETS_DIR, Target, load_cases, run_testset,
)

# اختيار الحالات: الاسم يُسجَّل في السجل مع N الفعلي
SELECTIONS = {
    "official_v0": "أمثلة الحزمة العلمية الاثنا عشر",
    "official_v0+critical": "أمثلة الحزمة الاثنا عشر مع الحالات الحرجة من extended_v1",
    "all": "كل الحالات (official_v0 وextended_v1)",
}


def select_cases(selection: str, testsets_dir: Path = TESTSETS_DIR) -> list[dict]:
    official = load_cases([testsets_dir / "official_v0.json"])
    if selection == "official_v0":
        return official
    every = load_cases([testsets_dir / "official_v0.json", testsets_dir / "extended_v1.json"])
    if selection == "all":
        return every
    if selection == "official_v0+critical":
        ids = {c["id"] for c in official}
        return official + [c for c in every if c["id"] not in ids and c.get("critical") is True]
    raise ValueError(f"اختيار حالات غير معروف: {selection} (المتاح: {', '.join(SELECTIONS)})")


@dataclass
class JudgeSetup:
    client: LLMClient
    model: str
    min_confidence: float


def judge_case(case: dict, answer_text: str, answer_model: str, judge: JudgeSetup, manual: dict | None = None):
    """الاستخراج ثم حكم الإسناد ثم حكم السلوك لحالة واحدة. يرفع الخطأ للمستدعي."""
    ex = extract(answer_text, judge.client, judge.model)
    cites = judge_citations([c.as_citation() for c in ex.citations], manual=manual)
    return judge_behavior(case, answer_text, cites, client=judge.client, model=judge.model,
                          min_confidence=judge.min_confidence, assistant_model=answer_model, manual=manual)


def current_commit(root: Path = ROOT) -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "miyar", "testsets", "data"], cwd=root,
                               capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() + ("-dirty" if dirty.stdout.strip() else "")


def evaluate(cases: list[dict], target: Target, judge: JudgeSetup, run_label: str, *, selection: str,
             run_id: str | None = None, manual: dict | None = None, commit: str | None = None,
             now: Callable[[], datetime] = lambda: datetime.now(RIYADH)) -> dict:
    """يعيد السجل الكامل (dict) دون كتابة."""
    record = run_testset(cases, target, run_label, run_id=run_id, now=now)
    by_id = {c["id"]: c for c in cases}
    out = record.to_dict()
    judged = judge_errors = 0
    for res, row in zip(record.cases, out["cases"]):
        if res.answer is None:
            continue
        try:
            j = judge_case(by_id[res.case_id], res.answer.text, res.answer.model, judge, manual)
        except Exception as e:  # noqa: BLE001 — يُسجَّل في الحالة ولا تُحذف، ولا تُحتسب في الدرجة
            row["judge_error"] = f"{type(e).__name__}: {e}"[:500]
            judge_errors += 1
            continue
        row["judgement"] = judgement_to_dict(j)
        judged += 1
    out.update({
        "commit": commit,
        "case_selection": selection,
        "judge_model": judge.model,
        "min_confidence": judge.min_confidence,
        "n_judged": judged,
        "n_judge_errors": judge_errors,
    })
    return out


def save(record: dict, directory: Path) -> Path:
    """OFFICIAL_RUN في evaluation/official/ فقط، وDEV_RUN خارجها؛ بلا كتابة فوق سجل موجود."""
    directory = Path(directory)
    official_dir = directory.resolve() == OFFICIAL_DIR.resolve() or directory.name == "official"
    if record["run_label"] == OFFICIAL_RUN and not official_dir:
        raise ValueError("سجل OFFICIAL_RUN لا يُحفظ إلا في evaluation/official/")
    if record["run_label"] != OFFICIAL_RUN and official_dir:
        raise ValueError(f"سجل {record['run_label']} لا يُحفظ في evaluation/official/")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['run_id']}.json"
    if path.exists():
        raise FileExistsError(f"سجل التشغيل موجود: {path.name}")
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m miyar.evaluate")
    p.add_argument("--assistant", default="baseline", choices=["baseline", "rag"])
    p.add_argument("--cases", default="official_v0+critical", choices=list(SELECTIONS))
    p.add_argument("--label", default=DEV_RUN, choices=list(LABELS))
    args = p.parse_args(argv)
    from .assistants import baseline, rag  # استيراد متأخر
    from .llm import client_from_env

    target = {"baseline": baseline, "rag": rag}[args.assistant].build()
    jclient, jmodel = client_from_env(role="judge")
    judge = JudgeSetup(jclient, jmodel, min_confidence_from_env())
    cases = select_cases(args.cases)
    record = evaluate(cases, target, judge, args.label, selection=args.cases, commit=current_commit())
    path = save(record, OFFICIAL_DIR if args.label == OFFICIAL_RUN else DEV_DIR)
    shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    print(f"{record['run_label']} {record['run_id']}: N={record['n_cases']}، أخطاء الإجابة={record['n_errors']}، "
          f"محكوم={record['n_judged']}، أخطاء الحكم={record['n_judge_errors']} → {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
