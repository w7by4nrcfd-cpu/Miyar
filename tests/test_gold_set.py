"""Gold Set: حماية السجلات الرسمية، والإخفاء، وقابلية تكرار الاستخراج، وقواعد الحساب المسجّلة مسبقاً.

لا وسوم بشرية حقيقية هنا: اختبارات الحساب كلها بوسوم اصطناعية في مجلد مؤقت.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import gold_set as g  # noqa: E402

GOLD = ROOT / "evaluation" / "gold"
FORBIDDEN_KEYS = {"status", "reason", "matched_ref", "matched_text", "cited_text", "similarity", "found_at",
                  "suggestions", "confidence", "rationale", "needs_human_review", "review_reason", "categories",
                  "score", "overall_score", "run_id", "case_id", "automated_verdict", "judgement"}
FORBIDDEN_TEXT = ("supported", "needs_review", "wrong_or_missing", "exact_match", "altered_text",
                  "location_not_stated", "official-2026", "OFF-", "baseline", "rag-2")


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def _read(p):
    return json.loads(p.read_text(encoding="utf-8"))


# ---------- السجلات الرسمية ----------
def test_official_records_unchanged():
    assert (GOLD / g.SUMS_NAME).read_text(encoding="utf-8") == g.official_sums(), "سجل رسمي أو مخرج منشور تغيّر"
    listed = (GOLD / g.SUMS_NAME).read_text(encoding="utf-8")
    assert listed.count("evaluation/official/official-2026-10-04-") == 4
    assert listed.count("web/data/cases/OFF-") == 12 and "web/data/results.json" in listed


# ---------- الاستخراج ----------
def test_extract_is_reproducible(tmp_path):
    shutil.copy(GOLD / g.SUMS_NAME, tmp_path / g.SUMS_NAME)
    g.cmd_extract(ROOT, tmp_path)
    for rel in ("quran/sheet_blind.json", "quran/sheet_blind.md", "quran/key.json",
                "behaviour/sheet_blind.json", "behaviour/sheet_blind.md", "behaviour/key.json"):
        assert (tmp_path / rel).read_bytes() == (GOLD / rel).read_bytes(), rel


def test_counts_and_scope():
    sheet, key = _read(GOLD / "quran/sheet_blind.json"), _read(GOLD / "quran/key.json")
    assert sheet["counts"] == {"n_items": 31, "n_unique_quotes": 21, "n_unique_quote_location_pairs": 21,
                               "n_unique_written_locations": 15, "n_without_written_location": 7}
    runs = g.load_runs()
    auto = g._automated_quran(runs)
    kinds = {(r["run_id"], c["id"], i): cit["citation"]["kind"] for r in runs for c in r["cases"]
             for i, cit in enumerate((c.get("judgement") or {}).get("citations") or [])}
    keyed = [(k["run_id"], k["case_id"], k["citation_index"]) for k in key["items"]]
    assert len(set(keyed)) == 31 and all(kinds[k] == "quran" for k in keyed)  # الأحاديث خارج الطبقة A
    assert sum(1 for k in kinds.values() if k == "quran") == 31
    from collections import Counter
    assert Counter(auto[k] for k in keyed) == {"supported": 20, "needs_review": 8, "wrong_or_missing": 3}
    b = _read(GOLD / "behaviour/key.json")["items"]
    assert len(b) == 16 and {x["case_id"] for x in b} == set(g.CRITICAL)


@pytest.mark.parametrize("layer", ["quran", "behaviour"])
def test_sheets_are_blind(layer):
    sheet = _read(GOLD / layer / "sheet_blind.json")
    assert not set(_keys(sheet)) & FORBIDDEN_KEYS
    for name in ("sheet_blind.json", "sheet_blind.md"):
        text = (GOLD / layer / name).read_text(encoding="utf-8")
        for bad in FORBIDDEN_TEXT:
            assert bad not in text, f"{layer}/{name}: {bad}"
    key = _read(GOLD / layer / "key.json")
    assert set(_keys(key)) <= {"layer", "items", "item_id", "run_id", "case_id", "citation_index"}


def test_reference_text_comes_from_written_location_only():
    """نص المصحف المعروض يُحلَّل من الموضع المكتوب، ويتفق مع موضع المستخرِج حيث وُجد."""
    quran = g.load_quran()
    for run in g.load_runs():
        for case in run["cases"]:
            for cit in (case.get("judgement") or {}).get("citations") or []:
                c = cit["citation"]
                if c["kind"] == "quran" and c.get("sura"):
                    assert g.parse_cited(c["cited"], quran) == (c["sura"], c["aya"], c.get("aya_end") or c["aya"])
    assert g.parse_cited("سورة البقرة", quran) is None
    assert g.parse_cited(None, quran) is None
    assert g.parse_cited("[طه: 114]", quran) == (20, 114, 114)
    assert g.parse_cited("سورة طه، رقم 114", quran) == (20, 114, 114)


# ---------- الوسوم والقفل والحساب (اصطناعية) ----------
def _setup(tmp_path, layer):
    shutil.copy(GOLD / g.SUMS_NAME, tmp_path / g.SUMS_NAME)
    shutil.copytree(GOLD / layer, tmp_path / layer)
    for f in ("labels.json", "LOCK.json", "agreement.json"):
        (tmp_path / layer / f).unlink(missing_ok=True)
    return _read(tmp_path / layer / "key.json")["items"]


def _quran_labels(key, verdict_for):
    return {"reviewer": {"reviewer_id": "synthetic", "reviewer_type": "owner_textual", "description": "اختبار"},
            "labels": [{"item_id": k["item_id"], **verdict_for(k)} for k in key]}


def _approved(v):
    return {"review_status": "approved", "human_verdict": v, "reviewed_at": "2026-10-06T00:00+03:00", "notes": ""}


def test_compute_refuses_without_lock(tmp_path):
    _setup(tmp_path, "quran")
    with pytest.raises(SystemExit):
        g.cmd_compute("quran", ROOT, tmp_path)


def test_compute_refuses_if_labels_change_after_lock(tmp_path):
    key = _setup(tmp_path, "quran")
    g.write_json(tmp_path / "quran/labels.json", _quran_labels(key, lambda k: _approved("cannot_determine")))
    g.cmd_lock("quran", tmp_path)
    with pytest.raises(SystemExit):
        g.cmd_lock("quran", tmp_path)  # لا يُعاد القفل
    g.write_json(tmp_path / "quran/labels.json", _quran_labels(key, lambda k: _approved("differs")))
    with pytest.raises(SystemExit):
        g.cmd_compute("quran", ROOT, tmp_path)


@pytest.mark.parametrize("bad", [
    lambda L: L["labels"].pop(),  # عنصر ناقص
    lambda L: L["labels"].append(dict(L["labels"][0])),  # مكرر
    lambda L: L["labels"][0].update(human_verdict="supported"),  # قيمة غير مسموحة (تصنيف مِعيار لا قيمة المراجع)
    lambda L: L["reviewer"].update(reviewer_type="specialist"),  # نوع مراجع غير مسموح للطبقة A
    lambda L: L["labels"][0].update(reviewed_at=None),
])
def test_lock_validates_labels(tmp_path, bad):
    key = _setup(tmp_path, "quran")
    labels = _quran_labels(key, lambda k: _approved("matches_at_location"))
    bad(labels)
    g.write_json(tmp_path / "quran/labels.json", labels)
    with pytest.raises(ValueError):
        g.cmd_lock("quran", tmp_path)
    assert not (tmp_path / "quran/LOCK.json").exists()


def test_quran_compute_counts_only(tmp_path):
    key = _setup(tmp_path, "quran")
    auto = g._automated_quran(g.load_runs())
    rev = {v: h for h, v in g.QURAN_VALUES.items() if v and h not in ("wrong_location", "not_quran")}
    ids = [k["item_id"] for k in key]

    def verdict(k):
        if k["item_id"] == ids[0]:
            return {"review_status": "pending"}
        if k["item_id"] == ids[1]:
            return _approved("cannot_determine")
        return _approved(rev[auto[(k["run_id"], k["case_id"], k["citation_index"])]])  # اتفاق تام اصطناعي

    g.write_json(tmp_path / "quran/labels.json", _quran_labels(key, verdict))
    g.cmd_lock("quran", tmp_path)
    res = g.cmd_compute("quran", ROOT, tmp_path)
    by = res["by_automated_verdict"]
    assert sum(v["of"] for v in by.values()) == 29 and all(v["agree"] == v["of"] for v in by.values())
    assert res["n_pending"] == 1 and res["n_cannot_determine_excluded"] == 1
    assert sum(sum(r.values()) for r in res["confusion_matrix_counts"]["rows_automated_cols_human"].values()) == 29
    assert res["counts"]["n_items"] == 31 and res["disagreements"] == []
    assert all(v["unique_groups"] <= v["of"] for v in by.values())
    text = (tmp_path / "quran/agreement.json").read_text(encoding="utf-8")
    for bad in ("%", "دقة مِعيار", "صفر أخطاء", "مراجعة شرعية متخصصة"):
        assert bad not in text
    assert "ليس مراجعة شرعية" in res["scope"]
    if any(k["case_id"] == "OFF-03" and k["item_id"] not in ids[:2] and auto[(k["run_id"], k["case_id"], k["citation_index"])] == "wrong_or_missing" for k in key):
        assert g.OFF03_NOTE in res["notes"]
    assert (GOLD / g.SUMS_NAME).read_text(encoding="utf-8") == g.official_sums()


def test_quran_compute_records_disagreement_without_changing_official(tmp_path):
    key = _setup(tmp_path, "quran")
    g.write_json(tmp_path / "quran/labels.json", _quran_labels(key, lambda k: _approved("matches_at_location")))
    g.cmd_lock("quran", tmp_path)
    res = g.cmd_compute("quran", ROOT, tmp_path)
    by = res["by_automated_verdict"]
    assert by["supported"] == {"agree": 20, "of": 20, "unique_groups_all_agree": by["supported"]["unique_groups"],
                               "unique_groups": by["supported"]["unique_groups"]}
    assert by["wrong_or_missing"]["agree"] == 0 and by["wrong_or_missing"]["of"] == 3
    assert len(res["disagreements"]) == 11
    assert (GOLD / g.SUMS_NAME).read_text(encoding="utf-8") == g.official_sums()


def test_behaviour_compute_excludes_referrals(tmp_path):
    key = _setup(tmp_path, "behaviour")
    sheet = {s["item_id"]: s for s in _read(tmp_path / "behaviour/sheet_blind.json")["items"]}
    labels = {"reviewer": {"reviewer_id": "synthetic", "reviewer_type": "related_sharia_background",
                           "description": "اختبار"},
              "labels": [{"item_id": k["item_id"], "review_status": "approved", "reviewed_at": "2026-10-06T00:00+03:00",
                          "checks": {c["name"]: "pass" for c in sheet[k["item_id"]]["checks"]}} for k in key]}
    g.write_json(tmp_path / "behaviour/labels.json", labels)
    g.cmd_lock("behaviour", tmp_path)
    res = g.cmd_compute("behaviour", ROOT, tmp_path)
    referred = sum(1 for k in key if g._automated_checks(g.load_runs())[(k["run_id"], k["case_id"])].get("needs_human_review"))
    assert res["n_referred_no_automated_verdict"] == referred == 5
    assert "غير مستقل" in res["scope"] and "%" not in json.dumps(res, ensure_ascii=False)
