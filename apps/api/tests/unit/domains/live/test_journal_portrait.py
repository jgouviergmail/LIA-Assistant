"""The native voice frames share a current, whole, bounded portrait."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.live.preferences import LivePreferences
from src.domains.live.providers.protocol import LiveSetupInputs
from src.domains.live.setup_render import render_setup_inputs
from src.domains.telephony.mandates import append_owner_portrait
from src.domains.telephony.models import CallKind
from src.domains.users.models import User

pytestmark = pytest.mark.unit


def _inputs(budget: int = 1000) -> LiveSetupInputs:
    return LiveSetupInputs(
        model="model",
        voice="voice",
        thinking_level=None,
        system_instruction="BASE FRAME",
        tool_declaration=None,
        preferences=LivePreferences(),
        trigger_tokens=2000,
        target_tokens=budget,
    )


@pytest.mark.parametrize("mode", ["direct", "delegated"])
async def test_live_start_and_wake_share_one_provider_neutral_portrait(mode):
    from src.domains.live import setup_render

    inputs = _inputs()
    connectors = MagicMock(setup_inputs=MagicMock(return_value=inputs))
    user = SimpleNamespace(id=uuid4(), phone_disabled_domains=[])
    chosen = SimpleNamespace(model="model", voice="voice", thinking_level=None)
    block = "<UserModelContext>Current user portrait.</UserModelContext>"
    with (
        patch.object(setup_render, "build_direct_setup_inputs", AsyncMock(return_value=inputs)),
        patch.object(
            setup_render, "build_journal_user_model_block", AsyncMock(return_value=block)
        ) as portrait,
    ):
        result = await render_setup_inputs(
            connectors,
            MagicMock(),
            user,
            chosen,
            mode=mode,
            language="fr",
            timezone="Europe/Paris",
            display_name="Alex",
            now=datetime.now(UTC),
            personality="",
            psyche_block="",
        )
    assert result.system_instruction == f"BASE FRAME\n\n{block}"
    portrait.assert_awaited_once_with(
        user.id, format="brief", flow="live", max_tokens=1000, budget_prefix="BASE FRAME"
    )
    assert inputs.system_instruction == "BASE FRAME"


@pytest.mark.parametrize("disabled,budget", [(["journal"], 1000), ([], 1)])
async def test_live_refusal_and_budget_never_publish_a_portrait_fragment(disabled, budget):
    from src.domains.live import setup_render

    inputs = _inputs(budget)
    connectors = MagicMock(setup_inputs=MagicMock(return_value=inputs))
    user = SimpleNamespace(id=uuid4(), phone_disabled_domains=disabled)
    with patch.object(
        setup_render, "build_journal_user_model_block", AsyncMock(return_value="")
    ) as portrait:
        result = await render_setup_inputs(
            connectors,
            MagicMock(),
            user,
            SimpleNamespace(),
            mode="delegated",
            language="fr",
            timezone="UTC",
            display_name="Alex",
            now=datetime.now(UTC),
            personality="",
            psyche_block="",
        )
    assert result.system_instruction == "BASE FRAME"
    if disabled:
        portrait.assert_not_awaited()
    else:
        assert portrait.await_args.kwargs["max_tokens"] == 1
        assert portrait.await_args.kwargs["budget_prefix"] == "BASE FRAME"


@pytest.mark.parametrize("kind", [CallKind.THIRD_PARTY, CallKind.VERIFICATION])
async def test_other_phone_kinds_never_open_or_receive_the_owner_portrait(kind):
    override = {"agent": {"prompt": {"prompt": "BASE"}}}
    with patch(
        "src.domains.journals.portrait_builder.build_journal_user_model_block", AsyncMock()
    ) as portrait:
        assert (
            await append_owner_portrait(
                override,
                user=SimpleNamespace(),
                kind=kind,
                user_context="",
                rich_context_allowed=True,
            )
            == override
        )
    portrait.assert_not_awaited()


async def test_owner_phone_retains_whole_block_and_neutralizes_vendor_variables():
    override = {"agent": {"prompt": {"prompt": "BASE"}}}
    user = SimpleNamespace(id=uuid4(), phone_disabled_domains=[], phone_rich_context_enabled=True)
    block = "<UserModelContext>User wrote {{example}}.</UserModelContext>"
    with patch(
        "src.domains.journals.portrait_builder.build_journal_user_model_block",
        AsyncMock(return_value=block),
    ):
        result = await append_owner_portrait(
            override, user=user, kind=CallKind.SELF, user_context="", rich_context_allowed=True
        )
    assert result["agent"]["prompt"]["prompt"] == "BASE\n\n" + block.replace("{{", "{ {").replace(
        "}}", "} }"
    )


@pytest.mark.parametrize(
    "rich_context,disabled,mandate_allows",
    [(False, [], True), (True, ["journal"], True), (True, [], False), (None, [], True)],
)
async def test_owner_phone_refused_context_never_opens_private_portrait(
    rich_context, disabled, mandate_allows
):
    override = {"agent": {"prompt": {"prompt": "OWNER MANDATE AND AVAILABILITY"}}}
    user = SimpleNamespace(
        id=uuid4(),
        phone_disabled_domains=disabled,
        phone_rich_context_enabled=rich_context,
    )
    if rich_context is None:
        del user.phone_rich_context_enabled
    with patch(
        "src.domains.journals.portrait_builder.build_journal_user_model_block",
        AsyncMock(return_value="<UserModelContext>Private synthesis.</UserModelContext>"),
    ) as portrait:
        result = await append_owner_portrait(
            override,
            user=user,
            kind=CallKind.SELF,
            user_context="",
            rich_context_allowed=mandate_allows,
        )
    portrait.assert_not_awaited()
    assert result is override
    assert result["agent"]["prompt"]["prompt"] == "OWNER MANDATE AND AVAILABILITY"


@pytest.mark.parametrize("refusal", ["rich_context", "journal_domain"])
async def test_owner_phone_rechecks_late_refusal_on_the_fresh_portrait_record(refusal):
    from src.domains.journals import portrait_builder

    owner_id = uuid4()
    stale_user = SimpleNamespace(
        id=owner_id, phone_disabled_domains=[], phone_rich_context_enabled=True
    )
    current_user = User(
        id=owner_id,
        email="phone-privacy@example.test",
        is_active=True,
        deleted_at=None,
        journals_enabled=True,
        phone_rich_context_enabled=refusal != "rich_context",
        phone_disabled_domains=["journal"] if refusal == "journal_domain" else [],
        journal_portrait_brief="A current private owner synthesis.",
        journal_portrait_compiled_at=datetime.now(UTC),
    )
    db = AsyncMock()
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=current_user))

    @asynccontextmanager
    async def session():
        yield db

    override = {"agent": {"prompt": {"prompt": "OWNER MANDATE"}}}
    with (
        patch.object(portrait_builder, "get_db_context", session),
        patch.object(portrait_builder.settings, "journals_enabled", True),
        patch.object(portrait_builder, "is_capability_enabled", AsyncMock(return_value=True)),
        patch(
            "src.domains.journals.lifecycle.portrait_is_current", AsyncMock(return_value=True)
        ) as lineage,
    ):
        result = await append_owner_portrait(
            override,
            user=stale_user,
            kind=CallKind.SELF,
            user_context="",
            rich_context_allowed=True,
        )
    assert result["agent"]["prompt"]["prompt"] == "OWNER MANDATE"
    lineage.assert_not_awaited()
    query = db.execute.await_args.args[0]
    assert query.get_execution_options()["populate_existing"] is True
