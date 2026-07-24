# Design notes

Notes on intended patterns that aren't built yet, kept separate from
README.md so "how it works today" doesn't get mixed up with "how it's meant
to grow." Sections below are marked "(not yet implemented)" unless they're
a record of a decision that's already been made and acted on — those are
kept here too, since the reasoning behind a decision is design context even
after it ships.

## Source vetting: G2 dropped (2026-07-24, implemented)

G2 was the planned source for the `known_onboarding_vendor` ground-truth
label (customer-onboarding-software category). It's dropped. Recon showed
that checking robots.txt alone would have gotten this wrong — and would
also have gotten YC wrong, in the opposite direction:

- **YC:** robots.txt disallows `/companies?*`, the filtered HTML directory
  page — a stated restriction. But the page's own client-side JS calls a
  public Algolia endpoint on a different host, which robots.txt says nothing
  about and which responds normally with no auth, no CAPTCHA, no blocking.
  Stated policy is stricter than what's actually enforced. `adapters/yc.py`
  uses that open endpoint instead of the disallowed HTML page.

- **G2:** robots.txt for `User-agent: *` does *not* disallow
  `/categories/*` — nothing in it stops a crawl of
  `g2.com/categories/customer-onboarding`. But the live response to that
  URL (and to every other category page checked, and the homepage, and even
  the sitemap robots.txt itself points to) is a 403 from a DataDome +
  Cloudflare bot challenge — `x-datadome: protected`, a JS/CAPTCHA
  interstitial, not HTML. The one G2 route that *does* return 200 (the bare
  `/categories` index — category names only, no vendor listings) sends back
  `x-scrapable-route: false`: G2 explicitly flagging that route as not
  meant to be scraped, on a page robots.txt is silent about. Stated policy
  is looser than what's actually enforced.

Both sources disagree with their own robots.txt, in opposite directions.
Checking only the stated policy would have blocked the YC adapter from
using a source that's actually fine, and would have waved the G2 adapter
through onto a source that's actively hostile to automated access. The
fetch policy in CLAUDE.md ("check robots.txt") is necessary but not
sufficient — the live response has to be checked too, per source.

**Decision:** drop G2. Replace it with a curated local file,
`data/known_onboarding_vendors.yaml`, read by
`adapters/onboarding_vendors.py`. See that module's docstring for why it
does *not* use the same `ADAPTER_RUNNERS`/`SourceResult` interface as
`adapters/yc.py` — forcing it in would have papered over a real difference
in shape between "fetch new companies" and "label companies already
found."

## CSV schema contract as a hook, not a function call (2026-07-24, implemented)

CLAUDE.md's hard constraints include: never write a CSV row without a
`domain`, never write a CSV file for a run that produced zero valid rows.
`pipeline/main.py` already enforces this — `parse_hit` drops rows with no
usable domain before they're ever built, and `main()` returns early instead
of calling `write_csv` when `final_rows` is empty. That's the invariant.
The question was how to keep it true going forward.

**Why not just leave it as a function call (or add a `validate()` one).**
A validation function is only as reliable as every future call site. It's
enforced by *remembering to call it* — which means it can be silently
defeated by a code change that never intends to break anything:
refactoring `write_csv`, adding a new call path, editing `dedupe_by_domain`,
reordering the early-return check. None of that requires editing the
validation function itself, or even knowing it exists. A future session
(or a future me) reasoning about "does this change break the contract?"
has to trace every code path by hand, every time — the check is
*reasonable-around*, not load-bearing on its own.

**Why a hook instead.** A Claude Code hook is registered outside the
Python codebase entirely, in `.claude/settings.json` — it's not a function
`pipeline/main.py` chooses to call, it's a control point the harness fires
on its own. `.claude/hooks/validate_csv_schema.py` runs as a `PostToolUse`
hook matched on the `Bash` tool: after *every* Bash call in a Claude Code
session, it checks every `out/*.csv` file for a `domain` column, a
non-empty `domain` on every row, and at least one data row. Any violation
exits 2, which Claude Code treats as a blocking error — the violation
gets surfaced to the agent regardless of what path produced the bad file
or whether anyone remembered to call a validator. Editing `main.py` to
remove its own internal checks wouldn't disable this — the hook doesn't
know or care how the CSV was produced, only whether the file on disk
satisfies the contract.

**Honest limits, so this isn't oversold.** Per the current hooks
reference (`code.claude.com/docs/en/hooks`, checked directly rather than
from memory): `PostToolUse` fires *after* the tool call already ran, and
its exit-2/`decision: "block"` signal stops Claude from continuing but
does **not** undo the tool call — the bad CSV briefly exists on disk
either way. There's no `PreToolUse` equivalent here because the write
happens inside a Python process invoked via `Bash`, not through a Claude
Code `Write`/`Edit` tool call that a `PreToolUse` hook could intercept
before it happens. So this is deterministic *detection-and-block*, not
physical prevention at the syscall level — but that's still a categorically
different guarantee than a function call: it doesn't depend on the
Python code path being correct, can't be quietly skipped by a refactor,
and fires the same way no matter which command produced the file. It also
only fires inside a Claude Code session — a `make run` invoked completely
outside one (cron, CI) wouldn't trigger it, which matches CLAUDE.md's
non-goal of no scheduling — all runs today happen interactively through a
session where this hook is live.

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
