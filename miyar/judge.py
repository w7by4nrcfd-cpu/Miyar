"""الحكم على الإجابة: دعم المصدر للإسناد + التزام سلوك المستوى — **هيكل فقط (2026-10-01)، بلا منطق.**

الحَكَم يطبّق معياراً مكتوباً (expected_behavior وchecks في الحالة) ولا يضع معياراً (docs/METHODOLOGY.md).
مطابقة الآيات حرفية في quran_match، والأحاديث في hadith_search؛ ولا يصدر «مؤيَّد» دون مطابقة فعلية في البيانات.
عند ضعف الثقة (أقل من MIYAR_JUDGE_MIN_CONFIDENCE) لا حكم آلي، بل مراجعة بشرية.
كل دالة ترفع NotImplementedError، ويحرس ذلك tests/test_skeletons.py حتى يُبنى المنطق (اليوم 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from miyar.quran_match import NEEDS_REVIEW, SUPPORTED, WRONG_OR_MISSING

CITATION_STATUSES = (SUPPORTED, NEEDS_REVIEW, WRONG_OR_MISSING)


@dataclass
class Citation:
    """إسناد مستخرج من إجابة المساعد (يُنتجه extract.py)."""

    kind: str  # quran أو hadith أو other
    quote: str
    cited: str | None = None  # الموضع كما ذكره المساعد، مثل «البقرة 255» أو «البخاري 1»


@dataclass
class CitationJudgement:
    citation: Citation
    status: str  # أحد CITATION_STATUSES
    reason: str
    matched_ref: str | None = None  # الموضع في البيانات إن وُجد


@dataclass
class BehaviorJudgement:
    case_id: str
    checks: dict[str, bool | None]  # لكل فحص في الحالة: نجح / أخفق / لم يُحسم
    confidence: float
    judge_model: str  # النموذج الذي حكم فعلاً (يختلف عن نموذج المساعد)
    needs_human_review: bool
    rationale: str = ""
    citations: list[CitationJudgement] = field(default_factory=list)


def judge_citation(citation: Citation) -> CitationJudgement:
    """يحكم على إسناد واحد بالمطابقة البرمجية مع البيانات (بلا نموذج لغوي للآيات)."""
    raise NotImplementedError("يُبنى يوم 2 (5 أكتوبر)")


def judge_behavior(case: dict, answer_text: str, citations: list[CitationJudgement]) -> BehaviorJudgement:
    """يقارن الإجابة بالسلوك المتوقع وفحوص الحالة، مع درجة ثقة."""
    raise NotImplementedError("يُبنى يوم 2 (5 أكتوبر)")


def requires_human_review(confidence: float, threshold: float) -> bool:
    """هل تُحال الحالة إلى مراجعة بشرية بدل الحكم الآلي؟"""
    raise NotImplementedError("يُبنى يوم 2 (5 أكتوبر)")
