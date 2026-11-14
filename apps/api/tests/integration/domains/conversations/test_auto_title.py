"""An annex created without a title takes it from its first message, on PostgreSQL.

What must hold (ADR-378 amendment 2026-11-12):

- a creation with no title waits, under a placeholder in the person's language,
  and its replay is the same creation;
- the first readable message names the discussion ONCE, without rotating its
  generation, and the change is said to the open tabs as a metadata change;
- a title the person typed — at creation or through the rename form — is never
  replaced, and a rename begun before the title arrived is a stale edit;
- Main and a retired discussion are never titled.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import CONVERSATION_RETIRED_TITLE
from src.core.i18n_api_messages import APIMessages
from src.domains.conversations import catalogue_service
from src.domains.conversations.catalogue_service import ConversationCatalogueService
from src.domains.conversations.models import Conversation, ConversationAuditLog
from src.domains.conversations.sync_signal import CONVERSATION_METADATA
from src.domains.users.models import User
from tests.integration.domains.conversations.test_catalogue_routes import client as client
from tests.integration.domains.conversations.test_catalogue_routes import owner as owner

pytestmark = pytest.mark.integration
URL = "/api/v1/conversations"
FIRST_MESSAGE_TITLE = "Plan my trip to Lisbon next spring"


async def _create(http: AsyncClient, **body: Any) -> dict[str, Any]:
    response = await http.post(URL, json={"request_id": str(uuid4()), **body})
    assert response.status_code == 200, response.text
    row: dict[str, Any] = response.json()["conversation"]
    return row


async def _stored(db: AsyncSession, conversation_id: str) -> Conversation:
    row = (
        await db.execute(
            select(Conversation)
            .where(Conversation.id == UUID(conversation_id))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return row


async def _settle(db: AsyncSession, conversation_id: str, title: str) -> bool:
    return await ConversationCatalogueService(db).settle_waiting_title(UUID(conversation_id), title)


async def test_an_untitled_creation_waits_under_a_placeholder_and_replays_as_itself(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    request = {"request_id": str(uuid4())}
    created = await client.post(URL, json=request)
    assert created.status_code == 200
    row = created.json()["conversation"]
    assert row["title"] == APIMessages.conversation_untitled()
    assert (await _stored(async_session, row["id"])).title_auto is True

    # Omitted and null are one request: the same attempt replays either way.
    replay = await client.post(URL, json={**request, "title": None})
    assert replay.status_code == 200 and replay.json()["replayed"]
    assert replay.json()["conversation"]["id"] == row["id"]
    # The same attempt with a typed title is another creation's words.
    conflict = await client.post(URL, json={**request, "title": "Typed after all"})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["error"] == "conversation_request_conflict"


async def test_a_typed_title_is_stored_as_the_persons_own(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    row = await _create(client, title="My own words")

    assert (await _stored(async_session, row["id"])).title_auto is False


async def test_the_first_message_names_the_discussion_once(
    client: AsyncClient, async_session: AsyncSession, owner: User
) -> None:
    row = await _create(client)

    with patch.object(catalogue_service, "arm_conversation_signal") as armed:
        assert await _settle(async_session, row["id"], FIRST_MESSAGE_TITLE) is True

    after = (await client.get(f"{URL}/{row['id']}")).json()
    assert after["title"] == FIRST_MESSAGE_TITLE
    # Metadata only: the generation, the runtime and the history are untouched.
    assert after["revision"] == row["revision"]
    assert (await _stored(async_session, row["id"])).title_auto is False
    # Said to the open tabs the way a rename is.
    armed.assert_called_once_with(
        async_session,
        user_id=owner.id,
        conversation_id=UUID(row["id"]),
        kind=CONVERSATION_METADATA,
    )
    audit = (
        await async_session.scalars(
            select(ConversationAuditLog.action).where(
                ConversationAuditLog.conversation_id == UUID(row["id"])
            )
        )
    ).all()
    assert sorted(audit) == ["created", "titled"]

    # Once: the second message changes nothing and says nothing.
    with patch.object(catalogue_service, "arm_conversation_signal") as armed_again:
        assert await _settle(async_session, row["id"], "Something else entirely") is False
    armed_again.assert_not_called()
    assert (await client.get(f"{URL}/{row['id']}")).json()["title"] == FIRST_MESSAGE_TITLE


async def test_a_typed_title_is_never_replaced(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    row = await _create(client, title="My own words")

    assert await _settle(async_session, row["id"], FIRST_MESSAGE_TITLE) is False
    assert (await client.get(f"{URL}/{row['id']}")).json()["title"] == "My own words"


async def test_renaming_a_waiting_discussion_keeps_what_the_person_typed(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    row = await _create(client)
    renamed = await client.patch(
        f"{URL}/{row['id']}",
        json={"title": "Mine", "expected_title": row["title"], "expected_revision": 0},
    )
    assert renamed.status_code == 200

    assert await _settle(async_session, row["id"], FIRST_MESSAGE_TITLE) is False
    assert (await client.get(f"{URL}/{row['id']}")).json()["title"] == "Mine"


async def test_keeping_the_placeholder_through_the_rename_form_makes_it_the_title(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    """Saving the form unchanged is the person saying « this title »."""
    row = await _create(client)
    kept = await client.patch(
        f"{URL}/{row['id']}",
        json={"title": row["title"], "expected_title": row["title"], "expected_revision": 0},
    )
    assert kept.status_code == 200

    assert await _settle(async_session, row["id"], FIRST_MESSAGE_TITLE) is False
    assert (await client.get(f"{URL}/{row['id']}")).json()["title"] == row["title"]


async def test_a_rename_begun_before_the_title_arrived_is_a_stale_edit(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    row = await _create(client)
    assert await _settle(async_session, row["id"], FIRST_MESSAGE_TITLE) is True

    late = await client.patch(
        f"{URL}/{row['id']}",
        json={"title": "Late edit", "expected_title": row["title"], "expected_revision": 0},
    )

    assert late.status_code == 409
    assert late.json()["detail"]["error"] == "conversation_title_changed"
    assert (await client.get(f"{URL}/{row['id']}")).json()["title"] == FIRST_MESSAGE_TITLE


async def test_main_is_never_titled(client: AsyncClient, async_session: AsyncSession) -> None:
    await _create(client)  # creating an annex ensures Main
    main = (await client.get(f"{URL}/me")).json()

    assert await _settle(async_session, main["id"], FIRST_MESSAGE_TITLE) is False
    assert (await client.get(f"{URL}/me")).json()["title"] == main["title"]


async def test_a_retired_discussion_is_never_titled(
    client: AsyncClient, async_session: AsyncSession
) -> None:
    row = await _create(client)
    await async_session.execute(
        update(Conversation)
        .where(Conversation.id == UUID(row["id"]))
        .values(deleted_at=datetime.now(UTC), title=CONVERSATION_RETIRED_TITLE)
    )

    assert await _settle(async_session, row["id"], FIRST_MESSAGE_TITLE) is False
    assert (await _stored(async_session, row["id"])).title == CONVERSATION_RETIRED_TITLE
