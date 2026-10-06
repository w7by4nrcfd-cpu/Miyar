"""Benefit Benchmark v2: إعادة تسجيل مسبق بعناصر وبذرة ومفتاح جديدة، ومراجع مستقل، وتوثيق مصدر الأداة.

يُبنى فوق دوال v1 (scripts/benefit_benchmark.py) دون تعديل ملفها المسجّل في v1. الفروق (evaluation/benefit_v2/PROTOCOL.md):
- بذرة جديدة، وتُستبعد مواضع عناصر v1 وجيرانها مع المواضع الرسمية.
- الأداة تحسب وقت التشغيل SHA-256 لبيانات العرض نفسها (payload) وتصدّرها مع البيانات الخام؛ ويرفض القفل أي بصمة لا تطابق المسجّلة.
- وصف المراجع من التوزيع لا ثابت في الأداة، وإقرار إلزامي قبل البدء (لا اطلاع مسبق، ولا أدوات خارجية).
- توثيق الملف المقدَّم للمراجع (provenance) قبل الجلسة: الملف المسجّل داخل غلاف المنصة بايتاً ببايت.

    python scripts/benefit_benchmark_v2.py build
    python scripts/benefit_benchmark_v2.py verify
    python scripts/benefit_benchmark_v2.py provenance ind1 <served.html> <artifact_url> <version_id>   # قبل الجلسة
    python scripts/benefit_benchmark_v2.py lock ind1
    python scripts/benefit_benchmark_v2.py reveal-key
    python scripts/benefit_benchmark_v2.py compute ind1
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import benefit_benchmark as v1  # noqa: E402

OUT = ROOT / "evaluation" / "benefit_v2"
SEED = "miyar-benefit-v2-2026-10-06"
TOOL_VERSION = "benefit-tool-v2"
REVIEWERS = {
    "ind1": {"reviewer_type": "independent_textual",
             "description": "مراجع مستقل: لا صلة له بالمشروع، ولم يرَ المستودع ولا المفتاح ولا إجابات جلسة سابقة؛ تحقق نصي لا مراجعة شرعية"},
    "ind2": {"reviewer_type": "independent_textual",
             "description": "مراجع مستقل ثانٍ (اختياري) بتوزيع معكوس؛ الشروط نفسها؛ تحقق نصي لا مراجعة شرعية"},
}
ATTESTATIONS = [
    "لم أطّلع على مستودع مِعيار، ولا على أي مفتاح أو إجابات أو نتائج لهذه التجربة أو لتجربة سابقة.",
    "لن أستعين أثناء الجلسة بأي أداة ذكاء اصطناعي (مثل ChatGPT) ولا بشخص آخر. المسموح: المصحف أو quran.com، وأدلة مِعيار في كتل «بمساعدة مِعيار» فقط.",
    "أفهم أن بعض العناصر مقاطع معدلة عمداً لأغراض الاختبار، وأنها ليست نصوصاً قرآنية صحيحة.",
]
# القيم نفسها كما في v1، بصياغة أوضح لخيارَي الموضع (في الجلسة الاستطلاعية r1 خُلط «موضع خاطئ» بـ«بلا موضع» مرتين).
VERDICTS = {
    "matches_at_location": "مطابق لنص المصحف عند الموضع المذكور (السورة ورقم الآية صحيحان)",
    "matches_no_location": "مطابق لنص المصحف، لكن لم يُذكر رقم آية (ذُكرت السورة وحدها أو لا شيء)",
    "differs": "يختلف عن نص المصحف (حرف أو كلمة)",
    "wrong_location": "نص قرآني صحيح، لكن رقم الآية أو السورة المذكور خطأ",
    "not_quran": "ليس نصاً قرآنياً",
    "cannot_determine": "لا أستطيع الحكم",
}
assert set(VERDICTS) == set(v1.VERDICTS)
PREREG = "PREREGISTRATION.json"
WRAP_HEAD_END = "<body>\n"  # غلاف منصة الصفحات: هيكل ثابت ينتهي بهذا، ثم الملف المسجّل، ثم الذيل
WRAP_TAIL = "\n</body></html>"


def v1_locations() -> set[tuple[int, int]]:
    """مواضع عناصر v1 (المصدر والموضع المنسوب) وجيرانها: لا تُعاد في v2."""
    key = json.loads((ROOT / "evaluation" / "benefit" / "key.json").read_text(encoding="utf-8"))
    out = set()
    for it in key["items"]:
        for ref in (it["source_ref"], it["stated_location"]):
            if ref:
                s, a = map(int, ref.split(":"))
                out |= {(s, x) for x in range(a - v1.NEIGHBOUR, a + v1.NEIGHBOUR + 1)}
    return out


def generate(quran) -> dict:
    rng = random.Random(SEED)
    excluded = v1.excluded_locations(ROOT) | v1_locations()
    used: set = set()
    sets = {s: [[v1.make_item(rng, quran, k, used, excluded) for k in v1.HALF_1],
                [v1.make_item(rng, quran, k, used, excluded) for k in v1.HALF_2]] for s in ("S1", "S2")}
    warm = {s: [v1.make_item(rng, quran, k, used, excluded) for k in v1.WARMUP_TYPES] for s in ("W1", "W2")}
    a_set = rng.choice(["S1", "S2"])
    b_set = "S2" if a_set == "S1" else "S1"
    for s in sets.values():
        for half in s:
            rng.shuffle(half)

    def seq_for(a, b, wa, wb):
        return ([(warm[wa][i], "A", 0, True) for i in range(2)] + [(x, "A", 1, False) for x in sets[a][0]]
                + [(warm[wb][i], "B", 2, True) for i in range(2)] + [(x, "B", 2, False) for x in sets[b][0]]
                + [(x, "B", 3, False) for x in sets[b][1]] + [(x, "A", 4, False) for x in sets[a][1]])

    s1 = seq_for(a_set, b_set, "W1", "W2")
    ids, nw, nt = {}, 0, 0
    for item, _, _, warmup in s1:
        if warmup:
            nw += 1
            ids[id(item)] = f"V2-W{nw}"
        else:
            nt += 1
            ids[id(item)] = f"V2-T{nt:02d}"
    s2 = seq_for(b_set, a_set, "W2", "W1")

    def order(seq):
        return [{"position": p, "item_id": ids[id(it)], "condition": c, "block": blk, "warmup": w}
                for p, (it, c, blk, w) in enumerate(seq, 1)]

    items = sorted((it for it, *_ in s1), key=lambda x: ids[id(x)])
    outputs = {}
    for it in items:
        j = v1.judge_citation(v1.Citation("quran", it["blind"]["quote"], it["blind"]["cited_as_written"],
                                          it["citation"]["sura"] if it["citation"]["aya"] else None, it["citation"]["aya"]), quran)
        outputs[ids[id(it)]] = {"status": j.status, "reason": j.reason, "matched_ref": j.matched_ref,
                                "matched_text": j.matched_text, "suggestion": (j.detail.get("suggestions") or [None])[0]}
    return {
        "items_blind": {"notice": v1.STIMULUS_NOTICE, "items": [{"item_id": ids[id(it)], **it["blind"]} for it in items]},
        "key": {"seed": SEED, "items": [{"item_id": ids[id(it)], **it["key"]} for it in items]},
        "miyar_outputs": {"note": "مخرجات judge_citation الحقيقية (مطابقة برمجية بلا نموذج لغوي) لكل عنصر", "items": outputs},
        "assignment": {
            "seed": SEED,
            "design": "ABBA كما في v1؛ قبل أول كتلة من كل حالة عنصرا إحماء لا يُحتسبان",
            "condition_labels": {"A": "Manual-only (يدوي)", "B": "Miyar-assisted (بمساعدة مِعيار)"},
            "reviewers": REVIEWERS,
            "sets": {"ind1": {"A": a_set, "B": b_set}, "ind2": {"A": b_set, "B": a_set}},
            "set_items": {s: [ids[id(x)] for half in sets[s] for x in half] for s in ("S1", "S2")},
            "order": {"ind1": order(s1), "ind2": order(s2)},
        },
    }


def payload_str(reviewer: str, blind: dict, outputs: dict, assignment: dict) -> str:
    """بيانات العرض كما تُضمَّن في الأداة حرفياً؛ بصمتها تُسجَّل مسبقاً وتُحسب في المتصفح وقت التشغيل."""
    by_id = {i["item_id"]: i for i in blind["items"]}
    seq = []
    for o in assignment["order"][reviewer]:
        it = by_id[o["item_id"]]
        e = {**o, "quote": it["quote"], "cited_as_written": it["cited_as_written"]}
        if o["condition"] == "B":
            m = outputs["items"][o["item_id"]]
            e["miyar"] = {"status": v1.STATUS_AR[m["status"]], "reason": v1.REASON_AR.get(m["reason"], m["reason"]),
                          "matched_ref": m["matched_ref"], "matched_text": m["matched_text"],
                          "suggestion": m["suggestion"] and {"ref": m["suggestion"]["ref"], "text": m["suggestion"].get("text")}}
        seq.append(e)
    data = {"tool_version": TOOL_VERSION, "reviewer": reviewer, "reviewer_info": assignment["reviewers"][reviewer],
            "assignment_sha256": v1.sha256_bytes(v1.dumps(assignment).encode()), "notice": blind["notice"],
            "attestations": ATTESTATIONS, "verdicts": [[k, v] for k, v in VERDICTS.items()], "sequence": seq}
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def tool_html(payload: str, template: str) -> str:
    literal = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return template.replace("__PAYLOAD__", literal)


def build_files(quran) -> dict[str, bytes]:
    g = generate(quran)
    template = (ROOT / "scripts" / "benefit_tool_template_v2.html").read_text(encoding="utf-8")
    files = {"items_blind.json": v1.dumps(g["items_blind"]).encode(), "assignment.json": v1.dumps(g["assignment"]).encode(),
             "miyar_outputs.json": v1.dumps(g["miyar_outputs"]).encode()}
    payloads = {}
    for r in REVIEWERS:
        p = payload_str(r, g["items_blind"], g["miyar_outputs"], g["assignment"])
        payloads[r] = v1.sha256_bytes(p.encode("utf-8"))
        files[f"tool/review_{r}.html"] = tool_html(p, template).encode()
    return files | {"__key__": v1.dumps(g["key"]).encode(), "__payloads__": json.dumps(payloads).encode()}


PREREG_INPUTS = ["PROTOCOL.md", "items_blind.json", "assignment.json", "miyar_outputs.json",
                 "tool/review_ind1.html", "tool/review_ind2.html"]
CODE_INPUTS = ["scripts/benefit_benchmark_v2.py", "scripts/benefit_tool_template_v2.html", "scripts/benefit_benchmark.py"]


def protected_sums() -> dict[str, str]:
    files = [p for d in ("evaluation/official", "evaluation/gold", "evaluation/benefit") for p in sorted((ROOT / d).rglob("*"))]
    return {p.relative_to(ROOT).as_posix(): v1.sha256(p) for p in files
            if p.is_file() and p.name not in ("README.md", "DEVIATIONS.md")}


def cmd_build(out: Path = OUT) -> dict:
    if (out / PREREG).exists():
        raise SystemExit("v2 مسجّلة مسبقاً؛ لا يُعاد البناء.")
    files = build_files(v1.load_quran())
    key, payloads = files.pop("__key__"), json.loads(files.pop("__payloads__"))
    for rel, b in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(b)
    prereg = {"registered_at": v1.riyadh_now(), "seed": SEED, "tool_version": TOOL_VERSION,
              "key_sha256": v1.sha256_bytes(key), "payload_sha256": payloads,
              "files_sha256": {rel: v1.sha256(out / rel) for rel in PREREG_INPUTS},
              "code_sha256": {rel: v1.sha256(ROOT / rel) for rel in CODE_INPUTS},
              "protected_sha256": protected_sums(),
              "note": "المفتاح لا يُرفع قبل قفل البيانات الخام؛ يُعاد توليده حتمياً من البذرة ويطابق key_sha256."}
    (out / PREREG).write_text(v1.dumps(prereg), encoding="utf-8")
    return prereg


def cmd_verify(out: Path = OUT) -> bytes:
    pre = json.loads((out / PREREG).read_text(encoding="utf-8"))
    for rel, h in pre["files_sha256"].items():
        if v1.sha256(out / rel) != h:
            raise SystemExit(f"تغيّر ملف مسجّل مسبقاً: {rel}")
    for rel, h in pre["code_sha256"].items():
        if v1.sha256(ROOT / rel) != h:
            raise SystemExit(f"تغيّر كود مسجّل مسبقاً: {rel}")
    if protected_sums() != pre["protected_sha256"]:
        raise SystemExit("تغيّرت السجلات الرسمية أو Gold Set أو سجل v1.")
    files = build_files(v1.load_quran())
    key, payloads = files.pop("__key__"), json.loads(files.pop("__payloads__"))
    if v1.sha256_bytes(key) != pre["key_sha256"] or payloads != pre["payload_sha256"]:
        raise SystemExit("المفتاح أو بصمات بيانات العرض المُعاد توليدها لا تطابق المسجّلة.")
    for rel, b in files.items():
        if (out / rel).read_bytes() != b:
            raise SystemExit(f"الملف لا يطابق إعادة التوليد: {rel}")
    return key


# ---------------- توثيق الملف المقدَّم قبل الجلسة ----------------
def check_served(served: bytes, tool: bytes) -> None:
    """الملف المقدَّم = غلاف المنصة + الأداة المسجّلة بايتاً ببايت + ذيل الغلاف، ولا شيء غير ذلك."""
    s = served.decode("utf-8")
    t = tool.decode("utf-8")
    i = s.find(t)
    if i < 0 or s.find(t, i + 1) >= 0:
        raise ValueError("الأداة المسجّلة غير موجودة مرة واحدة بايتاً ببايت داخل الملف المقدَّم")
    head, tail = s[:i], s[i + len(t):]
    if not head.startswith("<!doctype html>") or not head.endswith(WRAP_HEAD_END) or "<script" in head.lower() \
            or tail != WRAP_TAIL:
        raise ValueError("ما حول الأداة في الملف المقدَّم ليس غلاف المنصة المعروف")


def cmd_provenance(reviewer: str, served_path: str, url: str, version_id: str, out: Path = OUT) -> dict:
    cmd_verify(out)
    path = out / f"provenance_{reviewer}.json"
    if path.exists():
        raise SystemExit("توثيق المصدر لهذا المراجع مسجّل مسبقاً.")
    served = Path(served_path).read_bytes()
    tool = (out / "tool" / f"review_{reviewer}.html").read_bytes()
    check_served(served, tool)
    info = {"reviewer": reviewer, "artifact_url": url, "artifact_version_id": version_id,
            "served_sha256": v1.sha256_bytes(served), "served_bytes": len(served),
            "tool_sha256": v1.sha256_bytes(tool), "wrapper_bytes": len(served) - len(tool),
            "payload_sha256": json.loads((out / PREREG).read_text(encoding="utf-8"))["payload_sha256"][reviewer],
            "verified_at": v1.riyadh_now()}
    path.write_text(v1.dumps(info), encoding="utf-8")
    return info


# ---------------- بعد الجلسة ----------------
def validate_raw(raw: dict, pre: dict, prov: dict, assignment: dict, reviewer: str) -> None:
    if raw.get("tool_version") != TOOL_VERSION or raw.get("reviewer") != reviewer:
        raise ValueError("البيانات الخام ليست من أداة v2 لهذا المراجع")
    if raw.get("payload_sha256") != pre["payload_sha256"][reviewer] or raw.get("payload_sha256") != prov["payload_sha256"]:
        raise ValueError("بصمة بيانات العرض المحسوبة في المتصفح لا تطابق المسجّلة: الأداة المستخدمة ليست المسجّلة")
    if raw.get("reviewer_info") != assignment["reviewers"][reviewer]:
        raise ValueError("وصف المراجع لا يطابق التوزيع")
    att = raw.get("attestation") or {}
    if att.get("accepted") is not True or att.get("statements") != ATTESTATIONS:
        raise ValueError("الإقرار قبل الجلسة غير موجود أو مختلف")
    v1.validate_raw({**raw, "build": v1.sha256_bytes(v1.dumps(assignment).encode())}, assignment, reviewer)


def cmd_lock(reviewer: str, out: Path = OUT) -> dict:
    cmd_verify(out)
    lock = out / f"LOCK_{reviewer}.json"
    if lock.exists():
        raise SystemExit("البيانات الخام مقفلة مسبقاً.")
    prov_path = out / f"provenance_{reviewer}.json"
    if not prov_path.exists():
        raise SystemExit("لا قفل دون توثيق مصدر مسجّل قبل الجلسة.")
    raw = json.loads((out / f"raw_{reviewer}.json").read_text(encoding="utf-8"))
    validate_raw(raw, json.loads((out / PREREG).read_text(encoding="utf-8")), json.loads(prov_path.read_text(encoding="utf-8")),
                 json.loads((out / "assignment.json").read_text(encoding="utf-8")), reviewer)
    info = {"raw_sha256": v1.sha256(out / f"raw_{reviewer}.json"), "provenance_sha256": v1.sha256(prov_path),
            "locked_at": v1.riyadh_now(), "n_records": len(raw["records"])}
    lock.write_text(v1.dumps(info), encoding="utf-8")
    return info


def cmd_reveal_key(out: Path = OUT) -> None:
    if not any((out / f"LOCK_{r}.json").exists() for r in REVIEWERS):
        raise SystemExit("لا يُكشف المفتاح قبل قفل بيانات خام.")
    key = cmd_verify(out)
    path = out / "key.json"
    if path.exists() and path.read_bytes() != key:
        raise SystemExit("key.json الموجود لا يطابق المفتاح المسجّل.")
    path.write_bytes(key)


def cmd_compute(reviewer: str, out: Path = OUT) -> dict:
    lock = out / f"LOCK_{reviewer}.json"
    if not lock.exists() or not (out / "key.json").exists():
        raise SystemExit("لا حساب قبل قفل البيانات الخام وكشف المفتاح.")
    key = cmd_verify(out)
    if (out / "key.json").read_bytes() != key:
        raise SystemExit("key.json لا يطابق المفتاح المسجّل.")
    lk = json.loads(lock.read_text(encoding="utf-8"))
    if v1.sha256(out / f"raw_{reviewer}.json") != lk["raw_sha256"] or v1.sha256(out / f"provenance_{reviewer}.json") != lk["provenance_sha256"]:
        raise SystemExit("البيانات الخام أو توثيق المصدر تغيّرا بعد القفل.")
    raw = json.loads((out / f"raw_{reviewer}.json").read_text(encoding="utf-8"))
    res = v1.compute(raw, json.loads(key), json.loads((out / "miyar_outputs.json").read_text(encoding="utf-8")))
    res |= {"reviewer": raw["reviewer_info"], "tool_version": TOOL_VERSION, "computed_at": v1.riyadh_now()}
    (out / f"results_{reviewer}.json").write_text(v1.dumps(res), encoding="utf-8")
    return res


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["build", "verify", "provenance", "lock", "reveal-key", "compute"])
    p.add_argument("args", nargs="*")
    a = p.parse_args(argv)
    if a.command == "build":
        print(json.dumps(cmd_build(), ensure_ascii=False, indent=1))
    elif a.command == "verify":
        cmd_verify()
        print("كل بصمات v2 المسجّلة مسبقاً مطابقة، والمفتاح وبيانات العرض المُعاد توليدها تطابق بصماتها.")
    elif a.command == "reveal-key":
        cmd_reveal_key()
    elif a.command == "provenance":
        print(json.dumps(cmd_provenance(*a.args), ensure_ascii=False, indent=1))
    elif a.command == "lock":
        print(cmd_lock(*a.args))
    else:
        print(json.dumps(cmd_compute(*a.args), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
