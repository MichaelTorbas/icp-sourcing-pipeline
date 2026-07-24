from pathlib import Path

import pytest

from adapters.onboarding_vendors import build_ground_truth, load_vendor_list

PULLED_AT = "2026-07-24T00:00:00+00:00"


@pytest.fixture
def vendor_list_path(tmp_path: Path) -> Path:
    path = tmp_path / "vendors.yaml"
    path.write_text(
        """
        vendors:
          - domain: appcues.com
            vendor: Appcues
            why: In-product onboarding flows for SaaS user activation.
          - domain: HTTPS://WWW.Pendo.io/
            vendor: Pendo
            why: In-app guides used to build onboarding flows.
          - domain: not-a-domain
            vendor: Should Be Dropped
            why: Has no usable domain, must not appear in the loaded list.
        """
    )
    return path


def test_load_vendor_list_normalizes_domains_and_drops_unusable_ones(vendor_list_path: Path):
    vendors = load_vendor_list(vendor_list_path)

    domains = {v["domain"] for v in vendors}
    assert domains == {"appcues.com", "pendo.io"}


def test_build_ground_truth_labels_matched_and_unmatched_leads(vendor_list_path: Path):
    vendors = load_vendor_list(vendor_list_path)
    lead_domains = {"appcues.com", "some-other-company.com"}

    rows = build_ground_truth(vendors, lead_domains, PULLED_AT)
    by_domain = {r["domain"]: r for r in rows}

    assert by_domain["appcues.com"]["known_onboarding_vendor"] is True
    assert by_domain["appcues.com"]["vendor"] == "Appcues"
    assert by_domain["appcues.com"]["source"] == "onboarding_vendors"
    assert by_domain["appcues.com"]["pulled_at"] == PULLED_AT

    assert by_domain["some-other-company.com"]["known_onboarding_vendor"] is False
    assert by_domain["some-other-company.com"]["vendor"] is None
    assert by_domain["some-other-company.com"]["why"] is None


def test_build_ground_truth_is_exact_match_only_no_fuzzy_matching(vendor_list_path: Path):
    vendors = load_vendor_list(vendor_list_path)
    # A near-miss domain (subdomain of a known vendor) must not match —
    # exact-domain-only means a false positive here is worse than a miss.
    rows = build_ground_truth(vendors, {"app.appcues.com"}, PULLED_AT)

    assert rows[0]["known_onboarding_vendor"] is False


def test_build_ground_truth_covers_every_lead_domain_not_just_matches(vendor_list_path: Path):
    vendors = load_vendor_list(vendor_list_path)
    lead_domains = {"a.com", "b.com", "c.com"}

    rows = build_ground_truth(vendors, lead_domains, PULLED_AT)

    assert {r["domain"] for r in rows} == lead_domains
