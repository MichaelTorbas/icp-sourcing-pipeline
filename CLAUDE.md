# CLAUDE.md

GTM list-sourcing pipeline: pulls company data from public directories,
normalizes to one schema, emits a Clay-ready CSV. This file is policy only —
rationale lives in README.md.

## Hard constraints

- No LinkedIn. No source requiring auth or payment. Public, unauthenticated
  sources only.
- Never write a CSV row without a `domain`. Never write a CSV file for a run
  that produced zero valid rows.
- The main leads CSV is always label-free. `known_onboarding_vendor` and any
  other ground-truth labels go in a separate `out/ground_truth_*.csv`, never
  joined into the leads file.
- An adapter returning zero rows (or fewer than its configured floor) is a
  failure, not an empty result — log it, mark the run PARTIAL, do not treat
  silence as "no matches."

## Schema contract

Required: `domain` (normalized: lowercase, no protocol/www/path), `source`
(adapter name), `pulled_at` (ISO 8601). All other fields nullable.
- `domain_raw` — as scraped, kept alongside `domain`.
- `domain` — the dedup key.
- `headcount_min` / `headcount_max` — bands, never a single integer.
- `source_url` — the page the row was pulled from.
A row with no `domain` is dropped before write, not written with a null.

## Fetch policy

- Check for a public JSON endpoint before parsing HTML.
- Rate-limit requests, send a real User-Agent, respect robots.txt.
- Retry timeouts/429/5xx up to 3x with exponential backoff. Other 4xx errors
  are permanent — do not retry.
- One adapter's failure does not stop other adapters, but it does make the
  run exit non-zero and marks the run summary PARTIAL.
- Every run prints a summary: rows fetched per source, rows dropped (and
  why), duplicates removed, final row count, PARTIAL flag if applicable.

## Layout

- `config.yaml` — the ICP definition (filters), checked in, is policy.
- `adapters/` — one module per source, each emits the common schema.
- `out/` — run outputs (gitignored): `leads_<timestamp>.csv`,
  `ground_truth_<timestamp>.csv`, `leads_latest.csv` (stable path for Clay).
- `cache/` — dev-only raw response cache (gitignored). Use `--no-cache` for
  real runs.
- `examples/sample_leads.csv` — committed, redacted sample of output shape.

## Non-goals

- Fuzzy matching for `known_onboarding_vendor` (see README for why).
- Scheduling/cron — this runs manually via `make run`.
