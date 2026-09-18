"""The ReAct prompt promises only what the turn's tools can do (prompt audit 2026-09-12, A.5).

Measured: ``<Computation>`` promised ``run_python_tool`` unconditionally — on the
public demonstrator the sandbox is off and the tool is not even registered — and
told the model it had « a small number of runs » where the enforced budget is a
setting; and « Mutation tools require user approval automatically » was false for
the 22 tools whose policy is ``reversible``, ``artefact`` or ``sandboxed`` (they
run and are recorded, ADR-263).
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import settings
from src.domains.agents.nodes.react_prompt import build_system_prompt as _build_system_prompt
from src.domains.agents.nodes.react_prompt import sandbox_available as _sandbox_available

_STATE = {
    "personality_instruction": "friendly",
    "user_timezone": "Europe/Paris",
    "user_language": "fr",
}
_PLACEHOLDER_RE = re.compile(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})")


class TestComputationBlockFollowsTheTools:
    def test_absent_when_the_turn_cannot_compute(self) -> None:
        prompt = _build_system_prompt(_STATE, computation=False)
        assert "<Computation>" not in prompt
        assert "run_python_tool" not in prompt

    def test_present_with_the_enforced_budget_when_it_can(self) -> None:
        prompt = _build_system_prompt(_STATE, computation=True)
        assert "<Computation>" in prompt and "run_python_tool" in prompt
        assert f"{settings.python_sandbox_max_runs_per_turn} run" in prompt
        assert "a small number of runs" not in prompt

    def test_default_promises_nothing(self) -> None:
        """A caller that says nothing gets the conservative prompt."""
        assert "<Computation>" not in _build_system_prompt(_STATE)

    def test_no_placeholder_survives_either_way(self) -> None:
        for computation in (False, True):
            assert not _PLACEHOLDER_RE.findall(
                _build_system_prompt(_STATE, computation=computation)
            )

    async def test_availability_needs_the_tool_bound_and_the_switch_on(self) -> None:
        with patch(
            "src.domains.agents.nodes.react_prompt.is_capability_enabled",
            AsyncMock(return_value=True),
        ) as switch:
            assert await _sandbox_available(["get_emails_tool"]) is False
            switch.assert_not_awaited()  # not bound: the switch is not even read
            assert await _sandbox_available(["get_emails_tool", "run_python_tool"]) is True
        with patch(
            "src.domains.agents.nodes.react_prompt.is_capability_enabled",
            AsyncMock(return_value=False),
        ):
            assert await _sandbox_available(["run_python_tool"]) is False

    def test_no_run_of_blank_lines_when_the_block_is_absent(self) -> None:
        prompt = _build_system_prompt(_STATE).replace("\r\n", "\n")
        assert not re.search(r"\n{3,}", prompt)


class TestApprovalIsTheToolsDecision:
    def test_the_prompt_does_not_promise_a_confirmation_step(self) -> None:
        prompt = _build_system_prompt(_STATE)
        assert "require user approval automatically" not in prompt

    def test_the_prompt_says_who_decides(self) -> None:
        prompt = _build_system_prompt(_STATE)
        assert "decided by the tool" in prompt
        assert "run immediately" in prompt


# --- ADR-298: the living contract — four roles, the libraries, the reachable hosts ---


def _host(host: str, connector: str | None = None, **auth: str) -> Any:
    from src.domains.agents.python_sandbox.egress.hosts import ConnectorHost
    from src.domains.agents.python_sandbox.egress.offer import ReachableHost

    if connector is None:
        return ReachableHost(host=host, credential=None)
    return ReachableHost(
        host=host,
        credential=ConnectorHost(
            host=host,
            connector=connector,
            auth_method=auth.get("method", "header"),
            auth_name=auth.get("name", "X-Subscription-Token"),
            auth_prefix=auth.get("prefix", ""),
        ),
    )


def _offer(*hosts: Any, ask_enabled: bool = True) -> Any:
    from src.domains.agents.python_sandbox.egress.offer import NetworkOffer

    return NetworkOffer(hosts=tuple(hosts), ask_enabled=ask_enabled)


class TestTheComputationBlockIsTheLivingContract:
    def test_the_four_roles_the_libraries_and_the_bounds(self) -> None:
        from src.domains.agents.python_sandbox.libraries import PYTHON_SANDBOX_LIBRARIES

        prompt = _build_system_prompt(_STATE, computation=True)
        positions = [prompt.index(role) for role in ("CALCULATE", "DIAGNOSE", "FILL", "TRANSFORM")]
        assert positions == sorted(positions)
        for lib in PYTHON_SANDBOX_LIBRARIES:
            assert lib.import_name in prompt, lib.import_name
        assert f"{settings.skills_script_timeout_seconds} s" in prompt
        assert f"{settings.skills_script_max_memory_mb} MB" in prompt
        assert f"{settings.skills_script_max_output_kb} KB" in prompt
        assert "costs a container" not in prompt
        assert "correct your own code" in prompt

    def test_no_network_section_without_an_offer(self) -> None:
        prompt = _build_system_prompt(_STATE, computation=True)
        assert "Reachable now" not in prompt
        block = prompt.split("<Computation>")[1].split("</Computation>")[0]
        assert "hosts" not in block

    def test_the_offer_lists_hosts_with_their_credential_carrier(self) -> None:
        offer = _offer(_host("api.search.brave.com", "brave_search"), _host("status.example.org"))
        prompt = _build_system_prompt(_STATE, computation=True, network=offer)
        block = prompt.split("Reachable now")[1]
        assert "`api.search.brave.com`" in block and "`status.example.org`" in block
        # Measured 2026-09-18 on dev: told « `LIA_KEY_BRAVE_SEARCH` in the header »,
        # the model sent the variable's NAME as the header value (422 from Brave,
        # twice, no self-correction). The line spells the read out.
        assert 'os.environ["LIA_KEY_BRAVE_SEARCH"]' in block and "X-Subscription-Token" in block
        assert block.index("api.search.brave.com") < block.index("status.example.org")
        assert "asked" in block
        assert f"{settings.python_sandbox_max_hosts_per_run}" in prompt
        assert f"{settings.python_sandbox_network_timeout_seconds} s" in prompt
        assert f"{settings.python_sandbox_egress_max_body_bytes // 1024} KB" in prompt

    def test_a_query_credential_names_the_parameter(self) -> None:
        offer = _offer(
            _host("api.openweathermap.org", "openweathermap", method="query", name="appid")
        )
        prompt = _build_system_prompt(_STATE, computation=True, network=offer)
        assert "`appid=<value>`" in prompt
        assert 'os.environ["LIA_KEY_OPENWEATHERMAP"]' in prompt

    def test_a_bearer_prefix_travels_with_the_header(self) -> None:
        offer = _offer(
            _host("api.perplexity.ai", "perplexity", name="Authorization", prefix="Bearer")
        )
        prompt = _build_system_prompt(_STATE, computation=True, network=offer)
        assert "`Authorization: Bearer <value>`" in prompt

    def test_without_the_ask_the_rule_is_a_refusal(self) -> None:
        offer = _offer(_host("status.example.org"), ask_enabled=False)
        prompt = _build_system_prompt(_STATE, computation=True, network=offer)
        block = prompt.split("Reachable now")[1]
        assert "refused" in block and "asked" not in block

    def test_no_pre_permitted_host_is_said_not_left_blank(self) -> None:
        prompt = _build_system_prompt(_STATE, computation=True, network=_offer())
        assert "none pre-permitted" in prompt.split("Reachable now")[1]

    def test_the_network_is_never_promised_without_the_sandbox(self) -> None:
        prompt = _build_system_prompt(
            _STATE, computation=False, network=_offer(_host("status.example.org"))
        )
        assert "<Computation>" not in prompt and "status.example.org" not in prompt

    @pytest.mark.parametrize(
        "network", [None, _offer(), _offer(_host("a.example", "brave_search"))]
    )
    def test_no_placeholder_and_no_blank_run_either_way(self, network: Any) -> None:
        prompt = _build_system_prompt(_STATE, computation=True, network=network)
        assert not _PLACEHOLDER_RE.findall(prompt)
        assert not re.search(r"\n{3,}", prompt.replace("\r\n", "\n"))


class TestTheOfferFollowsTheTurn:
    """``network_available`` mirrors ``sandbox_available``: bound, switched on,
    and read from what the ACCOUNT holds — never a static list."""

    async def test_needs_the_tool_bound_and_the_egress_switch(self) -> None:
        from src.domains.agents.nodes.react_prompt import network_available

        with patch(
            "src.domains.agents.nodes.react_prompt.is_capability_enabled",
            AsyncMock(return_value=True),
        ) as switch:
            assert await network_available(["get_emails_tool"]) is None
            switch.assert_not_awaited()
        with patch(
            "src.domains.agents.nodes.react_prompt.is_capability_enabled",
            AsyncMock(return_value=False),
        ):
            assert await network_available(["run_python_tool"]) is None

    async def test_reads_the_active_connectors_and_the_operator_hosts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import uuid
        from types import SimpleNamespace

        from src.domains.agents.nodes.react_prompt import network_available

        monkeypatch.setattr(
            settings, "python_sandbox_egress_hosts", ["Status.Example.org", "api.search.brave.com"]
        )
        monkeypatch.setattr(settings, "python_sandbox_egress_ask_enabled", True)

        async def _active(user_id: Any, connector_type: Any) -> bool:
            return connector_type.value == "brave_search"

        gate = SimpleNamespace(is_connector_active=_active)
        context = SimpleNamespace(
            user_id=uuid.uuid4(),
            deps=SimpleNamespace(get_connector_service=AsyncMock(return_value=gate)),
        )
        with (
            patch(
                "src.domains.agents.nodes.react_prompt.is_capability_enabled",
                AsyncMock(return_value=True),
            ),
            patch(
                "src.domains.agents.nodes.react_prompt.runtime_context_if_running",
                return_value=context,
            ),
        ):
            offer = await network_available(["run_python_tool"])
        assert offer is not None and offer.ask_enabled is True
        assert [h.host for h in offer.hosts] == ["api.search.brave.com", "status.example.org"]
        assert offer.hosts[0].credential is not None
        assert offer.hosts[0].credential.connector == "brave_search"
        assert offer.hosts[1].credential is None, "an operator host carries no credential"

    async def test_outside_a_run_nothing_is_promised(self) -> None:
        from src.domains.agents.nodes.react_prompt import network_available

        with (
            patch(
                "src.domains.agents.nodes.react_prompt.is_capability_enabled",
                AsyncMock(return_value=True),
            ),
            patch(
                "src.domains.agents.nodes.react_prompt.runtime_context_if_running",
                return_value=None,
            ),
        ):
            assert await network_available(["run_python_tool"]) is None

    async def test_a_failing_connector_read_keeps_the_operator_hosts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Best-effort like every context block: the prompt is still built."""
        import uuid
        from types import SimpleNamespace

        from src.domains.agents.nodes.react_prompt import network_available

        monkeypatch.setattr(settings, "python_sandbox_egress_hosts", ["status.example.org"])
        context = SimpleNamespace(
            user_id=uuid.uuid4(),
            deps=SimpleNamespace(
                get_connector_service=AsyncMock(side_effect=RuntimeError("db down"))
            ),
        )
        with (
            patch(
                "src.domains.agents.nodes.react_prompt.is_capability_enabled",
                AsyncMock(return_value=True),
            ),
            patch(
                "src.domains.agents.nodes.react_prompt.runtime_context_if_running",
                return_value=context,
            ),
        ):
            offer = await network_available(["run_python_tool"])
        assert offer is not None
        assert [h.host for h in offer.hosts] == ["status.example.org"]
