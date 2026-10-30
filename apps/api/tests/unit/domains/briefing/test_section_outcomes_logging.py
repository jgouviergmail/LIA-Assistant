"""A section that failed is logged by its facts, never by the words its error carries (ADR-317).

A connector's exception text quotes what it read — an address, a subject, a URL with its
query — and the safety net of ``fetch_and_map`` logged it whole at WARNING.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from structlog.testing import capture_logs

from src.domains.briefing.schemas import CardStatus
from src.domains.briefing.section_outcomes import fetch_and_map

pytestmark = pytest.mark.unit

_WORDS = "invoice from someone@example.org about the private matter"


async def test_a_failed_section_logs_its_type_never_its_words() -> None:
    async def failing() -> None:
        raise RuntimeError(_WORDS)

    with capture_logs() as logs:
        section = await fetch_and_map("emails", failing, user_id=uuid4())

    assert section.status == CardStatus.ERROR
    (line,) = [entry for entry in logs if entry["event"] == "briefing_section_failed"]
    assert line["error_type"] == "RuntimeError"
    assert _WORDS not in str(line)
