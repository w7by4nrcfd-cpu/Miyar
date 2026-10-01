import hashlib
from pathlib import Path

import pytest

from miyar.normalize import normalize
from miyar.quran_match import (
    NEEDS_REVIEW,
    SUPPORTED,
    WRONG_OR_MISSING,
    load_quran,
)

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def q():
    return load_quran()


# ---------- سلامة البيانات ----------
def test_data_files_match_checksums():
    for line in (ROOT / "data/quran/SHA256SUMS").read_text().splitlines():
        digest, name = line.split()
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name


def test_source_metadata_matches_files():
    # النسخة والبصمات المسجّلة في source.json (من manifest Quranpedia الرسمي) تطابق الملفات فعلاً
    import json
    src = json.loads((ROOT / "data/quran/source.json").read_text(encoding="utf-8"))
    assert src["dump_version"] and src["source"].startswith("Quranpedia.net")
    for f in src["files"]:
        raw = (ROOT / "data/quran" / f["file"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == f["sha256"] and len(raw) == f["bytes"], f["file"]
    assert {f["role"] for f in src["files"]} == {"simple", "uthmani"}


def test_bom_removed_in_memory(q):
    assert not any("\ufeff" in v.text or "\ufeff" in v.text_simple for v in q.verses)


def test_counts(q):
    assert len(q.verses) == 6236
    assert q.sura_name(1) == "الفاتحة"
    assert q.sura_name(114) == "الناس"
    assert q.sura_length(2) == 286
    assert q.sura_length(9) == 129
    assert q.sura_name(115) is None


def test_basmala_not_attached_to_first_verse(q):
    assert normalize(q.verse(112, 1).text) == "قل هو الله احد"
    assert normalize(q.verse(95, 1).text) == "والتين والزيتون"  # بسملتها بصورة «بِّسْمِ»
    assert normalize(q.verse(1, 1).text) == "بسم الله الرحمن الرحيم"
    assert not any(
        normalize(v.text).startswith("بسم الله الرحمن الرحيم")
        for v in q.verses
        if v.aya == 1 and v.sura != 1
    )


def test_verse_lookup(q):
    v = q.verse(2, 255)
    assert v.sura_name == "البقرة" and v.ref == "2:255"
    assert q.verse(2, 287) is None


# ---------- البحث الحرفي ----------
def test_find_unique(q):
    assert [loc.ref for loc in q.find("قل هو الله أحد")] == ["112:1"]


def test_find_repeated_phrase(q):
    refs = [loc.ref for loc in q.find("فبأي آلاء ربكما تكذبان")]
    assert len(refs) == 31 and all(r.startswith("55:") for r in refs)


def test_find_across_verses(q):
    locs = q.find("الله الصمد لم يلد ولم يولد")
    assert [loc.ref for loc in locs] == ["112:2-3"]


def test_find_with_ellipsis(q):
    locs = q.find("الله لا إله إلا هو الحي القيوم ... وهو العلي العظيم")
    assert [loc.ref for loc in locs] == ["2:255"]


def test_find_accepts_uthmani_input(q):
    refs = [loc.ref for loc in q.find("ٱلْحَمْدُ لِلَّهِ رَبِّ ٱلْعَٰلَمِينَ")]
    assert refs[0] == "1:2" and "40:65" in refs  # العبارة تتكرر في مواضع أخرى


def test_find_too_short_or_absent(q):
    assert q.find("الله") == []
    assert q.find("إنما الأعمال بالنيات") == []


# ---------- التحقق من الإسناد ----------
def test_verify_exact(q):
    r = q.verify("﴿لَا إِكْرَاهَ فِي الدِّينِ﴾", 2, 256)
    assert r.status == SUPPORTED and r.reason == "exact_match"
    assert "اكراه" in normalize(r.cited_text)  # النص المعروض بالرسم العثماني من المصدر


def test_verify_without_diacritics_and_hamza(q):
    assert q.verify("وقل رب زدني علما", 20, 114).status == SUPPORTED
    assert q.verify("يا ايها الذين امنوا كتب عليكم الصيام", 2, 183).status == SUPPORTED


def test_verify_spacing_difference_is_not_alteration(q):
    assert q.verify("ياأيها الذين آمنوا كتب عليكم الصيام", 2, 183).status == SUPPORTED


def test_verify_range(q):
    assert q.verify("الله الصمد لم يلد ولم يولد", 112, 2, 3).status == SUPPORTED


def test_verify_short_whole_verse(q):
    assert q.verify("الله الصمد", 112, 2).status == SUPPORTED


def test_wrong_reference(q):
    r = q.verify("قل هو الله أحد", 113, 1)
    assert r.status == WRONG_OR_MISSING and r.reason == "wrong_reference"
    assert [loc.ref for loc in r.found_at] == ["112:1"]


def test_invalid_reference(q):
    r = q.verify("قل هو الله أحد", 112, 9)
    assert r.status == WRONG_OR_MISSING and r.reason == "invalid_reference"
    assert q.verify("قل هو الله أحد", 115, 1).reason == "invalid_reference"


def test_altered_verse_is_flagged_with_correct_suggestion(q):
    r = q.verify("وقل رب زدني فهما", 20, 114)
    assert r.status == WRONG_OR_MISSING and r.reason == "altered_text"
    assert r.suggestions[0].ref == "20:114"
    r = q.verify("قل هو الله واحد", 112, 1)
    assert r.status == WRONG_OR_MISSING and r.reason == "altered_text"


def test_non_quran_text_is_needs_review_not_wrong(q):
    # غياب التطابق مع عدم القرب ≠ خطأ مؤكد: يُحال إلى التحقق
    r = q.verify("إنما الأعمال بالنيات", 2, 1)
    assert r.status == NEEDS_REVIEW and r.reason == "not_found"


def test_single_word_quote_not_supported(q):
    assert q.verify("الله", 112, 1).status == NEEDS_REVIEW


def test_no_false_supported_from_partial_word(q):
    # «هو الله» يرد في 112:1 لكن «و الله» بجزء كلمة لا يجوز أن يُعد تطابقاً
    r = q.verify("و الله احد", 112, 1)
    assert r.status != SUPPORTED


def test_to_dict(q):
    d = q.verify("قل هو الله أحد", 113, 1).to_dict()
    assert d["status"] == WRONG_OR_MISSING and d["found_at"] == ["112:1"]
