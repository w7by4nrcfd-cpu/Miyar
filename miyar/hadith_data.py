"""طبقة تحميل الأحاديث — مستقلة عن المصدر.

كل مجموعة بيانات مسجّلة في ``data/hadith/manifest.json`` (المسار، الصيغة، الدور، المصدر، الترخيص).
هذه الوحدة تقرأ الـmanifest وتحوّل كل صيغة إلى سجل موحّد ``Hadith``، فلا يعرف أي كود آخر
من أين جاءت البيانات. لاستبدال المصدر:
  1. ولّد ملفاً بإحدى الصيغ المدعومة (``flat_jsonl`` أو ``graded_items_json``)،
     أو سجّل صيغة جديدة بـ ``register_format``.
  2. عدّل ``manifest.json`` فقط.

لا تنزيل ولا اتصال بالشبكة هنا: الملفات محلية بالكامل.

**الاعتماد:** manifest يحمل ``approved``. المجموعة الخارجية الحالية (``data/unapproved/hadith/``) غير معتمدة
(خارج مصادر الحزمة العلمية)، فلا تُحمَّل إلا بـ ``allow_unapproved=True`` في الاختبارات والتطوير، ولا تُستخدم في
الموقع ولا في أي تشغيل رسمي. التحقق من أحاديث حالات الاختبار يعتمد على ``miyar/hadith_manual.py``.
"""

from __future__ import annotations

import gzip
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable, Iterator

ROLES = {
    "corpus": "أحاديث مقبولة يُطابَق عليها (مثل الصحيحين)",
    "not_authentic": "أحاديث حكم العلماء بعدم صحتها؛ لاختبار الاختلاق والنسبة الخاطئة",
}

DEFAULT_DATA_DIR = Path(os.environ.get("MIYAR_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
UNAPPROVED_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "unapproved"


class UnapprovedSource(ValueError):
    """مجموعة أحاديث غير معتمدة (خارج الحزمة العلمية) طُلب تحميلها دون allow_unapproved=True."""


@dataclass(frozen=True)
class Grade:
    grade: str  # الحكم بلفظه الأصلي كما في المصدر
    scholar: str | None = None  # None إذا كان الحكم مستفاداً من الكتاب نفسه (مثل الصحيحين)
    basis: str = "scholar"  # "scholar" أو "collection"
    translation_ar: dict | None = None  # ترجمة من المشروع مع review_status


@dataclass(frozen=True)
class Hadith:
    id: str
    dataset: str
    role: str
    collection: str
    collection_ar: str
    number: str
    text: str
    grades: tuple[Grade, ...]
    source: str
    status: str | None = None  # مثل "fabricated" في مجموعة not_authentic


@dataclass(frozen=True)
class Dataset:
    name: str
    path: Path
    format: str
    role: str
    source: str
    license_declared: str | None
    license_clear: bool
    license_note: str | None = None


# ---------- الصيغ ----------
Reader = Callable[[Path, Dataset], Iterable[Hadith]]
_FORMATS: dict[str, Reader] = {}


def register_format(name: str) -> Callable[[Reader], Reader]:
    """تسجيل قارئ لصيغة ملف جديدة."""

    def deco(fn: Reader) -> Reader:
        _FORMATS[name] = fn
        return fn

    return deco


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, encoding="utf-8")


@register_format("flat_jsonl")
def _read_flat_jsonl(path: Path, ds: Dataset) -> Iterator[Hadith]:
    """سطر JSON لكل حديث: id، collection، collection_ar، number، text، grade، grade_basis، source."""
    with _open_text(path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            yield Hadith(
                id=r["id"],
                dataset=ds.name,
                role=ds.role,
                collection=r["collection"],
                collection_ar=r["collection_ar"],
                number=str(r["number"]),
                text=r["text"],
                grades=(Grade(grade=r["grade"], basis=r.get("grade_basis", "scholar")),),
                source=r["source"],
            )


@register_format("graded_items_json")
def _read_graded_items(path: Path, ds: Dataset) -> Iterator[Hadith]:
    """ملف JSON فيه items[]، ولكل عنصر grades[] بأحكام عدة علماء."""
    with _open_text(path) as f:
        doc = json.load(f)
    for r in doc["items"]:
        yield Hadith(
            id=r["id"],
            dataset=ds.name,
            role=ds.role,
            collection=r["collection"],
            collection_ar=r["collection_ar"],
            number=str(r["number"]),
            text=r["text"],
            grades=tuple(
                Grade(grade=g["grade"], scholar=g["scholar"], translation_ar=g.get("translation_ar"))
                for g in r["grades"]
            ),
            source=r["source"],
            status=r.get("status"),
        )


# ---------- المخزن ----------
class HadithStore:
    def __init__(self, datasets: list[Dataset], hadiths: list[Hadith]):
        self.datasets = {d.name: d for d in datasets}
        self._all = hadiths
        self._by_id: dict[str, Hadith] = {}
        for h in hadiths:
            if h.id in self._by_id:
                raise ValueError(f"معرّف مكرر: {h.id}")
            self._by_id[h.id] = h

    @classmethod
    def load(cls, data_dir: str | Path | None = None, allow_unapproved: bool = False) -> "HadithStore":
        d = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        return _load_cached(str(d.resolve()), allow_unapproved)

    def __len__(self) -> int:
        return len(self._all)

    def all(self) -> list[Hadith]:
        return list(self._all)

    def by_role(self, role: str) -> list[Hadith]:
        return [h for h in self._all if h.role == role]

    def by_dataset(self, name: str) -> list[Hadith]:
        return [h for h in self._all if h.dataset == name]

    def get(self, hadith_id: str) -> Hadith | None:
        return self._by_id.get(hadith_id)


def _parse_manifest(hadith_dir: Path, allow_unapproved: bool = False) -> list[Dataset]:
    m = json.loads((hadith_dir / "manifest.json").read_text(encoding="utf-8"))
    if m.get("approved") is False and not allow_unapproved:
        raise UnapprovedSource(
            f"مجموعة أحاديث غير معتمدة في {hadith_dir}: لا تُستخدم في الموقع ولا في التشغيلات الرسمية "
            "(allow_unapproved=True للاختبارات والتطوير فقط)"
        )
    out = []
    for e in m["datasets"]:
        if e["format"] not in _FORMATS:
            raise ValueError(f"صيغة غير مدعومة: {e['format']}")
        if e["role"] not in ROLES:
            raise ValueError(f"دور غير معروف: {e['role']}")
        path = (hadith_dir / e["path"]).resolve()
        if hadith_dir.resolve() not in path.parents:
            raise ValueError(f"مسار خارج مجلد البيانات: {e['path']}")
        out.append(
            Dataset(
                name=e["name"],
                path=path,
                format=e["format"],
                role=e["role"],
                source=e["source"],
                license_declared=e.get("license_declared"),
                license_clear=bool(e.get("license_clear", False)),
                license_note=e.get("license_note"),
            )
        )
    return out


def _validate(h: Hadith) -> None:
    for field in ("id", "collection", "collection_ar", "number", "text", "source"):
        if not getattr(h, field):
            raise ValueError(f"{h.id or '?'}: الحقل {field} فارغ")
    if not h.grades or not all(g.grade for g in h.grades):
        raise ValueError(f"{h.id}: لا حكم")


@lru_cache(maxsize=4)
def _load_cached(data_dir: str, allow_unapproved: bool = False) -> HadithStore:
    hadith_dir = Path(data_dir) / "hadith"
    datasets = _parse_manifest(hadith_dir, allow_unapproved)
    hadiths: list[Hadith] = []
    for ds in datasets:
        for h in _FORMATS[ds.format](ds.path, ds):
            _validate(h)
            hadiths.append(h)
    return HadithStore(datasets, hadiths)


def load_hadiths(data_dir: str | Path | None = None, allow_unapproved: bool = False) -> HadithStore:
    return HadithStore.load(data_dir, allow_unapproved)
