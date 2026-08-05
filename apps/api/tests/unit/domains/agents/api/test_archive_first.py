"""Unit tests for archive_user_message_first (ADR-117) + HITL flag patching.

Archive-first persists the user message BEFORE graph execution so the
turn survives client disconnects, cancellations and crashes. End-of-run
HITL flags are patched onto the row during finalization.

Habits Lot 0: an automated run (scheduled action) stamps
``is_automated_source: true`` into the row metadata so batch consumers can
exclude synthetic user messages; a human row never carries the key.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.field_names import FIELD_IS_AUTOMATED_SOURCE
from src.domains.agents.api.archive_first import archive_user_message_first
from src.domains.agents.api.service import AgentService


def _mock_db_context() -> MagicMock:
    """Async context manager yielding a MagicMock session."""
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=MagicMock())
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _service() -> AgentService:
    return AgentService.__new__(AgentService)  # skip graph-building __init__


@pytest.mark.unit
class TestArchiveUserMessageFirst:
    async def test_archives_user_message_with_run_id_and_stt(self):
        conversation_id = uuid.uuid4()
        archived_row = MagicMock(id=uuid.uuid4())
        conv_service = MagicMock()
        conv_service.archive_message = AsyncMock(return_value=archived_row)

        with patch(
            "src.infrastructure.database.get_db_context",
            return_value=_mock_db_context(),
        ):
            msg_id = await archive_user_message_first(
                conv_service=conv_service,
                conversation_id=conversation_id,
                user_message="hello",
                run_id="run_1",
                is_hitl_resumption=False,
                attachment_meta={},
                stt_kwargs={
                    "stt_provider": "whisper",
                    "stt_audio_duration_seconds": 2.0,
                    "stt_cost_usd": 0.01,
                    "stt_cost_eur": 0.009,
                },
            )

        assert msg_id == archived_row.id
        args, kwargs = conv_service.archive_message.await_args
        assert args[0] == conversation_id
        assert args[1] == "user"
        assert args[2] == "hello"
        assert args[3]["run_id"] == "run_1"
        assert "hitl_response" not in args[3]
        # A human row never carries the automated marker — absence IS the
        # human default (NULL semantics, mirroring source_policy).
        assert FIELD_IS_AUTOMATED_SOURCE not in args[3]
        assert kwargs["stt_provider"] == "whisper"

    async def test_hitl_resumption_flag_set_at_archive_time(self):
        conv_service = MagicMock()
        conv_service.archive_message = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

        with patch(
            "src.infrastructure.database.get_db_context",
            return_value=_mock_db_context(),
        ):
            await archive_user_message_first(
                conv_service=conv_service,
                conversation_id=uuid.uuid4(),
                user_message="oui",
                run_id="run_2",
                is_hitl_resumption=True,
                attachment_meta={},
                stt_kwargs={},
            )

        metadata = conv_service.archive_message.await_args.args[3]
        assert metadata["hitl_response"] is True

    async def test_automated_source_stamped_on_scheduled_runs(self):
        """Anti-feedback-loop marker (habits Lot 0): the synthetic user row
        written by the scheduled-action executor must be identifiable, or the
        rhythm profile would learn LIA's own automation times as habits."""
        conv_service = MagicMock()
        conv_service.archive_message = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

        with patch(
            "src.infrastructure.database.get_db_context",
            return_value=_mock_db_context(),
        ):
            await archive_user_message_first(
                conv_service=conv_service,
                conversation_id=uuid.uuid4(),
                user_message="daily digest prompt",
                run_id="run_auto",
                is_hitl_resumption=False,
                attachment_meta={},
                stt_kwargs={},
                is_automated_source=True,
            )

        metadata = conv_service.archive_message.await_args.args[3]
        assert metadata[FIELD_IS_AUTOMATED_SOURCE] is True

    async def test_attachment_meta_merged_into_metadata(self):
        conv_service = MagicMock()
        conv_service.archive_message = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        attachment_meta = {"attachments": [{"id": "a1", "filename": "f.png"}]}

        with patch(
            "src.infrastructure.database.get_db_context",
            return_value=_mock_db_context(),
        ):
            await archive_user_message_first(
                conv_service=conv_service,
                conversation_id=uuid.uuid4(),
                user_message="see attached",
                run_id="run_4",
                is_hitl_resumption=False,
                attachment_meta=attachment_meta,
                stt_kwargs={},
            )

        metadata = conv_service.archive_message.await_args.args[3]
        assert metadata["attachments"] == attachment_meta["attachments"]

    async def test_patch_flags_resumption_patches_decision_type(self):
        service = _service()
        conv_service = MagicMock()
        conv_service.patch_message_metadata = AsyncMock()
        msg_id = uuid.uuid4()

        await service._patch_user_message_hitl_flags(
            conv_service=conv_service,
            db=MagicMock(),
            archived_user_msg_id=msg_id,
            is_hitl_resumption=True,
            hitl_interrupt_detected=False,
            decision_type="APPROVED",
            run_id="run_p1",
            conversation_id=uuid.uuid4(),
        )

        args = conv_service.patch_message_metadata.await_args.args
        assert args[0] == msg_id
        assert args[1] == {"decision_type": "APPROVED"}

    async def test_patch_flags_interrupt_patches_hitl_interrupted(self):
        service = _service()
        conv_service = MagicMock()
        conv_service.patch_message_metadata = AsyncMock()
        msg_id = uuid.uuid4()

        await service._patch_user_message_hitl_flags(
            conv_service=conv_service,
            db=MagicMock(),
            archived_user_msg_id=msg_id,
            is_hitl_resumption=False,
            hitl_interrupt_detected=True,
            decision_type="UNKNOWN",
            run_id="run_p2",
            conversation_id=uuid.uuid4(),
        )

        args = conv_service.patch_message_metadata.await_args.args
        assert args[1] == {"hitl_interrupted": True}

    async def test_patch_flags_regular_message_patches_nothing(self):
        service = _service()
        conv_service = MagicMock()
        conv_service.patch_message_metadata = AsyncMock()

        await service._patch_user_message_hitl_flags(
            conv_service=conv_service,
            db=MagicMock(),
            archived_user_msg_id=uuid.uuid4(),
            is_hitl_resumption=False,
            hitl_interrupt_detected=False,
            decision_type="UNKNOWN",
            run_id="run_p3",
            conversation_id=uuid.uuid4(),
        )

        conv_service.patch_message_metadata.assert_not_awaited()

    async def test_patch_flags_missing_row_is_noop(self):
        # Archive-first failed earlier (best-effort): nothing to patch.
        service = _service()
        conv_service = MagicMock()
        conv_service.patch_message_metadata = AsyncMock()

        await service._patch_user_message_hitl_flags(
            conv_service=conv_service,
            db=MagicMock(),
            archived_user_msg_id=None,
            is_hitl_resumption=True,
            hitl_interrupt_detected=False,
            decision_type="APPROVED",
            run_id="run_p4",
            conversation_id=uuid.uuid4(),
        )

        conv_service.patch_message_metadata.assert_not_awaited()

    async def test_archive_failure_returns_none_and_does_not_raise(self):
        # Archive-first must NEVER block the run: a DB hiccup degrades to the
        # legacy behavior (no early row), it must not kill the generation.
        conv_service = MagicMock()
        conv_service.archive_message = AsyncMock(side_effect=RuntimeError("db down"))

        with patch(
            "src.infrastructure.database.get_db_context",
            return_value=_mock_db_context(),
        ):
            msg_id = await archive_user_message_first(
                conv_service=conv_service,
                conversation_id=uuid.uuid4(),
                user_message="hello",
                run_id="run_3",
                is_hitl_resumption=False,
                attachment_meta={},
                stt_kwargs={},
            )
        assert msg_id is None
