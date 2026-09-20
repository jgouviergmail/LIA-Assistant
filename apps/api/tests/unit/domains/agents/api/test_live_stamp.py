"""A delegated turn's user row carries the session it was spoken in (ADR-299, spec A7)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.field_names import FIELD_LIVE_SESSION_ID, FIELD_RUN_ID, FIELD_SPOKEN_TEXT
from src.domains.agents.api.archive_first import archive_user_message_first
from src.domains.agents.api.archive_metadata import with_live_stamp

pytestmark = pytest.mark.unit


def test_with_live_stamp_returns_the_same_object_when_no_session() -> None:
    base = {FIELD_RUN_ID: "r"}
    assert with_live_stamp(base, None, None) is base


def test_with_live_stamp_is_a_new_dict_with_both_keys() -> None:
    base = {FIELD_RUN_ID: "r"}
    stamped = with_live_stamp(base, "a" * 32, "what is on my agenda")
    assert stamped is not base
    assert stamped[FIELD_LIVE_SESSION_ID] == "a" * 32
    assert stamped[FIELD_SPOKEN_TEXT] == "what is on my agenda"
    assert FIELD_SPOKEN_TEXT not in base


def test_with_live_stamp_omits_an_empty_transcription() -> None:
    stamped = with_live_stamp({FIELD_RUN_ID: "r"}, "a" * 32, "")
    assert FIELD_LIVE_SESSION_ID in stamped
    assert FIELD_SPOKEN_TEXT not in stamped


async def test_archive_first_stamps_the_user_row() -> None:
    conv_service = MagicMock()
    conv_service.archive_message = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
    with patch("src.infrastructure.database.get_db_context") as ctx:
        ctx.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        ctx.return_value.__aexit__ = AsyncMock(return_value=False)
        await archive_user_message_first(
            conv_service=conv_service,
            conversation_id=uuid.uuid4(),
            user_message="agenda?",
            run_id="run_1",
            is_hitl_resumption=False,
            attachment_meta={},
            stt_kwargs={},
            live_session_id="b" * 32,
            spoken_text="agenda ?",
        )
    metadata = conv_service.archive_message.call_args.args[3]
    assert metadata[FIELD_LIVE_SESSION_ID] == "b" * 32
    assert metadata[FIELD_SPOKEN_TEXT] == "agenda ?"
    assert metadata[FIELD_RUN_ID] == "run_1"
