"""YC company directory adapter.

Data source: the public Algolia index that ycombinator.com/companies'
own client-side JS queries — not the HTML directory page itself, which
robots.txt disallows for filtered views. See README.md "Scraping posture"
for the full reasoning.

The API key below is not a secret: it's the same search-only, publicly
scoped key embedded in every ycombinator.com/companies page load (visible
via view-source), restricted server-side to public listings only.

Parsing is kept pure and network-free (`parse_hit`, `parse_response`,
`build_query_body`) so it can be tested against a recorded fixture with no
live calls. `fetch_all` is the only function that touches the network; it
owns pagination, rate-limiting, and the `max_records` cap.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from adapters.common import normalize_domain

SOURCE_NAME = "yc"

ALGOLIA_APP_ID = "45BWZJ1SGC"
ALGOLIA_API_KEY = (
    "NzllNTY5MzJiZGM2OTY2ZTQwMDEzOTNhYWZiZGRjODlhYzVkNjBmOGRjNzJiMWM4ZTU0ZDlhYTZj"
    "OTJiMjlhMWFuYWx5dGljc1RhZ3M9eWNkYyZyZXN0cmljdEluZGljZXM9WUNDb21wYW55X3Byb2R1"
    "Y3Rpb24lMkNZQ0NvbXBhbnlfQnlfTGF1bmNoX0RhdGVfcHJvZHVjdGlvbiZ0YWdGaWx0ZXJzPSU1"
    "QiUyMnljZGNfcHVibGljJTIyJTVE"
)
ALGOLIA_INDEX = "YCCompany_production"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/{ALGOLIA_INDEX}/query"
COMPANY_URL_TEMPLATE = "https://www.ycombinator.com/companies/{slug}"

HITS_PER_PAGE = 50

# config.yaml uses short human labels; Algolia's facets use the site's own
# display strings. The mapping is a detail of this one source, not policy,
# so it lives here rather than in config.
COUNTRY_TO_REGION = {"US": "United States of America"}
CATEGORY_TO_INDUSTRY = {"b2b": "B2B"}


class PermanentFetchError(RuntimeError):
    """A non-retryable 4xx (anything but 429) — retrying won't help."""


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, PermanentFetchError):
        return False
    if isinstance(exc, requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else None
        return status == 429 or (status is not None and status >= 500)
    return isinstance(exc, requests.exceptions.Timeout | requests.exceptions.ConnectionError)


def build_query_body(
    *,
    country: str,
    category: str,
    headcount_min: int,
    headcount_max: int,
    page: int,
    hits_per_page: int = HITS_PER_PAGE,
) -> dict[str, Any]:
    """Pure: build the Algolia query body for one page. No network I/O."""
    region = COUNTRY_TO_REGION.get(country)
    industry = CATEGORY_TO_INDUSTRY.get(category)

    facet_filters = []
    if industry:
        facet_filters.append([f"industry:{industry}"])
    if region:
        facet_filters.append([f"regions:{region}"])

    return {
        "query": "",
        "page": page,
        "hitsPerPage": hits_per_page,
        "facetFilters": facet_filters,
        "numericFilters": [
            f"team_size>={headcount_min}",
            f"team_size<={headcount_max}",
        ],
    }


def parse_hit(hit: dict[str, Any], pulled_at: str) -> dict[str, Any] | None:
    """Pure: map one Algolia hit to a common-schema row.

    Returns None if the hit has no usable domain — CLAUDE.md requires such
    rows to be dropped before write, never written with a null domain.
    """
    domain_raw = hit.get("website") or ""
    domain = normalize_domain(domain_raw)
    if not domain:
        return None

    slug = hit.get("slug")
    # team_size is the exact figure YC reports, not a band. Storing it
    # as-is (not just min/max) keeps the precision the source gave us;
    # collapsing it into a band would only discard information.
    #
    # 0 and missing are treated the same: "unknown," not "zero employees."
    # A real company with a public listing and no team size on record is
    # far more likely to be missing data than to literally have no staff,
    # so 0 is a null sentinel here, not a fact. The row is kept either way
    # — a missing headcount isn't grounds to drop a company, it's a gap for
    # downstream scoring to handle explicitly rather than a silently wrong
    # "0-0" band.
    team_size = hit.get("team_size") or None

    return {
        "domain": domain,
        "domain_raw": domain_raw,
        "source": SOURCE_NAME,
        "pulled_at": pulled_at,
        "source_url": COMPANY_URL_TEMPLATE.format(slug=slug) if slug else None,
        "company_name": hit.get("name"),
        "team_size": team_size,
        "headcount_min": team_size,
        "headcount_max": team_size,
        "industry": hit.get("industry"),
        "industries": hit.get("industries"),
        "batch": hit.get("batch"),
        "status": hit.get("status"),
        "tags": hit.get("tags"),
        "regions": hit.get("regions"),
        "one_liner": hit.get("one_liner"),
        "long_description": hit.get("long_description"),
    }


def parse_response(response: dict[str, Any], pulled_at: str) -> list[dict[str, Any]]:
    """Pure: map one Algolia response envelope to common-schema rows."""
    hits = response.get("hits", [])
    rows = (parse_hit(hit, pulled_at) for hit in hits)
    return [row for row in rows if row is not None]


@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _fetch_page(session: requests.Session, body: dict[str, Any], user_agent: str) -> dict[str, Any]:
    resp = session.post(
        ALGOLIA_URL,
        json=body,
        headers={
            "X-Algolia-API-Key": ALGOLIA_API_KEY,
            "X-Algolia-Application-Id": ALGOLIA_APP_ID,
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        },
        timeout=10,
    )
    # Timeouts/429/5xx retry (via _is_retryable above); other 4xx are
    # permanent per CLAUDE.md fetch policy.
    if resp.status_code == 429 or resp.status_code >= 500:
        resp.raise_for_status()
    if resp.status_code >= 400:
        raise PermanentFetchError(f"YC/Algolia returned {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def fetch_all(
    *,
    country: str,
    category: str,
    headcount_min: int,
    headcount_max: int,
    max_records: int,
    user_agent: str,
    rate_limit_seconds: float,
    session: requests.Session | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Paginate the live Algolia endpoint. Returns (rows, meta).

    Pagination, rate-limiting, and the max_records cap live here; parsing
    is delegated to the pure functions above so they stay fixture-testable
    with no network calls in this module's test path.
    """
    session = session or requests.Session()
    pulled_at = datetime.now(UTC).isoformat()

    rows: list[dict[str, Any]] = []
    page = 0
    nb_hits = 0
    dropped_no_domain = 0
    hit_the_cap = False

    while True:
        body = build_query_body(
            country=country,
            category=category,
            headcount_min=headcount_min,
            headcount_max=headcount_max,
            page=page,
            hits_per_page=HITS_PER_PAGE,
        )
        response = _fetch_page(session, body, user_agent)
        nb_hits = response.get("nbHits", 0)
        page_rows = parse_response(response, pulled_at)
        dropped_no_domain += len(response.get("hits", [])) - len(page_rows)
        rows.extend(page_rows)

        page += 1
        reached_last_page = page >= response.get("nbPages", 0)
        reached_cap = len(rows) >= max_records
        hit_the_cap = hit_the_cap or reached_cap
        if reached_last_page or reached_cap:
            break

        time.sleep(rate_limit_seconds)

    rows = rows[:max_records]

    return rows, {
        "source": SOURCE_NAME,
        "nb_hits_matched": nb_hits,
        "rows_fetched": len(rows),
        # Hits examined that had no usable domain and were dropped before
        # ever becoming a row (CLAUDE.md: never write a row without one).
        # This is a normal, expected shortfall — not truncation.
        "dropped_no_domain": dropped_no_domain,
        # True only if max_records cut pagination short — a config bound,
        # not "the source is empty" and not the (expected) gap from
        # dropped-no-domain rows above. See config.yaml's max_records
        # comment: this should be raised deliberately, not hit silently.
        "truncated": hit_the_cap,
    }
