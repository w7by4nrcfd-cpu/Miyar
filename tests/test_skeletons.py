"""حارس مؤقت: runner وjudge وscoring هياكل بلا منطق حتى 4 أكتوبر (قاعدة «لا نواة قبل أيام التحدي»).

كل دالة عامة جسمها docstring ثم raise NotImplementedError فقط. يُحذف هذا الملف عند بدء بناء كل وحدة
في أيام التحدي (الخطوة الأولى في docs/BUILD_PLAN.md)، ويُسجَّل حذفه في CHANGELOG.
"""

import ast
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULES = ("judge", "scoring")  # runner بُني في 2026-10-04 (اليوم 1) فحُذف من الحارس


def _functions(name):
    tree = ast.parse((ROOT / "miyar" / f"{name}.py").read_text(encoding="utf-8"))
    return [n for n in tree.body if isinstance(n, ast.FunctionDef)]


def test_modules_import():
    for name in MODULES:
        importlib.import_module(f"miyar.{name}")


def test_every_function_is_an_unimplemented_stub():
    for name in MODULES:
        funcs = _functions(name)
        assert funcs, name
        for f in funcs:
            body = f.body
            if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
                body = body[1:]  # docstring
            assert len(body) == 1 and isinstance(body[0], ast.Raise), f"{name}.{f.name}: فيه منطق قبل 4 أكتوبر"
            exc = body[0].exc
            target = exc.func if isinstance(exc, ast.Call) else exc
            assert isinstance(target, ast.Name) and target.id == "NotImplementedError", f"{name}.{f.name}"
