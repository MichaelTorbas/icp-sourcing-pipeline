"""Regression fixtures for normalize_domain against known-bad scraped input.

Each case here is a shape of garbage that's shown up (or is expected to
show up) in a source's website/domain field. The expected output is a
deliberate policy decision, not just "whatever the code happens to do" —
see the comment on each case and adapters/common.py's docstring for the
reasoning, particularly on email and bare-word rejection.
"""

from adapters.common import normalize_domain


def test_embedded_space_is_rejected_not_stripped():
    # A mangled URL with a space in the middle of the host. Stripping the
    # space would fabricate a domain that was never actually scraped;
    # rejecting it is the honest outcome.
    assert normalize_domain("exa mple.com") == ""


def test_url_with_path_keeps_only_the_host():
    assert normalize_domain("https://example.com/pricing/enterprise") == "example.com"


def test_email_in_field_is_rejected_not_guessed():
    # The local part of an email is not reliably the company's own domain
    # (e.g. a support inbox on Gmail) — don't extract and guess.
    assert normalize_domain("sales@example.com") == ""


def test_company_name_in_field_is_rejected():
    # A bare word with no dot isn't a hostname, even though urlparse would
    # happily treat it as one.
    assert normalize_domain("Cognito") == ""


def test_empty_is_rejected():
    assert normalize_domain("") == ""
    assert normalize_domain(None) == ""


def test_case_differing_duplicates_collapse_to_the_same_domain():
    # This is the property the whole function exists for: domain is the
    # dedup key, so case/www variants of the same site must collide.
    a = normalize_domain("WWW.Example.COM")
    b = normalize_domain("www.example.com")
    assert a == b == "example.com"
