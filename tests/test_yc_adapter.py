import json
from pathlib import Path

from adapters.yc import COMPANY_URL_TEMPLATE, parse_hit, parse_response

FIXTURE = Path(__file__).parent / "fixtures" / "yc_algolia_response.json"
PULLED_AT = "2026-07-23T00:00:00+00:00"


def _load_fixture() -> dict:
    return json.loads(FIXTURE.read_text())


def test_parse_response_maps_every_hit_in_the_fixture():
    response = _load_fixture()
    rows = parse_response(response, PULLED_AT)

    assert len(rows) == len(response["hits"])
    for row in rows:
        assert row["source"] == "yc"
        assert row["pulled_at"] == PULLED_AT
        assert row["domain"]
        assert row["source_url"].startswith("https://www.ycombinator.com/companies/")


def test_parse_response_derives_headcount_band_from_team_size():
    response = _load_fixture()
    rows = parse_response(response, PULLED_AT)

    hellosign = next(r for r in rows if r["company_name"] == "HelloSign")
    assert hellosign["domain"] == "hellosign.com"
    assert hellosign["domain_raw"] == "https://www.hellosign.com"
    assert hellosign["source_url"] == COMPANY_URL_TEMPLATE.format(slug="hellosign")
    assert hellosign["team_size"] == 100
    assert hellosign["headcount_min"] == 100
    assert hellosign["headcount_max"] == 100
    assert hellosign["industry"] == "B2B"
    assert hellosign["batch"] == "Winter 2011"
    assert hellosign["status"] == "Acquired"


def test_parse_hit_drops_rows_with_no_usable_domain():
    hit = {"name": "No Website Inc", "website": "", "slug": "no-website", "team_size": 5}
    assert parse_hit(hit, PULLED_AT) is None

    hit_missing = {"name": "Missing Website Inc", "slug": "missing", "team_size": 5}
    assert parse_hit(hit_missing, PULLED_AT) is None


def test_parse_hit_normalizes_domain_variants():
    hit = {
        "name": "Example",
        "website": "HTTP://WWW.Example.com/about",
        "slug": "example",
        "team_size": 42,
    }
    row = parse_hit(hit, PULLED_AT)
    assert row["domain"] == "example.com"
    assert row["domain_raw"] == "HTTP://WWW.Example.com/about"


def test_parse_hit_keeps_row_with_null_bands_for_missing_team_size():
    # A row with no domain is dropped; a row with no team_size is not — the
    # two are different kinds of gap. Missing headcount is left for
    # downstream scoring to handle, not silently discarded.
    hit = {"name": "No Headcount Inc", "website": "https://example.org", "slug": "nohc"}
    row = parse_hit(hit, PULLED_AT)
    assert row is not None
    assert row["team_size"] is None
    assert row["headcount_min"] is None
    assert row["headcount_max"] is None


def test_parse_hit_treats_zero_team_size_as_null_not_literal_zero():
    # team_size=0 in this source means "unknown," not "zero-person company"
    # — treated the same as missing, not stored as a real 0-0 band.
    hit = {"name": "Zero Inc", "website": "https://example.net", "slug": "zero", "team_size": 0}
    row = parse_hit(hit, PULLED_AT)
    assert row is not None
    assert row["team_size"] is None
    assert row["headcount_min"] is None
    assert row["headcount_max"] is None
