"""The sandbox tool's NETWORK path (ADR-298): a declared host is validated and
classified before any container starts; a permitted run is published to the
proxy, effected in the register, and handed its tokens; the proxy down means
the run is refused, named, and counted."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.core.constants import EXECUTION_MODE_REACT
from src.domains.agents.python_sandbox.egress.hosts import HostStatus
from src.domains.agents.python_sandbox.egress.proxy_client import EgressProxyUnavailable
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials

pytestmark = [pytest.mark.unit]

EXECUTE = "src.domains.skills.executor.SkillScriptExecutor.execute_source"
PUBLISHER = "src.domains.agents.python_sandbox.egress.run.deployment_publisher"
EFFECT = "src.domains.agents.python_sandbox.egress.run.in_turn_effect"


class FakeGate:
    def __init__(self, active: set[ConnectorType], keys: dict[ConnectorType, str]) -> None:
        self.active, self.keys = active, keys

    async def is_connector_active(self, user_id: Any, connector_type: ConnectorType) -> bool:
        return connector_type in self.active

    async def get_api_key_credentials(
        self, user_id: Any, connector_type: ConnectorType
    ) -> APIKeyCredentials | None:
        key = self.keys.get(connector_type)
        return APIKeyCredentials(api_key=key) if key else None


class FakePublisher:
    """Records what was served; `fail` refuses like a proxy that is down."""

    def __init__(self, *, fail: bool = False) -> None:
        self.served: list[tuple[Any, dict[str, str]]] = []
        self.fail = fail

    @asynccontextmanager
    async def serve(self, run: Any, secrets: dict[str, str]) -> AsyncIterator[None]:
        if self.fail:
            raise EgressProxyUnavailable("reload refused: HTTP 503")
        self.served.append((run, dict(secrets)))
        yield


def _runtime(gate: FakeGate) -> SimpleNamespace:
    deps = SimpleNamespace(get_connector_service=AsyncMock(return_value=gate))
    context = SimpleNamespace(
        user_id=uuid4(),
        thread_id="t1",
        conversation_id="c1",
        execution_mode=EXECUTION_MODE_REACT,
        deps=deps,
    )
    return SimpleNamespace(context=context)


def _ok(stdout: str = "200\n") -> SimpleNamespace:
    return SimpleNamespace(success=True, output=stdout, error=None)


@asynccontextmanager
async def _recorded_effect(**kwargs: Any) -> AsyncIterator[SimpleNamespace]:
    holder = SimpleNamespace(succeeded=False, kwargs=kwargs)
    RECORDED.append(holder)
    yield holder


RECORDED: list[Any] = []


@pytest.fixture(autouse=True)
def _fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import settings
    from src.domains.agents.tools import python_sandbox_tools

    RECORDED.clear()
    python_sandbox_tools.reset_turn_budget()
    monkeypatch.setattr(settings, "python_sandbox_tool_enabled", True, raising=False)
    monkeypatch.setattr(settings, "python_sandbox_egress_enabled", True, raising=False)
    monkeypatch.setattr(settings, "python_sandbox_egress_ask_enabled", False, raising=False)
    monkeypatch.setattr(settings, "python_sandbox_egress_hosts", ["api.example.org"], raising=False)
    monkeypatch.setattr(settings, "python_sandbox_max_hosts_per_run", 3, raising=False)
    monkeypatch.setattr(settings, "python_sandbox_network_timeout_seconds", 60, raising=False)
    # The grants store is a table on a session of its own; a unit test never
    # opens one (the repository has its PostgreSQL integration test).
    monkeypatch.setattr(
        "src.domains.agents.python_sandbox.egress.tool_path.load_grants",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "src.domains.agents.python_sandbox.egress.tool_path.mark_relied_grants", AsyncMock()
    )


async def _call(hosts: list[str], gate: FakeGate | None = None, **kwargs: Any) -> Any:
    from src.domains.agents.tools.python_sandbox_tools import run_python_tool

    gate = gate or FakeGate(active=set(), keys={})
    return await run_python_tool.coroutine(
        code=kwargs.pop(
            "code", "import requests; print(requests.get('https://api.example.org').status_code)"
        ),
        purpose=kwargs.pop("purpose", "probe the service"),
        hosts=hosts,
        runtime=kwargs.pop("runtime", _runtime(gate)),
        **kwargs,
    )


class TestValidation:
    async def test_an_invalid_host_is_refused_before_anything_runs(self) -> None:
        with patch(EXECUTE, new_callable=AsyncMock) as executor:
            result = await _call(["https://api.example.org/path"])
        assert result.success is False
        assert "hostname" in result.message.lower()
        executor.assert_not_awaited()

    async def test_too_many_hosts_are_refused_with_the_published_cap(self) -> None:
        with patch(EXECUTE, new_callable=AsyncMock) as executor:
            result = await _call(["a.org", "b.org", "c.org", "d.org"])
        assert result.success is False and "at most 3" in result.message
        executor.assert_not_awaited()

    async def test_egress_switched_off_refuses_a_network_run(self) -> None:
        """The operator's switch, read at the act — not the .env ceiling alone."""
        with (
            patch(
                "src.domains.feature_switches.registry.is_capability_enabled",
                new=AsyncMock(side_effect=lambda cap: cap.value != "python_sandbox_egress"),
            ),
            patch(EXECUTE, new_callable=AsyncMock) as executor,
        ):
            result = await _call(["api.example.org"])
        assert result.success is False and "network" in result.message.lower()
        executor.assert_not_awaited()

    async def test_an_unknown_host_is_refused_when_asking_is_off(self) -> None:
        with patch(EXECUTE, new_callable=AsyncMock) as executor:
            result = await _call(["mystery.example"])
        assert result.success is False
        assert "mystery.example" in result.message
        executor.assert_not_awaited()

    async def test_an_unknown_host_is_asked_of_the_person_when_asking_is_on(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The tool hands the call back as a draft; nothing runs before the answer."""
        from src.core.config import settings
        from src.domains.agents.tools import python_sandbox_tools

        monkeypatch.setattr(settings, "python_sandbox_egress_ask_enabled", True, raising=False)
        python_sandbox_tools.set_turn_data({"e1": {"type": "EMAIL"}})
        with patch(EXECUTE, new_callable=AsyncMock) as executor:
            result = await _call(["mystery.example", "api.example.org"], purpose="probe it")
        executor.assert_not_awaited()
        assert result.tool_metadata["requires_confirmation"] is True
        assert result.tool_metadata["draft_type"] == "sandbox_egress"
        content = result.registry_updates[result.tool_metadata["draft_id"]].payload["content"]
        assert content["hosts_unknown"] == ["mystery.example"]
        assert content["hosts"] == ["mystery.example", "api.example.org"]
        assert content["purpose"] == "probe it"
        assert content["data_summary"]["counts"] == {"email": 1}
        # The loop re-invokes the very call after the answer (react_egress_question):
        # the script never travels in the draft, nor anywhere near the wire.
        assert "replay" not in content and "code" not in json.dumps(content)
        # A question started no container: it costs none of the turn's runs.
        assert python_sandbox_tools.runs_spent() == 0

    async def test_a_refusal_before_the_container_costs_no_run(self) -> None:
        from src.domains.agents.tools import python_sandbox_tools

        result = await _call(["not a host"])
        assert result.success is False
        assert python_sandbox_tools.runs_spent() == 0


class TestAnApprovalForThisCall:
    """The answer to the question is handed to the SAME call, re-invoked in
    the loop: the approved hosts join the grants for that invocation alone,
    with the scope the person chose."""

    async def test_an_approved_host_runs_under_the_answers_scope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings
        from src.domains.agents.python_sandbox.egress.tool_path import approved_for_call
        from src.domains.agents.tools import python_sandbox_tools

        monkeypatch.setattr(settings, "python_sandbox_egress_ask_enabled", True, raising=False)
        python_sandbox_tools.set_turn_data({"e1": {"type": "EMAIL"}})
        with (
            patch(PUBLISHER, new=AsyncMock(return_value=FakePublisher())),
            patch(EFFECT, new=_recorded_effect),
            patch(EXECUTE, new_callable=AsyncMock, return_value=_ok()) as executor,
            approved_for_call({"mystery.example": False}),
        ):
            result = await _call(["mystery.example", "api.example.org"])
        assert result.success is True
        assert result.structured_data["authorizations"] == {
            "mystery.example": "grant",
            "api.example.org": "operator",
        }
        assert result.structured_data["turn_data_shared"] is False
        assert executor.await_args.kwargs["payload"] == {"items": {}}
        assert python_sandbox_tools.runs_spent() == 1

    async def test_the_approval_does_not_outlive_its_call(self) -> None:
        from src.domains.agents.python_sandbox.egress.tool_path import (
            approved_for_call,
            approved_hosts,
        )

        with approved_for_call({"mystery.example": True}):
            assert approved_hosts() == {"mystery.example": True}
        assert approved_hosts() == {}


class TestAPermittedRun:
    async def test_is_published_effected_and_handed_its_tokens(self) -> None:
        publisher = FakePublisher()
        gate = FakeGate(
            active={ConnectorType.BRAVE_SEARCH}, keys={ConnectorType.BRAVE_SEARCH: "BSA-real"}
        )
        with (
            patch(PUBLISHER, new=AsyncMock(return_value=publisher)),
            patch(EFFECT, new=_recorded_effect),
            patch(EXECUTE, new_callable=AsyncMock, return_value=_ok()) as executor,
        ):
            result = await _call(["api.search.brave.com", "api.example.org"], gate=gate)

        assert result.success is True
        # Published to the proxy: the run's hosts, one credential, the REAL key
        # in the secrets and only the TOKEN in the run.
        ((run, secrets),) = publisher.served
        assert set(run.hosts) == {"api.search.brave.com", "api.example.org"}
        assert secrets == {"brave_search": "BSA-real"}
        (credential,) = run.credentials
        assert credential.token.startswith("sbx_") and "BSA-real" not in credential.token
        assert credential.auth_name == "X-Subscription-Token"
        # The container got the network spec and the token under LIA_KEY_*.
        spec = executor.await_args.kwargs["egress"]
        assert spec.network == "lia-sandbox"
        assert spec.tokens == {"LIA_KEY_BRAVE_SEARCH": credential.token}
        assert executor.await_args.kwargs["timeout_seconds"] == 60
        # Effected in the register, closed as a success, naming the hosts.
        (effect,) = RECORDED
        assert effect.succeeded is True
        assert set(effect.kwargs["arguments"]["hosts"]) == set(run.hosts)
        assert effect.kwargs["arguments"]["turn_data_shared"] is True
        # And the answer says the data travelled.
        assert result.structured_data["turn_data_shared"] is True
        assert result.structured_data["hosts"] == list(run.hosts)

    async def test_the_turn_data_reaches_the_script_when_shared(self) -> None:
        from src.domains.agents.tools import python_sandbox_tools

        python_sandbox_tools.set_turn_data({"e1": {"type": "EMAIL"}})
        with (
            patch(PUBLISHER, new=AsyncMock(return_value=FakePublisher())),
            patch(EFFECT, new=_recorded_effect),
            patch(EXECUTE, new_callable=AsyncMock, return_value=_ok()) as executor,
        ):
            await _call(["api.example.org"])
        assert executor.await_args.kwargs["payload"]["items"] == {"e1": {"type": "EMAIL"}}

    async def test_a_failing_script_closes_the_effect_as_a_failure(self) -> None:
        with (
            patch(PUBLISHER, new=AsyncMock(return_value=FakePublisher())),
            patch(EFFECT, new=_recorded_effect),
            patch(
                EXECUTE,
                new_callable=AsyncMock,
                return_value=SimpleNamespace(success=False, output="", error="Traceback…"),
            ),
        ):
            result = await _call(["api.example.org"])
        assert result.success is False
        (effect,) = RECORDED
        assert effect.succeeded is False


class TestGrants:
    async def test_a_granted_host_runs_with_its_scope_and_is_stamped(self) -> None:
        """A host the person allowed WITHOUT the data narrows the run and, once
        run, is stamped as used."""
        with (
            patch(
                "src.domains.agents.python_sandbox.egress.tool_path.load_grants",
                new=AsyncMock(return_value={"granted.example": False}),
            ),
            patch(
                "src.domains.agents.python_sandbox.egress.tool_path.mark_relied_grants",
                new=AsyncMock(),
            ) as stamp,
            patch(PUBLISHER, new=AsyncMock(return_value=FakePublisher())),
            patch(EFFECT, new=_recorded_effect),
            patch(EXECUTE, new_callable=AsyncMock, return_value=_ok()) as executor,
        ):
            from src.domains.agents.tools import python_sandbox_tools

            python_sandbox_tools.set_turn_data({"e1": {"type": "EMAIL"}})
            result = await _call(["granted.example", "api.example.org"])
        assert result.success is True
        assert result.structured_data["turn_data_shared"] is False
        assert executor.await_args.kwargs["payload"] == {"items": {}}
        assert result.structured_data["authorizations"] == {
            "granted.example": "grant",
            "api.example.org": "operator",
        }
        stamp.assert_awaited_once()
        assert stamp.await_args.args[1]["granted.example"] is HostStatus.GRANT


class TestTheProxyDown:
    async def test_is_a_named_refusal_and_never_a_container(self) -> None:
        with (
            patch(PUBLISHER, new=AsyncMock(return_value=FakePublisher(fail=True))),
            patch(EFFECT, new=_recorded_effect),
            patch(EXECUTE, new_callable=AsyncMock) as executor,
        ):
            result = await _call(["api.example.org"])
        assert result.success is False
        assert "503" in result.message
        executor.assert_not_awaited()
        (effect,) = RECORDED
        assert effect.succeeded is False

    async def test_no_management_token_is_the_same_refusal(self) -> None:
        with (
            patch(
                PUBLISHER, new=AsyncMock(side_effect=EgressProxyUnavailable("no management.token"))
            ),
            patch(EXECUTE, new_callable=AsyncMock) as executor,
        ):
            result = await _call(["api.example.org"])
        assert result.success is False and "management.token" in result.message
        executor.assert_not_awaited()


class TestNoHostMeansTheOldRun:
    async def test_an_empty_list_is_air_gapped_and_unpublished(self) -> None:
        with (
            patch(PUBLISHER, new=AsyncMock()) as build,
            patch(EXECUTE, new_callable=AsyncMock, return_value=_ok("3\n")) as executor,
        ):
            result = await _call([])
        assert result.success is True
        assert executor.await_args.kwargs.get("egress") is None
        build.assert_not_awaited()
        assert "turn_data_shared" not in json.dumps(result.model_dump(), default=str)
