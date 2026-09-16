"""Unit tests for ``call_me`` — LIA calls the person, no confirmation card (lot 3).

The exception to the card rests on a VERIFIED number: the tool reads the one
seam the identity service exposes, and anything short of a verified line is a
localized refusal that points at the settings. The effect gate lets the tool
through unattended because its manifest says ``reversible`` — a routine
« call me every morning » is the reason a second tool exists at all.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

import src.domains.agents.tools.telephony_self_tools as smod
import src.domains.agents.tools.telephony_tools as tmod
from src.core.i18n_telephony import get_tool_phrases
from src.domains.agents.effects.gate import GateAction, decide_effect
from src.domains.agents.effects.scope import EffectScope
from src.domains.agents.telephony.catalogue_manifests import (
    TELEPHONY_AGENT_MANIFEST,
    call_me_catalogue_manifest,
)
from src.domains.telephony.identity import PhoneIdentity
from src.domains.telephony.service import InitiateCallResult


def _patch(
    monkeypatch: pytest.MonkeyPatch,
    *,
    connector_active: bool = True,
    verified_number: str | None = "+33612345678",
    status: str = "placed",
    context: str = "## Agenda",
) -> dict:
    captured: dict = {}

    async def _active(_user_id) -> bool:
        return connector_active

    async def _identity(_user_id) -> PhoneIdentity:
        return PhoneIdentity(
            phone_number=verified_number or "+33600000000",
            verified=verified_number is not None,
            verified_at=None,
            rich_context_enabled=True,
            disabled_domains=("email",),
        )

    async def _context(
        _user_id, *, language, timezone, objective, rich_context_enabled
    ) -> str:  # noqa: ANN001
        captured["context_requested"] = rich_context_enabled
        return context

    async def _initiate(**kwargs):  # noqa: ANN003
        captured["initiate"] = kwargs
        return InitiateCallResult(status=status, call_id=uuid4())  # type: ignore[arg-type]

    monkeypatch.setattr(smod, "_telephony_connector_active", _active)
    monkeypatch.setattr(smod, "_owner_identity", _identity)
    monkeypatch.setattr(smod, "_owner_context", _context)
    monkeypatch.setattr(smod, "_initiate_owner_call", _initiate)
    return captured


async def _run(objective: str = "go over the week") -> object:
    return await smod._build_call_me_output(
        user_id=uuid4(),
        locale="fr",
        timezone="Europe/Paris",
        objective=objective,
    )


@pytest.mark.unit
async def test_the_dial_receives_the_domains_the_person_switched_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch(monkeypatch, verified_number="+33612345678")
    await _run()
    assert captured["initiate"]["disabled_domains"] == frozenset({"email"})


@pytest.mark.unit
async def test_places_an_owner_call_on_the_verified_number(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch(monkeypatch)
    out = await _run()
    assert out.success is True
    assert out.message == get_tool_phrases("fr")["calling_you"]
    initiate = captured["initiate"]
    assert initiate["callee_phone"] == "+33612345678"
    assert initiate["objective"] == "go over the week"
    assert initiate["user_context"] == "## Agenda"
    assert captured["context_requested"] is True


@pytest.mark.unit
async def test_refuses_when_the_connector_is_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch(monkeypatch, connector_active=False)
    out = await _run()
    assert out.success is False
    assert out.error_code == "telephony_not_configured"
    assert "initiate" not in captured


@pytest.mark.unit
async def test_refuses_an_unverified_number_and_points_at_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _patch(monkeypatch, verified_number=None)
    out = await _run()
    assert out.success is False
    assert out.error_code == "phone_number_not_verified"
    assert out.message == get_tool_phrases("fr")["number_not_verified"]
    assert "initiate" not in captured


@pytest.mark.unit
@pytest.mark.parametrize(
    "status", ["already_active", "failed", "rejected", "auth_failed", "agent_sync_failed"]
)
async def test_non_placed_statuses_share_the_third_party_phrases(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    _patch(monkeypatch, status=status)
    out = await _run()
    assert out.success is False
    assert out.message == get_tool_phrases("fr")[tmod._STATUS_TO_PHRASE[status]]


@pytest.mark.unit
async def test_a_blank_objective_becomes_a_catch_up(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch(monkeypatch)
    await _run(objective="   ")
    assert captured["initiate"]["objective"] == ""  # the mandate says « a catch-up call »


@pytest.mark.unit
def test_manifest_declares_a_reversible_policy_with_a_written_reason() -> None:
    assert call_me_catalogue_manifest.mutation_policy == "reversible"
    assert call_me_catalogue_manifest.mutation_policy_reason
    assert len(call_me_catalogue_manifest.mutation_policy_reason) > 40
    assert call_me_catalogue_manifest.permissions.hitl_required is False
    assert "call_me_tool" in TELEPHONY_AGENT_MANIFEST.tools
    assert "contact" not in {p.name for p in call_me_catalogue_manifest.parameters}


@pytest.mark.unit
def test_the_gate_lets_call_me_run_unattended() -> None:
    """A routine « call me every morning » is the reason the tool exists."""
    scope = EffectScope(run_id="r", idempotency_key="k", source="scheduled")
    decision = decide_effect(call_me_catalogue_manifest.mutation_policy, scope)
    assert decision.action is GateAction.LEDGER


@pytest.mark.unit
async def test_third_party_tool_refuses_the_users_own_verified_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calling « yourself » through the stranger's mandate is a planner slip:
    the tool says so in technical English so the planner reaches for call_me."""

    async def _active(_user_id) -> bool:
        return True

    async def _verified(_user_id) -> str | None:
        return "+33612345678"

    async def _search(_user_id, _query, max_results=5):  # noqa: ANN001
        return [("Alex", "+33612345678")], "Alex"

    monkeypatch.setattr(tmod, "_telephony_connector_active", _active)
    monkeypatch.setattr(tmod, "_verified_number", _verified)
    monkeypatch.setattr(tmod, "_search_contacts_with_phones", _search)

    out = await tmod._build_place_phone_call_output(
        user_id=uuid4(), locale="fr", contact="Alex", objective="ask", date_window=None
    )
    assert out.success is False
    assert out.error_code == "callee_is_the_user"
    assert "call_me" in out.message


@pytest.mark.unit
async def test_third_party_tool_is_unaffected_when_no_number_is_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _active(_user_id) -> bool:
        return True

    async def _verified(_user_id) -> str | None:
        return None

    async def _search(_user_id, _query, max_results=5):  # noqa: ANN001
        return [("Alex", "+33612345678")], "Alex"

    monkeypatch.setattr(tmod, "_telephony_connector_active", _active)
    monkeypatch.setattr(tmod, "_verified_number", _verified)
    monkeypatch.setattr(tmod, "_search_contacts_with_phones", _search)

    out = await tmod._build_place_phone_call_output(
        user_id=uuid4(), locale="fr", contact="Alex", objective="ask", date_window=None
    )
    assert out.success is True
    assert out.registry_updates  # the PHONE_CALL draft, as before


# ---------------------------------------------------------------------------
# Live tools (lot 7): provisioned before the dial, attached to the call
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_live_tools_are_provisioned_and_handed_to_the_dial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from src.core.config import settings
    from src.domains.telephony.live_tools import LiveToolBinding

    monkeypatch.setattr(settings, "telephony_live_tools_enabled", True)
    connector = SimpleNamespace(connector_metadata={"agent_id": "ag"})
    seen: dict = {}

    class _Connectors:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def get_active(self, _user_id):  # noqa: ANN001
            return connector

    class _Creds:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def get_api_key_credentials(self, _user_id, _type):  # noqa: ANN001
            return SimpleNamespace(api_key="k", api_secret="whsec")

    async def _ensure(db, *, connector, api_key, api_secret):  # noqa: ANN001
        seen["ensure"] = (connector, api_key, api_secret)
        return (
            LiveToolBinding("get_events_tool", "tool_a", "event"),
            LiveToolBinding("get_emails_tool", "tool_b", "email"),
        )

    monkeypatch.setattr(smod, "TelephonyConnectorService", _Connectors)
    monkeypatch.setattr(smod, "ConnectorService", _Creds)
    monkeypatch.setattr(smod, "ensure_vendor_live_tools", _ensure)

    # Every available tool is provisioned once per connector; the person's own
    # switches decide what THIS call attaches (lot 8).
    bindings = await smod._live_tools_for(object(), uuid4(), disabled_domains=frozenset({"email"}))
    assert bindings == (LiveToolBinding("get_events_tool", "tool_a", "event"),)
    assert seen["ensure"] == (connector, "k", "whsec")


@pytest.mark.unit
async def test_live_tools_are_skipped_when_the_flag_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.core.config import settings

    monkeypatch.setattr(settings, "telephony_live_tools_enabled", False)

    class _Boom:
        def __init__(self, _db) -> None:  # noqa: ANN001
            raise AssertionError("nothing is looked up when the flag is off")

    monkeypatch.setattr(smod, "TelephonyConnectorService", _Boom)
    assert await smod._live_tools_for(object(), uuid4()) == ()


@pytest.mark.unit
async def test_live_tools_are_skipped_without_an_active_connector_or_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from src.core.config import settings

    monkeypatch.setattr(settings, "telephony_live_tools_enabled", True)

    class _NoConnector:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def get_active(self, _user_id):  # noqa: ANN001
            return None

    monkeypatch.setattr(smod, "TelephonyConnectorService", _NoConnector)
    assert await smod._live_tools_for(object(), uuid4()) == ()

    class _Connector:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def get_active(self, _user_id):  # noqa: ANN001
            return SimpleNamespace(connector_metadata={})

    class _NoSecret:
        def __init__(self, _db) -> None:  # noqa: ANN001
            pass

        async def get_api_key_credentials(self, _user_id, _type):  # noqa: ANN001
            return SimpleNamespace(api_key="k", api_secret=None)

    monkeypatch.setattr(smod, "TelephonyConnectorService", _Connector)
    monkeypatch.setattr(smod, "ConnectorService", _NoSecret)
    assert await smod._live_tools_for(object(), uuid4()) == ()


@pytest.mark.unit
def test_spoken_text_reads_a_card_and_markdown_as_words() -> None:
    """What the voice hears of a recent exchange: the words, never the markup."""
    text = smod.spoken_text('<div class="lia-card"><p><strong>Dentist</strong> at 10:00</p></div>')
    assert "<" not in text and "Dentist" in text and "10:00" in text
    assert smod.spoken_text("**Remind me** to *call* the bank") == "Remind me to call the bank"
