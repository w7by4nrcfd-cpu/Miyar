"""النشر من السجلات الرسمية إلى الموقع (docs/BUILD_SPEC.md §3): evaluation/official/ ← web/data/.

- يقرأ كل سجل ``OFFICIAL_RUN`` في ``evaluation/official/<run_id>.json``، ويحسب الدرجة من أحكام الحالات المحفوظة في السجل
  بـ ``scoring.score_run`` (فلا رقم يُكتب يدوياً)، ويكتب ``web/data/results.json`` و``web/data/cases/<id>.json``.
- **حتمي:** التشغيل مرتين يعطي الملفات نفسها (ترتيب ثابت، بلا وقت تشغيل)، والملفات القديمة في ``cases/`` تُحذف.
- **يرفض** (ولا يكتب أي شيء إن وُجد خطأ واحد): أي سجل خارج ``evaluation/official/``، أو وسمه غير ``OFFICIAL_RUN``
  (مثل DEV_RUN وLIVE_DEMO)، أو موسوم FIXTURE، أو معرّفه ``live-``، أو مخالف لحقول السجل الرسمي، أو بلا درجة محسوبة،
  أو فيه «مؤيَّد» بلا نص مطابَق وموضع من البيانات (BUILD_SPEC S2.1).
- لا يحكم ولا يستدعي أي نموذج: يجمع ما في السجلات فقط.

عقد السجل الرسمي: حقول ``RunRecord.to_dict()`` (``runner``)، ولكل حالة حقل ``judgement`` اختياري
بصيغة ``judgement_to_dict`` (الحالة بلا حكم تُعدّ «بلا حكم» ولا تُحتسب في الدرجة).
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .hadith_match import pending_entries_for_case
from .hadith_manual import load_manual
from .judge import BehaviorJudgement, Citation, CitationJudgement
from .quran_match import SUPPORTED
from .runner import OFFICIAL_RUN, Answer, CaseResult, RunRecord, load_cases
from .scoring import LEVELS, RunScore, gate_decision, score_run, stability

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_DIR = ROOT / "evaluation" / "official"
WEB_DATA = ROOT / "web" / "data"
TESTSETS_DIR = ROOT / "testsets"
NON_RECORDS = {"README.md", "official_run.schema.json"}
FIXTURE_MARK = "FIXTURE"
REQUIRED = ("run_label", "run_id", "executed_at", "n_cases", "testsets", "assistant", "model", "cases", "human_reviewed")
ROLES = ("specialist", "source_check")
RIYADH = timezone(timedelta(hours=3))
WINDOW = (datetime(2026, 10, 4, tzinfo=RIYADH), datetime(2026, 10, 7, tzinfo=RIYADH))  # [4 أكتوبر، 7 أكتوبر)
# أسئلة مقاطعها أُخذت أصلاً من مجموعة غير معتمدة: يُحجب نصها ما دام مدخلها اليدوي ناقصاً (BUILD_SPEC S2.2)
MASK_WHILE_PENDING = ("EXT-029", "EXT-030", "EXT-031", "EXT-032")
MASKED_TEXT = "نص السؤال محجوب حتى التحقق من مصدره"


class PublishError(ValueError):
    """سجل مرفوض أو بيانات لا تُنشر؛ لا يُكتب أي ملف."""


# ---------- تسلسل الأحكام ----------
def judgement_to_dict(j: BehaviorJudgement) -> dict:
    return asdict(j)


def judgement_from_dict(d: dict) -> BehaviorJudgement:
    cites = [CitationJudgement(Citation(**c["citation"]), c["status"], c["reason"], c.get("matched_ref"),
                               c.get("matched_text"), c.get("detail") or {}) for c in d.get("citations", [])]
    return BehaviorJudgement(**{**d, "citations": cites})


def record_from_dict(d: dict) -> RunRecord:
    cases = [CaseResult(c["id"], c.get("testset", ""), c.get("prompt", ""),
                        Answer(**c["answer"]) if c.get("answer") else None, c.get("level", ""), c.get("error"))
             for c in d["cases"]]
    return RunRecord(d["run_id"], d["run_label"], d["executed_at"], d["assistant"], d["model"], list(d["testsets"]),
                     cases, d["human_reviewed"])


# ---------- التحقق ----------
def _has_fixture_mark(obj) -> bool:
    if isinstance(obj, str):
        return FIXTURE_MARK in obj.upper()
    if isinstance(obj, dict):
        return any(_has_fixture_mark(k) or _has_fixture_mark(v) for k, v in obj.items())
    if isinstance(obj, list):
        return any(_has_fixture_mark(v) for v in obj)
    return False


def record_errors(rec: dict, path: Path, official_dir: Path = OFFICIAL_DIR) -> list[str]:
    """مخالفات سجل واحد (قائمة فارغة = صالح للنشر)."""
    name = path.name
    try:
        path.resolve().relative_to(official_dir.resolve())
    except ValueError:
        return [f"{name}: خارج evaluation/official/"]
    errs = [f"{name}: حقل مفقود: {k}" for k in REQUIRED if k not in rec]
    if errs:
        return errs
    if rec["run_label"] != OFFICIAL_RUN:
        errs.append(f"{name}: الوسم {rec['run_label']!r} ليس OFFICIAL_RUN")
    if _has_fixture_mark(rec):
        errs.append(f"{name}: سجل موسوم FIXTURE")
    if str(rec["run_id"]).startswith("live-"):
        errs.append(f"{name}: معرّف تشغيل حي (live-)")
    if f"{rec['run_id']}.json" != name:
        errs.append(f"{name}: run_id لا يطابق اسم الملف")
    try:
        at = datetime.fromisoformat(rec["executed_at"])
        if at.tzinfo is None or not (WINDOW[0] <= at < WINDOW[1]):
            errs.append(f"{name}: executed_at بلا منطقة زمنية أو خارج 4–6 أكتوبر 2026 (توقيت الرياض)")
    except (TypeError, ValueError):
        errs.append(f"{name}: executed_at ليس تاريخاً صالحاً")
    n = rec["n_cases"]
    if not isinstance(n, int) or isinstance(n, bool) or n < 1 or not isinstance(rec["cases"], list) \
            or len(rec["cases"]) != n or len({c.get("id") for c in rec["cases"]}) != n:
        errs.append(f"{name}: n_cases لا يساوي عدد الحالات الفريدة في cases")
    hr = rec["human_reviewed"]
    br = hr.get("by_role") if isinstance(hr, dict) else None
    if not isinstance(br, dict) or set(br) != set(ROLES) or \
            hr.get("approved") != sum(br.values()) or hr.get("total") != n:
        errs.append(f"{name}: human_reviewed غير متسق (approved = مجموع الأنواع، total = n_cases)")
    return errs


def _supported_guard(run_id: str, case_id: str, j: BehaviorJudgement) -> list[str]:
    return [f"{run_id}/{case_id}: «مؤيَّد» بلا نص مطابَق وموضع من البيانات"
            for c in j.citations if c.status == SUPPORTED and not (c.matched_text and c.matched_ref)]


# ---------- البناء ----------
def _load_records(official_dir: Path) -> list[tuple[Path, dict]]:
    out = []
    for p in sorted(official_dir.glob("*.json")):
        if p.name in NON_RECORDS:
            continue
        out.append((p, json.loads(p.read_text(encoding="utf-8"))))
    return out


def _case_payload(cid: str, case: dict, manual: dict) -> dict:
    masked = cid in MASK_WHILE_PENDING and bool(pending_entries_for_case(cid, manual))
    return {
        "schema_version": 1,
        "id": cid,
        "level": case.get("level", ""),
        "expected_behavior": case.get("expected_behavior", ""),
        "prompt": None if masked else case.get("prompt", ""),
        "prompt_masked": masked,
        "masked_text": MASKED_TEXT if masked else None,
        "runs": [],
    }


def _judgement_view(j: BehaviorJudgement) -> dict:
    return {
        "checks": j.checks, "confidence": j.confidence, "judge_model": j.judge_model,
        "needs_human_review": j.needs_human_review, "review_reason": j.review_reason, "rationale": j.rationale,
        "program_overrides": j.program_overrides,
        "citations": [{"kind": c.citation.kind, "quote": c.citation.quote, "cited": c.citation.cited, "status": c.status,
                       "reason": c.reason, "matched_ref": c.matched_ref, "matched_text": c.matched_text}
                      for c in j.citations],
    }


def build(official_dir: Path = OFFICIAL_DIR, cases: list[dict] | None = None,
          manual: dict | None = None) -> tuple[dict, dict[str, dict]]:
    """يعيد (results.json، {معرّف الحالة: ملف الحالة}). يرفع PublishError عند أي خطأ."""
    cases = cases if cases is not None else load_cases(sorted(TESTSETS_DIR.glob("*.json")))
    manual = manual if manual is not None else load_manual()
    by_case = {c["id"]: c for c in cases}
    records = _load_records(official_dir)
    errors = [e for p, rec in records for e in record_errors(rec, p, official_dir)]
    if errors:
        raise PublishError("\n".join(errors))

    runs, case_files, scores = [], {}, []
    for path, rec in records:
        record = record_from_dict(rec)
        unknown = [c.case_id for c in record.cases if c.case_id not in by_case]
        if unknown:
            raise PublishError(f"{path.name}: حالات غير موجودة في testsets/: {', '.join(unknown)}")
        js = {c["id"]: judgement_from_dict(c["judgement"]) for c in rec["cases"] if c.get("judgement")}
        guard = [e for cid, j in js.items() for e in _supported_guard(record.run_id, cid, j)]
        if guard:
            raise PublishError("\n".join(guard))
        score = score_run(record, list(js.values()), cases)
        if score.overall_score is None:
            raise PublishError(f"{path.name}: لا درجة محسوبة (لم تُحتسب أي حالة)")
        scores.append(score)
        runs.append({
            "run_id": record.run_id,
            "executed_at": record.executed_at,
            "assistant": record.assistant,
            "model": record.model,
            "testset": "+".join(record.testsets),
            "n_cases": record.n_cases,
            "overall_score": score.overall_score,
            "levels": {lv: {"n_cases": score.levels[lv].n_cases, "score": score.levels[lv].score,
                            "n_scored": score.levels[lv].n_scored} for lv in LEVELS},
            "wrong_citations": score.wrong_citations,
            "n_scored": score.n_scored,
            "human_review_needed": score.human_review_needed,
            "referral": dict(score.referral),
            "human_reviewed": record.human_reviewed,
            "evaluation_record": f"evaluation/official/{path.name}",
        })
        for res in record.cases:
            cf = case_files.setdefault(res.case_id, _case_payload(res.case_id, by_case[res.case_id], manual))
            j = js.get(res.case_id)
            cf["runs"].append({
                "run_id": record.run_id, "executed_at": record.executed_at, "assistant": record.assistant,
                "answer_model": res.answer.model if res.answer else None,
                "answer": res.answer.text if res.answer else None,
                "error": res.error,
                "judgement": _judgement_view(j) if j else None,
            })

    order = lambda r: (r["executed_at"], r["run_id"])  # noqa: E731
    runs.sort(key=order)
    for cf in case_files.values():
        cf["runs"].sort(key=order)
    results = {"schema_version": 1, "runs": runs}
    executed = {r["run_id"]: r["executed_at"] for r in runs}
    scores.sort(key=lambda s: (executed[s.run_id], s.run_id))
    gate = gate_view(scores)
    if gate is not None:
        results["gate"] = gate
    stab = stability_view(scores)
    if stab:
        results["stability"] = stab
    return results, dict(sorted(case_files.items()))


# ---------- البوابة والثبات (من scoring، لا من الصفحة) ----------
REFERENCE, CANDIDATE = "baseline", "rag"


def _latest(scores: list[RunScore], assistant: str) -> RunScore | None:
    xs = [s for s in scores if s.assistant == assistant]
    return xs[-1] if xs else None


def gate_view(scores: list[RunScore]) -> dict | None:
    """قرار البوابة بين آخر تشغيل rag (المرشحة) وآخر تشغيل baseline (المرجع) بـ scoring.gate_decision.
    None إن غاب أحدهما (فلا قرار يُعرض)."""
    ref, cand = _latest(scores, REFERENCE), _latest(scores, CANDIDATE)
    if ref is None or cand is None:
        return None
    d = gate_decision(cand, ref)
    return {"rule": d.rule, "reference_run_id": ref.run_id, "candidate_run_id": cand.run_id,
            "allow": d.allow, "reasons": list(d.reasons)}


def stability_view(scores: list[RunScore]) -> dict:
    """الثبات لكل مساعد له تشغيلان رسميان أو أكثر على مجموعة الحالات نفسها (scoring.stability). لا يُختار أفضل تشغيل."""
    out = {}
    for assistant in sorted({s.assistant for s in scores}):
        xs = [s for s in scores if s.assistant == assistant]
        if len(xs) >= 2 and len({tuple(sorted(s.case_ids)) for s in xs}) == 1:
            out[assistant] = stability(xs)
    return out


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"


def planned_files(results: dict, case_files: dict[str, dict], out_dir: Path = WEB_DATA) -> dict[Path, str]:
    files = {out_dir / "results.json": _dump(results)}
    files.update({out_dir / "cases" / f"{cid}.json": _dump(cf) for cid, cf in case_files.items()})
    return files


def diff(files: dict[Path, str], out_dir: Path = WEB_DATA) -> list[str]:
    """الملفات التي تختلف عن المكتوب حالياً (فارغة = متزامن)."""
    out = [str(p.relative_to(out_dir)) for p, text in files.items()
           if not p.is_file() or p.read_text(encoding="utf-8") != text]
    cases_dir = out_dir / "cases"
    if cases_dir.is_dir():
        out += [f"cases/{p.name} (قديم)" for p in sorted(cases_dir.glob("*.json")) if p not in files]
    return out


def write(files: dict[Path, str], out_dir: Path = WEB_DATA) -> None:
    cases_dir = out_dir / "cases"
    if cases_dir.is_dir():
        for p in cases_dir.glob("*.json"):
            if p not in files:
                p.unlink()
    for p, text in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
