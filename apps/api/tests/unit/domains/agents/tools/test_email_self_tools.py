"""``send_email_to_me_tool`` — an e-mail to the user themselves (ADR-314).

The recipient is never a parameter: the connected mailbox sends to its OWN
address; without one, LIA's relay sends to the account's VERIFIED address (owner
arbitration Q1). A broken mailbox is not a usable one — the relay delivers and
the « Reconnect » notice says why. Nothing reads as « sent » unless a provider
or the relay accepted it, and the policy is one the effect gate LEDGERS in a
routine, where a draft is refused.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.effects.gate import GateAction, decide_effect
from src.domains.agents.effects.scope import EffectScope
from src.domains.agents.emails.content_generation import NOTE_TO_SELF_RECIPIENT, EmailContent
from src.domains.agents.emails.self_send_manifest import send_email_to_me_catalogue_manifest
from src.domains.agents.tools import email_self_tools
from src.domains.agents.tools.output import UnifiedToolOutput

_CONTENT = EmailContent(subject="Weather", body="Sunny, 21 °C.")


def _client(own_address: str | None = "me@gmail.com") -> MagicMock:
    client = MagicMock()
    client.get_own_address = AsyncMock(return_value=own_address)
    client.send_email = AsyncMock(return_value={"id": "m-1"})
    return client


def _user(*, verified: bool = True) -> SimpleNamespace:
    return SimpleNamespace(email="me@example.com", is_verified=verified)


async def _run(
    *,
    active: object = "google_gmail",
    client: MagicMock | None = None,
    broken: str | None = None,
    user: SimpleNamespace | None = None,
    relay_accepts: bool = True,
    content: object = _CONTENT,
    **kwargs: object,
) -> SimpleNamespace:
    client = client or _client()
    relay = MagicMock()
    relay.send_email = AsyncMock(return_value=relay_accepts)
    notice = MagicMock()
    resolve_content = AsyncMock(return_value=content)
    db = MagicMock()
    db.get = AsyncMock(return_value=user if user is not None else _user())

    @asynccontextmanager
    async def session():  # noqa: ANN202
        yield db

    deps = MagicMock()
    deps.get_connector_service = AsyncMock(return_value=MagicMock())
    config = SimpleNamespace(user_id=str(uuid4()))
    with (
        patch.object(email_self_tools, "validate_runtime_config", return_value=config),
        patch.object(email_self_tools, "resolve_email_content", resolve_content),
        patch("src.domains.agents.dependencies.get_dependencies", return_value=deps),
        patch(
            "src.domains.connectors.provider_resolver.resolve_active_connector",
            AsyncMock(return_value=active),
        ),
        patch(
            "src.domains.connectors.provider_resolver.resolve_client_for_category",
            AsyncMock(return_value=(client, active)),
        ),
        patch(
            "src.domains.connectors.provider_resolver.find_error_connector_type",
            AsyncMock(return_value=broken),
        ),
        patch("src.domains.agents.services.connector_error_notice.emit_connector_notice", notice),
        patch("src.infrastructure.database.session.get_db_context", session),
        patch("src.infrastructure.email.email_service.get_email_service", return_value=relay),
    ):
        output = await email_self_tools.send_email_to_me_tool.coroutine(
            runtime=MagicMock(), **kwargs
        )
    return SimpleNamespace(
        output=output, client=client, relay=relay, notice=notice, resolve=resolve_content
    )


@pytest.mark.unit
class TestTheConnectedMailbox:
    async def test_it_sends_to_its_own_address_and_nobody_else(self) -> None:
        run = await _run(content_instruction="today's weather")

        assert run.output.success is True
        assert run.output.structured_data == {"sent_to": "mailbox", "message_id": "m-1"}
        run.client.send_email.assert_awaited_once_with(
            to="me@gmail.com", subject="Weather", body="Sunny, 21 °C.", is_html=False
        )
        run.relay.send_email.assert_not_awaited()
        # The content is written as a note to self, never as a letter to a third party.
        assert run.resolve.await_args.kwargs["recipient"] == NOTE_TO_SELF_RECIPIENT

    async def test_a_mailbox_that_states_no_address_sends_nothing(self) -> None:
        run = await _run(client=_client(own_address=None))

        assert run.output.success is False
        assert run.output.error_code == "CONFIGURATION_ERROR"
        run.client.send_email.assert_not_awaited()
        run.relay.send_email.assert_not_awaited()

    async def test_a_provider_failure_is_returned_classified_never_raised(self) -> None:
        client = _client()
        client.send_email = AsyncMock(side_effect=RuntimeError("provider down"))

        run = await _run(client=client)

        assert isinstance(run.output, UnifiedToolOutput)
        assert run.output.success is False
        run.relay.send_email.assert_not_awaited()


@pytest.mark.unit
class TestLiaRelayWithoutAMailbox:
    async def test_the_verified_account_address_receives_it(self) -> None:
        run = await _run(active=None)

        assert run.output.success is True
        assert run.output.structured_data["sent_to"] == "account_email"
        address, subject, html_body, text_body = run.relay.send_email.await_args.args
        assert (address, subject, text_body) == ("me@example.com", "Weather", "Sunny, 21 °C.")
        run.notice.assert_not_called()

    async def test_an_unverified_account_address_is_never_written_to(self) -> None:
        """Otherwise an account opened with someone else's address makes LIA a relay."""
        run = await _run(active=None, user=_user(verified=False))

        assert run.output.success is False
        assert run.output.error_code == "CONFIGURATION_ERROR"
        run.relay.send_email.assert_not_awaited()

    async def test_a_relay_that_refuses_is_a_failure(self) -> None:
        run = await _run(active=None, relay_accepts=False)

        assert run.output.success is False
        assert run.output.error_code == "EXTERNAL_API_ERROR"

    async def test_a_broken_mailbox_is_named_and_the_relay_delivers(self) -> None:
        run = await _run(active=None, broken="google_gmail")

        assert run.output.success is True
        assert "reconnected" in run.output.message
        run.notice.assert_called_once_with("google_gmail", "reconnect", "send_email_to_me_tool")


@pytest.mark.unit
class TestContentAndMarkup:
    async def test_missing_content_sends_nothing(self) -> None:
        refusal = UnifiedToolOutput.failure(message="missing", error_code="MISSING_CONTENT")
        run = await _run(content=refusal)

        assert run.output is refusal
        run.client.send_email.assert_not_awaited()
        run.relay.send_email.assert_not_awaited()

    def test_a_plain_body_is_escaped_into_the_relay_html(self) -> None:
        html_body, text_body = email_self_tools.relay_bodies(
            EmailContent(subject="s", body="<script>x</script> & more"), is_html=False
        )

        assert "<script>" not in html_body
        assert "&lt;script&gt;x&lt;/script&gt; &amp; more" in html_body
        assert text_body == "<script>x</script> & more"

    def test_an_html_body_gets_a_readable_plain_part(self) -> None:
        html_body, text_body = email_self_tools.relay_bodies(
            EmailContent(subject="s", body="<p>Hello <b>you</b></p>"), is_html=True
        )

        assert html_body == "<p>Hello <b>you</b></p>"
        assert "<" not in text_body and "Hello" in text_body


@pytest.mark.unit
class TestTheEffectGate:
    def test_a_routine_ledgers_it_where_a_draft_would_be_refused(self) -> None:
        scheduled = EffectScope(run_id="r", idempotency_key="k", source="scheduled")

        assert (
            decide_effect(send_email_to_me_catalogue_manifest.mutation_policy, scheduled).action
            is GateAction.LEDGER
        )
        assert decide_effect("draft", scheduled).action is GateAction.REFUSE

    def test_the_recipient_is_not_a_parameter(self) -> None:
        names = {p.name for p in send_email_to_me_catalogue_manifest.parameters}

        assert names == {"subject", "body", "content_instruction", "is_html"}
