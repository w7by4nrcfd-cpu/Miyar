"""الدرجة والمقارنة وقرار البوابة — **هيكل فقط (2026-10-01)، بلا منطق.**

يُنتج ما يُكتب في سجلات evaluation/official/ وweb/data/results.json (المخططان موثّقان هناك).
كل دالة ترفع NotImplementedError، ويحرس ذلك tests/test_skeletons.py حتى يُبنى المنطق (اليوم 2).
"""

from __future__ import annotations

from dataclasses import dataclass

from miyar.judge import BehaviorJudgement
from miyar.runner import RunRecord


@dataclass
class LevelScore:
    n_cases: int
    score: float | None  # 0–100؛ None إن لم تكن في المستوى حالات


@dataclass
class RunScore:
    run_id: str
    n_cases: int
    overall_score: float
    levels: dict[str, LevelScore]  # A وB وC وD
    wrong_citations: int
    critical_false_supported: int  # أحكام «مؤيَّد» خاطئة في الحالات الحرجة (تُعرض كما هي، مثل 0 من N)
    human_reviewed: dict  # {approved, total, by_role: {specialist, source_check}}


@dataclass
class GateDecision:
    allow: bool  # نشر النسخة المرشحة أو منعها
    reasons: list[str]


def score_run(record: RunRecord, judgements: list[BehaviorJudgement], cases: list[dict]) -> RunScore:
    """يحسب درجة التشغيل ودرجة كل مستوى."""
    raise NotImplementedError("يُبنى يوم 2 (5 أكتوبر)")


def compare_runs(scores: list[RunScore]) -> list[dict]:
    """جدول المقارنة بين المساعدين (baseline مقابل rag) أو بين نسختين."""
    raise NotImplementedError("يُبنى يوم 2 (5 أكتوبر)")


def gate_decision(candidate: RunScore, reference: RunScore) -> GateDecision:
    """قرار البوابة: يمنع نسخة تتراجع عن المرجع."""
    raise NotImplementedError("يُبنى يوم 2 (5 أكتوبر)")


def stability(scores: list[RunScore]) -> dict:
    """ثبات النتائج عبر التشغيلات الرسمية المتكررة (الفرق بين أعلى وأدنى درجة لكل مستوى)."""
    raise NotImplementedError("يُبنى يوم 3 (6 أكتوبر)")
