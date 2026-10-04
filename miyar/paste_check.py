"""وضع ثانوي «الصق نصاً وتحقق»: استخراج حتمي بقواعد ثابتة (بلا نموذج لغوي) ثم مطابقة برمجية.

هذه الوحدة هي **المرجع** لنسخة المتصفح ``web/assets/check-core.js``: الاثنتان تطبّقان القواعد نفسها،
واختبار التطابق (``tests/test_paste_check.py`` و``tests/web/check.test.mjs``) يشغّلهما على الحالات نفسها.

الاستخراج (لا يستنتج شيئاً لم يُكتب):
- **آية:** نص بين ﴿ ﴾ أو بين { }؛ أو نص بين «» أو "" أو “” يليه مباشرة موضع قرآني بين قوسين.
- **الموضع القرآني:** أول قوسين ( ) أو [ ] بعد النص مباشرة (يُسمح بمسافات وفاصلة أو نقطتين قبله):
  اسم سورة من بيانات Quranpedia مع رقم الآية (أو رقمين لمدى)، أو «رقم السورة:رقم الآية».
- **حديث:** نص بين «» أو "" أو “” لم يُعدّ آية، وقبله علامة نسبة إلى النبي ﷺ (مثل «قال رسول الله» أو ﷺ)
  أو بعده علامة تخريج (مثل «رواه» أو «أخرجه» أو «متفق عليه»). وموضعه ما بعد النص حتى نهاية الجملة إن ذُكر فيه التخريج.

المطابقة:
- الآية مع موضع: ``QuranIndex.verify`` كما هي (حرفية بعد ``normalize``).
- الآية بلا موضع: ``QuranIndex.find`` (3 كلمات على الأقل)؛ فإن لم تُوجد قورنت بأقرب الآيات:
  تشابه ≥ ``ALTERED_THRESHOLD`` ← «خاطئ» (نص محرّف)، وإلا ← «يحتاج تحقق».
- الحديث: ``hadith_match.verify`` على **المدخلات المكتملة فقط** من الملف اليدوي؛ وما عداها «يحتاج تحقق».

الاقتراحات (أقرب الآيات) مرتّبة ترتيباً حتمياً (الوزن ثم رقم الآية) لتتطابق النسختان.
لا يحكم هذا الوضع على مساعد، ولا يصدر فتوى، ولا يولّد نصاً شرعياً: كل نص معروض منقول من البيانات.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from . import hadith_match
from .hadith_manual import entry_status, load_manual
from .normalize import normalize
from .quran_match import (
    ALTERED_THRESHOLD, MIN_FIND_TOKENS, NEEDS_REVIEW, SUPPORTED, WRONG_OR_MISSING, QuranIndex, _segments,
)

ROOT = Path(__file__).resolve().parent.parent
PARITY_FILE = ROOT / "tests" / "fixtures" / "paste_parity.json"

# علامات الاقتباس: (فاتح، مغلق). ﴿ ﴾ تُكتب في الاتجاهين في النصوص المنقولة
QURAN_BRACKETS = (("﴿", "﴾"), ("﴾", "﴿"), ("{", "}"))
QUOTES = (("«", "»"), ("“", "”"), ('"', '"'))
MAX_QUOTE_CHARS = 2000
REF_LOOKAHEAD = 12  # أقصى ما يفصل نهاية النص عن قوس الموضع
REF_MAX_CHARS = 40  # أقصى طول لما بين قوسي الموضع
HADITH_BEFORE = 60  # نافذة علامة النسبة قبل النص
HADITH_AFTER = 80  # نافذة التخريج بعد النص
REF_FILLER = {"سوره", "الايه", "ايه", "الايات", "ايات", "رقم", "اية", "الاية"}
HADITH_MARKERS_BEFORE = ("قال رسول الله", "قال النبي", "عن النبي", "عن رسول الله", "صلي الله عليه وسلم")
SALLA = "ﷺ"  # رمز لا يبقى بعد normalize (يُعامل كترقيم)، فيُبحث عنه في النص الخام
HADITH_MARKERS_AFTER = ("رواه", "اخرجه", "متفق عليه")
MAX_SUGGESTIONS = 3
_DIGITS = re.compile(r"[0-9]+")  # أرقام لاتينية فقط (normalize يحوّل الهندية والفارسية إليها)
SUGGESTION_POOL = 25

def _strip_al(name: str) -> str:
    return name[2:].strip() if name.startswith("ال") else name


def sura_by_name(index: QuranIndex) -> dict[str, int]:
    """الاسم الموحّد (بأل وبدونها) ← رقم السورة."""
    out: dict[str, int] = {}
    for s in range(1, 115):
        n = normalize(index.sura_name(s) or "")
        out.setdefault(n, s)
        out.setdefault(_strip_al(n), s)
    return out


def parse_reference(after: str, names: dict[str, int]) -> dict | None:
    """موضع قرآني في أول قوسين بعد النص مباشرة، أو None."""
    m = re.match(r"^[\s،,:.\-–]{0,%d}[(\[]([^()\[\]]{1,%d})[)\]]" % (REF_LOOKAHEAD, REF_MAX_CHARS), after)
    if not m:
        return None
    toks = normalize(m.group(1)).split()
    nums = [int(t) for t in toks if _DIGITS.fullmatch(t)]
    words = [t for t in toks if not _DIGITS.fullmatch(t) and t not in REF_FILLER]
    if words:
        name = " ".join(words)
        sura = names.get(name) or names.get(_strip_al(name))
        if sura is None or not 1 <= len(nums) <= 2:
            return None
        aya, aya_end = nums[0], (nums[1] if len(nums) == 2 else None)
    else:
        if not 2 <= len(nums) <= 3:
            return None
        sura, aya, aya_end = nums[0], nums[1], (nums[2] if len(nums) == 3 else None)
    return {"text": m.group(0).strip(" ،,:.-–"), "sura": sura, "aya": aya, "aya_end": aya_end}


def _spans(text: str, pairs) -> list[tuple[int, int, int, int]]:
    """(بداية الفاتح، بداية النص، نهاية النص، نهاية المغلق) لكل اقتباس، بلا تداخل، بالترتيب."""
    out = []
    for o, c in pairs:
        i = 0
        while (a := text.find(o, i)) >= 0:
            b = text.find(c, a + 1)
            if b < 0:
                break
            if 0 < b - a - 1 <= MAX_QUOTE_CHARS:
                out.append((a, a + 1, b, b + 1))
            i = b + 1
    out.sort()
    kept, last = [], -1
    for s in out:
        if s[0] >= last:
            kept.append(s)
            last = s[3]
    return kept


def extract(text: str, index: QuranIndex) -> list[dict]:
    """الاستشهادات بالترتيب: {"kind", "quote", "start", "ref" أو "cited"}."""
    names = sura_by_name(index)
    found = []
    taken: list[tuple[int, int]] = []
    for a, qs, qe, b in _spans(text, QURAN_BRACKETS):
        quote = text[qs:qe].strip()
        if quote:
            found.append({"kind": "quran", "quote": quote, "start": a, "ref": parse_reference(text[b:], names)})
            taken.append((a, b))
    for a, qs, qe, b in _spans(text, QUOTES):
        if any(x < b and a < y for x, y in taken):
            continue
        quote = text[qs:qe].strip()
        if not quote:
            continue
        ref = parse_reference(text[b:], names)
        if ref is not None:
            found.append({"kind": "quran", "quote": quote, "start": a, "ref": ref})
            continue
        before_raw = text[max(0, a - HADITH_BEFORE):a]
        before = f" {normalize(before_raw)} "
        after_raw = re.split(r"[.\n!؟?]", text[b:b + HADITH_AFTER], maxsplit=1)[0]
        after = normalize(after_raw)
        has_before = SALLA in before_raw or any(f" {normalize(m)} " in before for m in HADITH_MARKERS_BEFORE)
        has_after = any(f" {normalize(m)} " in f" {after} " for m in HADITH_MARKERS_AFTER)
        if has_before or has_after:
            cited = after_raw.strip(" ،,:-–()[]") if has_after else None
            found.append({"kind": "hadith", "quote": quote, "start": a, "cited": cited or None})
    found.sort(key=lambda c: c["start"])
    return found


def suggestions(index: QuranIndex, quote: str, limit: int = MAX_SUGGESTIONS) -> list[dict]:
    """أقرب الآيات ترتيباً حتمياً: أعلى وزن مشترك (ثم رقم الآية)، ثم التشابه الحرفي (ثم السورة والآية)."""
    q = normalize(re.sub(r"\.{2,}|…|ـ{3,}", " ", quote)).split()
    if not q:
        return []
    weights: dict[int, float] = defaultdict(float)
    for tok in sorted(set(q)):
        for vid in index._inv.get(tok, ()):
            weights[vid] += index._idf.get(tok, 0.0)
    pool = sorted(weights, key=lambda v: (-round(weights[v], 9), v))[:SUGGESTION_POOL]
    scored = []
    for vid in pool:
        v = index.verses[vid]
        scored.append((-index.similarity(quote, v.sura, v.aya), v.sura, v.aya))
    scored.sort()
    return [{"ref": f"{s}:{a}", "score": -neg} for neg, s, a in scored[:limit]]


def _verse_payload(index: QuranIndex, ref: str) -> dict:
    s, rest = ref.split(":")
    a1, _, a2 = rest.partition("-")
    vs = index.verses_range(int(s), int(a1), int(a2 or a1))
    return {"ref": ref, "sura_name": index.sura_name(int(s)), "text": " ".join(v.text_simple for v in vs)}


def check_quran(item: dict, index: QuranIndex) -> dict:
    quote, ref = item["quote"], item.get("ref")
    if ref is not None:
        c = index.verify(quote, ref["sura"], ref["aya"], ref["aya_end"])
        status, reason, sim = c.status, c.reason, c.similarity
        found_at = [loc.ref for loc in c.found_at]
        cited = c.cited
        valid_ref = reason != "invalid_reference"
    else:
        cited, valid_ref = None, False
        if sum(len(s) for s in _segments(quote)) < MIN_FIND_TOKENS:
            status, reason, sim, found_at = NEEDS_REVIEW, "quote_too_short", None, []
        else:
            locs = index.find(quote)
            found_at = [loc.ref for loc in locs]
            if locs:
                status, reason, sim = SUPPORTED, "exact_match_unreferenced", 1.0
            else:
                sugg = suggestions(index, quote, 1)
                sim = sugg[0]["score"] if sugg else 0.0
                status = WRONG_OR_MISSING if sim >= ALTERED_THRESHOLD else NEEDS_REVIEW
                reason = "altered_text_unreferenced" if status == WRONG_OR_MISSING else "not_found"
    out = {
        "kind": "quran", "quote": quote, "ref_text": ref["text"] if ref else None, "cited": cited,
        "status": status, "reason": reason, "similarity": sim,
        "found_at": [_verse_payload(index, r) for r in found_at],
        "cited_verse": _verse_payload(index, cited) if cited and valid_ref else None,
        "suggestions": [],
    }
    if status != SUPPORTED and not found_at:
        out["suggestions"] = [{**_verse_payload(index, s["ref"]), "score": s["score"]} for s in suggestions(index, quote)]
    return out


def complete_manual(doc: dict | None = None) -> dict:
    """الملف اليدوي بمدخلاته المكتملة فقط (ما عداها لا يُستعمل في هذا الوضع)."""
    doc = load_manual() if doc is None else doc
    return {"entries": [e for e in doc.get("entries", []) if entry_status(e) == "complete"]}


def check_hadith(item: dict, manual: dict) -> dict:
    c = hadith_match.verify(item["quote"], item.get("cited"), manual)
    keys = ("kind", "text", "query", "source", "grade", "grade_by", "link", "max_number")
    entry = {k: c.entry[k] for k in keys if k in c.entry} if c.entry else None
    return {"kind": "hadith", "quote": item["quote"], "cited": item.get("cited"), "status": c.status,
            "reason": c.reason, "entry_id": c.entry_id, "entry": entry}


def check_text(text: str, index: QuranIndex | None = None, manual: dict | None = None) -> list[dict]:
    index = QuranIndex.load() if index is None else index
    manual = complete_manual() if manual is None else manual
    return [check_quran(i, index) if i["kind"] == "quran" else check_hadith(i, manual) for i in extract(text, index)]


# ---------- بيانات المتصفح واختبار التطابق ----------
def quran_web_data(index: QuranIndex, source: dict) -> dict:
    return {
        "source": source,
        "names": [index.sura_name(s) for s in range(1, 115)],
        "lens": [index.sura_length(s) for s in range(1, 115)],
        "simple": [v.text_simple for v in index.verses],
        "uthmani": [v.text for v in index.verses],
    }


def normalized_digest(index: QuranIndex) -> str:
    """بصمة نص المصحف موحّداً (الرسمان)، لتتحقق نسخة المتصفح من أن توحيدها يطابق بايثون على كل الآيات."""
    h = hashlib.sha256()
    for v in index.verses:
        h.update((normalize(v.text_simple) + "\n" + normalize(v.text) + "\n").encode("utf-8"))
    return h.hexdigest()


def parity_cases() -> list[str]:
    """نصوص اختبار التطابق: أسئلة الحالات الرسمية والموسّعة (فيها الآيات المحرّفة والأحاديث المختلقة)،
    ونصوص اصطناعية موسومة FIXTURE تغطي كل فرع، مع آيات منقولة حرفياً من البيانات."""
    from .runner import load_cases  # استيراد متأخر

    texts = [c["prompt"] for c in load_cases([ROOT / "testsets" / "official_v0.json", ROOT / "testsets" / "extended_v1.json"])]
    idx = QuranIndex.load()
    v = idx.verse
    manual = complete_manual()
    found = [e for e in manual["entries"] if e["kind"] == "found"]
    h0 = found[0]
    texts += [
        f"FIXTURE: قال تعالى: ﴿{v(112, 1).text}﴾ (الإخلاص: 1).",
        f"FIXTURE: ﴿{v(2, 255).text_simple}﴾ [البقرة 255]",
        f"FIXTURE: {{{v(1, 2).text_simple}}} (1:2)",
        f"FIXTURE: «{v(103, 1).text_simple} {v(103, 2).text_simple}» (سورة العصر، الآيات 1-2)",
        f"FIXTURE: ﴿{v(112, 1).text_simple}﴾ (البقرة: 1)",
        f"FIXTURE: ﴿{v(1, 2).text_simple}﴾ (الفاتحة: 99)",
        f"FIXTURE: ﴿{v(1, 2).text_simple}﴾",
        "FIXTURE: ﴿الحمد لله رب الناس﴾ (الفاتحة: 2)",
        "FIXTURE: ﴿الحمد لله رب الناس﴾",
        "FIXTURE: ﴿هذا نص اصطناعي ليس من القرآن الكريم إطلاقاً﴾ (البقرة: 3)",
        "FIXTURE: ﴿هذا نص اصطناعي ليس من القرآن﴾",
        "FIXTURE: ﴿الحمد لله﴾ (الفاتحة: 2)",
        f"FIXTURE: ﴿{v(2, 1).text_simple}﴾ (سورة لا توجد: 1)",
        f"FIXTURE: ﴿{v(1, 2).text_simple}﴾ (٢:١)",
        f"FIXTURE: ﴿{v(1, 2).text_simple} ... {v(1, 4).text_simple}﴾ (الفاتحة: 2-4)",
        f"FIXTURE: قال رسول الله ﷺ: «{h0['text']}» {h0['source']}.",
        f"FIXTURE: قال النبي ﷺ: «{h0['text']}» رواه البخاري.",
        f"FIXTURE: «{h0['text']}» رواه البخاري 999999.",
        f"FIXTURE: قال رسول الله ﷺ: «{h0['text']}».",
        "FIXTURE: قال رسول الله ﷺ: «هذا نص اصطناعي ليس حديثاً في أي كتاب» رواه مسلم 5.",
        "FIXTURE: «نص بين علامتي تنصيص بلا آية ولا حديث».",
        "FIXTURE: نص بلا أي اقتباس.",
        "",
    ]
    for e in found[1:]:
        texts.append(f"FIXTURE: قال رسول الله ﷺ: «{e['text']}» {e['source']}.")
    return texts


def parity_fixture() -> dict:
    idx = QuranIndex.load()
    return {
        "note": "مولّد بـ python -m miyar.paste_check --write-parity؛ لا يُعدَّل يدوياً.",
        "normalized_digest": normalized_digest(idx),
        "cases": [{"text": t, "result": check_text(t, idx)} for t in parity_cases()],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m miyar.paste_check")
    p.add_argument("--write-parity", action="store_true", help="اكتب tests/fixtures/paste_parity.json")
    p.add_argument("text", nargs="?", help="نص للفحص (أو من stdin)")
    args = p.parse_args(argv)
    if args.write_parity:
        PARITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        PARITY_FILE.write_text(json.dumps(parity_fixture(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(PARITY_FILE.relative_to(ROOT))
        return 0
    text = args.text if args.text is not None else sys.stdin.read()
    print(json.dumps(check_text(text), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
