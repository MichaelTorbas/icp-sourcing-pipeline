#!/usr/bin/env python3
"""PostToolUse hook (matcher: Bash) — enforces CLAUDE.md's CSV schema
contract deterministically, independent of pipeline/main.py's own code.
See docs/DESIGN.md "Why this is a hook, not a function call" for why this
exists outside the codebase rather than as a validation function main.py
calls: a function call is only as reliable as every future edit to the
code that's supposed to call it; this runs regardless of what main.py's
code does or doesn't do.

Checks every out/*.csv file after each Bash tool call:
  - has a `domain` column in its header
  - has at least one data row (CLAUDE.md: never write a CSV for a run
    that produced zero valid rows)
  - every data row has a non-empty `domain` value (CLAUDE.md: a row with
    no domain is dropped before write, never written with a null)

Runs unconditionally on every Bash call rather than trying to detect "was
this a pipeline run" — checking a handful of small CSVs is cheap, and a
CSV in out/ that violates the contract is a violation regardless of which
command produced or left it there.

Stdlib only, deliberately: this must run correctly with a bare `python3`,
not `uv run`, since a hook shouldn't depend on the project's own
virtualenv being set up.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent.parent / "out"


def validate_csv(path: Path) -> list[str]:
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        if "domain" not in fieldnames:
            return [f"{path.name}: no 'domain' column in header"]
        rows = list(reader)

    if not rows:
        return [
            f"{path.name}: header present but zero data rows "
            "(CLAUDE.md: never write a CSV for a run with zero valid rows)"
        ]

    errors = []
    for line_num, row in enumerate(rows, start=2):  # header is line 1
        if not (row.get("domain") or "").strip():
            errors.append(f"{path.name}: line {line_num} has an empty domain")
    return errors


def main() -> int:
    if not OUT_DIR.is_dir():
        return 0

    all_errors = []
    for csv_path in sorted(OUT_DIR.glob("*.csv")):
        all_errors.extend(validate_csv(csv_path))

    if all_errors:
        print("CSV schema contract violated (CLAUDE.md):", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
