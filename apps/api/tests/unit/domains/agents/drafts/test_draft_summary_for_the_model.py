"""What the model reads of a draft it created (ADR-323 review 14).

The preview draws each value with character references so the chat shows its
characters; the tool result the model reads is the same preview, read back —
handed ``jean_dupont&#64;example.com``, a model could reuse it as an address.
The header names the draft with its raw words, and is read as such.
"""

from __future__ import annotations

import pytest

from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.drafts.service import DraftService

pytestmark = pytest.mark.unit


def _summary(draft_type: DraftType, content: dict[str, object]) -> str:
    return DraftService()._build_draft_summary(Draft(type=draft_type, content=content), "fr")


def test_the_preview_s_values_are_read_back() -> None:
    summary = _summary(
        DraftType.EMAIL,
        {"to": "jean_dupont@example.com", "subject": "Réunion <lundi> [v2]", "body": "Salut"},
    )

    assert "jean_dupont@example.com" in summary
    assert "Réunion <lundi> [v2]" in summary
    assert "&#" not in summary


def test_a_raw_title_is_never_decoded() -> None:
    """A task titled « code &#60;b&#62; » is named so in the header and in the
    preview — decoding the header would have told the model « code <b> »."""
    summary = _summary(DraftType.TASK, {"title": "code &#60;b&#62;"})

    assert summary.count("code &#60;b&#62;") == 2
