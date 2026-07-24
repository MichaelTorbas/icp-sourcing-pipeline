"""Injects known non-YC companies into the leads set as additional rows,
flagged by `source`, so they're visible to downstream ground-truth matching
even though YC (the only live fetcher today) never surfaces them — they're
real companies matching the ICP, just not YC-backed.

Reads the same curated file as adapters/onboarding_vendors.py
(data/known_onboarding_vendors.yaml) but only ever touches `domain` and
`vendor`, never `why`. The competitor rationale is a labeling concept, not
a leads-row concept — CLAUDE.md's "leads CSV is always label-free" rule
means `why` must never leave the YAML by riding along on an injected row.
build_rows() below is the enforcement point: it doesn't accept or look at
`why` at all, so there's no path for it to leak through this adapter.

Unlike onboarding_vendors.py, this module DOES fit the
ADAPTER_RUNNERS/SourceResult interface cleanly: it's a genuine fetcher of
new leads rows (just from a local file instead of a network call), meant
to be merged and deduped alongside YC's rows exactly like any other source.
Rows carry no headcount/firmographic data of their own (same null-sentinel
precedent as adapters/yc.py's team_size=None: unknown is left null, not
guessed) — the curated file vouches that these companies already fit the
ICP. Dedup is first-seen-wins (pipeline/main.py), so a domain YC already
surfaced keeps YC's richer row; this adapter only fills gaps.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from adapters.onboarding_vendors import load_vendor_list

SOURCE_NAME = "manual_seed"


def build_rows(vendors: list[dict[str, Any]], pulled_at: str) -> list[dict[str, Any]]:
    """Pure: one leads-schema row per vendor domain. Deliberately reads only
    `domain` and `vendor` off each entry — see module docstring for why.
    """
    return [
        {
            "domain": vendor["domain"],
            "domain_raw": vendor["domain"],
            "source": SOURCE_NAME,
            "pulled_at": pulled_at,
            "source_url": None,
            "company_name": vendor["vendor"],
        }
        for vendor in vendors
    ]


def run(vendor_list_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Thin runner: load the local file, build leads rows. No network I/O,
    no retries — same reasoning as adapters/onboarding_vendors.py.
    """
    vendors = load_vendor_list(vendor_list_path)
    pulled_at = datetime.now(UTC).isoformat()
    rows = build_rows(vendors, pulled_at)

    return rows, {
        "source": SOURCE_NAME,
        "nb_hits_matched": len(rows),
        "dropped_no_domain": 0,
        "truncated": False,
        "rows_fetched": len(rows),
    }
