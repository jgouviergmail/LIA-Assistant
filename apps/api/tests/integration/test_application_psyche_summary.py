"""Paid prose is proposed without initialization and runs only against approved source facts."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, update

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.psyche_summary import (
    execute_psyche_summary,
    prepare_psyche_summary,
)
from src.domains.agents.application.psyche_summary_schemas import PsycheSummaryRequest
from src.domains.psyche.models import PsycheState
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("committed", [False, True])
async def test_initialization_lost_ack_is_unknown_and_never_starts_provider(
    async_session, test_user, monkeypatch, committed
):
    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(settings, "psyche_enabled", True)
    owner = test_user.id
    await async_session.commit()
    model = AsyncMock()
    monkeypatch.setattr("src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation", model)
    draft = await prepare_psyche_summary(
        async_session, owner, PsycheSummaryRequest(scope="current_account")
    )
    original = async_session.commit

    async def unknown():
        if committed:
            await original()
        raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgement"))

    monkeypatch.setattr(async_session, "commit", unknown)
    receipt = PreferenceWriteReceipt()
    with pytest.raises(CommandRejected) as refused:
        await execute_psyche_summary(async_session, owner, draft, receipt)
    assert refused.value.code == "COMPLETION_UNKNOWN" and not receipt.committed
    model.assert_not_called()
    await async_session.rollback()
    saved = await async_session.scalar(select(PsycheState.id).where(PsycheState.user_id == owner))
    assert (saved is not None) == committed


async def test_changed_state_between_committed_initialization_and_model_is_partial(
    async_session, test_user, monkeypatch
):
    from src.domains.psyche.service import PsycheService

    monkeypatch.setattr(settings, "psyche_enabled", True)
    owner = test_user.id
    model = AsyncMock()
    monkeypatch.setattr("src.infrastructure.llm.get_llm", lambda *args: MagicMock())
    monkeypatch.setattr("src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation", model)
    draft = await prepare_psyche_summary(
        async_session, owner, PsycheSummaryRequest(scope="current_account")
    )
    original = PsycheService.generate_summary

    async def changed(service, actor_id, language, **kwargs):
        await async_session.execute(
            update(PsycheState).where(PsycheState.user_id == owner).values(mood_pleasure=0.8)
        )
        await async_session.commit()
        return await original(service, actor_id, language, **kwargs)

    monkeypatch.setattr(PsycheService, "generate_summary", changed)
    receipt = PreferenceWriteReceipt()
    with pytest.raises(ResourceConflictError):
        await execute_psyche_summary(async_session, owner, draft, receipt)
    assert receipt.committed and receipt.values["psyche_summary"]["state_initialized"]
    assert receipt.values["psyche_summary"]["generation_status"] == "not_started"
    model.assert_not_called()


@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "absent",
        "stale",
        "expired",
        "withdrawn",
        "provider_failure",
        "late_withdrawal",
        "quota",
        "source_changed_during_model",
    ],
)
async def test_summary_confirmation_and_paid_boundaries(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "psyche_enabled", True)
    owner = test_user.id
    if scenario != "absent":
        async_session.add(PsycheState(user_id=owner, mood_pleasure=0.4))
        await async_session.commit()
    result = MagicMock(text="Observed companion mood.", usage_metadata=None)
    model = AsyncMock(return_value=result)
    if scenario == "provider_failure":
        model.side_effect = RuntimeError("provider unavailable")
    if scenario == "late_withdrawal":

        async def disable(**kwargs):
            monkeypatch.setattr(settings, "application_tools_enabled", False)
            return result

        model.side_effect = disable
    if scenario == "source_changed_during_model":

        async def change(**kwargs):
            await async_session.execute(
                update(PsycheState).where(PsycheState.user_id == owner).values(mood_pleasure=0.7)
            )
            await async_session.commit()
            return result

        model.side_effect = change
    monkeypatch.setattr("src.infrastructure.llm.get_llm", lambda *args: MagicMock())
    monkeypatch.setattr("src.infrastructure.llm.invoke_helpers.invoke_with_instrumentation", model)
    draft = await prepare_psyche_summary(
        async_session, owner, PsycheSummaryRequest(scope="current_account")
    )
    model.assert_not_called()
    stored = await async_session.scalar(select(PsycheState).where(PsycheState.user_id == owner))
    assert (stored is None) == (scenario == "absent")
    if scenario == "stale":
        await async_session.execute(
            update(PsycheState).where(PsycheState.user_id == owner).values(mood_pleasure=0.2)
        )
        await async_session.commit()
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "withdrawn":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    receipt = PreferenceWriteReceipt()
    if scenario == "quota":
        monkeypatch.setattr(
            "src.domains.agents.application.psyche_summary.enforce_usage_limit",
            AsyncMock(side_effect=AuthorizationError()),
        )
    errors = {
        "stale": ResourceConflictError,
        "expired": CommandRejected,
        "withdrawn": AuthorizationError,
        "late_withdrawal": AuthorizationError,
        "quota": AuthorizationError,
        "source_changed_during_model": ResourceConflictError,
    }
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await execute_psyche_summary(async_session, owner, draft, receipt)
        if scenario not in {"late_withdrawal", "source_changed_during_model"}:
            model.assert_not_called()
        assert receipt.values is None or "summary" not in receipt.values["psyche_summary"]
        return
    await execute_psyche_summary(async_session, owner, draft, receipt)
    assert receipt.committed and receipt.values["psyche_summary"]["summary"]
    assert model.await_count == 1
    if scenario != "provider_failure":
        assert receipt.values["psyche_summary"]["summary"] == "Observed companion mood."
    assert (
        await async_session.scalar(select(PsycheState).where(PsycheState.user_id == owner))
        is not None
    )
