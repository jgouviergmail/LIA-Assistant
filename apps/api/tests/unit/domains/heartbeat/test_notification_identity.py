"""The identity a heartbeat notification carries, end to end.

A proactive card in the chat offers 👍/👎. Pressing one calls
``PATCH /heartbeat/notifications/{id}/feedback`` with the card's metadata
``target_id`` — and that route declares ``notification_id: UUID``.

Until this contract was pinned, ``target_id`` was a synthetic
``heartbeat_<8 hex>`` string while the audit row got a fresh, unrelated UUID.
Every vote from the chat therefore died as a 422 the frontend deliberately
swallows, and ``mark_proactive_feedback_submitted`` — which looks the archived
card up BY that same ``target_id`` — matched zero rows for heartbeats (it was
correct for interests, whose target_id IS the interest UUID). The measured
consequence: with ``PROACTIVE_FEEDBACK_ENABLED`` true by default and in both
``.env.example`` files, the buttons shipped, were pressed, and recorded nothing.

Three properties are pinned here, because each one alone is insufficient:

- the identifier the card will carry is a *parseable UUID* (so the route
  accepts it at all);
- the audit row is created *under that very UUID* (so the route updates the
  right row rather than 404-ing);
- ``run_id`` carries the token-tracking run — the column's own docstring
  promises "Unique ID linking to token tracking", and it used to store the
  target_id instead, so the join to ``message_token_summary`` never resolved.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
from src.domains.heartbeat.schemas import HeartbeatContext, HeartbeatDecision, HeartbeatTarget
from src.infrastructure.proactive.base import ProactiveTaskResult

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _target() -> HeartbeatTarget:
    """A decision that notifies, with no interest topic (no enrichment path)."""
    return HeartbeatTarget(
        context=HeartbeatContext(),
        decision=HeartbeatDecision(
            action="notify",
            reason="something worth saying",
            message_draft="draft body",
            priority="medium",
            sources_used=["UPCOMING_CALENDAR_EVENTS"],
            interest_topic=None,
        ),
        decision_tokens_in=11,
        decision_tokens_out=7,
        decision_tokens_cache=0,
    )


@asynccontextmanager
async def _fake_db_ctx():
    session = MagicMock()
    session.commit = AsyncMock()
    yield session


def _patch_generation():
    """Neutralize the two LLM-bound calls inside generate_content."""
    return patch(
        "src.domains.heartbeat.proactive_task.generate_heartbeat_message",
        new=AsyncMock(return_value=("final message", 3, 5, 1)),
    )


async def _generate(task: HeartbeatProactiveTask) -> ProactiveTaskResult:
    with (
        _patch_generation(),
        patch.object(
            HeartbeatProactiveTask,
            "_get_user_personality",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.core.llm_config_helper.get_llm_config_for_agent",
            return_value=MagicMock(model="test-model"),
        ),
    ):
        return await task.generate_content(uuid4(), _target(), "fr")


# ---------------------------------------------------------------------------
# The contract
# ---------------------------------------------------------------------------


class TestNotificationIdentity:
    async def test_the_card_identifier_is_a_parseable_uuid(self) -> None:
        """The route declares `notification_id: UUID`; anything else is a 422.

        This is the half the frontend cannot compensate for: the identifier
        travels into the URL path, so a non-UUID is rejected before any
        handler runs.
        """
        result = await _generate(HeartbeatProactiveTask())

        assert result.target_id is not None
        # Raises ValueError — and fails the test — on the old synthetic form.
        UUID(result.target_id)

    async def test_the_audit_row_is_created_under_that_identifier(self) -> None:
        """`PATCH /heartbeat/notifications/{target_id}` must find a row.

        The card's identifier and the audit row's primary key are the SAME
        value, so the feedback route updates the notification the user is
        actually looking at.
        """
        task = HeartbeatProactiveTask()
        result = await _generate(task)
        result.metadata["run_id"] = "proactive_heartbeat_abc_deadbeef"

        with (
            patch(
                "src.domains.heartbeat.proactive_task.get_db_context",
                new=lambda: _fake_db_ctx(),
            ),
            patch("src.domains.heartbeat.repository.HeartbeatNotificationRepository") as repo_cls,
            patch("src.domains.agents.context.store.get_tool_context_store", new=AsyncMock()),
        ):
            repo_cls.return_value.create = AsyncMock()
            await task.on_notification_sent(uuid4(), _target(), result)

            kwargs = repo_cls.return_value.create.await_args.kwargs

        assert kwargs["notification_id"] == UUID(result.target_id)

    async def test_run_id_carries_the_token_tracking_run(self) -> None:
        """The column promises a link to token tracking — it must hold one.

        The runner injects the real run_id into the result metadata before
        dispatch (`proactive_{task}_{...}`); storing the target_id there
        instead left `message_token_summary` unjoinable.
        """
        task = HeartbeatProactiveTask()
        result = await _generate(task)
        result.metadata["run_id"] = "proactive_heartbeat_abc_deadbeef"

        with (
            patch(
                "src.domains.heartbeat.proactive_task.get_db_context",
                new=lambda: _fake_db_ctx(),
            ),
            patch("src.domains.heartbeat.repository.HeartbeatNotificationRepository") as repo_cls,
            patch("src.domains.agents.context.store.get_tool_context_store", new=AsyncMock()),
        ):
            repo_cls.return_value.create = AsyncMock()
            await task.on_notification_sent(uuid4(), _target(), result)

            kwargs = repo_cls.return_value.create.await_args.kwargs

        assert kwargs["run_id"] == "proactive_heartbeat_abc_deadbeef"

    async def test_a_missing_run_id_still_produces_a_unique_row(self) -> None:
        """No run_id in metadata (skip paths, older callers) must not collide.

        `run_id` is UNIQUE: falling back to a constant would make the second
        notification of that kind fail its INSERT. The identifier is unique by
        construction, so it is the safe fallback.
        """
        task = HeartbeatProactiveTask()
        result = await _generate(task)
        result.metadata.pop("run_id", None)

        with (
            patch(
                "src.domains.heartbeat.proactive_task.get_db_context",
                new=lambda: _fake_db_ctx(),
            ),
            patch("src.domains.heartbeat.repository.HeartbeatNotificationRepository") as repo_cls,
            patch("src.domains.agents.context.store.get_tool_context_store", new=AsyncMock()),
        ):
            repo_cls.return_value.create = AsyncMock()
            await task.on_notification_sent(uuid4(), _target(), result)

            kwargs = repo_cls.return_value.create.await_args.kwargs

        assert kwargs["run_id"] == result.target_id
        assert uuid.UUID(kwargs["run_id"])  # still unique per notification
