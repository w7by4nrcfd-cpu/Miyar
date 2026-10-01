import json
from pathlib import Path

import pytest

from miyar.hadith_data import UNAPPROVED_DATA_DIR, Hadith, UnapprovedSource, load_hadiths, register_format

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def store():
    # المجموعة الخارجية غير معتمدة: تُحمَّل في الاختبارات بإذن صريح فقط
    return load_hadiths(UNAPPROVED_DATA_DIR, allow_unapproved=True)


def test_unapproved_set_is_refused_by_default():
    with pytest.raises(UnapprovedSource):
        load_hadiths(UNAPPROVED_DATA_DIR)


def test_default_data_dir_has_no_hadith_corpus():
    # data/hadith/ فيه الملف اليدوي المعتمد فقط، ولا مجموعة يحمّلها هذا المحمّل
    assert not (ROOT / "data/hadith/manifest.json").exists()
    with pytest.raises(FileNotFoundError):
        load_hadiths()


def test_unapproved_flag_in_manifest(tmp_path):
    data = _mini_data(tmp_path, [_entry()], {"alt.jsonl": json.dumps(FIXTURE_HADITH, ensure_ascii=False) + "\n"},
                      approved=False)
    with pytest.raises(UnapprovedSource):
        load_hadiths(data)
    assert len(load_hadiths(data, allow_unapproved=True)) == 1


def test_loads_all_datasets_from_manifest(store):
    assert set(store.datasets) == {"sahihayn", "weak_fabricated"}
    assert len(store.by_dataset("sahihayn")) == 14940
    assert len(store.by_dataset("weak_fabricated")) == 18


def test_roles(store):
    assert {h.role for h in store.by_role("corpus")} == {"corpus"}
    assert all(h.status == "fabricated" for h in store.by_role("not_authentic"))


def test_unified_record(store):
    h = store.get("bukhari:1")
    assert h.collection_ar == "صحيح البخاري" and h.number == "1"
    assert h.grades[0].grade == "صحيح" and h.grades[0].basis == "collection" and h.grades[0].scholar is None
    w = store.get("ibnmajah:49")
    albani = next(g for g in w.grades if g.scholar == "Al-Albani")
    assert albani.grade == "Mawdu"  # اللفظ الأصلي من المصدر
    assert albani.translation_ar["review_status"] == "pending"


def test_license_status_is_exposed(store):
    for ds in store.datasets.values():
        assert ds.license_declared == "Unlicense" and ds.license_clear is False and ds.license_note


def _mini_data(tmp_path: Path, manifest_entries: list[dict], files: dict[str, str], approved: bool | None = None) -> Path:
    d = tmp_path / "data" / "hadith"
    d.mkdir(parents=True)
    for name, content in files.items():
        (d / name).write_text(content, encoding="utf-8")
    m = {"schema_version": 1, "datasets": manifest_entries}
    if approved is not None:
        m["approved"] = approved
    (d / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    return tmp_path / "data"


def _entry(**kw):
    base = {"name": "FIXTURE", "path": "alt.jsonl", "format": "flat_jsonl", "role": "corpus", "source": "FIXTURE"}
    base.update(kw)
    return base


# ⚠️ FIXTURE — سجل حديث مصطنع لاختبار طبقة التحميل فقط. ليس حديثاً ولا نصاً شرعياً ولا بيانات حقيقية،
# ويُكتب في مجلد مؤقت (tmp_path) لا في data/.
FIXTURE_HADITH = {
    "id": "FIXTURE:1",
    "collection": "FIXTURE",
    "collection_ar": "FIXTURE — مصدر وهمي للاختبار",
    "number": "1",
    "text": "FIXTURE — نص وهمي للاختبار وليس حديثاً",
    "grade": "FIXTURE-grade",
    "grade_basis": "collection",
    "source": "FIXTURE (test only, not real data)",
}


def test_swap_source_by_manifest_only(tmp_path):
    data = _mini_data(tmp_path, [_entry()], {"alt.jsonl": json.dumps(FIXTURE_HADITH, ensure_ascii=False) + "\n"})
    s = load_hadiths(data)
    assert len(s) == 1 and s.get("FIXTURE:1").collection_ar == FIXTURE_HADITH["collection_ar"]


def test_register_new_format(tmp_path):
    @register_format("test_tsv")
    def _read(path, ds):
        for line in path.read_text(encoding="utf-8").splitlines():
            hid, text = line.split("\t")
            yield Hadith(hid, ds.name, ds.role, "FIXTURE", "FIXTURE", "1", text, (), "FIXTURE")

    data = _mini_data(tmp_path, [_entry(path="a.tsv", format="test_tsv")], {"a.tsv": "FIXTURE:tsv\tFIXTURE — نص وهمي"})
    with pytest.raises(ValueError, match="لا حكم"):  # التحقق يرفض حديثاً بلا حكم
        load_hadiths(data)


@pytest.mark.parametrize(
    "entry,msg",
    [
        (_entry(format="nope"), "صيغة غير مدعومة"),
        (_entry(role="nope"), "دور غير معروف"),
        (_entry(path="../../etc.jsonl"), "مسار خارج"),
    ],
)
def test_manifest_validation(tmp_path, entry, msg):
    data = _mini_data(tmp_path, [entry], {"alt.jsonl": json.dumps(FIXTURE_HADITH) + "\n"})
    with pytest.raises(ValueError, match=msg):
        load_hadiths(data)


def test_duplicate_ids_rejected(tmp_path):
    line = json.dumps(FIXTURE_HADITH) + "\n"
    data = _mini_data(tmp_path, [_entry()], {"alt.jsonl": line + line})
    with pytest.raises(ValueError, match="معرّف مكرر"):
        load_hadiths(data)
