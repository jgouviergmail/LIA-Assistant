"""Two-step browser confirmation is owner-bound and never persists a raw secret."""

import pytest
from sqlalchemy import func, select

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.ingestion.models import IngestionToken
from tests.integration.test_application_sms_actions import origin_for

pytestmark = pytest.mark.integration


async def test_proposal_has_no_effect_and_confirm_is_once_only(db_session, test_user):
    from src.domains.agents.application.sms_ui_commands import confirm_sms_ui, propose_sms_ui

    origin = origin_for(test_user.id)
    proposal = await propose_sms_ui(
        db_session, test_user.id, "sms_token.create", {"label": "iPhone"}, origin
    )
    assert await db_session.scalar(select(func.count()).select_from(IngestionToken)) == 0
    issued = await confirm_sms_ui(
        db_session, test_user.id, proposal.command_id, proposal.content_digest, origin
    )
    assert issued.secret is not None and issued.secret.token.startswith("pi_")
    command = await db_session.get(ApplicationCommand, proposal.command_id)
    from src.core.security.utils import decrypt_data

    assert issued.secret.token not in decrypt_data(command.content_encrypted)
    assert issued.secret.token not in decrypt_data(command.result_encrypted)
    with pytest.raises(ResourceConflictError):
        await confirm_sms_ui(
            db_session, test_user.id, proposal.command_id, proposal.content_digest, origin
        )
    assert await db_session.scalar(select(func.count()).select_from(IngestionToken)) == 1


async def test_confirmation_from_another_browser_refuses_before_write(db_session, test_user):
    from src.core.application_origin import ApplicationOrigin, ApplicationSessionFacts
    from src.domains.agents.application.sms_ui_commands import confirm_sms_ui, propose_sms_ui

    origin = origin_for(test_user.id)
    proposal = await propose_sms_ui(
        db_session, test_user.id, "sms_token.create", {"label": "iPhone"}, origin
    )

    async def current():
        return ApplicationSessionFacts(test_user.id, "b" * 64, "other", None)

    other = ApplicationOrigin(test_user.id, "b" * 64, current)
    with pytest.raises(AuthorizationError):
        await confirm_sms_ui(
            db_session, test_user.id, proposal.command_id, proposal.content_digest, other
        )
    assert await db_session.scalar(select(func.count()).select_from(IngestionToken)) == 0


async def test_tampered_confirmation_digest_refuses(db_session, test_user):
    from src.domains.agents.application.sms_ui_commands import confirm_sms_ui, propose_sms_ui

    origin = origin_for(test_user.id)
    proposal = await propose_sms_ui(
        db_session, test_user.id, "sms_token.create", {"label": "iPhone"}, origin
    )
    with pytest.raises(ResourceConflictError):
        await confirm_sms_ui(db_session, test_user.id, proposal.command_id, "0" * 64, origin)
    assert await db_session.scalar(select(func.count()).select_from(IngestionToken)) == 0


async def test_http_uses_live_cookie_and_redacts_invalid_input(async_client, db_session, test_user):
    from src.core.config import settings
    from src.core.session_dependencies import get_current_active_session
    from src.infrastructure.cache.redis import get_redis_session
    from src.infrastructure.cache.session_store import SessionStore
    from src.main import app

    store = SessionStore(await get_redis_session())
    first = await store.create_session(str(test_user.id))
    second = await store.create_session(str(test_user.id))
    app.dependency_overrides[get_current_active_session] = lambda: test_user
    try:
        async_client.cookies.set(settings.session_cookie_name, first.session_id)
        proposed = await async_client.post(
            "/api/v1/sms/commands",
            json={"operation_id": "sms_token.create", "payload": {"label": "iPhone"}},
        )
        assert proposed.status_code == 200, proposed.text
        data = proposed.json()
        url = f"/api/v1/sms/commands/{data['command_id']}/confirm"
        async_client.cookies.set(settings.session_cookie_name, second.session_id)
        refused = await async_client.post(url, json={"content_digest": data["content_digest"]})
        assert refused.status_code == 403
        async_client.cookies.set(settings.session_cookie_name, first.session_id)
        invalid = await async_client.post(url, json={"content_digest": "PRIVATE-SMS-INPUT"})
        assert invalid.status_code == 422 and "PRIVATE-SMS-INPUT" not in invalid.text
        assert invalid.headers["cache-control"] == "no-store"
        accepted = await async_client.post(url, json={"content_digest": data["content_digest"]})
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["secret"]["token"].startswith("pi_")
        assert accepted.headers["cache-control"] == "no-store"
        again = await async_client.post(url, json={"content_digest": data["content_digest"]})
        assert again.status_code == 409 and "pi_" not in again.text
    finally:
        app.dependency_overrides.pop(get_current_active_session, None)
        async_client.cookies.clear()


async def test_cancelled_proposal_can_never_be_confirmed(db_session, test_user):
    from src.domains.agents.application.sms_ui_commands import (
        cancel_sms_ui,
        confirm_sms_ui,
        propose_sms_ui,
    )

    origin = origin_for(test_user.id)
    proposal = await propose_sms_ui(db_session, test_user.id, "sms_token.create", {}, origin)
    await cancel_sms_ui(db_session, test_user.id, proposal.command_id, origin)
    await cancel_sms_ui(db_session, test_user.id, proposal.command_id, origin)
    with pytest.raises(ResourceConflictError):
        await confirm_sms_ui(
            db_session, test_user.id, proposal.command_id, proposal.content_digest, origin
        )
    assert await db_session.scalar(select(func.count()).select_from(IngestionToken)) == 0


async def test_source_state_conflict_closes_command_without_replaying(db_session, test_user):
    from src.domains.agents.application.sms_ui_commands import confirm_sms_ui, propose_sms_ui
    from src.domains.agents.effects.models import AgentEffect, EffectStatus

    origin = origin_for(test_user.id)
    proposal = await propose_sms_ui(
        db_session,
        test_user.id,
        "sms_preferences.update",
        {"ingestion_enabled": True, "assistant_enabled": True, "push_enabled": True},
        origin,
    )
    test_user.sms_preferences = {
        "ingestion_enabled": True,
        "assistant_enabled": False,
        "push_enabled": False,
    }
    await db_session.commit()
    with pytest.raises(ResourceConflictError):
        await confirm_sms_ui(
            db_session, test_user.id, proposal.command_id, proposal.content_digest, origin
        )
    command = await db_session.get(ApplicationCommand, proposal.command_id)
    assert command.phase == "failed"
    assert await db_session.scalar(select(AgentEffect.status)) == EffectStatus.ABANDONED


async def test_browser_settings_remain_available_when_assistant_management_tools_are_disabled(
    db_session, test_user, monkeypatch
):
    from src.core.config import settings
    from src.domains.agents.application.sms_actions import prepare_sms_action
    from src.domains.agents.application.sms_ui_commands import confirm_sms_ui, propose_sms_ui

    monkeypatch.setattr(settings, "application_tools_enabled", False)
    origin = origin_for(test_user.id)
    with pytest.raises(AuthorizationError):
        await prepare_sms_action(db_session, test_user.id, "sms_token.create", {}, origin=origin)
    proposal = await propose_sms_ui(db_session, test_user.id, "sms_token.create", {}, origin)
    assert await db_session.scalar(select(func.count()).select_from(IngestionToken)) == 0
    result = await confirm_sms_ui(
        db_session, test_user.id, proposal.command_id, proposal.content_digest, origin
    )
    assert result.secret is not None and result.outcome.committed
    assert await db_session.scalar(select(func.count()).select_from(IngestionToken)) == 1
