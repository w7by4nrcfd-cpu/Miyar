"""الملف اليدوي المعتمد للأحاديث: البنية، وقواعد القيم، وعزل المجموعة الخارجية غير المعتمدة عن الموقع والتشغيل الرسمي."""

from pathlib import Path

from miyar.hadith_manual import entry_errors, entry_status, link_allowed, load_manual, manual_errors

ROOT = Path(__file__).resolve().parent.parent


def test_manual_file_is_valid():
    doc = load_manual()
    assert manual_errors(doc) == [], manual_errors(doc)
    assert {e["id"] for e in doc["entries"]} >= {f"H-00{i}" for i in range(1, 10)}


def test_links_only_from_package_sources():
    assert link_allowed("https://dorar.net/hadith/sharh/1") and link_allowed("https://shamela.ws/book/1/2")
    assert not link_allowed("https://example.com/dorar.net") and not link_allowed("ftp://dorar.net/x")
    assert not link_allowed("https://github.com/fawazahmed0/hadith-api")


def test_entry_rules():
    found = {"id": "H-X", "case_ids": ["EXT-029"], "kind": "found", "text": "نص", "source": "كتاب 1",
             "link": "https://dorar.net/h/1", "grade": "موضوع", "grade_by": "الألباني",
             "entered_by": "س", "entered_at": "2026-10-02"}
    assert entry_errors(found) == [] and entry_status(found) == "complete"
    assert entry_status({**found, "text": ""}) == "pending"
    assert entry_errors({**found, "grade_by": ""})  # الدرجة بلا قائلها
    assert entry_errors({**found, "link": "https://example.com/x"})
    assert entry_errors({**found, "entered_at": "2/10"})
    assert entry_errors({**found, "kind": "other"})
    rng = {"id": "H-Y", "case_ids": ["EXT-042"], "kind": "collection_range", "source": "صحيح البخاري",
           "max_number": "7563", "link": "https://shamela.ws/x", "entered_by": "س", "entered_at": "2026-10-02"}
    assert entry_errors(rng)  # max_number نصي


def test_unapproved_set_not_used_by_site_or_official_path():
    hits = []
    for base in ("web", "evaluation/official", "miyar"):
        for p in (ROOT / base).rglob("*"):
            if p.is_file() and p.suffix in {".html", ".js", ".json", ".py", ".md"} and p.name != "hadith_data.py":
                t = p.read_text(encoding="utf-8", errors="ignore")
                if "fawazahmed0" in t or "sahihayn.jsonl" in t or "weak_fabricated" in t:
                    hits.append(str(p.relative_to(ROOT)))
    assert hits == [], hits


def test_pending_hadith_fragments_stay_hidden_from_site():
    """نصوص أسئلة EXT-029 إلى EXT-032 (مقاطعها أصلها مجموعة غير معتمدة) محجوبة في الموقع ما دام مدخلها اليدوي غير مكتمل."""
    import json
    from miyar.hadith_manual import entries_by_id
    entries = entries_by_id()
    cases = json.loads((ROOT / "testsets/extended_v1.json").read_text(encoding="utf-8"))["cases"]
    site = "".join(p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "web").rglob("*") if p.is_file()
                   and p.suffix in {".html", ".js", ".json"})
    checked = 0
    for c in cases:
        dc = c.get("data_check", {})
        if dc.get("type") == "hadith_fabricated" and entry_status(entries[dc["manual_ref"]]) != "complete":
            assert dc["fragment"] not in site, c["id"]
            checked += 1
    assert checked >= 1
