"""An HTTP refusal is classified by its STATUS, shared by every HTTP-bound tool.

``web_fetch`` mapped 404 to ``NOT_FOUND`` and everything else — including the
403 an anti-bot answers — to ``EXTERNAL_API_ERROR``, a code the honesty
directive reads as « the provider is failing, a fallback may apply ». It is the
opposite advice: a site refusing automated reading will refuse the retry too.

One function, so a second HTTP tool cannot invent a second taxonomy (ADR-303).
"""

from __future__ import annotations

import pytest

from src.domains.agents.tools.common import ToolErrorCode, http_status_to_error_code

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ToolErrorCode.UNAUTHORIZED),
        (403, ToolErrorCode.FORBIDDEN),
        (404, ToolErrorCode.NOT_FOUND),
        (410, ToolErrorCode.NOT_FOUND),
        (429, ToolErrorCode.RATE_LIMIT_EXCEEDED),
        (408, ToolErrorCode.EXTERNAL_API_ERROR),
        (500, ToolErrorCode.EXTERNAL_API_ERROR),
        (503, ToolErrorCode.EXTERNAL_API_ERROR),
        (400, ToolErrorCode.INVALID_INPUT),
        (418, ToolErrorCode.INVALID_INPUT),
        (302, ToolErrorCode.EXTERNAL_API_ERROR),
    ],
)
def test_http_status_to_error_code(status: int, expected: ToolErrorCode) -> None:
    assert http_status_to_error_code(status) is expected


def test_a_refusal_is_never_reported_as_a_provider_outage() -> None:
    """403 and 401 must not read as « retry, the provider is flaky »."""
    for status in (401, 403):
        assert http_status_to_error_code(status) is not ToolErrorCode.EXTERNAL_API_ERROR
