"""نشر نتائج التشغيلات الرسمية إلى الموقع: evaluation/official/ ← web/data/ (docs/BUILD_SPEC.md §3).

    python scripts/publish_results.py           # يكتب web/data/results.json وweb/data/cases/<id>.json
    python scripts/publish_results.py --check   # لا يكتب؛ رمز خروج 1 إن لم تكن الملفات متزامنة مع السجلات

حتمي، ويرفض كل ما ليس OFFICIAL_RUN داخل evaluation/official/ (DEV_RUN وLIVE_DEMO وFIXTURE)، ولا يكتب شيئاً عند أي خطأ.
لا يستدعي أي نموذج. نشر الملفات إلى الموقع الحي يتم بالدمج إلى main، وبموافقة صاحب المشروع الصريحة فقط.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from miyar.publish import PublishError, build, diff, planned_files, write  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python scripts/publish_results.py")
    p.add_argument("--check", action="store_true", help="تحقق من التزامن دون كتابة")
    args = p.parse_args(argv)
    try:
        results, case_files = build()
    except PublishError as e:
        print(f"مرفوض، ولم يُكتب أي ملف:\n{e}", file=sys.stderr)
        return 1
    files = planned_files(results, case_files)
    changed = diff(files)
    if args.check:
        if changed:
            print("غير متزامن مع evaluation/official/: " + "، ".join(changed), file=sys.stderr)
            return 1
        print(f"متزامن: {len(results['runs'])} تشغيلاً رسمياً، و{len(case_files)} حالة.")
        return 0
    write(files)
    print(f"نُشر {len(results['runs'])} تشغيلاً رسمياً، و{len(case_files)} حالة؛ تغيّر {len(changed)} ملفاً.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
