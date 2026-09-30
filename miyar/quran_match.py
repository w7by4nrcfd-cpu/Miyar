"""مطابقة حرفية لنصوص القرآن الكريم — بلا نموذج لغوي.

يحمّل نص Tanzil (الإملائي والعثماني)، ويوحّده بـ miyar.normalize، ثم:
- ``find``: يبحث عن مقطع منقول بتطابق حرفي تام (بعد التوحيد) في أي موضع من المصحف،
  ولو امتد عبر آيات متتالية من السورة نفسها.
- ``verify``: يتحقق من نسبة مقطع إلى سورة وآية محددتين، ويعيد أحد التصنيفات الثلاثة:
  ``supported`` / ``needs_review`` / ``wrong_or_missing`` مع السبب والشاهد.
- ``closest``: يقترح أقرب الآيات لمقطع لا يطابق حرفياً (للتنبيه على النقل الخاطئ).

قاعدة ثابتة: لا يصدر ``supported`` إلا عند تطابق حرفي فعلي في الموضع المذكور.
ملفات البيانات لا تُعدَّل (شرط ترخيص Tanzil)؛ كل التوحيد يتم في الذاكرة.
"""

from __future__ import annotations

import math
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from .normalize import normalize

SUPPORTED = "supported"
NEEDS_REVIEW = "needs_review"
WRONG_OR_MISSING = "wrong_or_missing"

TOTAL_VERSES = 6236
TOTAL_SURAS = 114

# عتبة التشابه التي يُعد فوقها المقطع «نقلاً محرّفاً» للآية المذكورة لا نصاً آخر
ALTERED_THRESHOLD = 0.80
# أقل عدد كلمات لبحث عام في كل المصحف (المقاطع الأقصر كثيرة التكرار)
MIN_FIND_TOKENS = 3

_ELLIPSIS = re.compile(r"\.{2,}|…|ـ{3,}")

DEFAULT_DATA_DIR = Path(os.environ.get("MIYAR_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))


@dataclass(frozen=True)
class Verse:
    sura: int
    aya: int
    sura_name: str
    text: str  # الرسم العثماني كما في Tanzil (للعرض)
    text_simple: str  # الرسم الإملائي كما في Tanzil

    @property
    def ref(self) -> str:
        return f"{self.sura}:{self.aya}"


@dataclass(frozen=True)
class Location:
    sura: int
    aya_start: int
    aya_end: int
    script: str  # "simple" أو "uthmani": الرسم الذي وقع فيه التطابق

    @property
    def ref(self) -> str:
        if self.aya_start == self.aya_end:
            return f"{self.sura}:{self.aya_start}"
        return f"{self.sura}:{self.aya_start}-{self.aya_end}"


@dataclass
class Suggestion:
    sura: int
    aya: int
    sura_name: str
    text: str
    score: float

    @property
    def ref(self) -> str:
        return f"{self.sura}:{self.aya}"


@dataclass
class CitationCheck:
    status: str
    reason: str
    quote: str
    cited: str
    found_at: list[Location] = field(default_factory=list)
    cited_text: str | None = None
    similarity: float | None = None
    suggestions: list[Suggestion] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "quote": self.quote,
            "cited": self.cited,
            "cited_text": self.cited_text,
            "found_at": [loc.ref for loc in self.found_at],
            "similarity": self.similarity,
            "suggestions": [
                {"ref": s.ref, "sura_name": s.sura_name, "text": s.text, "score": s.score}
                for s in self.suggestions
            ],
        }


class _Stream:
    """سلسلة كلمات المصحف كاملة لرسم واحد، مع مرجع كل كلمة إلى آيتها."""

    def __init__(self, verses: list[Verse], attr: str):
        self.tokens: list[str] = []
        self.owner: list[int] = []  # رقم الآية (فهرس في verses) لكل كلمة
        self.verse_span: list[tuple[int, int]] = []  # [بداية، نهاية) كلمات كل آية
        for i, v in enumerate(verses):
            toks = normalize(getattr(v, attr)).split()
            start = len(self.tokens)
            self.tokens.extend(toks)
            self.owner.extend([i] * len(toks))
            self.verse_span.append((start, len(self.tokens)))
        self.first: dict[str, list[int]] = defaultdict(list)
        for pos, tok in enumerate(self.tokens):
            self.first[tok].append(pos)

    def occurrences(self, q: list[str], lo: int = 0, hi: int | None = None) -> list[int]:
        """مواضع بداية q متطابقة تماماً داخل [lo, hi)."""
        if not q:
            return []
        hi = len(self.tokens) if hi is None else hi
        n = len(q)
        return [
            p
            for p in self.first.get(q[0], ())
            if lo <= p and p + n <= hi and self.tokens[p : p + n] == q
        ]


class QuranIndex:
    def __init__(self, verses: list[Verse]):
        if len(verses) != TOTAL_VERSES:
            raise ValueError(f"عدد الآيات {len(verses)} لا يساوي {TOTAL_VERSES}")
        self.verses = verses
        self._pos: dict[tuple[int, int], int] = {(v.sura, v.aya): i for i, v in enumerate(verses)}
        self._sura_range: dict[int, tuple[int, int]] = {}
        for i, v in enumerate(verses):
            lo, _ = self._sura_range.get(v.sura, (i, i))
            self._sura_range[v.sura] = (lo, i + 1)
        self._streams = {"simple": _Stream(verses, "text_simple"), "uthmani": _Stream(verses, "text")}
        # فهرس مقلوب للكلمات (رسم إملائي + عثماني) لاقتراح أقرب الآيات
        self._inv: dict[str, set[int]] = defaultdict(set)
        for s in self._streams.values():
            for pos, tok in enumerate(s.tokens):
                self._inv[tok].add(s.owner[pos])
        self._idf = {t: math.log(TOTAL_VERSES / (1 + len(ids))) for t, ids in self._inv.items()}

    # ---------- تحميل ----------
    @classmethod
    def load(cls, data_dir: str | Path | None = None) -> "QuranIndex":
        d = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        return _load_cached(str(d.resolve()))

    # ---------- استعلامات أساسية ----------
    def verse(self, sura: int, aya: int) -> Verse | None:
        i = self._pos.get((sura, aya))
        return None if i is None else self.verses[i]

    def sura_name(self, sura: int) -> str | None:
        r = self._sura_range.get(sura)
        return None if r is None else self.verses[r[0]].sura_name

    def sura_length(self, sura: int) -> int:
        r = self._sura_range.get(sura)
        return 0 if r is None else r[1] - r[0]

    def verses_range(self, sura: int, aya_start: int, aya_end: int | None = None) -> list[Verse]:
        aya_end = aya_start if aya_end is None else aya_end
        return [v for a in range(aya_start, aya_end + 1) if (v := self.verse(sura, a))]

    # ---------- البحث الحرفي ----------
    def find(self, quote: str, min_tokens: int = MIN_FIND_TOKENS) -> list[Location]:
        """كل المواضع التي يرد فيها المقطع حرفياً (بعد التوحيد) داخل سورة واحدة.

        إن احتوى المقطع على حذف (... أو …) فيجب أن ترد أجزاؤه بالترتيب في المقطع نفسه
        من السورة، ويُعاد الموضع من أول جزء إلى آخره.
        """
        segments = _segments(quote)
        if not segments or sum(len(s) for s in segments) < min_tokens:
            return []
        results: list[Location] = []
        seen: set[tuple[int, int, int]] = set()
        for script, stream in self._streams.items():
            for start in stream.occurrences(segments[0]):
                sura = self.verses[stream.owner[start]].sura
                vlo, vhi = self._sura_range[sura]
                hi = stream.verse_span[vhi - 1][1]
                end = _match_rest(stream, segments, start, hi)
                if end is None:
                    continue
                a1 = self.verses[stream.owner[start]].aya
                a2 = self.verses[stream.owner[end - 1]].aya
                key = (sura, a1, a2)
                if key not in seen:
                    seen.add(key)
                    results.append(Location(sura, a1, a2, script))
        results.sort(key=lambda loc: (loc.sura, loc.aya_start, loc.aya_end))
        return results

    def _in_range(self, quote: str, sura: int, a1: int, a2: int) -> Location | None:
        segments = _segments(quote)
        if not segments:
            return None
        i1, i2 = self._pos[(sura, a1)], self._pos[(sura, a2)]
        for script, stream in self._streams.items():
            lo, hi = stream.verse_span[i1][0], stream.verse_span[i2][1]
            for start in stream.occurrences(segments[0], lo, hi):
                if _match_rest(stream, segments, start, hi) is not None:
                    return Location(sura, a1, a2, script)
            # اختلاف المسافات وحده (مثل «ياايها» مقابل «يا ايها») ليس تحريفاً
            if _joined_match(segments, stream.tokens[lo:hi]):
                return Location(sura, a1, a2, script)
        return None

    # ---------- الاقتراحات ----------
    def similarity(self, quote: str, sura: int, a1: int, a2: int | None = None) -> float:
        """أعلى تشابه حرفي (0..1) بين المقطع وأي نافذة من الآيات المذكورة، في الرسمين."""
        a2 = a1 if a2 is None else a2
        q = normalize(_ELLIPSIS.sub(" ", quote)).split()
        if not q:
            return 0.0
        i1, i2 = self._pos[(sura, a1)], self._pos[(sura, a2)]
        best = 0.0
        qs = " ".join(q)
        for stream in self._streams.values():
            lo, hi = stream.verse_span[i1][0], stream.verse_span[i2][1]
            toks = stream.tokens[lo:hi]
            n = len(q)
            sizes = {max(1, n - 1), n, n + 1}
            for size in sizes:
                if size >= len(toks):
                    windows = [toks]
                else:
                    windows = [toks[j : j + size] for j in range(len(toks) - size + 1)]
                for w in windows:
                    best = max(best, SequenceMatcher(None, qs, " ".join(w), autojunk=False).ratio())
        return round(best, 3)

    def closest(self, quote: str, limit: int = 3) -> list[Suggestion]:
        """أقرب الآيات لمقطع لا يطابق حرفياً (ترتيب بالكلمات المشتركة ثم بالتشابه الحرفي)."""
        q = normalize(_ELLIPSIS.sub(" ", quote)).split()
        if not q:
            return []
        weights: Counter[int] = Counter()
        for tok in set(q):
            for vid in self._inv.get(tok, ()):
                weights[vid] += self._idf.get(tok, 0.0)
        out: list[Suggestion] = []
        for vid, _ in weights.most_common(25):
            v = self.verses[vid]
            score = self.similarity(quote, v.sura, v.aya)
            out.append(Suggestion(v.sura, v.aya, v.sura_name, v.text, score))
        out.sort(key=lambda s: (-s.score, s.sura, s.aya))
        return out[:limit]

    # ---------- التحقق من الإسناد ----------
    def verify(self, quote: str, sura: int, aya: int, aya_end: int | None = None) -> CitationCheck:
        """التحقق من أن المقطع هو نص الآية (أو الآيات) المذكورة حرفياً."""
        aya_end = aya if aya_end is None else aya_end
        cited = f"{sura}:{aya}" if aya_end == aya else f"{sura}:{aya}-{aya_end}"

        n = self.sura_length(sura)
        if n == 0 or not (1 <= aya <= aya_end <= n):
            return CitationCheck(
                WRONG_OR_MISSING,
                "invalid_reference",
                quote,
                cited,
                found_at=self.find(quote),
                suggestions=self.closest(quote),
            )

        cited_text = " ".join(v.text for v in self.verses_range(sura, aya, aya_end))
        q_tokens = [t for s in _segments(quote) for t in s]
        if len(q_tokens) < 2:
            return CitationCheck(NEEDS_REVIEW, "quote_too_short", quote, cited, cited_text=cited_text)

        loc = self._in_range(quote, sura, aya, aya_end)
        if loc is not None:
            return CitationCheck(SUPPORTED, "exact_match", quote, cited, [loc], cited_text, 1.0)

        elsewhere = self.find(quote, min_tokens=2)
        if elsewhere:
            return CitationCheck(WRONG_OR_MISSING, "wrong_reference", quote, cited, elsewhere, cited_text)

        sim = self.similarity(quote, sura, aya, aya_end)
        suggestions = self.closest(quote)
        if sim >= ALTERED_THRESHOLD:
            # قريب جداً من الآية المذكورة لكنه ليس نصها: نقل محرّف
            return CitationCheck(
                WRONG_OR_MISSING, "altered_text", quote, cited, [], cited_text, sim, suggestions
            )
        # لا تطابق ولا قرب كافٍ: قد يكون نقلاً بالمعنى أو نصاً غير موجود — يحتاج تحقق بشري
        return CitationCheck(NEEDS_REVIEW, "not_found", quote, cited, [], cited_text, sim, suggestions)


# ---------- أدوات داخلية ----------
def _segments(quote: str) -> list[list[str]]:
    parts = [normalize(p).split() for p in _ELLIPSIS.split(quote)]
    return [p for p in parts if p]


def _match_rest(stream: _Stream, segments: list[list[str]], start: int, hi: int) -> int | None:
    """بعد تطابق الجزء الأول عند start، ابحث عن بقية الأجزاء بالترتيب. يعيد نهاية التطابق."""
    pos = start + len(segments[0])
    for seg in segments[1:]:
        occ = stream.occurrences(seg, pos, hi)
        if not occ:
            return None
        pos = occ[0] + len(seg)
    return pos


def _joined_match(segments: list[list[str]], window: list[str]) -> bool:
    """تطابق بعد حذف المسافات، بشرط أن يبدأ كل جزء وينتهي عند حدود كلمات."""
    joined = "".join(window)
    bounds = {0}
    acc = 0
    for tok in window:
        acc += len(tok)
        bounds.add(acc)
    pos = 0
    for seg in segments:
        part = "".join(seg)
        i = joined.find(part, pos)
        while i >= 0 and not (i in bounds and i + len(part) in bounds):
            i = joined.find(part, i + 1)
        if i < 0:
            return False
        pos = i + len(part)
    return True


def _parse_simple(path: Path) -> dict[tuple[int, int], tuple[str, str]]:
    root = ET.parse(path).getroot()
    out = {}
    for sura in root.iter("sura"):
        s, name = int(sura.get("index")), sura.get("name")
        for aya in sura.iter("aya"):
            out[(s, int(aya.get("index")))] = (name, aya.get("text"))
    return out


_BASMALA = "بسم الله الرحمن الرحيم"


def _parse_uthmani(path: Path) -> dict[tuple[int, int], str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        s, a, text = line.split("|", 2)
        out[(int(s), int(a))] = text
    return out


def _drop_leading_basmala(sura: int, aya: int, text: str) -> str:
    """ملف Tanzil العثماني يسبق الآية الأولى من كل سورة بالبسملة (عدا الفاتحة والتوبة).

    البسملة هنا ليست جزءاً من الآية، فتُفصل في الذاكرة فقط (الملف لا يُعدَّل).
    """
    if aya != 1 or sura in (1, 9):
        return text
    words = text.split(" ")
    if normalize(" ".join(words[:4])) == _BASMALA:
        return " ".join(words[4:])
    return text


@lru_cache(maxsize=4)
def _load_cached(data_dir: str) -> QuranIndex:
    d = Path(data_dir) / "quran"
    simple = _parse_simple(d / "quran-simple.xml")
    uthmani = _parse_uthmani(d / "quran-uthmani.txt")
    if simple.keys() != uthmani.keys():
        raise ValueError("اختلاف في مراجع الآيات بين الرسم الإملائي والعثماني")
    verses = [
        Verse(s, a, simple[(s, a)][0], _drop_leading_basmala(s, a, uthmani[(s, a)]), simple[(s, a)][1])
        for (s, a) in sorted(simple)
    ]
    return QuranIndex(verses)


def load_quran(data_dir: str | Path | None = None) -> QuranIndex:
    return QuranIndex.load(data_dir)
