"""A mailbox draft is found by WHO it is for.

Every draft is « from » the person, so « the draft for Marie » can only match
on the recipient: the e-mail context type must search the ``to`` field.
"""

from __future__ import annotations

import pytest

from src.domains.agents.constants import CONTEXT_DOMAIN_EMAILS
from src.domains.agents.context import ContextTypeRegistry
from src.domains.agents.context.resolver import ReferenceResolver
from src.domains.agents.tools import emails_tools  # noqa: F401 — registers the e-mail context type

pytestmark = pytest.mark.unit

_DRAFTS = [
    {
        "index": 1,
        "id": "m-1",
        "subject": "Budget 2027",
        "snippet": "Voici le budget",
        "from_email": "me@example.com",
        "to": "Paul Durand <paul@example.com>",
    },
    {
        "index": 2,
        "id": "m-2",
        "subject": "Réunion de jeudi",
        "snippet": "Je confirme pour jeudi",
        "from_email": "me@example.com",
        "to": "Marie Martin <marie@example.com>",
    },
]


def test_a_draft_is_resolved_by_its_recipient() -> None:
    definition = ContextTypeRegistry.get_definition(CONTEXT_DOMAIN_EMAILS)

    result = ReferenceResolver(definition).resolve("Marie Martin", _DRAFTS)

    assert result.success is True
    assert result.item is not None
    assert result.item["id"] == "m-2"
