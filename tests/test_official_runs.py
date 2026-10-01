"""حارس: النتائج المنشورة لا تأتي إلا من سجلات OFFICIAL_RUN داخل evaluation/official/.

- results.json لا يشير إلى أي مسار خارج evaluation/official/، والسجل المشار إليه موجود ويطابقه.
- كل سجل رسمي يحمل OFFICIAL_RUN وتاريخ تشغيل داخل أيام التحدي وعدد الحالات N = len(cases).
"""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_DIR = ROOT / "evaluation" / "official"
OFFICIAL_PREFIX = "evaluation/official/"
LABEL = "OFFICIAL_RUN"
RIYADH = timezone(timedelta(hours=3))
WINDOW = (datetime(2026, 10, 4, tzinfo=RIYADH), datetime(2026, 10, 7, tzinfo=RIYADH))  # [4 أكتوبر، 7 أكتوبر)
NON_RECORDS = {"README.md", "official_run.schema.json"}
REQUIRED = ("run_label", "run_id", "executed_at", "n_cases", "testsets", "assistant", "model", "cases", "human_reviewed")
ROLES = ("specialist", "source_check")  # source_check ليس مراجعة شرعية متخصصة


def record_errors(rec: dict, filename: str) -> list[str]:
    """مخالفات سجل رسمي واحد (قائمة فارغة = صالح)."""
    errs = [f"حقل مفقود: {k}" for k in REQUIRED if k not in rec]
    if errs:
        return errs
    if rec["run_label"] != LABEL:
        errs.append("run_label ليس OFFICIAL_RUN")
    if f'{rec["run_id"]}.json' != filename:
        errs.append("run_id لا يطابق اسم الملف")
    try:
        at = datetime.fromisoformat(rec["executed_at"])
        if at.tzinfo is None:
            errs.append("executed_at بلا منطقة زمنية")
        elif not (WINDOW[0] <= at < WINDOW[1]):
            errs.append("executed_at خارج أيام التحدي 4–6 أكتوبر 2026 (توقيت الرياض)")
    except (TypeError, ValueError):
        errs.append("executed_at ليس تاريخاً صالحاً")
    n = rec["n_cases"]
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        errs.append("n_cases يجب أن يكون عدداً صحيحاً ≥ 1")
    elif not isinstance(rec["cases"], list) or len(rec["cases"]) != n:
        errs.append("n_cases لا يساوي عدد الحالات في cases")
    elif len({c.get("id") for c in rec["cases"]}) != n:
        errs.append("معرّفات الحالات مكررة أو مفقودة")
    if not rec["testsets"] or not all(isinstance(t, str) and t for t in rec["testsets"]):
        errs.append("testsets فارغة")
    hr = rec["human_reviewed"]
    br = hr.get("by_role") if isinstance(hr, dict) else None
    if not isinstance(br, dict) or set(br) != set(ROLES) or not all(isinstance(br[r], int) and br[r] >= 0 for r in ROLES):
        errs.append("human_reviewed.by_role يجب أن يحمل specialist وsource_check")
    elif hr.get("approved") != br["specialist"] + br["source_check"] or hr.get("total") != rec["n_cases"]:
        errs.append("human_reviewed: approved ≠ مجموع الأنواع، أو total ≠ n_cases")
    return errs


def results_errors(results: dict, root: Path = ROOT) -> list[str]:
    """مخالفات results.json: كل run يشير إلى سجل رسمي موجود داخل evaluation/official/ ويطابقه."""
    errs = []
    for i, run in enumerate(results.get("runs", [])):
        path = run.get("evaluation_record", "")
        if not path.startswith(OFFICIAL_PREFIX) or ".." in path.split("/"):
            errs.append(f"runs[{i}]: evaluation_record خارج {OFFICIAL_PREFIX}")
            continue
        f = root / path
        if not f.is_file():
            errs.append(f"runs[{i}]: السجل غير موجود: {path}")
            continue
        rec = json.loads(f.read_text(encoding="utf-8"))
        if rec.get("run_label") != LABEL:
            errs.append(f"runs[{i}]: السجل ليس OFFICIAL_RUN")
        if rec.get("n_cases") != run.get("n_cases"):
            errs.append(f"runs[{i}]: n_cases لا يطابق السجل")
        if rec.get("executed_at") != run.get("executed_at"):
            errs.append(f"runs[{i}]: executed_at لا يطابق السجل")
        if rec.get("human_reviewed") != run.get("human_reviewed"):
            errs.append(f"runs[{i}]: human_reviewed (لكل نوع مراجعة) لا يطابق السجل")
    return errs


def _records():
    return [p for p in OFFICIAL_DIR.rglob("*") if p.is_file() and p.name not in NON_RECORDS]


# ---------- الحارس على الملفات الفعلية ----------
def test_official_dir_exists_with_readme_and_schema():
    assert (OFFICIAL_DIR / "README.md").is_file()
    assert json.loads((OFFICIAL_DIR / "official_run.schema.json").read_text(encoding="utf-8"))


def test_every_official_record_is_valid():
    for p in _records():
        assert p.suffix == ".json", f"ملف غير متوقع في evaluation/official/: {p.name}"
        rec = json.loads(p.read_text(encoding="utf-8"))
        assert record_errors(rec, p.name) == [], (p.name, record_errors(rec, p.name))


def test_no_dev_run_material_in_official_dir():
    for p in OFFICIAL_DIR.rglob("*"):
        if p.is_file():
            assert "DEV_RUN" not in p.read_text(encoding="utf-8", errors="ignore"), p.name


def test_published_results_point_only_to_official_records():
    results = json.loads((ROOT / "web/data/results.json").read_text(encoding="utf-8"))
    assert results_errors(results) == []
    # ولا أي مسار آخر داخل evaluation/ في أي مكان من الملف
    text = (ROOT / "web/data/results.json").read_text(encoding="utf-8")
    for m in re.findall(r"evaluation/[^\"\s]*", text):
        assert m.startswith(OFFICIAL_PREFIX), m


# ---------- اختبارات الحارس نفسه على سجلات اصطناعية ----------
HR = {"approved": 1, "total": 2, "by_role": {"specialist": 0, "source_check": 1}}


def _rec(**patch):
    rec = {
        "run_label": LABEL, "run_id": "r1", "executed_at": "2026-10-05T10:00:00+03:00", "n_cases": 2,
        "testsets": ["official_v0"], "assistant": "baseline", "model": "m", "cases": [{"id": "a"}, {"id": "b"}],
        "human_reviewed": HR,
    }
    return {**rec, **patch}


def test_record_validator_accepts_valid_and_rejects_violations():
    assert record_errors(_rec(), "r1.json") == []
    assert record_errors(_rec(run_label="DEV_RUN"), "r1.json")
    assert record_errors(_rec(), "other.json")
    assert record_errors(_rec(executed_at="2026-10-03T23:59:00+03:00"), "r1.json")  # قبل التحدي
    assert record_errors(_rec(executed_at="2026-10-07T00:00:00+03:00"), "r1.json")  # بعده
    assert record_errors(_rec(executed_at="2026-10-05T10:00:00"), "r1.json")  # بلا منطقة زمنية
    assert record_errors(_rec(n_cases=3), "r1.json")
    assert record_errors(_rec(n_cases=0, cases=[]), "r1.json")
    assert record_errors(_rec(cases=[{"id": "a"}, {"id": "a"}]), "r1.json")
    assert record_errors(_rec(human_reviewed={"approved": 1, "total": 2}), "r1.json")  # بلا تفصيل النوع
    assert record_errors(_rec(human_reviewed={**HR, "approved": 2}), "r1.json")  # المجموع لا يطابق
    assert record_errors(_rec(human_reviewed={**HR, "by_role": {"specialist": 1}}), "r1.json")
    rec = _rec()
    del rec["executed_at"]
    assert record_errors(rec, "r1.json")


def test_results_validator(tmp_path):
    (tmp_path / "evaluation/official").mkdir(parents=True)
    (tmp_path / "evaluation/official/r1.json").write_text(json.dumps(_rec()), encoding="utf-8")
    run = {"evaluation_record": "evaluation/official/r1.json", "n_cases": 2, "executed_at": "2026-10-05T10:00:00+03:00",
           "human_reviewed": HR}
    assert results_errors({"runs": [run]}, tmp_path) == []
    assert results_errors({"runs": [{**run, "evaluation_record": "evaluation/r1.json"}]}, tmp_path)
    assert results_errors({"runs": [{**run, "evaluation_record": "evaluation/official/../official/r1.json"}]}, tmp_path)
    assert results_errors({"runs": [{**run, "evaluation_record": "evaluation/official/missing.json"}]}, tmp_path)
    assert results_errors({"runs": [{**run, "n_cases": 3}]}, tmp_path)
    assert results_errors({"runs": [{**run, "executed_at": "2026-10-05T11:00:00+03:00"}]}, tmp_path)
    other = {"approved": 1, "total": 2, "by_role": {"specialist": 1, "source_check": 0}}
    assert results_errors({"runs": [{**run, "human_reviewed": other}]}, tmp_path)
