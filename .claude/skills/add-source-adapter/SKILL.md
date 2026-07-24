---
name: add-source-adapter
description: Checklist for adding a new source adapter (fetcher or labeler) to this pipeline — recon, fetcher-vs-labeler classification, file layout, fixture-first testing, schema contract, min_rows floor, wiring. Use when asked to add a new data source, scraper, vendor list, or adapter to icp-sourcing-pipeline.
---

# Adding a new source adapter

## 1. Recon before code

Check robots.txt **and** the actual live response (status code, body, bot-wall
signals like `x-datadome` / Cloudflare challenge pages). They can disagree in
*either* direction: YC's robots.txt disallowed a page whose backing endpoint
was open; G2's robots.txt allowed a page that was actively blocked
(`x-scrapable-route: false`). Checking only one would have gotten both wrong —
see `docs/DESIGN.md` "Source vetting: G2 dropped."

If the source actively blocks automated access or requires auth/payment,
stop and report it — don't build against it (CLAUDE.md hard constraints).

## 2. Classify: fetcher or labeler

This is the decision that matters — not network vs. local file.

- **Fetcher** — produces *new* rows for the leads set.
  `adapters/yc.py` (network) and `adapters/manual_seed.py` (local file) are
  both fetchers. Emits rows conforming to the schema contract (§4), runs
  through `ADAPTER_RUNNERS`/`SourceResult` in `pipeline/main.py`, gets merged
  + deduped, lands in the leads CSV.
- **Labeler** — annotates rows *already in* the leads set.
  `adapters/onboarding_vendors.py` (also a local file) is a labeler, not a
  fetcher. Takes the finalized lead domains as input, not config alone. Does
  **not** go through `ADAPTER_RUNNERS`; runs as its own stage in `main()`
  after `final_rows` exists. Output is a separate file/schema, never merged
  into the leads CSV (CLAUDE.md: leads CSV is always label-free).

Test: does it produce companies that weren't already leads, or say something
*about* companies that already are? First = fetcher, second = labeler.

## 3. Where files go

- `adapters/<name>.py` — the module.
- `tests/test_<name>_adapter.py` — unit tests against a fixture, no live
  network calls.
- `tests/fixtures/<name>_response.json` — a real recorded response (fetchers
  hitting a network source).
- `data/<name>.yaml` — curated local data, if hand-maintained rather than a
  live pull.

## 4. Fixture-first, schema contract

Hit the real source once, save the raw response as a fixture, *then* write
the parser. Split pure parsing (`parse_hit`/`parse_response`-style, tested
against the fixture) from network I/O (retries, rate limit, pagination) —
same split as `adapters/yc.py`.

Every fetcher row needs `domain` (via `adapters/common.py:normalize_domain`),
`source`, `pulled_at`; everything else nullable. Drop rows with no usable
domain before returning them — never write one with a null domain. Full
contract: CLAUDE.md "Schema contract."

## 5. min_rows floor

Add a `sources.<name>` block to `config.yaml` with `min_rows`.

- Fetcher: floor on rows returned. Below it = PARTIAL, not "no matches" —
  zero/low rows from a working adapter is a failure signal, not silence.
- Labeler: floor on the labeler's *own* health (e.g. entries loaded from its
  file), not on how many leads matched — match count depends on the run's
  companies, not the source's health. See `onboarding_vendors`'s comment in
  `config.yaml`.

## 6. Wire it up

- Fetcher → add to `ADAPTER_RUNNERS` in `pipeline/main.py`.
- Labeler → call directly as a second stage in `main()`, after `final_rows`
  is computed (see `run_ground_truth`).
- Network source → fetch policy applies: real User-Agent, rate limit, retry
  3x on timeout/429/5xx with backoff, permanent-fail other 4xx (CLAUDE.md
  "Fetch policy").
