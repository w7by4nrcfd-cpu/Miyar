"""Benefit Benchmark: التسجيل المسبق مقفل، والتوزيع حتمي، والعناصر مخفية، والمفتاح بالإنشاء، والحساب لا يعمل قبل القفل.

لا بيانات قياس حقيقية هنا: اختبارات الحساب كلها ببيانات خام اصطناعية في مجلد مؤقت.
"""

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import benefit_benchmark as b  # noqa: E402

BEN = ROOT / "evaluation" / "benefit"


def _read(p):
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def quran():
    return b.load_quran()


@pytest.fixture(scope="module")
def key():
    return json.loads(b.cmd_verify())  # يتحقق من كل البصمات ويعيد المفتاح المُعاد توليده


# ---------- التسجيل المسبق ----------
def test_preregistration_hashes_hold(key):
    pre = _read(BEN / b.PREREG)
    assert pre["seed"] == b.SEED
    assert set(pre["files_sha256"]) == set(b.PREREG_INPUTS)
    assert set(pre["code_sha256"]) == set(b.CODE_INPUTS)
    assert any(k.startswith("evaluation/official/") for k in pre["protected_sha256"])
    assert any(k.startswith("evaluation/gold/") for k in pre["protected_sha256"])
    assert b.sha256_bytes(b.dumps(key).encode()) == pre["key_sha256"]


def test_key_not_published_before_raw_lock():
    locked = any((BEN / f"LOCK_{r}.json").exists() for r in b.REVIEWERS)
    assert locked or not (BEN / "key.json").exists(), "المفتاح لا يُرفع قبل قفل البيانات الخام"


def test_build_refuses_to_overwrite():
    with pytest.raises(SystemExit):
        b.cmd_build()


# ---------- التوزيع ----------
@pytest.mark.parametrize("r", b.REVIEWERS)
def test_assignment_is_complete_and_abba(r):
    a = _read(BEN / "assignment.json")
    order = a["order"][r]
    ids = [o["item_id"] for o in order]
    assert len(ids) == 28 and len(set(ids)) == 28  # كل عنصر مرة واحدة
    assert [o["position"] for o in order] == list(range(1, 29))
    main = [o for o in order if not o["warmup"]]
    assert Counter(o["condition"] for o in main) == {"A": 12, "B": 12}
    assert Counter(o["condition"] for o in order if o["warmup"]) == {"A": 2, "B": 2}
    assert [o["condition"] for o in main] == ["A"] * 6 + ["B"] * 12 + ["A"] * 6  # ABBA
    assert {o["item_id"] for o in main if o["condition"] == "A"} == set(a["set_items"][a["sets"][r]["A"]])


def test_reviewer2_reverses_conditions():
    a = _read(BEN / "assignment.json")
    c1 = {o["item_id"]: o["condition"] for o in a["order"]["r1"]}
    c2 = {o["item_id"]: o["condition"] for o in a["order"]["r2"]}
    assert set(c1) == set(c2) and all(c1[i] != c2[i] for i in c1)


def test_sets_are_balanced(key):
    a = _read(BEN / "assignment.json")
    types = {i["item_id"]: i["type"] for i in key["items"]}
    want = Counter(b.HALF_1 + b.HALF_2)
    for s in ("S1", "S2"):
        assert Counter(types[i] for i in a["set_items"][s]) == want
    assert sum(1 for t in want.elements() if t != "match") == 6


# ---------- الإخفاء والتنبيه ----------
def test_blind_items_hide_key():
    blind = _read(BEN / "items_blind.json")
    assert blind["notice"] == b.STIMULUS_NOTICE and "مقطع معدل عمداً لأغراض الاختبار" in blind["notice"]
    for it in blind["items"]:
        assert set(it) == {"item_id", "quote", "cited_as_written"}


@pytest.mark.parametrize("r", b.REVIEWERS)
def test_tool_has_only_condition_b_evidence_and_no_key(r, key):
    html = (BEN / "tool" / f"review_{r}.html").read_text(encoding="utf-8")
    data = json.loads(html.split("const DATA = ", 1)[1].split(";\nconst KEY", 1)[0].replace("<\\/", "</"))
    assert data["reviewer"] == r and data["notice"] == b.STIMULUS_NOTICE
    a = _read(BEN / "assignment.json")
    assert [s["item_id"] for s in data["sequence"]] == [o["item_id"] for o in a["order"][r]]
    for s in data["sequence"]:
        assert ("miyar" in s) == (s["condition"] == "B")
    for bad in ("original_fragment", "expected_verdict", "source_ref", "letter_sub", "word_drop", "is_altered_text"):
        assert bad not in html


def test_nothing_published_on_site():
    for p in (ROOT / "web").rglob("*"):
        if p.is_file() and p.suffix in (".html", ".js", ".json"):
            t = p.read_text(encoding="utf-8", errors="ignore")
            assert "benefit" not in t.lower() and "مقطع معدل عمداً" not in t, p


# ---------- المفتاح بالإنشاء ----------
def test_key_items_are_constructed_as_labelled(key, quran):
    excluded = b.excluded_locations()
    for it in key["items"]:
        s, a = map(int, it["source_ref"].split(":"))
        assert (s, a) not in excluded
        locs = quran.find(it["original_fragment"])
        assert [(l.sura, l.aya_start, l.aya_end) for l in locs] == [(s, a, a)]
        assert it["expected_verdict"] == b.EXPECTED[it["type"]]
        assert (it["label"] == b.ALTERED_LABEL) == it["is_altered_text"]
    blind = {i["item_id"]: i for i in _read(BEN / "items_blind.json")["items"]}
    for it in key["items"]:
        shown = blind[it["item_id"]]["quote"][1:-1]
        if it["is_altered_text"]:
            assert not quran.find(shown, min_tokens=2), it["item_id"]
            assert b.normalize(shown) != b.normalize(it["original_fragment"])
        else:
            assert shown == it["original_fragment"]
        if it["type"] == "wrong_location":
            assert it["stated_location"] != it["source_ref"]
        if it["type"] == "no_location":
            assert not any(ch.isdigit() for ch in blind[it["item_id"]]["cited_as_written"])


def test_miyar_outputs_are_real_judge_outputs(key, quran):
    """مخرجات الحالة B هي judge_citation نفسها على العناصر، بلا تعديل."""
    out = _read(BEN / "miyar_outputs.json")["items"]
    blind = {i["item_id"]: i for i in _read(BEN / "items_blind.json")["items"]}
    for it in key["items"]:
        loc = it["stated_location"]
        sura, aya = (map(int, loc.split(":")) if loc else (None, None))
        j = b.judge_citation(b.Citation("quran", blind[it["item_id"]]["quote"], blind[it["item_id"]]["cited_as_written"],
                                        sura, aya), quran)
        assert out[it["item_id"]]["status"] == j.status and out[it["item_id"]]["reason"] == j.reason


# ---------- القفل والحساب (اصطناعي) ----------
def _tmp(tmp_path):
    d = tmp_path / "benefit"
    shutil.copytree(BEN, d)
    for p in list(d.glob("raw_*")) + list(d.glob("LOCK_*")) + list(d.glob("results_*")) + [d / "key.json"]:
        p.unlink(missing_ok=True)
    return d


def _raw(d, r, verdict_for, dur_for):
    a = _read(d / "assignment.json")
    recs, t = [], 1_000_000
    for o in a["order"][r]:
        dur = dur_for(o)
        recs.append({**{k: o[k] for k in ("position", "item_id", "condition", "block", "warmup")},
                     "started_at_ms": t, "submitted_at_ms": t + dur, "duration_ms": dur,
                     "human_verdict": verdict_for(o), "notes": "", "interrupted": False})
        t += dur + 5000
    raw = {"reviewer": r, "build": b.sha256_bytes(b.dumps(a).encode()), "reviewer_info": {"reviewer_type": "synthetic"},
           "records": recs}
    (d / f"raw_{r}.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


def test_compute_refuses_before_lock_and_key(tmp_path):
    d = _tmp(tmp_path)
    with pytest.raises(SystemExit):
        b.cmd_reveal_key(ROOT, d)  # لا كشف قبل القفل
    with pytest.raises(SystemExit):
        b.cmd_compute("r1", ROOT, d)


def test_synthetic_session_end_to_end(tmp_path, key):
    d = _tmp(tmp_path)
    exp = {i["item_id"]: i["expected_verdict"] for i in key["items"]}
    _raw(d, "r1", lambda o: exp[o["item_id"]], lambda o: 40_000 if o["condition"] == "A" else 20_000)
    b.cmd_lock("r1", ROOT, d)
    with pytest.raises(SystemExit):
        b.cmd_lock("r1", ROOT, d)  # لا يُعاد القفل
    b.cmd_reveal_key(ROOT, d)
    res = b.cmd_compute("r1", ROOT, d)
    A, B = res["by_condition"]["A"], res["by_condition"]["B"]
    assert A["n_items"] == B["n_items"] == 12  # الإحماء مستبعد
    assert A["median_seconds"] == 40.0 and B["median_seconds"] == 20.0
    assert A["correct"] == B["correct"] == 12 and A["problems_detected"] == A["n_problem_items"] == 6
    assert A["false_alarms"] == 0 and B["disagreed_with_miyar"] == 0
    assert res["preregistered_interpretation"] == "positive"
    assert res["miyar_status_matches_key"] == {"agree": 24, "of": 24}
    assert "%" not in (d / "results_r1.json").read_text(encoding="utf-8")


def test_compute_refuses_if_raw_changes_after_lock(tmp_path, key):
    d = _tmp(tmp_path)
    exp = {i["item_id"]: i["expected_verdict"] for i in key["items"]}
    _raw(d, "r1", lambda o: exp[o["item_id"]], lambda o: 30_000)
    b.cmd_lock("r1", ROOT, d)
    b.cmd_reveal_key(ROOT, d)
    _raw(d, "r1", lambda o: "cannot_determine", lambda o: 30_000)
    with pytest.raises(SystemExit):
        b.cmd_compute("r1", ROOT, d)


@pytest.mark.parametrize("bad", [
    lambda raw: raw["records"].pop(),  # عنصر ناقص
    lambda raw: raw["records"].reverse(),  # ترتيب مختلف
    lambda raw: raw["records"][0].update(condition="B"),  # حالة مختلفة
    lambda raw: raw["records"][0].update(human_verdict="supported"),  # قيمة غير مسموحة
    lambda raw: raw["records"][0].update(duration_ms=1),  # زمن لا يطابق الطابعين
    lambda raw: raw.update(build="x"),  # من أداة أخرى
])
def test_lock_validates_raw(tmp_path, bad):
    d = _tmp(tmp_path)
    _raw(d, "r1", lambda o: "matches_at_location", lambda o: 30_000)
    raw = _read(d / "raw_r1.json")
    bad(raw)
    (d / "raw_r1.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        b.cmd_lock("r1", ROOT, d)
    assert not (d / "LOCK_r1.json").exists()


def test_interpretation_rule():
    cases = [((40, 20, 12, 12, 6, 6), "positive"), ((40, 20, 12, 11, 6, 6), "negative"),
             ((20, 20, 12, 12, 6, 6), "negative"), ((20, 30, 11, 12, 6, 6), "mixed")]
    for (ma, mb, ca, cb, da, db), want in cases:
        a = {"median_seconds": ma, "correct": ca, "problems_detected": da}
        bb = {"median_seconds": mb, "correct": cb, "problems_detected": db}
        assert b.interpret(a, bb) == want
