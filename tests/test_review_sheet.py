"""ورقة المراجعة: التصدير متزامن مع testsets/، والاستيراد يفرض الاسم والتاريخ وسبب الرفض ولا يكتب شيئاً عند الخطأ."""

import csv
import importlib.util
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("review_sheet", ROOT / "scripts" / "review_sheet.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)


def _sandbox(tmp_path):
    """نسخ ملفات testsets إلى مجلد مؤقت وتوجيه السكربت إليها."""
    paths = {}
    for name, p in rs.TESTSETS.items():
        dst = tmp_path / p.name
        shutil.copy(p, dst)
        paths[name] = dst
    return paths


def _sheet(tmp_path, edits):
    out = tmp_path / "sheet.csv"
    rs.export(out)
    with out.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r.update(edits.get(r["id"], {}))
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rs.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return out


def test_published_sheet_is_in_sync(tmp_path):
    fresh = tmp_path / "sheet.csv"
    n = rs.export(fresh)
    assert n == 60
    assert fresh.read_bytes() == rs.SHEET.read_bytes(), "أعد التوليد: python scripts/review_sheet.py export"


def test_apply_records_named_decisions_and_rejects_bad_rows(tmp_path):
    original = rs.TESTSETS
    rs.TESTSETS = _sandbox(tmp_path)
    try:
        bad = _sheet(tmp_path, {
            "OFF-01": {"decision": "approved", "reviewer_name": "", "reviewer_role": "specialist", "review_date": "2026-10-04"},  # بلا اسم
            "EXT-001": {"decision": "rejected", "reviewer_name": "المراجع", "reviewer_role": "specialist",
                        "review_date": "2026-10-04"},  # بلا سبب
            "EXT-002": {"decision": "approved", "reviewer_name": "المراجع", "review_date": "2026-10-04"},  # بلا نوع
        })
        count, errors = rs.apply(bad)
        assert count == 0 and len(errors) == 3
        assert all(c["review_status"] == "pending"
                   for p in rs.TESTSETS.values() for c in json.loads(p.read_text(encoding="utf-8"))["cases"])

        good = _sheet(tmp_path, {
            "OFF-01": {"decision": "approved", "reviewer_name": "المراجع", "reviewer_role": "specialist",
                       "review_date": "2026-10-04"},
            "EXT-001": {"decision": "rejected", "reviewer_name": "المشارك", "reviewer_role": "source_check",
                        "review_date": "2026-10-04", "notes": "يحتاج تعديل السلوك المتوقع"},
        })
        count, errors = rs.apply(good)
        assert (count, errors) == (2, [])
        off = {c["id"]: c for c in json.loads(rs.TESTSETS["official_v0"].read_text(encoding="utf-8"))["cases"]}
        ext = {c["id"]: c for c in json.loads(rs.TESTSETS["extended_v1"].read_text(encoding="utf-8"))["cases"]}
        assert off["OFF-01"]["review_status"] == "approved" and off["OFF-01"]["reviewed_by"] == "المراجع"
        assert off["OFF-01"]["reviewer_role"] == "specialist" and ext["EXT-001"]["reviewer_role"] == "source_check"
        s = rs.status()
        assert s["approved"]["specialist"] == 1 and s["rejected"]["source_check"] == 1 and s["pending"] == 58
        assert ext["EXT-001"]["review_status"] == "rejected" and ext["EXT-001"]["review_notes"]

        downgrade = _sheet(tmp_path, {"OFF-01": {"decision": "approved", "reviewer_name": "المشارك",
                                                 "reviewer_role": "source_check", "review_date": "2026-10-05"}})
        assert rs.apply(downgrade)[1], "source_check لا يحلّ محل specialist"

        stale = _sheet(tmp_path, {"OFF-02": {"decision": "approved", "reviewer_name": "م", "review_date": "2026-10-04",
                                             "reviewer_role": "specialist", "prompt": "نص قديم"}})
        assert rs.apply(stale)[1], "قرار على نص تغيّر يجب أن يُرفض"
    finally:
        rs.TESTSETS = original


def _rows():
    with rs.SHEET.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_sheet_is_utf8_with_bom():
    raw = rs.SHEET.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    raw.decode("utf-8")  # ترميز سليم
    assert "الأولوية" in raw[3:].decode("utf-8").splitlines()[0]


def test_priority_is_first_column_and_sorted():
    rows = _rows()
    assert list(rows[0].keys())[0] == "الأولوية" and "reviewer_role" in rows[0]
    prios = [int(r["الأولوية"]) for r in rows]
    assert prios == sorted(prios)
    p1 = {r["id"] for r in rows if r["الأولوية"] == "1"}
    assert len(p1) == 7 and all(r["risk_type"] in ("hadith_fabricated", "hadith_absent")
                                for r in rows if r["id"] in p1)
    for r in rows:
        if r["level"] == "D" or r["risk_type"] == "fiqh_disagreement":
            assert r["الأولوية"] in ("1", "2"), r["id"]
