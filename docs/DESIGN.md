# Design notes

Notes on intended patterns that aren't built yet, kept separate from
README.md so "how it works today" doesn't get mixed up with "how it's meant
to grow." Nothing in this file is implemented until an adapter or pipeline
change says otherwise.

## Delta runs (not yet implemented)

Every run is currently a full pull, written to a fresh
`out/leads_<timestamp>.csv`. The pipeline isn't built to diff between runs
yet, but the schema and output naming are already shaped so that it can be,
without a redesign later:

- **`pulled_at` on every row** — an ISO 8601 timestamp per row, not just per
  file, so a future diff can tell *when* a row was last confirmed present,
  independent of when the CSV containing it happened to be generated.
- **Stable, sortable output naming** — `out/leads_<timestamp>.csv` per run,
  plus `out/leads_latest.csv` as a fixed path. A future diff tool can always
  find "the previous run" by listing `leads_*.csv` and taking the
  second-most-recent, with no separate manifest to maintain.

**Intended pattern, once built:** the first run seeds the corpus — there's
nothing to diff against, so it's just the full matched set. Every run after
that diffs the new pull against the previous `leads_*.csv` on the `domain`
key and surfaces three things:

- **Entrants** — domains present now that weren't in the previous run.
  These are the interesting case: a company crossing into the ICP band (say,
  headcount growing past 11) is a GTM signal, not just a data update — it's
  a company that just became sellable and wasn't before.
- **Exits** — domains that were present and now aren't (fell out of the
  headcount band, or dropped from the source entirely). Surfaced, not
  silently dropped, since "no longer qualifies" and "we can no longer see
  it" are different things worth telling apart.
- **Band changes** — same domain, different `headcount_min`/`headcount_max`
  (or other tracked field) between runs. Movement within the ICP is weaker
  signal than an entrant/exit but still worth surfacing, e.g. for
  prioritization.

The diff is domain-keyed and per-source — it should not require re-running
adapters that haven't changed, and it should not require any state beyond
"the previous CSV on disk."
