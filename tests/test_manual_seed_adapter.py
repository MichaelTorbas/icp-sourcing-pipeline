from adapters.manual_seed import SOURCE_NAME, build_rows

PULLED_AT = "2026-07-24T00:00:00+00:00"


def test_build_rows_emits_one_leads_row_per_vendor():
    vendors = [
        {"domain": "appcues.com", "vendor": "Appcues", "why": "Direct onboarding overlap."},
        {"domain": "pendo.io", "vendor": "Pendo", "why": "In-app guides overlap."},
    ]

    rows = build_rows(vendors, PULLED_AT)

    assert {r["domain"] for r in rows} == {"appcues.com", "pendo.io"}
    for row in rows:
        assert row["source"] == SOURCE_NAME
        assert row["pulled_at"] == PULLED_AT


def test_build_rows_never_includes_why():
    # The competitor rationale is a ground-truth-only concept — it must
    # never ride along into a leads row via this adapter.
    vendors = [
        {"domain": "appcues.com", "vendor": "Appcues", "why": "Should never appear in a lead row."}
    ]

    rows = build_rows(vendors, PULLED_AT)

    assert "why" not in rows[0]
    assert not any("Should never appear" in str(v) for v in rows[0].values())


def test_build_rows_sets_company_name_from_vendor_field():
    vendors = [{"domain": "appcues.com", "vendor": "Appcues", "why": "..."}]
    rows = build_rows(vendors, PULLED_AT)
    assert rows[0]["company_name"] == "Appcues"


def test_build_rows_tolerates_entries_with_no_why_key():
    vendors = [{"domain": "appcues.com", "vendor": "Appcues"}]
    rows = build_rows(vendors, PULLED_AT)
    assert rows[0]["domain"] == "appcues.com"
