"""Benefit Benchmark: زمن التحقق النصي من استشهاد قرآني يدوياً مقابل بمساعدة أدلة مِعيار.

تجربة مسجّلة مسبقاً (evaluation/benefit/PROTOCOL.md). لا تستدعي أي نموذج ولا شبكة، ولا تعدّل أي سجل رسمي
ولا Gold Set. العناصر محفزات اختبار يولّدها هذا السكربت ببذرة ثابتة من نص Quranpedia في data/؛ بعضها
**مقطع معدل عمداً لأغراض الاختبار**، ولا يُعرض أي منها في الموقع ولا يُقدَّم نصاً قرآنياً صحيحاً.

    python scripts/benefit_benchmark.py build          # مرة واحدة قبل الجلسة: العناصر والتوزيع ومخرجات مِعيار والأداة والتسجيل المسبق
    python scripts/benefit_benchmark.py verify         # البصمات المسجّلة مسبقاً لم تتغير، والمفتاح المُعاد توليده يطابق بصمته
    python scripts/benefit_benchmark.py lock r1        # بعد الجلسة: قفل raw_r1.json كما صدّرته الأداة
    python scripts/benefit_benchmark.py reveal-key     # بعد قفل البيانات الخام فقط: كتابة key.json والتحقق من بصمته
    python scripts/benefit_benchmark.py compute r1     # بعد القفل وكشف المفتاح فقط: أعداد وأزمنة بلا نسب
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from miyar.judge import Citation, judge_citation  # noqa: E402
from miyar.normalize import normalize  # noqa: E402
from miyar.quran_match import load_quran  # noqa: E402

BENEFIT_DIR = ROOT / "evaluation" / "benefit"
SEED = "miyar-benefit-2026-10-06"
STIMULUS_NOTICE = "تنبيه: عناصر هذه التجربة محفزات اختبار، وبعضها مقطع معدل عمداً لأغراض الاختبار؛ لا يُعامل أي منها نصاً قرآنياً صحيحاً."
ALTERED_LABEL = "مقطع معدل عمداً لأغراض الاختبار"

# تركيب كل نصف مجموعة (6 عناصر)؛ المجموعة = نصفان، وكل حالة تأخذ مجموعة كاملة (12 عنصراً).
HALF_1 = ["match", "match", "match", "letter_sub", "word_drop", "wrong_location"]
HALF_2 = ["match", "match", "match", "letter_sub", "letter_drop", "no_location"]
WARMUP_TYPES = ["match", "letter_sub"]  # لكل حالة؛ تُستبعد من الحساب
EXPECTED = {
    "match": "matches_at_location",
    "letter_sub": "differs",
    "letter_drop": "differs",
    "word_drop": "differs",
    "wrong_location": "wrong_location",
    "no_location": "matches_no_location",
}
VERDICTS = {
    "matches_at_location": "مطابق لنص المصحف عند الموضع الذي ذكره المساعد",
    "matches_no_location": "مطابق لنص المصحف، لكن لم يُذكر موضع محدد (سورة وآية)",
    "differs": "يختلف عن نص المصحف عند الموضع المذكور (حرف أو كلمة)",
    "wrong_location": "نص قرآني صحيح لكن في موضع غير المذكور",
    "not_quran": "ليس نصاً قرآنياً",
    "cannot_determine": "لا أستطيع الحكم",
}
HUMAN_TO_STATUS = {  # التحويل نفسه المسجّل في Gold Set، لمقارنة حكم المراجع بحكم مِعيار في الحالة B
    "matches_at_location": "supported", "matches_no_location": "needs_review", "differs": "wrong_or_missing",
    "wrong_location": "wrong_or_missing", "not_quran": "wrong_or_missing", "cannot_determine": None,
}
# أزواج إبدال لا تمسّها قواعد التوحيد، وتُتجنب فيها س/ص لأنها قد تكون وجه قراءة.
SUB_PAIRS = {"ح": "خ", "خ": "ح", "ع": "غ", "غ": "ع", "د": "ذ", "ذ": "د", "ت": "ط", "ط": "ت", "ض": "ظ", "ظ": "ض"}
DROP_LETTERS = set("بتثجحخدذرزسشصضطظعغفقكلمن")
NEIGHBOUR = 3  # تُستبعد المواضع المستشهد بها رسمياً وجيرانها
CITED_FORMATS = ["({name}: {aya})", "[{name}: {aya}]", "سورة {name}، الآية {aya}", "سورة {name} ({sura}: {aya})"]
WRAPS = [("{", "}"), ("«", "»"), ("﴿", "﴾")]
PREREG = "PREREGISTRATION.json"
REVIEWERS = ("r1", "r2")


def riyadh_now() -> str:
    return datetime.now(ZoneInfo("Asia/Riyadh")).isoformat(timespec="minutes")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


# ---------------- توليد العناصر ----------------
def excluded_locations(root: Path = ROOT) -> set[tuple[int, int]]:
    """المواضع المستشهد بها في التشغيلات الرسمية وجيرانها: لا تدخل التجربة (تجنباً لأثر التذكر)."""
    out = set()
    for f in sorted((root / "evaluation" / "official").glob("official-*.json")):
        for case in json.loads(f.read_text(encoding="utf-8"))["cases"]:
            for cit in (case.get("judgement") or {}).get("citations") or []:
                c = cit["citation"]
                refs = [(c["sura"], c["aya"], c.get("aya_end") or c["aya"])] if c.get("sura") else []
                for r in cit.get("detail", {}).get("found_at", []) or []:
                    s, a = r.split(":")
                    a1, _, a2 = a.partition("-")
                    refs.append((int(s), int(a1), int(a2 or a1)))
                for s, a1, a2 in refs:
                    for a in range(a1 - NEIGHBOUR, a2 + NEIGHBOUR + 1):
                        out.add((s, a))
    return out


def _words(text: str) -> list[str]:
    return text.split()


def _not_in_quran(quran, text: str) -> bool:
    return not quran.find(text, min_tokens=2)


def _letter_sub(rng, words: list[str]) -> tuple[list[str], str] | None:
    idx = list(range(1, len(words) - 1))
    rng.shuffle(idx)
    for i in idx:
        chars = [j for j, ch in enumerate(words[i]) if ch in SUB_PAIRS]
        if chars:
            j = rng.choice(chars)
            old = words[i][j]
            w = words[i][:j] + SUB_PAIRS[old] + words[i][j + 1:]
            return words[:i] + [w] + words[i + 1:], f"إبدال الحرف «{old}» بـ«{SUB_PAIRS[old]}» في الكلمة {i + 1}"
    return None


_MARK = re.compile("[ً-ٰٟۖ-ۭ]")


def _letter_drop(rng, words: list[str]) -> tuple[list[str], str] | None:
    idx = list(range(1, len(words) - 1))
    rng.shuffle(idx)
    for i in idx:
        w = words[i]
        bases = [j for j, ch in enumerate(w) if ch in DROP_LETTERS]
        if len(normalize(w)) >= 4 and bases:
            j = rng.choice(bases)
            k = j + 1
            while k < len(w) and _MARK.match(w[k]):
                k += 1  # يُحذف الحرف مع حركاته
            return words[:i] + [w[:j] + w[k:]] + words[i + 1:], f"حذف الحرف «{w[j]}» من الكلمة {i + 1}"
    return None


def _word_drop(rng, words: list[str]) -> tuple[list[str], str] | None:
    if len(words) < 6:
        return None
    i = rng.randrange(1, len(words) - 1)
    return words[:i] + words[i + 1:], f"حذف الكلمة {i + 1} «{words[i]}»"


def _cited(rng, quran, sura: int, aya: int | None) -> str:
    name = quran.sura_name(sura)
    if aya is None:
        return f"سورة {name}"
    return rng.choice(CITED_FORMATS).format(name=name, sura=sura, aya=aya)


def make_item(rng, quran, kind: str, used: set, excluded: set) -> dict:
    """عنصر واحد بنوعه، مع مفتاحه (المصدر والنص الأصلي ووصف التعديل)."""
    verses = quran.verses
    for _ in range(5000):
        v = rng.choice(verses)
        if (v.sura, v.aya) in excluded or (v.sura, v.aya) in used:
            continue
        words = _words(v.text_simple)
        if len(words) < 7:
            continue
        n = rng.randint(6, min(9, len(words)))
        start = rng.randint(0, len(words) - n)
        frag = words[start:start + n]
        original = " ".join(frag)
        locs = quran.find(original)
        if [(l.sura, l.aya_start, l.aya_end) for l in locs] != [(v.sura, v.aya, v.aya)]:
            continue  # المقطع الأصلي يرد مرة واحدة فقط وفي آيته
        edit, stated = None, (v.sura, v.aya)
        shown = frag
        if kind in ("letter_sub", "letter_drop", "word_drop"):
            res = {"letter_sub": _letter_sub, "letter_drop": _letter_drop, "word_drop": _word_drop}[kind](rng, frag)
            if not res:
                continue
            shown, edit = res
            if normalize(" ".join(shown)) == normalize(original) or not _not_in_quran(quran, " ".join(shown)):
                continue
        elif kind == "wrong_location":
            n_ayat = quran.sura_length(v.sura)
            if n_ayat < 2 * NEIGHBOUR + 3:
                continue
            cands = [a for a in range(1, n_ayat + 1) if abs(a - v.aya) > NEIGHBOUR and (v.sura, a) not in excluded]
            if not cands:
                continue
            stated = (v.sura, rng.choice(cands))
            edit = f"الموضع المنسوب {stated[0]}:{stated[1]} بدل الموضع الصحيح {v.sura}:{v.aya}"
        elif kind == "no_location":
            stated = (v.sura, None)
            edit = "ذُكرت السورة دون رقم آية"
        used.add((v.sura, v.aya))
        left, right = rng.choice(WRAPS)
        quote = left + " ".join(shown) + right
        return {
            "blind": {"quote": quote, "cited_as_written": _cited(rng, quran, stated[0], stated[1])},
            "citation": {"sura": stated[0], "aya": stated[1]},
            "key": {
                "type": kind,
                "expected_verdict": EXPECTED[kind],
                "is_altered_text": kind in ("letter_sub", "letter_drop", "word_drop"),
                "label": ALTERED_LABEL if kind in ("letter_sub", "letter_drop", "word_drop") else "مقطع غير معدل (نص البيانات)",
                "source": f"Quranpedia mushafs-1 (data/quran) {v.sura}:{v.aya}",
                "source_ref": f"{v.sura}:{v.aya}",
                "original_fragment": original,
                "stated_location": None if stated[1] is None else f"{stated[0]}:{stated[1]}",
                "edit": edit,
            },
        }
    raise RuntimeError(f"تعذّر توليد عنصر من النوع {kind}")


def generate(quran, root: Path = ROOT) -> dict:
    """كل شيء من البذرة وحدها: العناصر، والتوزيع للمراجعَين، والمفتاح، ومخرجات مِعيار."""
    rng = random.Random(SEED)
    excluded = excluded_locations(root)
    used: set = set()
    sets = {s: [[make_item(rng, quran, k, used, excluded) for k in HALF_1],
                [make_item(rng, quran, k, used, excluded) for k in HALF_2]] for s in ("S1", "S2")}
    warm = {s: [make_item(rng, quran, k, used, excluded) for k in WARMUP_TYPES] for s in ("W1", "W2")}
    a_set = rng.choice(["S1", "S2"])  # المجموعة اليدوية للمراجع الأول؛ والمراجع الثاني بالعكس
    for s in sets.values():
        for half in s:
            rng.shuffle(half)

    # المعرّفات بترتيب عرض المراجع الأول: W، ثم كتل ABBA
    def seq_for(a: str, b: str, wa: str, wb: str):
        return ([(warm[wa][i], "A", 0, True) for i in range(2)] + [(x, "A", 1, False) for x in sets[a][0]]
                + [(warm[wb][i], "B", 2, True) for i in range(2)] + [(x, "B", 2, False) for x in sets[b][0]]
                + [(x, "B", 3, False) for x in sets[b][1]] + [(x, "A", 4, False) for x in sets[a][1]])

    b_set = "S2" if a_set == "S1" else "S1"
    r1 = seq_for(a_set, b_set, "W1", "W2")
    ids: dict[int, str] = {}
    nw = nt = 0
    for item, _, _, warmup in r1:
        if warmup:
            nw += 1
            ids[id(item)] = f"W{nw}"
        else:
            nt += 1
            ids[id(item)] = f"T{nt:02d}"
    r2 = seq_for(b_set, a_set, "W2", "W1")  # المراجع الثاني: الحالتان معكوستان، والترتيب ABBA نفسه

    def order(seq):
        return [{"position": p, "item_id": ids[id(it)], "condition": c, "block": blk, "warmup": w}
                for p, (it, c, blk, w) in enumerate(seq, 1)]

    all_items = [it for it, *_ in r1]
    items_blind = [{"item_id": ids[id(it)], **it["blind"]} for it in sorted(all_items, key=lambda x: ids[id(x)])]
    key = {"seed": SEED, "items": [{"item_id": ids[id(it)], **it["key"]} for it in sorted(all_items, key=lambda x: ids[id(x)])]}
    outputs = {}
    for it in sorted(all_items, key=lambda x: ids[id(x)]):
        j = judge_citation(Citation("quran", it["blind"]["quote"], it["blind"]["cited_as_written"],
                                    it["citation"]["sura"] if it["citation"]["aya"] else None, it["citation"]["aya"]), quran)
        outputs[ids[id(it)]] = {"status": j.status, "reason": j.reason, "matched_ref": j.matched_ref,
                                "matched_text": j.matched_text,
                                "suggestion": (j.detail.get("suggestions") or [None])[0]}
    assignment = {
        "seed": SEED,
        "design": "ABBA: كتلة يدوية (A) ثم كتلتان بمساعدة مِعيار (B) ثم كتلة يدوية؛ قبل أول كتلة من كل حالة عنصرا إحماء لا يُحتسبان",
        "condition_labels": {"A": "Manual-only (يدوي)", "B": "Miyar-assisted (بمساعدة مِعيار)"},
        "sets": {"r1": {"A": a_set, "B": b_set}, "r2": {"A": b_set, "B": a_set}},
        "set_items": {s: [ids[id(x)] for half in sets[s] for x in half] for s in ("S1", "S2")},
        "order": {"r1": order(r1), "r2": order(r2)},
    }
    return {"items_blind": {"notice": STIMULUS_NOTICE, "items": items_blind}, "key": key,
            "miyar_outputs": {"note": "مخرجات judge_citation الحقيقية (مطابقة برمجية بلا نموذج لغوي) لكل عنصر", "items": outputs},
            "assignment": assignment}


# ---------------- أداة المراجعة ----------------
STATUS_AR = {"supported": "مؤيَّد", "needs_review": "يحتاج تحقق", "wrong_or_missing": "خاطئ أو غير موجود"}
REASON_AR = {
    "exact_match": "تطابق حرفي مع نص البيانات عند الموضع المذكور",
    "altered_text": "قريب من نص الموضع المذكور لكنه ليس نصه (نقل محرّف)",
    "wrong_reference": "النص موجود في موضع آخر غير المذكور",
    "not_found": "لم يُعثر على النص حرفياً ولا قرب كافٍ منه",
    "location_not_stated": "لم يُذكر موضع (سورة وآية)؛ النص موجود في البيانات",
    "location_not_stated_not_found": "لم يُذكر موضع، ولم يُعثر على النص",
    "invalid_reference": "الموضع المذكور غير موجود",
    "quote_too_short": "المقطع أقصر من أن يُحكم عليه",
}


def tool_html(reviewer: str, blind: dict, outputs: dict, assignment: dict, template: str) -> str:
    """أداة الجلسة لمراجع واحد: الترتيب المقفل، ومخرجات مِعيار لعناصر الحالة B فقط، ولا شيء من المفتاح."""
    by_id = {i["item_id"]: i for i in blind["items"]}
    seq = []
    for o in assignment["order"][reviewer]:
        it = by_id[o["item_id"]]
        entry = {**o, "quote": it["quote"], "cited_as_written": it["cited_as_written"]}
        if o["condition"] == "B":
            m = outputs["items"][o["item_id"]]
            entry["miyar"] = {"status": STATUS_AR[m["status"]], "reason": REASON_AR.get(m["reason"], m["reason"]),
                              "matched_ref": m["matched_ref"], "matched_text": m["matched_text"],
                              "suggestion": m["suggestion"] and {"ref": m["suggestion"]["ref"],
                                                                 "text": m["suggestion"].get("text")}}
        seq.append(entry)
    data = {"reviewer": reviewer, "build": sha256_bytes(dumps(assignment).encode()), "notice": blind["notice"],
            "verdicts": [[k, v] for k, v in VERDICTS.items()], "sequence": seq}
    return template.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


# ---------------- البناء والتسجيل المسبق ----------------
def build_files(quran, root: Path = ROOT, out: Path = BENEFIT_DIR) -> dict[str, bytes]:
    g = generate(quran, root)
    template = (root / "scripts" / "benefit_tool_template.html").read_text(encoding="utf-8")
    files = {
        "items_blind.json": dumps(g["items_blind"]).encode(),
        "assignment.json": dumps(g["assignment"]).encode(),
        "miyar_outputs.json": dumps(g["miyar_outputs"]).encode(),
    }
    for r in REVIEWERS:
        files[f"tool/review_{r}.html"] = tool_html(r, g["items_blind"], g["miyar_outputs"], g["assignment"], template).encode()
    return files | {"__key__": dumps(g["key"]).encode()}


PREREG_INPUTS = ["PROTOCOL.md", "items_blind.json", "assignment.json", "miyar_outputs.json",
                 "tool/review_r1.html", "tool/review_r2.html"]
CODE_INPUTS = ["scripts/benefit_benchmark.py", "scripts/benefit_tool_template.html"]


def protected_sums(root: Path = ROOT) -> dict[str, str]:
    files = sorted((root / "evaluation" / "official").glob("*")) + sorted(
        p for p in (root / "evaluation" / "gold").rglob("*") if p.is_file())
    return {p.relative_to(root).as_posix(): sha256(p) for p in files if p.is_file()}


def cmd_build(root: Path = ROOT, out: Path = BENEFIT_DIR) -> dict:
    if (out / PREREG).exists():
        raise SystemExit("التجربة مسجّلة مسبقاً؛ لا يُعاد البناء.")
    files = build_files(load_quran(), root, out)
    key = files.pop("__key__")
    for rel, b in files.items():
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(b)
    prereg = {
        "registered_at": riyadh_now(),
        "seed": SEED,
        "key_sha256": sha256_bytes(key),
        "files_sha256": {rel: sha256(out / rel) for rel in PREREG_INPUTS},
        "code_sha256": {rel: sha256(root / rel) for rel in CODE_INPUTS},
        "protected_sha256": protected_sums(root),
        "note": "المفتاح لا يُرفع قبل قفل البيانات الخام؛ يُعاد توليده حتمياً من البذرة وتُطابق بصمته key_sha256.",
    }
    (out / PREREG).write_text(dumps(prereg), encoding="utf-8")
    return prereg


def cmd_verify(root: Path = ROOT, out: Path = BENEFIT_DIR) -> bytes:
    """يتحقق من كل بصمة مسجّلة مسبقاً ويعيد المفتاح المُعاد توليده."""
    prereg = json.loads((out / PREREG).read_text(encoding="utf-8"))
    for rel, h in prereg["files_sha256"].items():
        if sha256(out / rel) != h:
            raise SystemExit(f"تغيّر ملف مسجّل مسبقاً: {rel}")
    for rel, h in prereg["code_sha256"].items():
        if sha256(root / rel) != h:
            raise SystemExit(f"تغيّر كود مسجّل مسبقاً: {rel}")
    if protected_sums(root) != prereg["protected_sha256"]:
        raise SystemExit("تغيّرت السجلات الرسمية أو Gold Set.")
    files = build_files(load_quran(), root, out)
    key = files.pop("__key__")
    if sha256_bytes(key) != prereg["key_sha256"]:
        raise SystemExit("المفتاح المُعاد توليده لا يطابق بصمته المسجّلة.")
    for rel, b in files.items():
        if (out / rel).read_bytes() != b:
            raise SystemExit(f"الملف لا يطابق إعادة التوليد: {rel}")
    return key


# ---------------- بعد الجلسة ----------------
def validate_raw(raw: dict, assignment: dict, reviewer: str) -> None:
    order = assignment["order"][reviewer]
    if raw.get("reviewer") != reviewer or raw.get("build") != sha256_bytes(dumps(assignment).encode()):
        raise ValueError("البيانات الخام ليست من أداة هذا المراجع وهذا التوزيع")
    rows = raw.get("records", [])
    if [r["item_id"] for r in rows] != [o["item_id"] for o in order]:
        raise ValueError("ترتيب العناصر أو عددها لا يطابق التوزيع المقفل")
    for r, o in zip(rows, order):
        if (r["condition"], r["block"], r["warmup"], r["position"]) != (o["condition"], o["block"], o["warmup"], o["position"]) \
                or r["human_verdict"] not in VERDICTS:
            raise ValueError(f"{r['item_id']}: حالة أو حكم غير مسموح")
        if not (isinstance(r["started_at_ms"], int) and isinstance(r["submitted_at_ms"], int)
                and r["submitted_at_ms"] >= r["started_at_ms"] and r["duration_ms"] == r["submitted_at_ms"] - r["started_at_ms"]):
            raise ValueError(f"{r['item_id']}: أزمنة غير صالحة")


def cmd_lock(reviewer: str, root: Path = ROOT, out: Path = BENEFIT_DIR) -> dict:
    cmd_verify(root, out)
    lock = out / f"LOCK_{reviewer}.json"
    if lock.exists():
        raise SystemExit("البيانات الخام مقفلة مسبقاً.")
    raw = json.loads((out / f"raw_{reviewer}.json").read_text(encoding="utf-8"))
    validate_raw(raw, json.loads((out / "assignment.json").read_text(encoding="utf-8")), reviewer)
    info = {"raw_sha256": sha256(out / f"raw_{reviewer}.json"), "locked_at": riyadh_now(), "n_records": len(raw["records"])}
    lock.write_text(dumps(info), encoding="utf-8")
    return info


def cmd_reveal_key(root: Path = ROOT, out: Path = BENEFIT_DIR) -> None:
    if not any((out / f"LOCK_{r}.json").exists() for r in REVIEWERS):
        raise SystemExit("لا يُكشف المفتاح قبل قفل بيانات خام لمراجع واحد على الأقل.")
    key = cmd_verify(root, out)
    path = out / "key.json"
    if path.exists() and path.read_bytes() != key:
        raise SystemExit("key.json الموجود لا يطابق المفتاح المسجّل.")
    path.write_bytes(key)


def interpret(a: dict, b: dict) -> str:
    """قاعدة التفسير المسجّلة مسبقاً (PROTOCOL §5)."""
    if b["correct"] < a["correct"] or b["problems_detected"] < a["problems_detected"] or (
            b["median_seconds"] >= a["median_seconds"] and b["correct"] == a["correct"]
            and b["problems_detected"] == a["problems_detected"]):
        return "negative"
    if b["median_seconds"] < a["median_seconds"]:
        return "positive"  # والصحة والاكتشاف في B لا يقلان (استُبعد ذلك أعلاه)
    return "mixed"


def compute(raw: dict, key: dict, outputs: dict) -> dict:
    """المقياس الرئيسي: الزمن الوسيط للعنصر لكل حالة. والباقي ثانوي بالأعداد. عناصر الإحماء مستبعدة."""
    k = {i["item_id"]: i for i in key["items"]}
    res = {}
    for cond in ("A", "B"):
        rows = [r for r in raw["records"] if r["condition"] == cond and not r["warmup"]]
        durs = [r["duration_ms"] / 1000 for r in rows]
        problems = [r for r in rows if k[r["item_id"]]["type"] != "match"]
        clean = [r for r in rows if k[r["item_id"]]["type"] == "match"]
        c = {
            "n_items": len(rows),
            "median_seconds": round(statistics.median(durs), 1),
            "total_seconds": round(sum(durs), 1),
            "min_seconds": round(min(durs), 1),
            "max_seconds": round(max(durs), 1),
            "correct": sum(r["human_verdict"] == k[r["item_id"]]["expected_verdict"] for r in rows),
            "problems_detected": sum(r["human_verdict"] not in ("matches_at_location", "cannot_determine") for r in problems),
            "n_problem_items": len(problems),
            "false_alarms": sum(r["human_verdict"] not in ("matches_at_location", "cannot_determine") for r in clean),
            "n_clean_items": len(clean),
            "cannot_determine": sum(r["human_verdict"] == "cannot_determine" for r in rows),
            "interrupted": sum(bool(r.get("interrupted")) for r in rows),
        }
        if cond == "B":
            dis = [r for r in rows if HUMAN_TO_STATUS[r["human_verdict"]] is not None
                   and HUMAN_TO_STATUS[r["human_verdict"]] != outputs["items"][r["item_id"]]["status"]]
            c["disagreed_with_miyar"] = len(dis)
            c["disagreed_and_reviewer_correct"] = sum(r["human_verdict"] == k[r["item_id"]]["expected_verdict"] for r in dis)
        res[cond] = c
    label = interpret(res["A"], res["B"])
    expected_status = {"match": "supported", "no_location": "needs_review"}
    miyar_ok = sum(outputs["items"][i]["status"] == expected_status.get(k[i]["type"], "wrong_or_missing")
                   for i in k if i.startswith("T"))
    return {"primary_endpoint": "median_seconds per item: A (Manual-only) vs B (Miyar-assisted)",
            "by_condition": res, "preregistered_interpretation": label,
            "miyar_status_matches_key": {"agree": miyar_ok, "of": sum(1 for i in k if i.startswith("T"))},
            "percentages": "لا نسب مئوية؛ أعداد ومقامات وأزمنة فعلية فقط."}


def cmd_compute(reviewer: str, root: Path = ROOT, out: Path = BENEFIT_DIR) -> dict:
    lock = out / f"LOCK_{reviewer}.json"
    if not lock.exists() or not (out / "key.json").exists():
        raise SystemExit("لا حساب قبل قفل البيانات الخام وكشف المفتاح.")
    key_bytes = cmd_verify(root, out)
    if (out / "key.json").read_bytes() != key_bytes:
        raise SystemExit("key.json لا يطابق المفتاح المسجّل.")
    if sha256(out / f"raw_{reviewer}.json") != json.loads(lock.read_text(encoding="utf-8"))["raw_sha256"]:
        raise SystemExit("البيانات الخام تغيّرت بعد القفل.")
    raw = json.loads((out / f"raw_{reviewer}.json").read_text(encoding="utf-8"))
    res = compute(raw, json.loads(key_bytes), json.loads((out / "miyar_outputs.json").read_text(encoding="utf-8")))
    res |= {"reviewer": raw.get("reviewer_info"), "computed_at": riyadh_now()}
    (out / f"results_{reviewer}.json").write_text(dumps(res), encoding="utf-8")
    return res


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["build", "verify", "lock", "reveal-key", "compute"])
    p.add_argument("reviewer", nargs="?", choices=REVIEWERS)
    a = p.parse_args(argv)
    if a.command == "build":
        print(json.dumps(cmd_build(), ensure_ascii=False, indent=1))
    elif a.command == "verify":
        cmd_verify()
        print("كل البصمات المسجّلة مسبقاً مطابقة، والمفتاح المُعاد توليده يطابق بصمته.")
    elif a.command == "reveal-key":
        cmd_reveal_key()
    elif not a.reviewer:
        p.error("حدّد المراجع: r1 أو r2")
    elif a.command == "lock":
        print(cmd_lock(a.reviewer))
    else:
        print(json.dumps(cmd_compute(a.reviewer), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
