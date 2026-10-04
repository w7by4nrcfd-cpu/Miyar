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
from difflib import SequenceMatcher
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
# عرض «لم يُطابَق حرفياً، أقرب مدخل كذا» للأحاديث: شروط محافظة كلها مطلوبة معاً (لا يصدر معه «مؤيَّد» أبداً)
NEAR_MIN_WORDS = 3  # أقل عدد كلمات (كما MIN_MATCH_WORDS في hadith_match)
NEAR_MIN_WORD_LEN = 3  # أقصر كلمة تُقبل مختلفة (الكلمات القصيرة ملتبسة: «في» و«من»…)
NEAR_MIN_RATIO = 0.92  # أدنى تشابه حرفي (بعد التوحيد) بين النص والنافذة المقارَنة من المدخل
MAX_DIFF_CHUNKS = 5

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


def _extract_all(text: str, index: QuranIndex) -> tuple[list[dict], list[dict]]:
    """(المستخرَج، المتخطّى): المتخطّى نصوص بين علامتي تنصيص لم تُقرأ لها آية ولا نسبة حديثية."""
    names = sura_by_name(index)
    found = []
    skipped = []
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
        else:
            skipped.append({"quote": quote, "start": a})
    found.sort(key=lambda c: c["start"])
    return found, skipped


def extract(text: str, index: QuranIndex) -> list[dict]:
    """الاستشهادات بالترتيب: {"kind", "quote", "start", "ref" أو "cited"}."""
    return _extract_all(text, index)[0]


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


def word_diff(a: list[str], b: list[str]) -> list[dict]:
    """فروق على مستوى الكلمات بأطول تتابع مشترك (LCS) وكسر تعادل ثابت، ينقله check-core.js حرفياً.

    كل فرق مقطع متصل من الكلمات المختلفة: ``q``/``w`` مدى [من، إلى) في القائمتين، مع كلماتهما.
    """
    n, m = len(a), len(b)
    lcs = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            lcs[i][j] = lcs[i + 1][j + 1] + 1 if a[i] == b[j] else max(lcs[i + 1][j], lcs[i][j + 1])
    chunks: list[dict] = []
    cur: dict | None = None
    i = j = 0

    def close() -> None:
        nonlocal cur
        if cur is not None:
            cur["q"], cur["w"] = [cur.pop("q0"), i], [cur.pop("w0"), j]
            cur["q_words"], cur["w_words"] = a[cur["q"][0]:i], b[cur["w"][0]:j]
            chunks.append(cur)
            cur = None

    while i < n or j < m:
        if i < n and j < m and a[i] == b[j]:
            close()
            i += 1
            j += 1
            continue
        if cur is None:
            cur = {"q0": i, "w0": j}
        if j >= m or (i < n and lcs[i + 1][j] >= lcs[i][j + 1]):
            i += 1
        else:
            j += 1
    close()
    return chunks


def quran_diff(index: QuranIndex, quote: str, ref: str) -> dict | None:
    """الكلمة المختلفة بين المقطع وأقرب نافذة من نص الموضع (الرسمان، والإملائي أولاً عند التعادل)."""
    s, rest = ref.split(":")
    a1, _, a2 = rest.partition("-")
    sura, aya1, aya2 = int(s), int(a1), int(a2 or a1)
    q = normalize(re.sub(r"\.{2,}|…|ـ{3,}", " ", quote)).split()
    if not q or (sura, aya1) not in index._pos or (sura, aya2) not in index._pos:
        return None
    i1, i2 = index._pos[(sura, aya1)], index._pos[(sura, aya2)]
    qs = " ".join(q)
    best = None  # (تشابه، الرسم، بداية النافذة، كلمات النافذة)
    for script, stream in index._streams.items():
        lo, hi = stream.verse_span[i1][0], stream.verse_span[i2][1]
        toks = stream.tokens[lo:hi]
        for size in sorted({max(1, len(q) - 1), len(q), len(q) + 1}):
            windows = [(0, toks)] if size >= len(toks) else [(j, toks[j:j + size]) for j in range(len(toks) - size + 1)]
            for j, w in windows:
                r = SequenceMatcher(None, qs, " ".join(w), autojunk=False).ratio()
                if best is None or r > best[0]:
                    best = (r, script, j, w)
    if best is None:
        return None
    chunks = word_diff(q, best[3])[:MAX_DIFF_CHUNKS]
    return {"ref": ref, "script": best[1], "similarity": round(best[0], 3), "offset": best[2], "chunks": chunks}


def _lev1(a: str, b: str) -> bool:
    """هل بين الكلمتين حرف واحد بالضبط (استبدال أو حذف أو إضافة)؟"""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(short) and short[i] == long_[i]:
        i += 1
    return short[i:] == long_[i + 1:]


def _near_pair(a: list[str], b: list[str]) -> tuple[int, float] | None:
    """نافذتان بطول واحد: كلمة واحدة مختلفة بحرف واحد، وتشابه عام فوق العتبة. يعيد (موضع الكلمة، التشابه)."""
    diffs = [k for k in range(len(a)) if a[k] != b[k]]
    if len(diffs) != 1:
        return None
    k = diffs[0]
    if len(a[k]) < NEAR_MIN_WORD_LEN or len(b[k]) < NEAR_MIN_WORD_LEN or not _lev1(a[k], b[k]):
        return None
    r = SequenceMatcher(None, " ".join(a), " ".join(b), autojunk=False).ratio()
    return (k, r) if r >= NEAR_MIN_RATIO else None


_ENTRY_KEYS = ("kind", "text", "query", "source", "grade", "grade_by", "link", "max_number")


def near_entry(quote: str, manual: dict) -> dict | None:
    """أقرب مدخل ``found`` مكتمل إن اختلف نص الاستشهاد عنه بحرف واحد في كلمة واحدة فقط (وإلا None).

    شروط محافظة كلها مطلوبة: ≥ 3 كلمات، كلمة واحدة مختلفة بحرف واحد وطول كلٍّ منهما ≥ 3، وتشابه ≥ 0.92.
    الأقصر يُقارَن بنوافذ الأطول. وإن وافق أكثر من مدخل أو أكثر من نافذة فلا يُعرض شيء (التباس).
    للعرض والمقارنة فقط: لا يمرّ هذا على ``hadith_match.verify``، ولا يصدر بسببه «مؤيَّد» أبداً.
    """
    q = normalize(quote).split()
    if len(q) < NEAR_MIN_WORDS:
        return None
    hits = []
    for e in manual["entries"]:
        if e.get("kind") != "found":
            continue
        p = normalize(e.get("text") or "").split()
        if len(p) < NEAR_MIN_WORDS:
            continue
        for s in range(abs(len(q) - len(p)) + 1):
            qw, pw = (q[s:s + len(p)], p) if len(q) >= len(p) else (q, p[s:s + len(q)])
            r = _near_pair(qw, pw)
            if r is not None:
                k, ratio = r
                qi, pi = (s + k, k) if len(q) >= len(p) else (k, s + k)
                hits.append({"entry_id": e["id"], "entry": {k2: e[k2] for k2 in _ENTRY_KEYS if k2 in e},
                             "q_word": q[qi], "entry_word": p[pi], "q_index": qi, "entry_index": pi,
                             "similarity": round(ratio, 3)})
    return hits[0] if len(hits) == 1 else None


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
    out["diff"] = None
    if status == WRONG_OR_MISSING and reason in ("altered_text", "altered_text_unreferenced"):
        target = cited if reason == "altered_text" else (out["suggestions"][0]["ref"] if out["suggestions"] else None)
        out["diff"] = quran_diff(index, quote, target) if target else None
    return out


def complete_manual(doc: dict | None = None) -> dict:
    """الملف اليدوي بمدخلاته المكتملة فقط (ما عداها لا يُستعمل في هذا الوضع)."""
    doc = load_manual() if doc is None else doc
    return {"entries": [e for e in doc.get("entries", []) if entry_status(e) == "complete"]}


def check_hadith(item: dict, manual: dict) -> dict:
    c = hadith_match.verify(item["quote"], item.get("cited"), manual)
    keys = ("kind", "text", "query", "source", "grade", "grade_by", "link", "max_number")
    entry = {k: c.entry[k] for k in keys if k in c.entry} if c.entry else None
    reason, near = c.reason, None
    if c.reason == "no_manual_entry":  # لا مدخل حرفي: قد يوجد مدخل قريب يُعرض للمقارنة وحدها
        near = near_entry(item["quote"], manual)
        if near is not None:
            assert c.status == NEEDS_REVIEW  # لا «مؤيَّد» مع الاقتراب أبداً
            reason = "near_match_not_literal"
    return {"kind": "hadith", "quote": item["quote"], "cited": item.get("cited"), "status": c.status,
            "reason": reason, "entry_id": c.entry_id, "entry": entry, "near": near}


def check_text(text: str, index: QuranIndex | None = None, manual: dict | None = None) -> list[dict]:
    index = QuranIndex.load() if index is None else index
    manual = complete_manual() if manual is None else manual
    return [check_quran(i, index) if i["kind"] == "quran" else check_hadith(i, manual) for i in extract(text, index)]


def hints_for(text: str, index: QuranIndex | None = None, manual: dict | None = None) -> list[dict]:
    """تلميحات بلا حكم: نص بين علامتي تنصيص لم يُفحص (لا علامة نسبة) لكنه يطابق أو يقارب مدخلاً في الملف اليدوي."""
    index = QuranIndex.load() if index is None else index
    manual = complete_manual() if manual is None else manual
    out = []
    for sk in _extract_all(text, index)[1]:
        lit = [e for e in hadith_match.find_entries(sk["quote"], manual) if e.get("kind") == "found"]
        if len(lit) == 1:
            e = lit[0]
            out.append({"quote": sk["quote"], "match": "literal", "entry_id": e["id"], "near": None,
                        "entry": {k: e[k] for k in _ENTRY_KEYS if k in e}})
            continue
        near = near_entry(sk["quote"], manual) if not lit else None
        if near is not None:
            out.append({"quote": sk["quote"], "match": "near", "entry_id": near["entry_id"], "near": near,
                        "entry": near["entry"]})
    return out


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
        # حرف محذوف: (أ) داخل نص الحديث، (ب) داخل عبارة النسبة، وما يتبعه من تلميح للنص غير المستخرج
        "FIXTURE: قال رسول الله ﷺ: «اطلبوا العلم ولو بالصن» رواه البخاري 1.",
        "FIXTURE: قال رسول الله ﷺ: «اطبوا العلم ولو بالصين»",
        "FIXTURE: قال رسول الله ﷺ: «العلم ولو بالصن»",
        "FIXTURE: قال رسول الله ﷺ: «اطلبوا العم ولو بالصن»",
        "FIXTURE: قال رسول اله ﷺ: «اطلبوا العلم ولو بالصين»",
        "FIXTURE: قال رسول اله: «اطلبوا العلم ولو بالصين»",
        "FIXTURE: قال رسول اله: «اطلبوا العلم ولو بالصن»",
        "FIXTURE: قال رسو الله: «اطلبوا العلم ولو بالصن» ثم «حب الوطن من الايمان»",
        "FIXTURE: قال رسول اله: «نص اصطناعي لا يقارب أي مدخل في الملف اليدوي»",
        "FIXTURE: قال النبي ﷺ: «اعمل لدنياك كأنك تعيش أبدا واعمل لاخرتك كأنك تموت عدا»",
        # الآيات: حرف محذوف داخل الآية (بموضع وبلا موضع)، وبكلمة قصيرة، وفي اسم السورة
        "FIXTURE: قال تعالى: ﴿قل هو الله أح﴾ (الإخلاص: 1).",
        "FIXTURE: قال تعالى: ﴿قل هو الله أح﴾",
        "FIXTURE: قال تعالى: ﴿قل ه الله أحد﴾ (الإخلاص: 1).",
        "FIXTURE: قا تعالى: ﴿قل هو الله أحد﴾ (الإخلاص: 1).",
        "FIXTURE: قال تعالى: ﴿قل هو الله أحد﴾ (الإخلا: 1).",
        "FIXTURE: ﴿ذلك من أنباء الغيب نوحيه إليك وما كنت لديهم إذ ألقوا أقلامهم أيهم يكفل مريم﴾ (آل عمران: 44)",
        "FIXTURE: ﴿ذلك من أنباء الغيب نوحيه إليك وما كنت لديهم إذ ألقوا أقلامهم أيهم يكفل مريم﴾",
        f"FIXTURE: ﴿{v(1, 2).text_simple.replace('رب', 'ربب')}﴾ (الفاتحة: 2)",
        f"FIXTURE: ﴿{v(1, 2).text_simple} {v(1, 3).text_simple}﴾ (الفاتحة: 2-3)",
    ]
    for e in found[1:]:
        texts.append(f"FIXTURE: قال رسول الله ﷺ: «{e['text']}» {e['source']}.")
    return texts


def near_fuzz_texts(manual: dict | None = None) -> list[str]:
    """كل حذف لحرف واحد داخل كل كلمة من كل مدخل found (بعد التوحيد): دخل اختبار الاقتراب المحافظ."""
    manual = complete_manual() if manual is None else manual
    out = []
    for e in manual["entries"]:
        if e["kind"] != "found":
            continue
        words = normalize(e["text"]).split()
        for k, w in enumerate(words):
            for c in range(len(w)):
                mut = words[:k] + [w[:c] + w[c + 1:]] + words[k + 1:]
                out.append("قال رسول الله ﷺ: «" + " ".join(mut) + "»")
    return out


def parity_fixture() -> dict:
    idx = QuranIndex.load()
    return {
        "note": "مولّد بـ python -m miyar.paste_check --write-parity؛ لا يُعدَّل يدوياً.",
        "normalized_digest": normalized_digest(idx),
        "cases": [{"text": t, "result": check_text(t, idx), "hints": hints_for(t, idx)} for t in parity_cases()],
        "near_fuzz": [_fuzz_row(t, idx) for t in near_fuzz_texts()],
    }


def _fuzz_row(text: str, idx: QuranIndex) -> dict:
    [r] = check_text(text, idx)
    near = r["near"] or {}
    return {"text": text, "status": r["status"], "reason": r["reason"], "near_id": near.get("entry_id"),
            "q_word": near.get("q_word"), "entry_word": near.get("entry_word"), "similarity": near.get("similarity")}


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
