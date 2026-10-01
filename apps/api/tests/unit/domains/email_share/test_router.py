"""``/email-share/options`` publishes the suggestions; ``/recipients`` serves them.

Suggestions are offered only where recipients are free (the mailbox road) and
a contacts connector exists; the relay's one recipient is locked, so nothing
would be typed. The route bounds its query and answers the published shape.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.core.constants import (
    EMAIL_SHARE_RECIPIENT_QUERY_MAX_CHARS,
    EMAIL_SHARE_RECIPIENT_QUERY_MIN_CHARS,
    EMAIL_SHARE_RECIPIENT_SUGGESTIONS_MAX,
)
from src.core.session_dependencies import get_current_active_session
from src.domains.connectors.models import ConnectorType
from src.domains.email_share import router as email_share_router
from src.domains.email_share.recipient_match import RecipientSuggestion
from src.domains.email_share.recipients import RecipientSuggestions
from src.domains.email_share.service import ShareRoute

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(email_share_router.router)
    app.dependency_overrides[get_current_active_session] = lambda: SimpleNamespace(
        id=uuid4(), is_verified=True, email="me@example.org"
    )
    # The capability guard and the per-account limiters are proven elsewhere.
    for dependency in email_share_router.router.dependencies:
        app.dependency_overrides[dependency.dependency] = lambda: None
    app.dependency_overrides[email_share_router.rate_limit_recipient_suggestions] = lambda: None
    return TestClient(app)


MAILBOX = ShareRoute.mailbox(ConnectorType.GOOGLE_GMAIL, max_file_bytes=1_000_000)
RELAY = ShareRoute.relay("me@example.org", max_file_bytes=1_000_000)


@pytest.mark.parametrize(
    ("route", "contacts", "offered"),
    [(MAILBOX, True, True), (MAILBOX, False, False), (RELAY, True, False)],
)
def test_suggestions_are_offered_only_for_free_recipients_with_a_contacts_connector(
    client: TestClient, route: ShareRoute, contacts: bool, offered: bool
) -> None:
    with (
        patch.object(email_share_router, "resolve_route", AsyncMock(return_value=route)),
        patch.object(email_share_router, "suggestions_available", AsyncMock(return_value=contacts)),
    ):
        response = client.get("/email-share/options")

    assert response.status_code == 200
    body = response.json()
    assert body["recipient_suggestions"] is offered
    assert body["recipient_query_min_chars"] == EMAIL_SHARE_RECIPIENT_QUERY_MIN_CHARS
    assert body["recipient_suggestions_max"] == EMAIL_SHARE_RECIPIENT_SUGGESTIONS_MAX


def test_the_suggestions_answer_their_query(client: TestClient) -> None:
    found = RecipientSuggestions(
        query="jer",
        suggestions=[RecipientSuggestion(name="Jérôme", email="jerome@example.org")],
        truncated=True,
    )
    with patch.object(
        email_share_router, "suggest_recipients", AsyncMock(return_value=found)
    ) as suggest:
        response = client.get("/email-share/recipients", params={"q": "jer"})

    assert response.status_code == 200
    assert response.json() == {
        "query": "jer",
        "suggestions": [{"name": "Jérôme", "email": "jerome@example.org"}],
        "truncated": True,
    }
    assert suggest.await_args is not None and suggest.await_args.args[1] == "jer"


@pytest.mark.parametrize("params", [{}, {"q": "x" * (EMAIL_SHARE_RECIPIENT_QUERY_MAX_CHARS + 1)}])
def test_a_missing_or_oversized_query_is_refused(
    client: TestClient, params: dict[str, str]
) -> None:
    with patch.object(email_share_router, "suggest_recipients", AsyncMock()) as suggest:
        response = client.get("/email-share/recipients", params=params)

    assert response.status_code == 422
    suggest.assert_not_awaited()
