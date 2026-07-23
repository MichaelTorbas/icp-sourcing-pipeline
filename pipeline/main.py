"""Pipeline entrypoint: run configured adapters, apply the schema contract,
write the leads CSV, print the run summary.

Only the YC adapter is wired in today. G2 (ground_truth_<timestamp>.csv,
the known_onboarding_vendor label) isn't built yet — see README.md for why
that output is separate from the leads CSV once it exists.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from adapters.yc import fetch_all as fetch_yc

# Column order for the leads CSV. domain/source/pulled_at are the only
# required fields (CLAUDE.md schema contract); everything else is nullable.
CSV_FIELDS = [
    "domain",
    "domain_raw",
    "source",
    "pulled_at",
    "source_url",
    "company_name",
    "team_size",
    "headcount_min",
    "headcount_max",
    "industry",
    "industries",
    "batch",
    "status",
    "tags",
    "regions",
    "one_liner",
]


@dataclass
class SourceResult:
    name: str
    rows: list[dict[str, Any]]
    meta: dict[str, Any]
    min_rows: int
    ok: bool


def load_config(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f)


def run_yc(config: dict[str, Any]) -> SourceResult:
    filters = config["filters"]
    yc_config = config["sources"]["yc"]
    fetch_config = config["fetch"]

    rows, meta = fetch_yc(
        country=filters["country"],
        category=filters["category"],
        headcount_min=filters["headcount"]["min"],
        headcount_max=filters["headcount"]["max"],
        max_records=yc_config["max_records"],
        user_agent=fetch_config["user_agent"],
        rate_limit_seconds=fetch_config["rate_limit_seconds"],
    )

    min_rows = yc_config["min_rows"]
    ok = len(rows) >= min_rows
    return SourceResult(name="yc", rows=rows, meta=meta, min_rows=min_rows, ok=ok)


# One adapter today; add G2 here (name -> runner) once it exists. Each
# runner is invoked independently below so one adapter failing doesn't stop
# the others (CLAUDE.md fetch policy).
ADAPTER_RUNNERS: dict[str, Callable[[dict[str, Any]], SourceResult]] = {
    "yc": run_yc,
}


def run_all_sources(config: dict[str, Any]) -> list[SourceResult]:
    results = []
    for name, runner in ADAPTER_RUNNERS.items():
        try:
            results.append(runner(config))
        except Exception as exc:
            print(f"  {name}: adapter raised {exc!r}", file=sys.stderr)
            min_rows = config.get("sources", {}).get(name, {}).get("min_rows", 0)
            failed = SourceResult(
                name=name, rows=[], meta={"error": str(exc)}, min_rows=min_rows, ok=False
            )
            results.append(failed)
    return results


def dedupe_by_domain(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """First-seen-wins dedup on domain, the schema contract's dedup key."""
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        seen.setdefault(row["domain"], row)
    return list(seen.values()), len(rows) - len(seen)


def _csv_value(value: Any) -> Any:
    if isinstance(value, list):
        return ";".join(str(v) for v in value)
    return value


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in CSV_FIELDS})


def print_summary(
    results: list[SourceResult],
    final_rows: list[dict[str, Any]],
    duplicates_removed: int,
) -> None:
    print("=== Run summary ===")
    for result in results:
        if "error" in result.meta:
            print(f"  {result.name}: FAILED — {result.meta['error']}")
            continue
        status = "ok" if result.ok else f"PARTIAL (below min_rows floor of {result.min_rows})"
        print(
            f"  {result.name}: fetched {len(result.rows)} rows "
            f"(matched {result.meta.get('nb_hits_matched', '?')} at source, "
            f"dropped {result.meta.get('dropped_no_domain', 0)} for no domain, "
            f"truncated={result.meta.get('truncated', False)}) — {status}"
        )
    print(f"  duplicates removed across sources: {duplicates_removed}")
    print(f"  final row count: {len(final_rows)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the ICP sourcing pipeline.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    args = parser.parse_args(argv)

    config = load_config(args.config)
    results = run_all_sources(config)

    all_rows = [row for result in results for row in result.rows]
    final_rows, duplicates_removed = dedupe_by_domain(all_rows)

    partial = any(not result.ok for result in results)

    print_summary(results, final_rows, duplicates_removed)

    if not final_rows:
        # CLAUDE.md: never write a CSV file for a run that produced zero valid rows.
        print(
            "  RUN STATUS: PARTIAL — no valid rows, not writing a CSV"
            if partial
            else "  RUN STATUS: FAILED — no valid rows, not writing a CSV"
        )
        return 1

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    write_csv(args.out_dir / f"leads_{timestamp}.csv", final_rows)
    write_csv(args.out_dir / "leads_latest.csv", final_rows)

    print(f"  RUN STATUS: {'PARTIAL' if partial else 'OK'}")
    return 1 if partial else 0


if __name__ == "__main__":
    raise SystemExit(main())
