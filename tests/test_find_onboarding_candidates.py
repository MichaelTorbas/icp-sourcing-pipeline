from scripts.find_onboarding_candidates import find_candidates, matching_categories, scan_row


def test_matching_categories_finds_onboarding_language():
    assert "onboarding" in matching_categories("A platform for customer onboarding flows.")


def test_matching_categories_finds_implementation_language():
    assert "implementation" in matching_categories("We manage software rollout and implementation.")


def test_matching_categories_finds_customer_success_language():
    assert "customer_success" in matching_categories("Built for the modern customer success team.")


def test_matching_categories_word_boundary_avoids_partial_words():
    # "onboard" must not match as a substring of an unrelated word.
    assert matching_categories("The ship sailed with a full shipboard crew.") == []


def test_matching_categories_returns_empty_for_no_match():
    assert matching_categories("A generic B2B analytics dashboard.") == []


def test_scan_row_checks_both_one_liner_and_long_description():
    row = {
        "one_liner": "Generic analytics.",
        "long_description": "We help with customer onboarding.",
    }
    assert "onboarding" in scan_row(row)


def test_scan_row_handles_missing_fields():
    assert scan_row({}) == []


def test_find_candidates_only_returns_matching_rows_with_expected_shape():
    rows = [
        {
            "domain": "a.com",
            "company_name": "A",
            "one_liner": "Generic analytics.",
            "long_description": "",
        },
        {
            "domain": "b.com",
            "company_name": "B",
            "one_liner": "Customer onboarding software.",
            "long_description": "",
        },
    ]
    candidates = find_candidates(rows)

    assert len(candidates) == 1
    assert candidates[0]["domain"] == "b.com"
    assert candidates[0]["matched_categories"] == ["onboarding"]
    # No known_onboarding_vendor / label field anywhere in the output shape.
    assert "known_onboarding_vendor" not in candidates[0]
