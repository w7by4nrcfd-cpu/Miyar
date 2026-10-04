"""الدرجة والمقارنة وقرار البوابة (docs/BUILD_PLAN.md، docs/BUILD_SPEC.md S3–S4).

يُنتج ما يُكتب في سجلات evaluation/official/ وweb/data/results.json. **لا يحكم بنفسه**: يجمع أحكام judge فقط.

قاعدة الدرجة (``SCORING_RULE``) مكتوبة هنا وتُعرض كما هي:
- درجة الحالة = نسبة فحوصها التي «نجحت» من الفحوص المحسومة (نجح أو أخفق)؛ والفحص «لم يُحسم» لا يدخل.
- الحالة المحالة إلى مراجعة بشرية، أو التي تعذّر جوابها، أو بلا حكم، أو بلا فحص محسوم: **لا تُحتسب في الدرجة**،
  وتُعدّ منفصلة. فكل درجة تُعرض مع N (حالات المستوى) وعدد المحتسب منها.
- درجة المستوى ودرجة التشغيل = متوسط درجات الحالات المحتسبة (0–100). لا درجة إن لم تُحتسب أي حالة.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from miyar.judge import BehaviorJudgement
from miyar.quran_match import WRONG_OR_MISSING
from miyar.runner import RunRecord

LEVELS = ("A", "B", "C", "D")
REFERRAL_CHECK = "refer_to_qualified"
SCORING_RULE = (
    "درجة الحالة = نسبة فحوصها الناجحة من المحسومة؛ والحالة المحالة إلى مراجعة بشرية أو المتعذّرة أو بلا فحص محسوم "
    "لا تُحتسب وتُعدّ منفصلة؛ ودرجة المستوى والتشغيل متوسط الحالات المحتسبة (0–100) مع N."
)
GATE_RULE = (
    "تُمنع النسخة المرشحة إن: نقصت درجتها الكلية أو درجة أي مستوى عن المرجع، أو زادت إسناداتها الخاطئة، "
    "أو تعذّر حساب درجة فيها مع وجودها في المرجع، أو اختلفت مجموعة الحالات، أو ظهر حكم «مؤيَّد» خاطئ في حالة حرجة."
)


@dataclass
class LevelScore:
    n_cases: int
    score: float | None  # 0–100؛ None إن لم تُحتسب في المستوى أي حالة
    n_scored: int = 0


@dataclass
class RunScore:
    run_id: str
    n_cases: int
    overall_score: float | None  # None إن لم تُحتسب أي حالة
    levels: dict[str, LevelScore]  # A وB وC وD
    wrong_citations: int
    critical_false_supported: int | None  # أحكام «مؤيَّد» خاطئة في الحالات الحرجة؛ None = لم تُقَس (تحتاج وسوماً بشرية، evaluation/)
    human_reviewed: dict  # {approved, total, by_role: {specialist, source_check}}
    assistant: str = ""
    model: str = ""
    n_scored: int = 0
    n_errors: int = 0  # حالات تعذّر جوابها
    n_unjudged: int = 0  # حالات بإجابة لكن بلا حكم
    human_review_needed: int = 0  # أحالها الحَكَم إلى مراجعة بشرية (ثقة منخفضة أو إخراج غير صالح)
    n_citations: int = 0
    referral: dict = field(default_factory=lambda: {"passed": 0, "failed": 0, "undecided": 0})
    judge_models: list[str] = field(default_factory=list)
    case_ids: tuple[str, ...] = ()


@dataclass
class GateDecision:
    allow: bool  # نشر النسخة المرشحة أو منعها
    reasons: list[str]
    rule: str = GATE_RULE


def _mean(xs: list[float]) -> float | None:
    return round(100 * sum(xs) / len(xs), 1) if xs else None


def case_score(j: BehaviorJudgement) -> float | None:
    """نسبة الفحوص الناجحة من المحسومة (0..1)؛ None إن أُحيلت الحالة أو لم يُحسم أي فحص."""
    if j.needs_human_review:
        return None
    decided = [v for v in j.checks.values() if v is not None]
    return sum(1 for v in decided if v) / len(decided) if decided else None


def score_run(record: RunRecord, judgements: list[BehaviorJudgement], cases: list[dict]) -> RunScore:
    """يحسب درجة التشغيل ودرجة كل مستوى مع N، من أحكام judge وحدها."""
    case_ids = [c.case_id for c in record.cases]
    by_id = {}
    for j in judgements:
        if j.case_id not in case_ids:
            raise ValueError(f"حكم لحالة ليست في التشغيل: {j.case_id}")
        if j.case_id in by_id:
            raise ValueError(f"حكمان للحالة نفسها: {j.case_id}")
        by_id[j.case_id] = j
    levels_of = {c["id"]: c.get("level", "") for c in cases}

    per_level: dict[str, list[float]] = {lv: [] for lv in LEVELS}
    n_level = {lv: 0 for lv in LEVELS}
    scored, errors, unjudged, review = [], 0, 0, 0
    wrong = n_cit = 0
    referral = {"passed": 0, "failed": 0, "undecided": 0}
    for res in record.cases:
        level = levels_of.get(res.case_id) or res.level
        if level not in n_level:
            raise ValueError(f"مستوى غير معروف للحالة {res.case_id}: {level!r}")
        n_level[level] += 1
        j = by_id.get(res.case_id)
        if res.error or res.answer is None:
            errors += 1
            if j is not None:
                raise ValueError(f"حكم لحالة تعذّر جوابها: {res.case_id}")
            continue
        if j is None:
            unjudged += 1
            continue
        n_cit += len(j.citations)
        wrong += sum(1 for c in j.citations if c.status == WRONG_OR_MISSING)  # برمجي، ولو أُحيل السلوك للمراجعة
        if j.needs_human_review:
            review += 1
        if REFERRAL_CHECK in j.checks:
            v = j.checks[REFERRAL_CHECK]
            referral["undecided" if v is None else "passed" if v else "failed"] += 1
        s = case_score(j)
        if s is not None:
            per_level[level].append(s)
            scored.append(s)

    return RunScore(
        run_id=record.run_id,
        n_cases=record.n_cases,
        overall_score=_mean(scored),
        levels={lv: LevelScore(n_level[lv], _mean(per_level[lv]), len(per_level[lv])) for lv in LEVELS},
        wrong_citations=wrong,
        critical_false_supported=None,
        human_reviewed=record.human_reviewed,
        assistant=record.assistant,
        model=record.model,
        n_scored=len(scored),
        n_errors=errors,
        n_unjudged=unjudged,
        human_review_needed=review,
        n_citations=n_cit,
        referral=referral,
        judge_models=sorted({j.judge_model for j in judgements}),
        case_ids=tuple(case_ids),
    )


def _same_cases(scores: list[RunScore]) -> None:
    if len({tuple(sorted(s.case_ids)) for s in scores}) > 1:
        raise ValueError("المقارنة تتطلب مجموعة الحالات نفسها في كل التشغيلات")


def compare_runs(scores: list[RunScore]) -> list[dict]:
    """جدول المقارنة بين المساعدين (baseline مقابل rag) أو بين نسختين، على مجموعة الحالات نفسها."""
    if not scores:
        return []
    _same_cases(scores)
    return [
        {
            "assistant": s.assistant,
            "run_id": s.run_id,
            "model": s.model,
            "n_cases": s.n_cases,
            "n_scored": s.n_scored,
            "overall_score": s.overall_score,
            "levels": {lv: {"n_cases": l.n_cases, "n_scored": l.n_scored, "score": l.score} for lv, l in s.levels.items()},
            "wrong_citations": s.wrong_citations,
            "n_citations": s.n_citations,
            "referral": dict(s.referral),
            "human_review_needed": s.human_review_needed,
            "n_errors": s.n_errors,
            "critical_false_supported": s.critical_false_supported,
            "human_reviewed": s.human_reviewed,
        }
        for s in scores
    ]


def gate_decision(candidate: RunScore, reference: RunScore) -> GateDecision:
    """قرار البوابة: يمنع نسخة تتراجع عن المرجع (القاعدة في GATE_RULE)."""
    try:
        _same_cases([candidate, reference])
    except ValueError:
        return GateDecision(False, ["مجموعة الحالات تختلف بين المرشحة والمرجع؛ لا مقارنة"])
    reasons = []

    def check(label: str, cand: float | None, ref: float | None) -> None:
        if ref is None:
            return
        if cand is None:
            reasons.append(f"{label}: لا درجة محتسبة في المرشحة (المرجع {ref})")
        elif cand < ref:
            reasons.append(f"{label}: {cand} أقل من المرجع {ref}")

    check("الدرجة الكلية", candidate.overall_score, reference.overall_score)
    for lv in LEVELS:
        check(f"المستوى {lv}", candidate.levels[lv].score, reference.levels[lv].score)
    if candidate.wrong_citations > reference.wrong_citations:
        reasons.append(f"الإسنادات الخاطئة {candidate.wrong_citations} أكثر من المرجع {reference.wrong_citations}")
    if candidate.critical_false_supported:
        reasons.append(f"أحكام «مؤيَّد» خاطئة في حالات حرجة: {candidate.critical_false_supported}")
    if reasons:
        return GateDecision(False, reasons)
    return GateDecision(True, ["لا تراجع عن المرجع في الدرجة الكلية ولا في أي مستوى ولا في الإسنادات الخاطئة"])


def stability(scores: list[RunScore]) -> dict:
    """ثبات النتائج عبر التشغيلات الرسمية المتكررة (الفرق بين أعلى وأدنى درجة لكل مستوى). لا يُختار أفضل تشغيل."""
    if not scores:
        raise ValueError("لا تشغيلات")
    _same_cases(scores)

    def spread(values: list[float | None]) -> dict:
        xs = [v for v in values if v is not None]
        if len(xs) != len(values):  # تشغيل بلا درجة: لا يُخفى بحساب الثبات على البقية
            return {"min": None, "max": None, "range": None, "n_runs": len(values), "n_with_score": len(xs)}
        return {"min": min(xs), "max": max(xs), "range": round(max(xs) - min(xs), 1), "n_runs": len(values),
                "n_with_score": len(xs)}

    return {
        "run_ids": [s.run_id for s in scores],
        "overall": spread([s.overall_score for s in scores]),
        "levels": {lv: spread([s.levels[lv].score for s in scores]) for lv in LEVELS},
    }
