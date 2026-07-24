"""Hand-review aid: scan a leads CSV for onboarding/implementation/
customer-success language in `one_liner` and `long_description`, and print
candidates.

This does NOT write `known_onboarding_vendor` or any other label — the
ground-truth list (data/known_onboarding_vendors.yaml, read by
adapters/onboarding_vendors.py) is hand-curated on purpose, see README "Why
the vendor-list match is exact-domain-only, no fuzzy matching." Keyword
matching here is deliberately loose (recall over precision) because a human
is filtering the output before anything gets added to that list — the two
are different bars: this script surfaces candidates, it never decides.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any

# Loose on purpose: this is a candidate finder for a human, not a
# classifier. Broad terms (e.g. "rollout") are fine here even though
# they'd be too noisy for an automated label.
CANDIDATE_TERMS: dict[str, list[str]] = {
    "onboarding": [r"\bonboard(?:ing|s|ed)?\b"],
    "implementation": [
        r"\bimplementation\b",
        r"\brollout\b",
        r"\broll-out\b",
        r"\bgo-live\b",
    ],
    "customer_success": [
        r"\bcustomer success\b",
        r"\bcustomer experience\b",
        r"\bclient success\b",
        r"\bsuccess manager\b",
        r"\bcsm\b",
        r"\bcustomer education\b",
    ],
}

_COMPILED_TERMS = {
    category: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    for category, patterns in CANDIDATE_TERMS.items()
}


def matching_categories(text: str) -> list[str]:
    """Pure: which candidate categories does this text hit, if any."""
    if not text:
        return []
    return [
        category
        for category, patterns in _COMPILED_TERMS.items()
        if any(p.search(text) for p in patterns)
    ]


def scan_row(row: dict[str, Any]) -> list[str]:
    """Pure: categories matched across this row's one_liner + long_description."""
    combined = f"{row.get('one_liner') or ''} {row.get('long_description') or ''}"
    return matching_categories(combined)


def find_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pure: rows with at least one category match, annotated with which."""
    candidates = []
    for row in rows:
        categories = scan_row(row)
        if categories:
            candidates.append(
                {
                    "domain": row.get("domain"),
                    "company_name": row.get("company_name"),
                    "matched_categories": categories,
                    "one_liner": row.get("one_liner"),
                }
            )
    return candidates


def load_leads(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def print_candidates(candidates: list[dict[str, Any]]) -> None:
    print(f"=== {len(candidates)} candidate(s) for hand review ===")
    for c in candidates:
        categories = ", ".join(c["matched_categories"])
        print(f"\n{c['domain']}  [{categories}]")
        print(f"  {c['company_name']}: {c['one_liner']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Scan a leads CSV for onboarding/implementation/customer-success "
            "language and print candidates for hand review. Does not label."
        )
    )
    parser.add_argument("--leads-csv", type=Path, default=Path("out/leads_latest.csv"))
    args = parser.parse_args(argv)

    rows = load_leads(args.leads_csv)
    candidates = find_candidates(rows)
    print_candidates(candidates)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
