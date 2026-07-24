# ICP Sourcing Pipeline

Pulls company data from public directories, normalizes it to one schema, and
emits a Clay-ready CSV of your ICP.

```bash
make install
make run
```

Output lands in `out/leads_latest.csv`.

## What it does

Two source adapters feed a common schema:

- **YC directory** — public company listings, filtered by B2B / US / team
  size (see `config.yaml`).
- **G2 (customer-onboarding-software category)** — not used to filter the
  lead list. It produces a separate ground-truth file
  (`out/ground_truth_<timestamp>.csv`) mapping domain to
  `known_onboarding_vendor`, for downstream scoring/QA. The leads CSV never
  carries this label — see "Why G2 produces a label, not a filter" below.

Every run prints a summary: rows fetched per source, rows dropped (and why),
duplicates removed, final row count, and a PARTIAL flag if any adapter
failed.

## Quickstart

```bash
make install   # uv sync
make test      # pytest, adapters run against fixtures, no live network calls
make run       # full pipeline, writes out/leads_<timestamp>.csv + latest
```

Edit `config.yaml` to change the ICP definition (country, category, headcount
band, G2 category). CLI flags override config for one-off runs.

## Scraping posture

Public sources only, no auth, no payment. Requests are rate-limited, send a
real User-Agent, and respect robots.txt. LinkedIn is deliberately out of
scope — its ToS doesn't permit this kind of scraping. Adapters check for a
public JSON endpoint before falling back to HTML parsing, since JSON is more
stable and less likely to break silently.

**YC adapter, specifically:** `ycombinator.com/robots.txt` disallows
`/companies?*` — the filtered HTML directory view. This adapter never
requests that page; it queries the Algolia endpoint the page's own
client-side JS calls, using the same search-only, publicly-scoped key
embedded in the page (read-only, restricted to public listings). robots.txt
says nothing about that host, since it's a separate domain — but the
`Disallow` is a signal about the company-list view generally, so this is
logged as a judgment call, not a clean pass. Kept low-volume (`max_records`
in `config.yaml`, default 300) with a real delay between pages, since this
is personal research, not an index crawl.

## Design notes

**Why `domain_raw` and `domain` are both kept.** Sources format domains
inconsistently (protocol, `www.`, trailing paths). `domain` is normalized
(lowercase, stripped) and is the dedup key; `domain_raw` is kept for
auditing when normalization looks wrong.

**Why headcount is a band, not an integer.** Sources report ranges.
Collapsing "11-50" into a single number invents precision that isn't there —
a fake-precise integer is worse than an honest band.

**Why the G2 match is exact-domain-only, no fuzzy matching.** A false
positive here silently drops a company from the list with no trace. Fuzzy
name matching would catch more real matches, but a silent, unrecoverable
false exclude is worse than a missed one. If domain matching misses a known
vendor, it shows up as `known_onboarding_vendor = false` and can be
corrected by hand — never as a row that's just quietly missing.

**Why G2 produces a label, not a filter.** Keeping the leads CSV label-free
means the ground-truth set can be re-derived, corrected, or extended without
re-running the whole pipeline or silently changing who's on the list.

**Why an empty adapter result is treated as a failure.** A source changing
its HTML and returning zero parseable rows looks identical, from the
pipeline's point of view, to "there really are no matches." Since the two
are indistinguishable, both are treated as failures pending review, gated by
a configurable per-adapter floor.

## Layout

```
config.yaml                  ICP definition — the actual policy, not just settings
adapters/                    one module per source, each emits the common schema
out/                         run outputs (gitignored)
cache/                       dev-only raw response cache (gitignored), see --no-cache
examples/sample_leads.csv    redacted sample of output shape, committed
```

## License

MIT — see LICENSE.
