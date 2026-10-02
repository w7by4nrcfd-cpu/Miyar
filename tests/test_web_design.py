"""نظام التصميم: تباين ألوان النص ≥ 4.5:1 في الوضعين، واحترام تقليل الحركة، ولا خطوط أو موارد خارجية."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "web/assets/style.css").read_text(encoding="utf-8")

# أزواج (نص، خلفية) مستخدمة فعلاً في style.css
PAIRS = [
    ("text", "bg"), ("text", "surface"), ("text", "surface-2"),
    ("muted", "bg"), ("muted", "surface"), ("muted", "surface-2"),
    ("primary", "bg"), ("primary", "surface"), ("primary", "surface-2"),
    ("primary-text", "primary"), ("accent", "bg"),
    ("ok-fg", "ok-bg"), ("rev-fg", "rev-bg"), ("bad-fg", "bad-bg"), ("todo-fg", "todo-bg"),
]


def _tokens(block: str) -> dict:
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", block))


def _themes():
    light = _tokens(CSS.split("@media (prefers-color-scheme: dark)", 1)[0])
    dark_block = CSS.split("@media (prefers-color-scheme: dark)", 1)[1].split("\n}\n", 1)[0]
    return {"light": light, "dark": {**light, **_tokens(dark_block)}}


def _lum(hex_):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("fg,bg", PAIRS)
def test_text_contrast_at_least_4_5(theme, fg, bg):
    t = _themes()[theme]
    assert contrast(t[fg], t[bg]) >= 4.5, (theme, fg, bg, round(contrast(t[fg], t[bg]), 2))


def test_reduced_motion_respected():
    assert "@media (prefers-reduced-motion: reduce)" in CSS


def test_no_external_fonts_or_imports():
    assert "@import" not in CSS and "@font-face" not in CSS and "url(" not in CSS
    assert not list((ROOT / "web").rglob("*.woff*")) and not list((ROOT / "web").rglob("*.ttf"))


def test_dark_mode_defined():
    assert set(_themes()["dark"]) == set(_themes()["light"])
