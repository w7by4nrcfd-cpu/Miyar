"""Benefit Benchmark v2: تسجيل مسبق جديد، وعناصر لا تتقاطع مع v1، وتوثيق مصدر الأداة، وقفل يرفض أي أداة أو إقرار غير مطابق.

لا بيانات قياس حقيقية: اختبارات القفل والحساب ببيانات خام اصطناعية في مجلد مؤقت.
"""

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import benefit_benchmark as v1  # noqa: E402
import benefit_benchmark_v2 as v2  # noqa: E402

OUT = ROOT / "evaluation" / "benefit_v2"


def _read(p):
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def key():
    return json.loads(v2.cmd_verify())


def _payload(r):
    html = (OUT / "tool" / f"review_{r}.html").read_text(encoding="utf-8")
    literal = html.split("const PAYLOAD = ", 1)[1].split(";\nconst DATA", 1)[0]
    return json.loads(literal)


# ---------- التسجيل المسبق ----------
def test_preregistration_holds(key):
    pre = _read(OUT / v2.PREREG)
    assert pre["seed"] == v2.SEED != v1.SEED and pre["tool_version"] == v2.TOOL_VERSION
    assert set(pre["files_sha256"]) == set(v2.PREREG_INPUTS) and set(pre["code_sha256"]) == set(v2.CODE_INPUTS)
    for d in ("evaluation/official/", "evaluation/gold/", "evaluation/benefit/"):
        assert any(k.startswith(d) for k in pre["protected_sha256"]), d
    assert "evaluation/benefit/raw_r1.json" in pre["protected_sha256"]  # سجل v1 محمي كما هو
    assert v1.sha256_bytes(v1.dumps(key).encode()) == pre["key_sha256"]
    assert not (OUT / "key.json").exists() or any((OUT / f"LOCK_{r}.json").exists() for r in v2.REVIEWERS)
    with pytest.raises(SystemExit):
        v2.cmd_build()


@pytest.mark.parametrize("r", list(v2.REVIEWERS))
def test_payload_hash_registered_and_embedded(r):
    p = _payload(r)
    assert v1.sha256_bytes(p.encode("utf-8")) == _read(OUT / v2.PREREG)["payload_sha256"][r]
    data = json.loads(p)
    assert data["reviewer"] == r and data["reviewer_info"] == v2.REVIEWERS[r]
    assert data["reviewer_info"]["reviewer_type"] == "independent_textual"
    assert data["attestations"] == v2.ATTESTATIONS and data["tool_version"] == v2.TOOL_VERSION
    html = (OUT / "tool" / f"review_{r}.html").read_text(encoding="utf-8")
    assert "owner_nonindependent" not in html and "Gold Set" not in html
    for bad in ("original_fragment", "expected_verdict", "source_ref", "is_altered_text"):
        assert bad not in html
    for s in data["sequence"]:
        assert ("miyar" in s) == (s["condition"] == "B")


# ---------- العناصر والتوزيع ----------
def test_items_new_and_balanced(key):
    k1 = _read(ROOT / "evaluation" / "benefit" / "key.json")
    v1_refs = {i["source_ref"] for i in k1["items"]} | {i["stated_location"] for i in k1["items"] if i["stated_location"]}
    banned = v2.v1_locations() | v1.excluded_locations()
    for it in key["items"]:
        assert it["source_ref"] not in v1_refs
        assert tuple(map(int, it["source_ref"].split(":"))) not in banned
    assert not {i["original_fragment"] for i in key["items"]} & {i["original_fragment"] for i in k1["items"]}
    a = _read(OUT / "assignment.json")
    types = {i["item_id"]: i["type"] for i in key["items"]}
    for s in ("S1", "S2"):
        assert Counter(types[i] for i in a["set_items"][s]) == Counter(v1.HALF_1 + v1.HALF_2)
    for r in v2.REVIEWERS:
        order = a["order"][r]
        assert len({o["item_id"] for o in order}) == 28
        main = [o for o in order if not o["warmup"]]
        assert [o["condition"] for o in main] == ["A"] * 6 + ["B"] * 12 + ["A"] * 6
    c1 = {o["item_id"]: o["condition"] for o in a["order"]["ind1"]}
    c2 = {o["item_id"]: o["condition"] for o in a["order"]["ind2"]}
    assert all(c1[i] != c2[i] for i in c1)


def test_miyar_outputs_real(key):
    q = v1.load_quran()
    out = _read(OUT / "miyar_outputs.json")["items"]
    blind = {i["item_id"]: i for i in _read(OUT / "items_blind.json")["items"]}
    for it in key["items"]:
        loc = it["stated_location"]
        s, a = (map(int, loc.split(":")) if loc else (None, None))
        j = v1.judge_citation(v1.Citation("quran", blind[it["item_id"]]["quote"], blind[it["item_id"]]["cited_as_written"], s, a), q)
        assert (out[it["item_id"]]["status"], out[it["item_id"]]["reason"]) == (j.status, j.reason)


# ---------- توثيق الملف المقدَّم ----------
HEAD = '<!doctype html><html><head><meta charset=utf8><style>:root{color-scheme:light}</style></head><body>\n'


def test_check_served_accepts_only_known_wrapper():
    tool = (OUT / "tool" / "review_ind1.html").read_bytes()
    good = HEAD.encode() + tool + v2.WRAP_TAIL.encode()
    v2.check_served(good, tool)
    altered = tool.replace("تنبيه".encode(), "تنبيـه".encode(), 1)
    assert altered != tool
    for bad in (HEAD.encode() + altered + v2.WRAP_TAIL.encode(),  # محتوى مختلف
                HEAD.replace("<body>", "<script>x()</script><body>").encode() + tool + v2.WRAP_TAIL.encode(),  # سكربت في الغلاف
                HEAD.encode() + tool + b"<script>x()</script>" + v2.WRAP_TAIL.encode()):  # زيادة بعد الأداة
        with pytest.raises(ValueError):
            v2.check_served(bad, tool)


# ---------- القفل والحساب (اصطناعي) ----------
def _tmp(tmp_path):
    d = tmp_path / "benefit_v2"
    shutil.copytree(OUT, d)
    for p in [*d.glob("raw_*"), *d.glob("LOCK_*"), *d.glob("results_*"), *d.glob("provenance_*"), d / "key.json"]:
        p.unlink(missing_ok=True)
    return d


def _provenance(d, r="ind1"):
    tool = (d / "tool" / f"review_{r}.html").read_bytes()
    served = d / "served.html"
    served.write_bytes(HEAD.encode() + tool + v2.WRAP_TAIL.encode())
    return v2.cmd_provenance(r, str(served), "https://claude.ai/artifact/example", "v-test", d)


def _raw(d, key, r="ind1", **over):
    a = _read(d / "assignment.json")
    exp = {i["item_id"]: i["expected_verdict"] for i in key["items"]}
    recs, t = [], 1_000_000
    for o in a["order"][r]:
        dur = 40_000 if o["condition"] == "A" else 20_000
        recs.append({**{k: o[k] for k in ("position", "item_id", "condition", "block", "warmup")}, "started_at_ms": t,
                     "submitted_at_ms": t + dur, "duration_ms": dur, "human_verdict": exp[o["item_id"]], "notes": "",
                     "interrupted": False})
        t += dur + 1000
    raw = {"tool_version": v2.TOOL_VERSION, "reviewer": r, "reviewer_info": a["reviewers"][r],
           "assignment_sha256": v1.sha256_bytes(v1.dumps(a).encode()),
           "payload_sha256": _read(d / v2.PREREG)["payload_sha256"][r],
           "attestation": {"accepted": True, "statements": v2.ATTESTATIONS, "accepted_at": "x"}, "records": recs} | over
    (d / f"raw_{r}.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


def test_lock_requires_provenance(tmp_path, key):
    d = _tmp(tmp_path)
    _raw(d, key)
    with pytest.raises(SystemExit):
        v2.cmd_lock("ind1", d)


def test_end_to_end_synthetic(tmp_path, key):
    d = _tmp(tmp_path)
    prov = _provenance(d)
    assert prov["tool_sha256"] == _read(d / v2.PREREG)["files_sha256"]["tool/review_ind1.html"]
    _raw(d, key)
    v2.cmd_lock("ind1", d)
    v2.cmd_reveal_key(d)
    res = v2.cmd_compute("ind1", d)
    assert res["by_condition"]["A"]["median_seconds"] == 40.0 and res["by_condition"]["B"]["median_seconds"] == 20.0
    assert res["preregistered_interpretation"] == "positive" and res["reviewer"]["reviewer_type"] == "independent_textual"
    assert "%" not in (d / "results_ind1.json").read_text(encoding="utf-8")


@pytest.mark.parametrize("over", [
    {"payload_sha256": "0" * 64},  # أداة غير المسجّلة
    {"attestation": None},  # بلا إقرار
    {"attestation": {"accepted": True, "statements": ["x"]}},  # إقرار مختلف
    {"reviewer_info": {"reviewer_type": "owner_nonindependent", "description": "x"}},  # وصف لا يطابق التوزيع
    {"tool_version": "benefit-tool-v1"},
])
def test_lock_rejects_bad_raw(tmp_path, key, over):
    d = _tmp(tmp_path)
    _provenance(d)
    _raw(d, key, **over)
    with pytest.raises(ValueError):
        v2.cmd_lock("ind1", d)
    assert not (d / "LOCK_ind1.json").exists()


def test_compute_refuses_if_provenance_changes_after_lock(tmp_path, key):
    d = _tmp(tmp_path)
    _provenance(d)
    _raw(d, key)
    v2.cmd_lock("ind1", d)
    v2.cmd_reveal_key(d)
    p = d / "provenance_ind1.json"
    p.write_text(p.read_text(encoding="utf-8").replace("v-test", "v-other"), encoding="utf-8")
    with pytest.raises(SystemExit):
        v2.cmd_compute("ind1", d)


def test_v1_audit_record_untouched():
    v1.cmd_verify()  # بصمات v1 المسجّلة ما زالت مطابقة
    assert (ROOT / "evaluation" / "benefit" / "DEVIATIONS.md").exists()


def test_nothing_published_on_site():
    for p in (ROOT / "web").rglob("*"):
        if p.is_file() and p.suffix in (".html", ".js", ".json"):
            t = p.read_text(encoding="utf-8", errors="ignore")
            assert "benefit" not in t.lower() and "مقطع معدل عمداً" not in t, p
