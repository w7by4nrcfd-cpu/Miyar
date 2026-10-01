"""تشغيل مجموعة الاختبار على مساعد وحفظ الإجابات — **هيكل فقط (2026-10-01)، بلا منطق.**

الواجهات هنا عقد للبناء في أيام التحدي (اليوم 1، docs/BUILD_PLAN.md). كل دالة ترفع NotImplementedError،
ويحرس ذلك tests/test_skeletons.py حتى يُبنى المنطق في 4 أكتوبر.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class Target(Protocol):
    """المساعد المُختبَر (يُنفَّذ في targets.py وassistants/ يوم 1)."""

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
    answer: Answer


@dataclass
class RunRecord:
    run_id: str
    run_label: str  # DEV_RUN أو OFFICIAL_RUN
    executed_at: str  # ISO 8601 بمنطقة زمنية
    assistant: str
    model: str
    testsets: list[str]
    cases: list[CaseResult] = field(default_factory=list)  # N = len(cases)


def load_cases(testset_paths: list[Path]) -> list[dict]:
    """يقرأ حالات الاختبار من ملفات testsets/ بترتيبها."""
    raise NotImplementedError("يُبنى يوم 1 (4 أكتوبر)")


def run_testset(cases: list[dict], target: Target, run_label: str) -> RunRecord:
    """يطرح كل حالة على المساعد ويجمع الإجابات في سجل تشغيل."""
    raise NotImplementedError("يُبنى يوم 1 (4 أكتوبر)")


def save_run(record: RunRecord, directory: Path) -> Path:
    """يحفظ السجل: evaluation/dev/ لـ DEV_RUN، وevaluation/official/<run_id>.json لـ OFFICIAL_RUN."""
    raise NotImplementedError("يُبنى يوم 1 (4 أكتوبر)")
