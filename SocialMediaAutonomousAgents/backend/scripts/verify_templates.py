"""Verify every TEMPLATE_MAP preset validates and compiles.

Run from backend/:  python -m scripts.verify_templates

Posting templates are validated with kind="post"; anything outside
VALID_POSTING_TEMPLATE_IDS (i.e. reply_mode) is a reply-family spec and
validated with kind="reply". Exits non-zero if any template fails.
"""

from __future__ import annotations

import sys

from app.pipeline.runbooks.templates import TEMPLATE_MAP, VALID_POSTING_TEMPLATE_IDS
from app.pipeline.spec.catalog import get_tool_catalog
from app.pipeline.spec.compiler import compile_spec
from app.pipeline.spec.validator import validate_spec

ACCOUNT_ID = "verify_account"


def main() -> int:
    catalog = get_tool_catalog()
    failures = 0

    for template_id, factory in TEMPLATE_MAP.items():
        kind = "post" if template_id in VALID_POSTING_TEMPLATE_IDS else "reply"
        spec = factory(ACCOUNT_ID)

        report = validate_spec(spec, catalog, kind=kind)
        try:
            compile_spec(spec)
            compiled, compile_err = True, ""
        except Exception as exc:  # compile_spec raises on a shape/catalog defect
            compiled, compile_err = False, f"{type(exc).__name__}: {exc}"

        ok = report.ok and compiled
        failures += not ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {template_id:<14} kind={kind:<5} validate.ok={report.ok} compile={compiled}")
        if not report.ok:
            print(f"         validate errors: {report.codes()}")
        if not compiled:
            print(f"         compile error: {compile_err}")

    print(f"\n{len(TEMPLATE_MAP) - failures}/{len(TEMPLATE_MAP)} templates passed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
