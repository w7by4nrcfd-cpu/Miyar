"""توحيد النص العربي للمطابقة الحرفية.

الهدف: أن يتطابق النص نفسه مهما اختلف التشكيل أو صور الهمزة أو علامات الترقيم،
دون تغيير أي حرف أصلي آخر. لا يستخدم أي نموذج لغوي.

القواعد (كلها قابلة للتعطيل عبر المعاملات):
- حذف التشكيل والحركات (U+064B–U+065F)، والألف الخنجرية (U+0670)،
  وعلامات المصحف الصغيرة (U+06D6–U+06ED)، والتطويل (U+0640).
- توحيد صور الألف: أ إ آ ٱ ٲ ٳ ٵ ← ا
- توحيد الهمزة على الواو والياء: ؤ ← و ، ئ ← ي (الهمزة المفردة ء تبقى).
- ى ← ي ، ة ← ه
- الحروف الفارسية/الأردية الشائعة: ک ← ك ، ی ← ي ، ہ ← ه
- الأرقام العربية الهندية والفارسية ← أرقام لاتينية.
- حذف علامات الترقيم والرموز (ومنها أقواس المصحف ﴿ ﴾) وضم المسافات.
"""

from __future__ import annotations

import re
import unicodedata

# التشكيل والحركات وما يلحق بها
_DIACRITICS = re.compile(
    "["
    "ؐ-ؚ"  # علامات فوق الحروف (صلى الله عليه وسلم الصغيرة وغيرها)
    "ً-ٟ"  # الحركات والتنوين والشدة والسكون والمدة والهمزة فوق/تحت
    "ٰ"  # الألف الخنجرية
    "ۖ-ۭ"  # علامات الوقف والرموز الصغيرة في المصحف
    "࣓-ࣿ"  # علامات قرآنية إضافية
    "]"
)
_TATWEEL = "ـ"
_ZERO_WIDTH = re.compile("[​-‏‪-‮⁦-⁩﻿]")

_ALEF_MAP = str.maketrans({c: "ا" for c in "أإآٱٲٳٵ"})
_HAMZA_CARRIER_MAP = str.maketrans({"ؤ": "و", "ئ": "ي"})
_YA_MAP = str.maketrans({"ى": "ي", "ی": "ي", "ې": "ي"})
_TA_MARBUTA_MAP = str.maketrans({"ة": "ه"})
_PERSIAN_MAP = str.maketrans({"ک": "ك", "ڪ": "ك", "ہ": "ه", "ھ": "ه"})
_DIGIT_MAP = str.maketrans(
    {**{chr(0x0660 + i): str(i) for i in range(10)}, **{chr(0x06F0 + i): str(i) for i in range(10)}}
)


def _is_word_char(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return cat[0] in ("L", "N") or cat == "Mn"


def strip_diacritics(text: str) -> str:
    """حذف التشكيل والتطويل وعلامات المصحف فقط، دون أي توحيد آخر."""
    return _DIACRITICS.sub("", text).replace(_TATWEEL, "")


def normalize(
    text: str,
    *,
    diacritics: bool = True,
    alef: bool = True,
    hamza_carriers: bool = True,
    ya: bool = True,
    ta_marbuta: bool = True,
    punctuation: bool = True,
    digits: bool = True,
) -> str:
    """يعيد نصاً موحّداً صالحاً للمطابقة الحرفية."""
    if not text:
        return ""
    # NFC أولاً حتى تُعامل الصور المركّبة والمفككة معاملة واحدة
    # (مثل ا + U+0653 ← آ ، و + U+0654 ← ؤ).
    t = unicodedata.normalize("NFC", text)
    t = _ZERO_WIDTH.sub("", t)
    if diacritics:
        t = strip_diacritics(t)
    if alef:
        t = t.translate(_ALEF_MAP)
    if hamza_carriers:
        t = t.translate(_HAMZA_CARRIER_MAP)
    if ya:
        t = t.translate(_YA_MAP)
    if ta_marbuta:
        t = t.translate(_TA_MARBUTA_MAP)
    t = t.translate(_PERSIAN_MAP)
    if digits:
        t = t.translate(_DIGIT_MAP)
    if punctuation:
        t = "".join(ch if _is_word_char(ch) else " " for ch in t)
    return " ".join(t.split())


def tokens(text: str, **kwargs) -> list[str]:
    """تقسيم النص الموحّد إلى كلمات."""
    return normalize(text, **kwargs).split()
