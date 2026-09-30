"""A skill's command on the network (ADR-327 lot 3, through ADR-298's proxy).

The container is a recorded ``run_command`` and the proxy a recorded
publisher; everything the command's network path DECIDES is real: which hosts
are permitted and by whom, that a skill written elsewhere never reaches the
person's connectors nor carries a token, that an unknown host is asked where
the loop can settle it and refused elsewhere with where the person allows it,
that « without the turn's data » keeps the attached files out, that the act is
claimed under its own name, and that a proxy that is down runs nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from src.core.context import (
    SkillTurnFile,
    bind_skill_context,
    record_skill_turn_files,
    reset_skill_context,
)
from src.domains.agents.python_sandbox.egress.proxy_client import EgressProxyUnavailable
from src.domains.agents.python_sandbox.egress.tool_path import (
    approved_for_call,
    settling_questions,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials
from src.domains.skills.cache import SkillsCache
from src.domains.skills.command_bundle import CommandOutput
from src.domains.skills.command_outputs import Delivery
from src.domains.skills.command_tool import run_skill_command
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

_ME = "11111111-1111-4111-8111-111111111111"
_CONVERSATION = "22222222-2222-4222-8222-222222222222"
PUBLISHER = "src.domains.agents.python_sandbox.egress.run.deployment_publisher"
EFFECT = "src.domains.agents.python_sandbox.egress.run.in_turn_effect"
GRANTS = "src.domains.agents.python_sandbox.egress.tool_path.load_grants"


class FakeGate:
    """The person's connectors: Brave is active, with its key."""

    async def is_connector_active(self, user_id: Any, connector_type: ConnectorType) -> bool:
        return connector_type == ConnectorType.BRAVE_SEARCH

    async def get_api_key_credentials(
        self, user_id: Any, connector_type: ConnectorType
    ) -> APIKeyCredentials | None:
        if connector_type == ConnectorType.BRAVE_SEARCH:
            return APIKeyCredentials(api_key="brave-real-key")
        return None


class FakePublisher:
    def __init__(self, *, fail: bool = False) -> None:
        self.served: list[tuple[Any, dict[str, str]]] = []
        self.fail = fail

    @asynccontextmanager
    async def serve(self, run: Any, secrets: dict[str, str]) -> AsyncIterator[None]:
        if self.fail:
            raise EgressProxyUnavailable("reload refused: HTTP 503")
        self.served.append((run, dict(secrets)))
        yield


EFFECTS: list[SimpleNamespace] = []


@asynccontextmanager
async def _recorded_effect(**kwargs: Any) -> AsyncIterator[SimpleNamespace]:
    holder = SimpleNamespace(succeeded=False, kwargs=kwargs)
    EFFECTS.append(holder)
    yield holder


def _write(base: Path, name: str) -> None:
    folder = base / name
    (folder / "scripts").mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill {name}.\n---\n\nRun things.\n",
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def network(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.core.config import settings

    EFFECTS.clear()
    monkeypatch.setattr(settings, "python_sandbox_egress_enabled", True)
    monkeypatch.setattr(settings, "python_sandbox_egress_ask_enabled", True)
    monkeypatch.setattr(settings, "python_sandbox_egress_hosts", ["registry.npmjs.org"])
    monkeypatch.setattr(settings, "python_sandbox_max_hosts_per_run", 4)
    monkeypatch.setattr(settings, "skill_command_network_enabled", True)
    monkeypatch.setattr(GRANTS, AsyncMock(return_value={}))
    # The capability's own reader is tested apart; here the switch is on.
    monkeypatch.setattr(
        "src.domains.feature_switches.registry.is_capability_enabled",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        "src.domains.skills.command_tool.mark_relied_grants", AsyncMock(return_value=None)
    )


@pytest.fixture()
def skills(tmp_path: Path) -> Iterator[Path]:
    """My own ``notes`` (authored) and ``pdf`` (third-party), one attached file, all bound."""
    from src.core.config import settings

    _write(tmp_path / "users" / _ME, "notes")
    _write(tmp_path / "users" / _ME, "pdf")
    (tmp_path / "system").mkdir()
    storage = tmp_path / "attachments"
    (storage / _ME).mkdir(parents=True)
    (storage / _ME / "stored.pdf").write_bytes(b"%PDF-1.7")
    saved = SkillsCache._skills, SkillsCache._loaded
    tokens = bind_skill_context({"notes", "pdf"}, frozenset({"pdf"}))
    record_skill_turn_files(
        [
            SkillTurnFile(
                attachment_id="a1", filename="form.pdf", file_path=f"{_ME}/stored.pdf", size=8
            )
        ]
    )
    try:
        with (
            patch.object(settings, "skills_scripts_enabled", True),
            patch.object(settings, "skills_script_sandbox", "container"),
            patch.object(settings, "attachments_storage_path", str(storage)),
        ):
            SkillsCache.load_from_disk(str(tmp_path / "system"), str(tmp_path / "users"))
            yield tmp_path
    finally:
        reset_skill_context(tokens)
        SkillsCache._skills, SkillsCache._loaded = saved


def _runtime() -> Any:
    deps = SimpleNamespace(get_connector_service=AsyncMock(return_value=FakeGate()))
    return make_tool_runtime(
        user_id=UUID(_ME),
        thread_id=_CONVERSATION,
        conversation_id=_CONVERSATION,
        store=MagicMock(),
        deps=deps,
        language="fr",
    )


def _output(exit_code: int = 0) -> CommandOutput:
    return CommandOutput(
        exit_code=exit_code,
        stdout="1.3.0\n",
        stderr="",
        stdout_truncated=False,
        stderr_truncated=False,
        files=(),
        skipped=(),
    )


async def _call(
    hosts: list[str],
    name: str = "notes",
    *,
    publisher: FakePublisher | None = None,
    exit_code: int = 0,
) -> tuple[Any, AsyncMock, AsyncMock, FakePublisher]:
    run = AsyncMock(return_value=_output(exit_code))
    prepare = MagicMock(return_value=(b"bundle", [], []))
    publisher = publisher or FakePublisher()
    with (
        patch("src.domains.skills.command_tool.run_command", run),
        patch("src.domains.skills.command_tool._prepare", prepare),
        patch(
            "src.domains.skills.command_tool.deliver_outputs",
            AsyncMock(return_value=Delivery(delivered=(), skipped=())),
        ),
        patch(PUBLISHER, new=AsyncMock(return_value=publisher)),
        patch(EFFECT, new=_recorded_effect),
    ):
        result = await run_skill_command.coroutine(
            skill_name=name,
            command="npm view left-pad version",
            hosts=hosts,
            runtime=_runtime(),
        )
    return result, run, prepare, publisher


class TestAPermittedHost:
    async def test_runs_on_the_proxy_network_claimed_under_its_own_name(self, skills: Path) -> None:
        result, run, _, publisher = await _call(["registry.npmjs.org"])

        assert result.success is True
        egress = run.await_args.kwargs["egress"]
        assert egress is not None and egress.network == "lia-sandbox"
        assert [r.hosts for r, _ in publisher.served] == [("registry.npmjs.org",)]
        (effect,) = EFFECTS
        assert effect.kwargs["tool_name"] == "skill_command_network"
        assert effect.succeeded is True
        assert "registry.npmjs.org" in result.message

    async def test_a_failing_command_closes_the_act_as_a_failure(self, skills: Path) -> None:
        result, _, _, _ = await _call(["registry.npmjs.org"], exit_code=1)

        assert result.success is False
        assert EFFECTS[0].succeeded is False

    async def test_the_person_s_own_skill_carries_its_connector_token(self, skills: Path) -> None:
        result, run, _, publisher = await _call(["api.search.brave.com"])

        assert result.success is True
        tokens = run.await_args.kwargs["egress"].tokens
        assert set(tokens) == {"LIA_KEY_BRAVE_SEARCH"}
        ((_, secrets),) = publisher.served
        assert secrets == {"brave_search": "brave-real-key"}


class TestASkillWrittenElsewhere:
    async def test_never_reaches_the_person_s_connectors(self, skills: Path) -> None:
        """A connector host is not permitted for it, and nobody can ask from here."""
        result, run, _, publisher = await _call(["api.search.brave.com"], name="pdf")

        assert result.success is False
        assert "api.search.brave.com" in result.message and "Settings" in result.message
        run.assert_not_awaited()
        assert publisher.served == []

    async def test_reaches_the_operator_s_hosts_without_any_token(self, skills: Path) -> None:
        result, run, _, publisher = await _call(["registry.npmjs.org"], name="pdf")

        assert result.success is True
        assert run.await_args.kwargs["egress"].tokens == {}
        assert publisher.served[0][1] == {}


class TestAnUnknownHost:
    async def test_is_asked_where_the_loop_settles_the_question(self, skills: Path) -> None:
        with settling_questions():
            result, run, _, _ = await _call(["example.com"])

        run.assert_not_awaited()
        assert result.tool_metadata["requires_confirmation"] is True
        assert result.tool_metadata["draft_type"] == "sandbox_egress"
        content = result.registry_updates[result.tool_metadata["draft_id"]].payload["content"]
        assert content["hosts_unknown"] == ["example.com"]
        assert content["purpose"] == "notes: npm view left-pad version"
        # The attached file is counted, never carried.
        assert content["data_summary"]["counts"] == {"file": 1}
        # The person's own skill: the card carries no warning.
        assert "third_party_skill" not in content

    async def test_the_card_says_when_a_skill_written_elsewhere_asks(self, skills: Path) -> None:
        with settling_questions():
            result, run, _, _ = await _call(["example.com"], name="pdf")

        run.assert_not_awaited()
        content = result.registry_updates[result.tool_metadata["draft_id"]].payload["content"]
        assert content["third_party_skill"] is True

    async def test_is_refused_with_where_to_allow_it_anywhere_else(self, skills: Path) -> None:
        result, run, _, _ = await _call(["example.com"])

        run.assert_not_awaited()
        assert result.success is False
        assert "example.com" in result.message and "Settings" in result.message

    async def test_allowed_without_the_turn_s_data_the_files_stay_out(self, skills: Path) -> None:
        with approved_for_call({"example.com": False}):
            result, run, prepare, _ = await _call(["example.com"])

        assert result.success is True
        assert prepare.call_args.args[1] == (), "an attached file entered the container"
        assert "WITHOUT the turn's data" in result.message


class TestWhatIsRefused:
    async def test_the_instance_may_keep_commands_offline(
        self, skills: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "skill_command_network_enabled", False)
        result, run, _, _ = await _call(["registry.npmjs.org"])

        assert result.success is False and "offline" in result.message
        run.assert_not_awaited()

    async def test_an_invalid_host_runs_nothing(self, skills: Path) -> None:
        result, run, _, _ = await _call(["https://example.com/x"])

        assert result.success is False
        run.assert_not_awaited()

    async def test_a_proxy_that_is_down_runs_nothing_and_says_so(self, skills: Path) -> None:
        result, run, _, _ = await _call(["registry.npmjs.org"], publisher=FakePublisher(fail=True))

        assert result.success is False and "proxy" in result.message
        run.assert_not_awaited()
        assert EFFECTS[0].succeeded is False

    async def test_no_hosts_is_offline_and_publishes_nothing(self, skills: Path) -> None:
        result, run, _, publisher = await _call([])

        assert result.success is True
        assert run.await_args.kwargs["egress"] is None
        assert publisher.served == [] and EFFECTS == []


class TestWhatTheRunnerIsTold:
    """The runner's network line states exactly what the run enforces."""

    @staticmethod
    def _context() -> Any:
        deps = SimpleNamespace(get_connector_service=AsyncMock(return_value=FakeGate()))
        return SimpleNamespace(user_id=UUID(_ME), deps=deps)

    async def test_offline_when_the_skills_switch_is_off(
        self, skills: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings
        from src.domains.skills.command_network import runner_network_line

        monkeypatch.setattr(settings, "skill_command_network_enabled", False)
        line = await runner_network_line(third_party=False, context=self._context())

        assert line.startswith("There is no network")

    async def test_offline_without_a_context(self, skills: Path) -> None:
        from src.domains.skills.command_network import runner_network_line

        assert (await runner_network_line(third_party=False, context=None)).startswith(
            "There is no network"
        )

    async def test_the_person_s_own_skill_is_told_its_hosts_and_how_to_read_a_token(
        self, skills: Path
    ) -> None:
        from src.domains.skills.command_network import runner_network_line

        line = await runner_network_line(third_party=False, context=self._context())

        assert "`registry.npmjs.org`" in line
        assert '"$LIA_KEY_BRAVE_SEARCH"' in line
        assert "at most 4" in line

    async def test_where_the_instance_never_asks_the_line_names_no_settings(
        self, skills: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Told « the user can allow it in Settings » on an instance whose settings
        refuse it, the model would send the person to a door that is shut."""
        from src.core.config import settings
        from src.domains.skills.command_network import runner_network_line

        monkeypatch.setattr(settings, "python_sandbox_egress_ask_enabled", False)
        line = await runner_network_line(third_party=False, context=self._context())

        assert "`registry.npmjs.org`" in line
        assert "Settings" not in line
        assert "refused on this instance" in line

    async def test_a_skill_written_elsewhere_is_offered_no_connector(self, skills: Path) -> None:
        from src.domains.skills.command_network import runner_network_line

        line = await runner_network_line(third_party=True, context=self._context())

        assert "`registry.npmjs.org`" in line
        assert "LIA_KEY" not in line and "brave" not in line
