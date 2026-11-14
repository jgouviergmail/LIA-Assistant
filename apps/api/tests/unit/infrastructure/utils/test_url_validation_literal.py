"""The refusals a URL earns before its name is resolved (ADR-326, ADR-387).

An API boundary may not make a network call, and resolving a name is one: it
refuses what the URL's own spelling already rules out — a scheme, a missing
host, a blocked name, a blocked literal address — through the same checks
:func:`validate_url` makes before it resolves. The fetch still validates every
hop in full.
"""

from __future__ import annotations

import pytest

from src.infrastructure.utils.url_validation import literal_refusal, validate_url

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/",
        "http://example.org/a?b=c#d",
        "https://93.184.216.34/",
        "  https://example.org/padded  ",
    ],
)
def test_a_url_its_spelling_does_not_rule_out_passes(url: str) -> None:
    assert literal_refusal(url) is None


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("", "Empty URL"),
        ("   ", "Empty URL"),
        ("ftp://example.org/", "Unsupported scheme"),
        ("example.org/path", "Unsupported scheme"),
        ("https://", "No hostname"),
        ("https://localhost/", "Blocked hostname"),
        ("https://printer.local/", "Blocked hostname suffix"),
        ("http://127.0.0.1:8000/", "Blocked IP address"),
        ("http://10.1.2.3/", "Blocked IP address"),
        ("http://[::ffff:127.0.0.1]/", "Blocked IP address"),
        ("http://[::1]/", "Blocked IP address"),
    ],
)
def test_a_url_its_spelling_rules_out_is_refused(url: str, reason: str) -> None:
    refusal = literal_refusal(url)

    assert refusal is not None and reason in refusal


@pytest.mark.parametrize(
    "url",
    ["ftp://example.org/", "https://", "https://localhost/", "http://10.1.2.3/"],
)
async def test_the_full_validation_states_the_same_refusal(url: str) -> None:
    verdict = await validate_url(url)

    assert not verdict.valid
    assert verdict.error == literal_refusal(url)
