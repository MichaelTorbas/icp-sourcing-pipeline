"""Helpers shared across source adapters — see CLAUDE.md "Schema contract"."""

from __future__ import annotations

import re
from urllib.parse import urlparse

# A bare hostname: labels of letters/digits/hyphens, at least one dot, no
# leading/trailing hyphen on a label. Deliberately excludes anything that
# isn't shaped like a domain — see normalize_domain for why "close enough"
# inputs (a bare word, an email) are rejected rather than coerced.
_DOMAIN_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$")


def normalize_domain(raw: str | None) -> str:
    """Lowercase, protocol/www/path-stripped domain — the dedup key.

    Returns "" for anything that doesn't reduce to a usable domain. Callers
    are responsible for dropping the row: CLAUDE.md requires every written
    row to have a domain, never a null.

    Deliberately conservative rather than clever:
    - Whitespace anywhere (not just leading/trailing) means the field isn't
      a clean domain/URL — reject rather than strip-and-guess.
    - "@" means the field is an email address, not a website. We don't
      extract the part after "@": a personal or support inbox's domain is
      often not the company's own domain, and guessing would silently plant
      a wrong dedup key.
    - The result must look like a real hostname (letters/digits/hyphens,
      at least one dot). A bare word ("Acme", a company name with no dot)
      is rejected rather than treated as a single-label host.
    """
    if not raw:
        return ""
    raw = raw.strip()
    if not raw or re.search(r"\s", raw):
        return ""
    if "@" in raw:
        return ""
    candidate = raw if "//" in raw else f"//{raw}"
    netloc = urlparse(candidate).netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    host = netloc.split(":")[0]
    if not _DOMAIN_RE.match(host):
        return ""
    return host
