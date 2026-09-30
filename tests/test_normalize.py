from miyar.normalize import normalize, strip_diacritics, tokens


def test_strips_tashkeel():
    assert normalize("بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ") == "بسم الله الرحمن الرحيم"


def test_unifies_alef_forms():
    assert normalize("أإآٱ") == "اااا"
    assert normalize("إِلَهِ") == normalize("اله")


def test_unifies_hamza_carriers_keeps_standalone_hamza():
    assert normalize("مُؤْمِنٌ") == "مومن"
    assert normalize("سَائِل") == "سايل"
    assert normalize("السَّمَاءِ") == "السماء"


def test_ya_and_ta_marbuta():
    assert normalize("هُدًى") == "هدي"
    assert normalize("الصَّلَاةَ") == normalize("الصلاه")


def test_uthmani_marks_and_tatweel_removed():
    # ألف خنجرية + ألف وصل + علامة صغيرة + تطويل
    assert normalize("ٱلرَّحْمَٰنِ") == "الرحمن"
    assert normalize("ذَٰلِكَ ٱلْكِتَٰبُ لَا رَيْبَ ۛ فِيهِ ۛ") == "ذلك الكتب لا ريب فيه"
    assert normalize("ٱلْـَٔاخِرَةِ") == "الاخره"


def test_punctuation_and_quran_brackets():
    assert normalize("﴿قُلْ هُوَ اللَّهُ أَحَدٌ﴾ [الإخلاص: 1]") == "قل هو الله احد الاخلاص 1"
    assert normalize("«نعم»، قال: (لا)!") == "نعم قال لا"


def test_digits():
    assert normalize("آية ١٢٣ و۴۵") == "ايه 123 و45"


def test_decomposed_forms_equal_composed():
    decomposed = "آمن"  # ا + مدة ← آمن
    assert normalize(decomposed) == normalize("آمن") == "امن"


def test_zero_width_and_whitespace():
    assert normalize("  الحمد‏  لله\n\tرب ") == "الحمد لله رب"


def test_persian_letters():
    assert normalize("کتاب یوم") == "كتاب يوم"


def test_flags_can_disable_rules():
    assert normalize("هُدًى", ya=False) == "هدى"
    assert normalize("رَحْمَة", ta_marbuta=False) == "رحمة"
    assert normalize("أَحَد", alef=False) == "أحد"
    assert normalize("قال:", punctuation=False) == "قال:"


def test_strip_diacritics_only():
    assert strip_diacritics("أَحَدٌ") == "أحد"


def test_tokens_and_empty():
    assert tokens("قُلْ هُوَ") == ["قل", "هو"]
    assert normalize("") == ""
    assert tokens("") == []


def test_latin_text_untouched():
    assert normalize("Tawhid: Oneness of God") == "Tawhid Oneness of God"
