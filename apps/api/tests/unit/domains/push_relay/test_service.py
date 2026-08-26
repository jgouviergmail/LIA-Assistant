"""
The relay service — what it tells a calling server, and what it refuses to say.

Two contracts meet here. The first is honesty about delivery: Apple accepting a
notification is the only thing the relay may report as success, and every other
answer must be distinguishable so a calling server knows whether to drop its
stored handle, retry later, or do nothing. Collapsing "this device is gone" into
"try again later" is how a dead token gets pushed to forever.

The second is the privacy contract the relay exists to keep: the notification it
sends is a fixed sentence, and no caller can influence it. That is asserted
here on the payload actually handed to Apple, because it is the only place the
promise is either kept or broken.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from cryptography.fernet import Fernet

from src.domains.push_relay.seal import seal_device
from src.domains.push_relay.service import PushRelayService, WakeOutcome
from src.infrastructure.external.apns_client import ApnsDeliveryStatus, ApnsResult

pytestmark = pytest.mark.unit

SEAL_KEY = Fernet.generate_key().decode()


def _apns(status: ApnsDeliveryStatus = ApnsDeliveryStatus.ACCEPTED) -> Mock:
    client = Mock()
    client.send = AsyncMock(return_value=ApnsResult(status=status))
    return client


def _service(
    apns: Mock | None = None,
    *,
    allowed: bool = True,
    limiter: Mock | None = None,
) -> PushRelayService:
    if limiter is None:
        limiter = Mock()
        limiter.acquire = AsyncMock(return_value=allowed)
    return PushRelayService(
        seal_key=SEAL_KEY,
        apns_client=apns or _apns(),
        handle_max_age_days=180,
        limiter_factory=AsyncMock(return_value=limiter),
    )


def _handle(*, sandbox: bool = False, language: str = "fr") -> str:
    return seal_device("device-token-1", sandbox=sandbox, key=SEAL_KEY, language=language)


class TestRegistration:
    async def test_a_device_gets_a_handle_that_names_it_to_nobody(self) -> None:
        service = _service()

        handle = await service.register("device-token-1", sandbox=False, language="fr")

        assert "device-token-1" not in handle

    async def test_the_handle_it_returns_is_one_it_can_read_back(self) -> None:
        service = _service()

        handle = await service.register("device-token-1", sandbox=True, language="de")
        outcome = await service.wake(handle)

        assert outcome is WakeOutcome.SENT


class TestWaking:
    async def test_apple_accepting_is_the_only_success(self) -> None:
        apns = _apns(ApnsDeliveryStatus.ACCEPTED)
        service = _service(apns)

        assert await service.wake(_handle()) is WakeOutcome.SENT

    async def test_a_handle_we_cannot_read_is_not_an_error_to_retry(self) -> None:
        service = _service()

        outcome = await service.wake("forged-handle")

        # The caller must delete it: retrying a forged or expired handle can
        # never start working.
        assert outcome is WakeOutcome.UNKNOWN_HANDLE

    async def test_a_gone_device_is_reported_as_gone(self) -> None:
        service = _service(_apns(ApnsDeliveryStatus.DEVICE_GONE))

        outcome = await service.wake(_handle())

        # This is the signal that lets a self-hosted server stop pushing to a
        # phone that uninstalled the app.
        assert outcome is WakeOutcome.DEVICE_GONE

    async def test_apple_being_unavailable_is_worth_retrying(self) -> None:
        service = _service(_apns(ApnsDeliveryStatus.UNAVAILABLE))

        assert await service.wake(_handle()) is WakeOutcome.UNAVAILABLE

    async def test_our_own_misconfiguration_never_blames_the_device(self) -> None:
        service = _service(_apns(ApnsDeliveryStatus.REJECTED))

        outcome = await service.wake(_handle())

        # Reporting DEVICE_GONE here would make every self-hosted server delete
        # every handle it holds, over one wrong environment variable of ours.
        assert outcome is WakeOutcome.MISCONFIGURED

    async def test_the_sealed_gateway_decides_where_the_push_goes(self) -> None:
        apns = _apns()
        service = _service(apns)

        await service.wake(_handle(sandbox=True))

        assert apns.send.await_args.kwargs["sandbox"] is True


class TestThrottling:
    async def test_a_handle_past_its_budget_is_refused(self) -> None:
        apns = _apns()
        service = _service(apns, allowed=False)

        outcome = await service.wake(_handle())

        assert outcome is WakeOutcome.THROTTLED
        apns.send.assert_not_awaited()

    async def test_the_budget_follows_the_handle_not_the_caller(self) -> None:
        limiter = Mock()
        limiter.acquire = AsyncMock(return_value=True)
        service = _service(limiter=limiter)

        await service.wake(_handle())

        key = limiter.acquire.await_args.kwargs["key"]
        # One self-hosted server legitimately wakes many devices from one
        # address, so an IP budget would punish the wrong thing.
        assert key.startswith("push_relay:wake:")
        # And the capability itself must not become a Redis key or a log line.
        assert _handle() not in key


class TestTheOnlyThingItMaySay:
    async def test_the_payload_is_the_fixed_sentence_in_the_sealed_language(self) -> None:
        apns = _apns()
        service = _service(apns)

        await service.wake(_handle(language="de"))

        payload = apns.send.await_args.args[1]
        assert payload["aps"]["alert"]["body"] == "Es gibt Neues für Sie. Zum Ansehen öffnen."

    async def test_nothing_in_the_payload_comes_from_the_caller(self) -> None:
        apns = _apns()
        service = _service(apns)

        await service.wake(_handle(language="en"))

        payload = apns.send.await_args.args[1]
        # The relay's whole justification is that it carries no content. If a
        # field ever appears here that a caller can influence, that is over.
        assert set(payload) == {"aps"}
        assert set(payload["aps"]["alert"]) == {"title", "body"}

    async def test_a_burst_folds_into_one_notification(self) -> None:
        apns = _apns()
        service = _service(apns)

        await service.wake(_handle())

        assert apns.send.await_args.kwargs["collapse_id"] == "lia-wake"


class TestObservability:
    async def test_no_handle_and_no_device_token_ever_reaches_a_log(self) -> None:
        apns = _apns()
        service = _service(apns)
        handle = _handle()

        with patch("src.domains.push_relay.service.logger") as log:
            await service.wake(handle)

        emitted = repr(log.mock_calls)
        assert handle not in emitted
        assert "device-token-1" not in emitted


class TestCompleteness:
    """The verdict map is a registry keyed by an enum (ADR-085 doctrine)."""

    def test_every_apns_verdict_has_a_decision(self) -> None:
        from src.domains.push_relay.service import assert_wake_outcome_completeness

        # Not a KeyError on the hot path: an APNs status added without a
        # decision would raise mid-wake, on a device whose owner is waiting.
        assert_wake_outcome_completeness()

    def test_the_assertion_names_what_is_missing(self) -> None:
        import src.domains.push_relay.service as module

        original = module._OUTCOME_BY_STATUS
        module._OUTCOME_BY_STATUS = {
            k: v for k, v in original.items() if k is not ApnsDeliveryStatus.UNAVAILABLE
        }
        try:
            with pytest.raises(AssertionError, match="unavailable"):
                module.assert_wake_outcome_completeness()
        finally:
            module._OUTCOME_BY_STATUS = original
