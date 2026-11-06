"""What the person signs with: one door for the composer and the assistant (ADR-369, lot 7, A3).

A signature is free text a recipient reads: it keeps its lines and its quotes, which the
preferences that reach a prompt never may. It belongs to the mailbox, so only the active one is
read, from the database and never from the provider.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.constants import MAIL_SIGNATURE_MAX_CHARS
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences import mail_signature
from src.domains.connectors.preferences.registry import get_preference_schema
from src.domains.connectors.preferences.schemas import PreferencesRequest
from src.domains.connectors.preferences.service import ConnectorPreferencesService

pytestmark = pytest.mark.unit

USER = uuid4()
TEXT = 'Ana Lima\nDirectrice "Produit"\n{Acme}'
MAILBOXES = [
    ConnectorType.GOOGLE_GMAIL,
    ConnectorType.MICROSOFT_OUTLOOK,
    ConnectorType.APPLE_EMAIL,
]


def _service(connector_type: ConnectorType | None) -> Any:
    """The door's reads: a session, and the provider the account has active."""
    service = MagicMock(db=MagicMock())

    @contextlib.asynccontextmanager
    async def unit_of_work() -> AsyncIterator[Any]:
        yield service

    connectors = MagicMock(unit_of_work=unit_of_work)
    return (
        patch.object(mail_signature, "DetachedConnectorService", return_value=connectors),
        patch.object(
            mail_signature, "resolve_active_connector", AsyncMock(return_value=connector_type)
        ),
    )


class TestTheText:
    @pytest.mark.parametrize("connector_type", MAILBOXES)
    def test_every_mailbox_keeps_one(self, connector_type: ConnectorType) -> None:
        kept = ConnectorPreferencesService.validate_and_sanitize(
            connector_type.value, {"signature": TEXT}
        )

        assert kept.model_dump() == {"signature": TEXT}

    @pytest.mark.parametrize("connector_type", MAILBOXES)
    def test_a_control_character_never_reaches_a_message(
        self, connector_type: ConnectorType
    ) -> None:
        kept = ConnectorPreferencesService.validate_and_sanitize(
            connector_type.value, {"signature": "Ana\x00\x07 Lima\r\nAcme"}
        )

        assert kept.model_dump() == {"signature": "Ana Lima\nAcme"}

    def test_it_is_bounded_where_it_is_written(self) -> None:
        with pytest.raises(ValidationError):
            PreferencesRequest(signature="a" * (MAIL_SIGNATURE_MAX_CHARS + 1))

    def test_a_longer_text_than_a_calendar_s_name_survives(self) -> None:
        long = "a" * MAIL_SIGNATURE_MAX_CHARS

        kept = ConnectorPreferencesService.validate_and_sanitize(
            ConnectorType.GOOGLE_GMAIL.value, {"signature": long}
        )

        assert kept.model_dump() == {"signature": long}

    def test_a_name_that_reaches_a_prompt_stays_cleaned(self) -> None:
        kept = ConnectorPreferencesService.validate_and_sanitize(
            ConnectorType.GOOGLE_CALENDAR.value, {"default_calendar_name": 'a"{b}\nc'}
        )

        assert kept.model_dump() == {"default_calendar_name": "abc"}

    def test_the_schema_is_found_for_the_three(self) -> None:
        assert all(get_preference_schema(item.value) for item in MAILBOXES)


class TestTheBlock:
    def test_none_adds_nothing(self) -> None:
        assert mail_signature.signature_block("") == ""

    def test_it_is_set_off_by_the_mail_delimiter(self) -> None:
        assert mail_signature.signature_block("Ana\nAcme") == "\n\n-- \nAna\nAcme"

    def test_in_html_its_words_stay_words(self) -> None:
        block = mail_signature.signature_block("Ana <b>\nAcme", is_html=True)

        assert block == "<br><br>-- <br>Ana &lt;b&gt;<br>Acme"


class TestReading:
    async def test_it_reads_the_active_mailbox_s(self) -> None:
        resolved, active = _service(ConnectorType.MICROSOFT_OUTLOOK)
        read = AsyncMock(return_value=TEXT)
        with resolved, active, patch.object(mail_signature, "read_owner_preference_name", read):
            text = await mail_signature.read_signature(USER)

        assert text == TEXT
        assert read.await_args.args[1:] == (USER, ConnectorType.MICROSOFT_OUTLOOK, "signature")

    async def test_a_mailbox_nothing_was_written_for_signs_with_nothing(self) -> None:
        resolved, active = _service(ConnectorType.GOOGLE_GMAIL)
        read = AsyncMock(return_value=None)
        with resolved, active, patch.object(mail_signature, "read_owner_preference_name", read):
            assert await mail_signature.read_signature(USER) == ""

    async def test_no_mailbox_signs_with_nothing(self) -> None:
        resolved, active = _service(None)
        with resolved, active:
            assert await mail_signature.read_signature(USER) == ""


class TestSaving:
    def _row(self) -> Any:
        return patch.object(
            mail_signature,
            "ConnectorRepository",
            return_value=MagicMock(get_by_user_and_type=AsyncMock(return_value=MagicMock(id="c1"))),
        )

    async def test_it_goes_through_the_owner_s_own_write(self) -> None:
        resolved, active = _service(ConnectorType.APPLE_EMAIL)
        write = AsyncMock(return_value=MagicMock(preferences={"signature": TEXT}))
        with (
            resolved,
            active,
            self._row(),
            patch.object(mail_signature, "update_owned_connector_preferences", write),
        ):
            saved = await mail_signature.save_signature(USER, TEXT)

        assert saved == TEXT
        assert write.await_args.args[1:3] == (USER, "c1")
        assert write.await_args.args[3].signature == TEXT

    async def test_an_empty_text_clears_it(self) -> None:
        resolved, active = _service(ConnectorType.APPLE_EMAIL)
        write = AsyncMock(return_value=MagicMock(preferences={"signature": ""}))
        with (
            resolved,
            active,
            self._row(),
            patch.object(mail_signature, "update_owned_connector_preferences", write),
        ):
            assert await mail_signature.save_signature(USER, "") == ""

        assert write.await_args.args[3].signature == ""

    async def test_no_mailbox_has_nowhere_to_keep_it(self) -> None:
        resolved, active = _service(None)
        with resolved, active, pytest.raises(mail_signature.NoActiveMailboxError):
            await mail_signature.save_signature(USER, TEXT)
