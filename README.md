# ICP Sourcing Pipeline

Pulls company data from public directories, normalizes it to one schema, and
emits a Clay-ready CSV of your ICP.

```bash
make install
make run
```

Output lands in `out/leads_latest.csv`.

## What it does

Two source adapters feed the leads CSV:

- **YC directory** — public company listings, filtered by B2B / US / team
  size (see `config.yaml`).
- **Manual seed** (`adapters/manual_seed.py`) — injects the companies in
  `data/known_onboarding_vendors.yaml` into the leads set as additional
  rows, flagged `source=manual_seed`. Most of them aren't YC-backed, so
  without this they'd never show up — YC is the only live fetcher today,
  and these are real companies that fit the ICP regardless. Rows carry no
  headcount/firmographic data of their own (left null, same as any other
  unknown field) and never carry the vendor list's `why` rationale — see
  "Why `why` never leaves the YAML" below. If YC also surfaces one of these
  domains, YC's richer row wins on dedup.

A third stage, not a source adapter, runs after the leads set is final:

- **Ground truth** (`adapters/onboarding_vendors.py`) — labels every domain
  in the finished leads set against the same curated vendor file, writing
  `out/ground_truth_<timestamp>.csv` (`known_onboarding_vendor`, `vendor`,
  `why`). Never joined into the leads CSV — see "Why the vendor list
  produces a label, not a filter" below. This was originally going to be a
  live G2 category scrape; see `docs/DESIGN.md` "Source vetting: G2
  dropped" for why that source was dropped in favor of a hand-curated
  local file.

`scripts/find_onboarding_candidates.py` is a separate, human-in-the-loop
tool: it scans the leads CSV's `one_liner`/`long_description` for
onboarding/implementation/customer-success language and prints candidates
for hand review. It never writes a label — it's how you find new entries
to add to `data/known_onboarding_vendors.yaml` yourself, not a second
labeling path. Run it with `uv run python -m scripts.find_onboarding_candidates`.

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
band). Edit `data/known_onboarding_vendors.yaml` to change the ground-truth
vendor list. CLI flags override config for one-off runs.

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

**Why the vendor-list match is exact-domain-only, no fuzzy matching.** A false
positive here silently drops a company from the list with no trace. Fuzzy
name matching would catch more real matches, but a silent, unrecoverable
false exclude is worse than a missed one. If domain matching misses a known
vendor, it shows up as `known_onboarding_vendor = false` and can be
corrected by hand — never as a row that's just quietly missing.

**Why the vendor list produces a label, not a filter.** Keeping the leads
CSV label-free means the ground-truth set can be re-derived, corrected, or
extended (by editing the YAML) without re-running the whole pipeline or
silently changing who's on the list.

**Why `why` never leaves the YAML.** `adapters/manual_seed.py` reads the
same curated file as the ground-truth adapter, but only ever touches
`domain` and `vendor` — the competitor rationale (`why`) is a labeling
concept, not a leads-row concept, and the "leads CSV is always label-free"
rule (see hard constraints) would be violated if it rode along on an
injected row. `build_rows()` in that module is the enforcement point: it
doesn't read `why` at all, so there's no code path for it to leak through.

**Why an empty adapter result is treated as a failure.** A source changing
its HTML and returning zero parseable rows looks identical, from the
pipeline's point of view, to "there really are no matches." Since the two
are indistinguishable, both are treated as failures pending review, gated by
a configurable per-adapter floor.

## Layout

```
config.yaml                            ICP definition — the actual policy, not just settings
adapters/                              one module per source, each emits the common schema
data/known_onboarding_vendors.yaml      curated ground-truth vendor list, committed
scripts/                                standalone tools, not part of the run pipeline (e.g. candidate scan)
.claude/hooks/                          Claude Code hooks enforcing invariants outside the codebase, see docs/DESIGN.md
out/                                    run outputs (gitignored)
cache/                                  dev-only raw response cache (gitignored), see --no-cache
examples/sample_leads.csv              redacted sample of output shape, committed
```

## License

MIT — see LICENSE.
