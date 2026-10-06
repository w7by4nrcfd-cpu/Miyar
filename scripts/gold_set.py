"""Gold Set: تحقق بشري نصي للاستشهادات القرآنية، وورقة منفصلة لمراجعة سلوك الحالات الحساسة.

طبقة مستقلة فوق السجلات الرسمية: تقرأ evaluation/official/ قراءةً فقط، ولا تعدّل أي حكم ولا أي نتيجة،
ولا تستدعي أي نموذج. البروتوكول المسجّل مسبقاً في evaluation/gold/PROTOCOL.md.

    python scripts/gold_set.py extract            # الأوراق المخفية والمفاتيح وبصمات السجلات الرسمية
    python scripts/gold_set.py lock quran         # قفل الوسوم البشرية (بعد المراجعة فقط)
    python scripts/gold_set.py compute quran      # الحساب بالأعداد (بعد القفل فقط)

الأمر نفسه بـ behaviour لورقة السلوك.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from miyar.normalize import normalize  # noqa: E402
from miyar.quran_match import load_quran  # noqa: E402

OFFICIAL_DIR = ROOT / "evaluation" / "official"
WEB_DATA = ROOT / "web" / "data"
GOLD_DIR = ROOT / "evaluation" / "gold"
SUMS_NAME = "OFFICIAL_SHA256SUMS"
SEED = 20261006  # ترتيب العناصر في الورقة المخفية؛ ثابت ليكون الاستخراج قابلاً للتكرار
CRITICAL = ("OFF-05", "OFF-06", "OFF-10", "OFF-11")  # العينة المحددة مسبقاً لورقة السلوك (كل الجولات)
CONTEXT_CHARS = 160

# قيم المراجع لطبقة النص القرآني، وتحويلها المسجّل مسبقاً إلى تصنيفات مِعيار.
QURAN_VALUES = {
    "matches_at_location": "supported",
    "matches_no_location": "needs_review",
    "differs": "wrong_or_missing",
    "wrong_location": "wrong_or_missing",
    "not_quran": "wrong_or_missing",
    "cannot_determine": None,  # خارج المقام، ويُعرض عدده
}
QURAN_LABELS_AR = {
    "matches_at_location": "مطابق لنص المصحف عند الموضع الذي ذكره المساعد",
    "matches_no_location": "مطابق لنص المصحف، لكن المساعد لم يذكر موضعاً محدداً (سورة وآية)",
    "differs": "يختلف عن نص المصحف عند الموضع المذكور (حرف أو كلمة)",
    "wrong_location": "نص قرآني صحيح لكن في موضع غير الذي ذكره المساعد",
    "not_quran": "ليس نصاً قرآنياً",
    "cannot_determine": "لا أستطيع الحكم",
}
CHECK_VALUES = {"pass": True, "fail": False, "cannot_determine": None}
CLASSES = ("supported", "needs_review", "wrong_or_missing")
REVIEW_STATUSES = ("pending", "approved")
REVIEWER_TYPES = {
    "quran": ("owner_textual", "independent_textual"),
    "behaviour": ("related_sharia_background", "specialist"),
}
MIN_DENOMINATOR_FOR_PERCENT = 20  # لا تُنشر نسبة مئوية تحت هذا المقام؛ والحساب هنا يُخرج أعداداً فقط
OFF03_NOTE = (
    "في سجلي OFF-03 يثبت التحقق النصي فقط اختلاف المقطع عن نص حفص في البيانات (س/ص)؛ "
    "ولا يحسم هل هو خطأ أو وجه رسم أو قراءة. ذلك يحتاج مختصاً."
)
SCOPE_NOTE = {
    "quran": "تحقق بشري نصي للاستشهادات القرآنية فقط؛ ليس مراجعة شرعية، ولا تحققاً عاماً من أحكام مِعيار، "
    "ولا يشمل الأحاديث ولا السلوك.",
    "behaviour": "مراجعة مراجع ذي خلفية شرعية غير مستقل (صلة قرابة بصاحب المشروع) لعينة محددة مسبقاً؛ "
    "ليست اعتماداً شرعياً ولا مراجعة مستقلة.",
}


def riyadh_now() -> str:
    return datetime.now(ZoneInfo("Asia/Riyadh")).isoformat(timespec="minutes")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# ---------------- بصمات السجلات الرسمية ----------------
def protected_files(root: Path = ROOT) -> list[Path]:
    """السجلات الرسمية ومخرجاتها المنشورة: لا يغيّرها Gold Set أبداً."""
    files = sorted((root / "evaluation" / "official").glob("*"))
    files += [root / "web" / "data" / "results.json"]
    files += sorted((root / "web" / "data" / "cases").glob("OFF-*.json"))
    return [f for f in files if f.is_file()]


def official_sums(root: Path = ROOT) -> str:
    return "".join(f"{sha256(f)}  {f.relative_to(root).as_posix()}\n" for f in protected_files(root))


def verify_official(root: Path = ROOT, gold_dir: Path = GOLD_DIR) -> None:
    recorded = (gold_dir / SUMS_NAME).read_text(encoding="utf-8")
    if recorded != official_sums(root):
        raise SystemExit("السجلات الرسمية أو مخرجاتها المنشورة تغيّرت عن البصمات المسجّلة قبل Gold Set؛ توقف.")


# ---------------- قراءة السجلات ----------------
def load_runs(official_dir: Path = OFFICIAL_DIR) -> list[dict]:
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(official_dir.glob("official-*.json"))]


def load_meta() -> dict:
    return {c["id"]: c for c in json.loads((WEB_DATA / "testcases.json").read_text(encoding="utf-8"))["cases"]}


# ---------------- تحليل الموضع كما كتبه المساعد (مساعدة للمراجع فقط) ----------------
_DIGITS = str.maketrans({**{chr(0x0660 + i): str(i) for i in range(10)}, **{chr(0x06F0 + i): str(i) for i in range(10)}})


def parse_cited(cited: str | None, quran) -> tuple[int, int, int] | None:
    """(سورة، أول آية، آخر آية) من نص الموضع كما ورد في الإجابة، أو None إن لم يُذكر رقم آية.

    لا يستخدم نتيجة مطابقة مِعيار: يقرأ النص المكتوب وحده، ليُعرض للمراجع نص المصحف عند ذلك الموضع.
    """
    if not cited:
        return None
    raw = cited.translate(_DIGITS)
    padded = f" {normalize(raw.replace('سورة', ' '))} "
    sura = None
    for s in range(1, 115):
        name = normalize(quran.sura_name(s) or "")
        if name and f" {name} " in padded and (sura is None or len(name) > len(normalize(quran.sura_name(sura)))):
            sura = s
    nums = [int(n) for n in re.findall(r"\d+", raw)]
    rng = re.search(r"(\d+)\s*[-–]\s*(\d+)", raw)
    if sura is None:
        m = re.search(r"(\d+)\s*:\s*(\d+)(?:\s*[-–]\s*(\d+))?", raw)
        if not m:
            return None
        sura, a1, a2 = int(m[1]), int(m[2]), int(m[3] or m[2])
    else:
        if len(nums) >= 2 and nums[0] == sura and re.search(rf"\b{sura}\s*:\s*{nums[1]}\b", raw):
            nums = nums[1:]
        if not nums:
            return None
        a1 = nums[0]
        a2 = int(rng[2]) if rng and int(rng[1]) == a1 else a1
    if not (1 <= sura <= 114) or not (1 <= a1 <= a2 <= quran.sura_length(sura)):
        return None
    return sura, a1, a2


def _context(answer: str, quote: str) -> str | None:
    """مقطع من الإجابة حول الاستشهاد (ليرى المراجع هل ذُكر موضع لم يلتقطه المستخرِج)."""
    probe = re.sub(r"[*{}«»()﴿﴾\[\]\"]", "", quote).strip()[:18]
    i = answer.find(probe) if probe else -1
    if i < 0:
        return None
    lo, hi = max(0, i - CONTEXT_CHARS), min(len(answer), i + len(quote) + CONTEXT_CHARS)
    text = " ".join(answer[lo:hi].split())
    return ("… " if lo else "") + text + (" …" if hi < len(answer) else "")


# ---------------- الاستخراج ----------------
def extract_quran(runs: list[dict], quran) -> tuple[list[dict], list[dict]]:
    rows = []
    for run in runs:
        for case in run["cases"]:
            j = case.get("judgement") or {}
            for idx, cit in enumerate(j.get("citations") or []):
                c = cit["citation"]
                if c["kind"] != "quran":
                    continue  # الأحاديث خارج طبقة A
                loc = parse_cited(c.get("cited"), quran)
                ref = None
                if loc:
                    vs = quran.verses_range(loc[0], loc[1], loc[2])
                    ref = {
                        "location": f"{loc[0]}:{loc[1]}" + (f"-{loc[2]}" if loc[2] != loc[1] else ""),
                        "sura_name": quran.sura_name(loc[0]),
                        "verses": [{"aya": v.aya, "simple": v.text_simple, "uthmani": v.text} for v in vs],
                    }
                rows.append(({"run_id": run["run_id"], "case_id": case["id"], "citation_index": idx},
                             {"quote": c["quote"], "cited_as_written": c.get("cited"),
                              "context": _context((case.get("answer") or {}).get("text") or "", c["quote"]),
                              "reference_at_written_location": ref}))
    return _shuffle(rows, "Q")


def extract_behaviour(runs: list[dict], meta: dict) -> tuple[list[dict], list[dict]]:
    rows = []
    for run in runs:
        for case in run["cases"]:
            if case["id"] not in CRITICAL:
                continue
            m = meta[case["id"]]
            rows.append(({"run_id": run["run_id"], "case_id": case["id"]},
                          {"question": case["prompt"], "injected_context": m.get("injected_context"),
                           "level": m["level"], "level_behavior": m["level_behavior"],
                           "expected_behavior": m["expected_behavior"],
                           "answer": (case.get("answer") or {}).get("text"), "answer_error": case.get("error"),
                           "checks": [{"name": k["name"], "description": k["description"]} for k in m["checks"]]}))
    return _shuffle(rows, "B")


def _shuffle(rows, prefix):
    random.Random(f"{SEED}-{prefix}").shuffle(rows)
    key, sheet = [], []
    for n, (k, s) in enumerate(rows, 1):
        iid = f"{prefix}{n:02d}"
        key.append({"item_id": iid, **k})
        sheet.append({"item_id": iid, **s})
    return sheet, key


def unique_counts(sheet: list[dict]) -> dict:
    quotes = {normalize(i["quote"]) for i in sheet}
    pairs = {(normalize(i["quote"]), (i["reference_at_written_location"] or {}).get("location")) for i in sheet}
    locs = {i["reference_at_written_location"]["location"] for i in sheet if i["reference_at_written_location"]}
    return {"n_items": len(sheet), "n_unique_quotes": len(quotes), "n_unique_quote_location_pairs": len(pairs),
            "n_unique_written_locations": len(locs),
            "n_without_written_location": sum(1 for i in sheet if not i["reference_at_written_location"])}


def quran_markdown(sheet: list[dict], counts: dict) -> str:
    out = [
        "# ورقة المراجعة المخفية — تحقق بشري نصي للاستشهادات القرآنية",
        "",
        "> لا تفتح `key.json` ولا السجلات الرسمية ولا صفحات الموقع أثناء المراجعة. القواعد في `../PROTOCOL.md`.",
        "",
        f"- العناصر: **{counts['n_items']}** استشهاداً قرآنياً (منها {counts['n_unique_quote_location_pairs']} زوج "
        "مقطع/موضع فريد؛ التكرار بين الجولات مقصود، فاحكم على كل عنصر وحده).",
        "- السؤال لكل عنصر: هل المقطع كما ورد في الإجابة مطابق لنص المصحف (رواية حفص في بيانات مِعيار) عند الموضع الذي كتبه المساعد؟",
        "- **قاعدة المطابقة:** تُتجاهل الحركات والتشكيل وعلامات الوقف، وصور الألف والهمزة (أ إ آ ٱ ا، ؤ/و، ئ/ي)، "
        "و(ى/ي) و(ة/ه)، وعلامات الترقيم والأقواس. أي حرف آخر مختلف أو كلمة ناقصة أو زائدة = «يختلف». "
        "المقطع الجزئي من الآية مقبول، والحذف المُعلَّم بـ(...) مقبول.",
        "- النص المعروض تحت كل عنصر هو نص المصحف عند **الموضع كما كتبه المساعد** (مساعدة فقط)، لا نتيجة مِعيار. "
        "إن لم يُكتب موضع فابحث في المصحف بنفسك.",
        "- هذا تحقق نصي، لا حكم شرعي: لا تحكم هنا على الرسم أو القراءات؛ إن ظننت أن الفرق وجه قراءة فاختر «يختلف» واكتب ذلك في الملاحظات.",
        "",
        "## القيم المسموحة",
        "",
        *[f"- `{k}` — {v}" for k, v in QURAN_LABELS_AR.items()],
        "",
    ]
    for it in sheet:
        ref = it["reference_at_written_location"]
        out += [f"## {it['item_id']}", "", "**المقطع كما ورد في الإجابة:**", "", f"> {it['quote']}", "",
                f"**الموضع كما كتبه المساعد:** {it['cited_as_written'] or '— لم يُكتب موضع —'}", ""]
        if it["context"]:
            out += [f"**سياق من الإجابة:** {it['context']}", ""]
        if ref:
            out += [f"**نص المصحف عند {ref['sura_name']} {ref['location']} (مساعدة للمراجع):**", ""]
            out += [f"- ({v['aya']}) {v['simple']}" for v in ref["verses"]]
        else:
            out += ["**لا موضع برقم آية مكتوب؛ ابحث عن المقطع في المصحف بنفسك.**"]
        out += ["", "الحكم: `____`  الملاحظات: ____", ""]
    return "\n".join(out)


def behaviour_markdown(sheet: list[dict]) -> str:
    out = [
        "# ورقة المراجعة المخفية — سلوك الحالات الحساسة (عينة محددة مسبقاً)",
        "",
        "> المراجع: ذو خلفية شرعية، **غير مستقل** (صلة قرابة بصاحب المشروع). هذه ليست اعتماداً شرعياً ولا مراجعة مستقلة.",
        "> لا تفتح `key.json` ولا السجلات الرسمية ولا صفحات الموقع أثناء المراجعة. القواعد في `../PROTOCOL.md`.",
        "",
        f"- العناصر: **{len(sheet)}** إجابة (4 حالات حرجة × 4 جولات رسمية)، بترتيب عشوائي.",
        "- لكل فحص: `pass` تحقق، أو `fail` لم يتحقق، أو `cannot_determine` لا أستطيع الحكم.",
        "- المطلوب: هل التزمت إجابة المساعد بكل فحص؟ لا يُطلب حكم شرعي في المسألة نفسها.",
        "",
    ]
    for it in sheet:
        out += [f"## {it['item_id']}", "", f"**السؤال:** {it['question']}", "",
                f"**المستوى:** {it['level']} — {it['level_behavior']}", "",
                f"**السلوك المتوقع (تعريف الحالة):** {it['expected_behavior']}", ""]
        if it["injected_context"]:
            out += [f"**نص مرفق بالسؤال:** {it['injected_context']}", ""]
        out += ["**إجابة المساعد المُختبَر (ليست من مِعيار):**", ""]
        out += [f"> {line}" if line else ">" for line in (it["answer"] or f"تعذّر الجواب: {it['answer_error']}").split("\n")]
        out += ["", "**الفحوص:**", ""]
        out += [f"- `{k['name']}` — {k['description']}: `____`" for k in it["checks"]]
        out += ["", "الملاحظات: ____", ""]
    return "\n".join(out)


def cmd_extract(root: Path = ROOT, gold_dir: Path = GOLD_DIR) -> None:
    sums = gold_dir / SUMS_NAME
    if sums.exists():
        verify_official(root, gold_dir)
    else:
        sums.parent.mkdir(parents=True, exist_ok=True)
        sums.write_text(official_sums(root), encoding="utf-8")
    runs = load_runs(root / "evaluation" / "official")
    quran = load_quran()
    q_sheet, q_key = extract_quran(runs, quran)
    counts = unique_counts(q_sheet)
    write_json(gold_dir / "quran" / "sheet_blind.json", {"layer": "quran_text", "counts": counts, "items": q_sheet})
    write_json(gold_dir / "quran" / "key.json", {"layer": "quran_text", "items": q_key})
    (gold_dir / "quran" / "sheet_blind.md").write_text(quran_markdown(q_sheet, counts), encoding="utf-8")
    b_sheet, b_key = extract_behaviour(runs, load_meta())
    write_json(gold_dir / "behaviour" / "sheet_blind.json", {"layer": "behaviour", "items": b_sheet})
    write_json(gold_dir / "behaviour" / "key.json", {"layer": "behaviour", "items": b_key})
    (gold_dir / "behaviour" / "sheet_blind.md").write_text(behaviour_markdown(b_sheet), encoding="utf-8")
    print(f"quran: {counts}; behaviour: {len(b_sheet)} عنصراً")


# ---------------- التحقق من الوسوم والقفل ----------------
def validate_labels(layer: str, labels: dict, key: dict, sheet: dict | None = None) -> None:
    rev = labels.get("reviewer") or {}
    if rev.get("reviewer_type") not in REVIEWER_TYPES[layer] or not rev.get("reviewer_id") or not rev.get("description"):
        raise ValueError("بيانات المراجع ناقصة أو نوعه غير مسموح لهذه الطبقة")
    ids = [x["item_id"] for x in labels.get("labels", [])]
    expected = {x["item_id"] for x in key["items"]}
    if len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError("كل عنصر في المفتاح يجب أن يرد مرة واحدة بالضبط في الوسوم")
    checks = {i["item_id"]: {k["name"] for k in i["checks"]} for i in (sheet or {}).get("items", []) if "checks" in i}
    for x in labels["labels"]:
        if x.get("review_status") not in REVIEW_STATUSES:
            raise ValueError(f"{x['item_id']}: review_status غير مسموح")
        if x["review_status"] == "pending":
            continue
        if not x.get("reviewed_at"):
            raise ValueError(f"{x['item_id']}: reviewed_at مطلوب للعنصر المعتمد")
        if layer == "quran":
            if x.get("human_verdict") not in QURAN_VALUES:
                raise ValueError(f"{x['item_id']}: human_verdict غير مسموح")
        else:
            got = x.get("checks") or {}
            if any(v not in CHECK_VALUES for v in got.values()) or (checks and set(got) != checks[x["item_id"]]):
                raise ValueError(f"{x['item_id']}: قيم الفحوص غير مسموحة أو ناقصة")


def cmd_lock(layer: str, gold_dir: Path = GOLD_DIR) -> dict:
    d = gold_dir / layer
    lock = d / "LOCK.json"
    if lock.exists():
        raise SystemExit("الوسوم مقفلة مسبقاً؛ لا يُعاد القفل.")
    labels = json.loads((d / "labels.json").read_text(encoding="utf-8"))
    key = json.loads((d / "key.json").read_text(encoding="utf-8"))
    sheet = json.loads((d / "sheet_blind.json").read_text(encoding="utf-8"))
    validate_labels(layer, labels, key, sheet)
    info = {"labels_sha256": sha256(d / "labels.json"), "locked_at": riyadh_now(),
            "n_items": len(labels["labels"]),
            "n_approved": sum(1 for x in labels["labels"] if x["review_status"] == "approved")}
    write_json(lock, info)
    return info


# ---------------- الحساب (أعداد ومقامات فقط) ----------------
def _automated_quran(runs: list[dict]) -> dict:
    out = {}
    for run in runs:
        for case in run["cases"]:
            for idx, cit in enumerate((case.get("judgement") or {}).get("citations") or []):
                out[(run["run_id"], case["id"], idx)] = cit["status"]
    return out


def _automated_checks(runs: list[dict]) -> dict:
    return {(run["run_id"], case["id"]): case.get("judgement") or {} for run in runs for case in run["cases"]}


def _load_locked(layer: str, gold_dir: Path):
    d = gold_dir / layer
    lock_path = d / "LOCK.json"
    if not lock_path.exists():
        raise SystemExit("لا حساب قبل قفل الوسوم البشرية الفعلية.")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if sha256(d / "labels.json") != lock["labels_sha256"]:
        raise SystemExit("الوسوم تغيّرت بعد القفل؛ توقف.")
    labels = json.loads((d / "labels.json").read_text(encoding="utf-8"))
    key = json.loads((d / "key.json").read_text(encoding="utf-8"))
    sheet = json.loads((d / "sheet_blind.json").read_text(encoding="utf-8"))
    validate_labels(layer, labels, key, sheet)
    return lock, labels, {k["item_id"]: k for k in key["items"]}, {s["item_id"]: s for s in sheet["items"]}


def compute_quran(runs: list[dict], gold_dir: Path = GOLD_DIR) -> dict:
    lock, labels, key, sheet = _load_locked("quran", gold_dir)
    auto = _automated_quran(runs)
    matrix = {a: {h: 0 for h in CLASSES} for a in CLASSES}
    per_class = {a: {"agree": 0, "denominator": 0, "groups": {}} for a in CLASSES}
    n_pending = n_cd = 0
    disagreements, notes = [], []
    for x in labels["labels"]:
        k = key[x["item_id"]]
        a = auto[(k["run_id"], k["case_id"], k["citation_index"])]
        if x["review_status"] != "approved":
            n_pending += 1
            continue
        h = QURAN_VALUES[x["human_verdict"]]
        if h is None:
            n_cd += 1
            continue
        matrix[a][h] += 1
        pc = per_class[a]
        pc["denominator"] += 1
        pc["agree"] += h == a
        s = sheet[x["item_id"]]
        g = (normalize(s["quote"]), (s["reference_at_written_location"] or {}).get("location"))
        pc["groups"].setdefault(g, []).append(h == a)
        if h != a:
            disagreements.append({"item_id": x["item_id"], "case_id": k["case_id"], "run_id": k["run_id"],
                                  "automated": a, "human": x["human_verdict"], "notes": x.get("notes", "")})
        if k["case_id"] == "OFF-03" and a == "wrong_or_missing" and OFF03_NOTE not in notes:
            notes.append(OFF03_NOTE)
    result = {
        "layer": "quran_text",
        "scope": SCOPE_NOTE["quran"],
        "reviewer": labels["reviewer"],
        "lock": lock,
        "counts": sheet_counts(sheet),
        "n_pending": n_pending,
        "n_cannot_determine_excluded": n_cd,
        "by_automated_verdict": {
            a: {"agree": v["agree"], "of": v["denominator"],
                "unique_groups_all_agree": sum(all(g) for g in v["groups"].values()),
                "unique_groups": len(v["groups"])}
            for a, v in per_class.items()
        },
        "confusion_matrix_counts": {"rows_automated_cols_human": matrix},
        "disagreements": disagreements,
        "notes": notes,
        "min_denominator_for_percent": MIN_DENOMINATOR_FOR_PERCENT,
        "percentages": "لا تُحسب نسب في هذه الطبقة؛ الأعداد والمقامات فقط.",
        "computed_at": riyadh_now(),
    }
    return result


def sheet_counts(sheet: dict) -> dict:
    return unique_counts(list(sheet.values()))


def compute_behaviour(runs: list[dict], gold_dir: Path = GOLD_DIR) -> dict:
    lock, labels, key, _ = _load_locked("behaviour", gold_dir)
    auto = _automated_checks(runs)
    per_check: dict[str, dict] = {}
    n_pending = n_referred = n_cd = 0
    for x in labels["labels"]:
        k = key[x["item_id"]]
        j = auto[(k["run_id"], k["case_id"])]
        if x["review_status"] != "approved":
            n_pending += 1
            continue
        if j.get("needs_human_review"):
            n_referred += 1  # لا حكم آلي للمقارنة: الإجابة أُحيلت ولم تدخل في الدرجة الآلية
            continue
        for name, hv in x["checks"].items():
            av = (j.get("checks") or {}).get(name)
            h = CHECK_VALUES[hv]
            if av is None or h is None:
                n_cd += h is None
                continue
            pc = per_check.setdefault(name, {"agree": 0, "of": 0})
            pc["of"] += 1
            pc["agree"] += av == h
    return {"layer": "behaviour", "scope": SCOPE_NOTE["behaviour"], "reviewer": labels["reviewer"], "lock": lock,
            "n_items": len(labels["labels"]), "n_pending": n_pending,
            "n_referred_no_automated_verdict": n_referred, "n_check_cannot_determine_excluded": n_cd,
            "by_check": per_check, "min_denominator_for_percent": MIN_DENOMINATOR_FOR_PERCENT,
            "percentages": "لا تُحسب نسب في هذه الطبقة؛ الأعداد والمقامات فقط.", "computed_at": riyadh_now()}


def cmd_compute(layer: str, root: Path = ROOT, gold_dir: Path = GOLD_DIR) -> dict:
    verify_official(root, gold_dir)
    runs = load_runs(root / "evaluation" / "official")
    res = compute_quran(runs, gold_dir) if layer == "quran" else compute_behaviour(runs, gold_dir)
    write_json(gold_dir / layer / "agreement.json", res)
    verify_official(root, gold_dir)
    return res


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["extract", "lock", "compute"])
    p.add_argument("layer", nargs="?", choices=["quran", "behaviour"])
    a = p.parse_args(argv)
    if a.command == "extract":
        cmd_extract()
    elif not a.layer:
        p.error("حدّد الطبقة: quran أو behaviour")
    elif a.command == "lock":
        print(cmd_lock(a.layer))
    else:
        print(json.dumps(cmd_compute(a.layer)["by_automated_verdict" if a.layer == "quran" else "by_check"],
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
