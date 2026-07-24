"""Ground-truth vendor list adapter — reads `data/known_onboarding_vendors.yaml`
and labels domains already in the leads set with `known_onboarding_vendor`.
See CLAUDE.md "Hard constraints" (this label never joins the leads file) and
docs/DESIGN.md "Source vetting: G2 dropped" for why this exists instead of a
live G2 category scrape.

Deliberately NOT wired through the same ADAPTER_RUNNERS/SourceResult
interface as adapters/yc.py, and deliberately not generalized into a
multi-source ground-truth plugin system (there's exactly one source):

- adapters/yc.py's interface is "fetch new companies from config alone,
  return rows that get merged and deduped into the leads CSV." This module
  does the opposite: it takes the leads set's already-deduped domains as
  input and produces a label for each one — it can't run before the leads
  stage, and its output must never merge into the leads file at all.
- The fetch-policy half of the YC adapter (retries, rate limiting, a real
  User-Agent, permanent-vs-retryable HTTP errors) doesn't apply here — this
  is a local file read, not a network fetch. Reusing that shape would mean
  either faking a retry loop around a file read or leaving unused parameters
  on the interface, neither of which is honest about what this source is.

pipeline/main.py calls `run()` directly as a second stage, after the leads
set is finalized, rather than folding it into run_all_sources.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from adapters.common import normalize_domain

SOURCE_NAME = "onboarding_vendors"


def load_vendor_list(path: Path) -> list[dict[str, Any]]:
    """Local file I/O, no network: read and validate the curated vendor list.

    An entry with no usable domain is dropped, same policy as every other
    source (CLAUDE.md schema contract) — even hand-curated input gets
    normalized and checked, not trusted blindly.
    """
    with path.open() as f:
        raw = yaml.safe_load(f) or {}

    vendors = []
    for entry in raw.get("vendors", []):
        domain = normalize_domain(entry.get("domain"))
        if not domain:
            continue
        vendors.append(
            {
                "domain": domain,
                "vendor": entry.get("vendor"),
                "why": entry.get("why"),
            }
        )
    return vendors


def build_ground_truth(
    vendors: list[dict[str, Any]],
    lead_domains: set[str],
    pulled_at: str,
) -> list[dict[str, Any]]:
    """Pure: label every lead domain against the curated vendor list.

    Exact normalized-domain match only — see README "Why the G2 match is
    exact-domain-only, no fuzzy matching," which applies just as much to a
    hand-curated list: a false-positive label silently misrepresents a
    company with no trace, a false negative just shows up as `false` and
    can be corrected by editing the YAML.
    """
    by_domain = {v["domain"]: v for v in vendors}

    rows = []
    for domain in sorted(lead_domains):
        match = by_domain.get(domain)
        rows.append(
            {
                "domain": domain,
                "known_onboarding_vendor": match is not None,
                "vendor": match["vendor"] if match else None,
                "why": match["why"] if match else None,
                "source": SOURCE_NAME,
                "pulled_at": pulled_at,
            }
        )
    return rows


def run(
    vendor_list_path: Path, lead_domains: set[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Thin runner: load the local file, label the leads set. No network
    I/O, no retries, no rate limiting — see module docstring for why.
    """
    vendors = load_vendor_list(vendor_list_path)
    pulled_at = datetime.now(UTC).isoformat()
    rows = build_ground_truth(vendors, lead_domains, pulled_at)
    matched = sum(1 for r in rows if r["known_onboarding_vendor"])

    return rows, {
        "source": SOURCE_NAME,
        "vendor_count": len(vendors),
        "rows_fetched": len(rows),
        "matched": matched,
    }
