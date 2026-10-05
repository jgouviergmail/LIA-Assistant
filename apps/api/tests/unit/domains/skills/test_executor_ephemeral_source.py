"""Running source the MODEL wrote, in the sandbox that already exists.

An installed skill is code the user chose. An ephemeral script is code an LLM
produced while reading third-party content — an email can therefore reach the
interpreter. The isolation that answers this is the one SEC-001 already built
(no network, no credentials, read-only rootfs, uid 65534, all capabilities
dropped, throwaway container), so this entry point adds NO new sandbox: it adds
a way to hand that sandbox a source string instead of a file path.

One hardening decision belongs here and nowhere else: **the legacy in-process
mode is refused**. That mode only isolates when the API runs as root, a
trade-off accepted for code the user installed deliberately; it is not
acceptable for code a model wrote from an email. Fail closed, never downgrade.
"""

from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.core.config import Settings, get_settings
from src.core.constants import SKILLS_SCRIPT_SANDBOX_MAX_SOURCE_BYTES
from src.domains.skills.executor import EgressSpec, SkillScriptExecutor

pytestmark = [pytest.mark.unit]


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "skills_script_sandbox": "container",
        "skills_script_sandbox_image": "lia-api:local",
        "skills_script_timeout_seconds": 30,
        "skills_script_max_output_kb": 50,
        "skills_script_max_input_kb": 100,
    }
    base.update(overrides)
    return get_settings().model_copy(update=base)


def _completed(stdout: str = "42\n", returncode: int = 0) -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def _launch_test_python(**kwargs: object) -> subprocess.CompletedProcess[str]:
    """Run deterministic test sources through the actual launcher, without Docker."""
    argv = kwargs["cmd"]
    assert isinstance(argv, list)
    image_index = argv.index("lia-api:local")
    return subprocess.run(
        [sys.executable, *argv[image_index + 1 :]],
        input=str(kwargs["stdin_payload"]),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )


class TestTheLegacyModeIsRefused:
    """Model-authored code never runs in the path that only isolates as root."""

    @pytest.mark.parametrize("mode", ["subprocess", "", "SUBPROCESS"])
    async def test_a_non_container_sandbox_refuses_to_run(self, mode: str) -> None:
        with (
            patch(
                "src.core.config.get_settings", return_value=_settings(skills_script_sandbox=mode)
            ),
            patch.object(SkillScriptExecutor, "_run_sandbox_sync") as spawn,
        ):
            result = await SkillScriptExecutor.execute_source(
                source="print(1)", payload={}, label="ephemeral"
            )

        assert result.success is False
        assert result.execution_started is False
        assert "sandbox" in (result.error or "").lower()
        spawn.assert_not_called(), "nothing may be spawned when the sandbox is not the container"


class TestTheSourceTravelsWithoutAFile:
    async def test_the_launcher_preserves_future_imports_argv_and_json_stdin(self) -> None:
        source = (
            "from __future__ import annotations\n"
            "import json, sys\n"
            "print(json.dumps([sys.argv, json.load(sys.stdin)['items']]))\n"
        )
        with (
            patch("src.core.config.get_settings", return_value=_settings()),
            patch.object(SkillScriptExecutor, "_run_sandbox_sync", side_effect=_launch_test_python),
        ):
            result = await SkillScriptExecutor.execute_source(
                source=source, payload={"items": {"x": 1}}, label="ephemeral"
            )

        assert result.execution_started is True
        assert result.success is True
        assert json.loads(result.output) == [["-c"], {"x": 1}]

    async def test_the_model_source_reaches_the_container_argv(self) -> None:
        source = "import json,sys; print(len(json.load(sys.stdin)['items']))"
        with (
            patch("src.core.config.get_settings", return_value=_settings()),
            patch.object(
                SkillScriptExecutor, "_run_sandbox_sync", return_value=_completed()
            ) as spawn,
        ):
            result = await SkillScriptExecutor.execute_source(
                source=source, payload={"items": [1, 2]}, label="ephemeral"
            )

        assert result.success is True
        assert result.execution_started is True
        argv = spawn.call_args.kwargs["cmd"]
        assert argv[-1] == source, "the source is passed inline, never mounted"
        assert "--network" in argv and argv[argv.index("--network") + 1] == "none"

    async def test_the_payload_is_handed_on_stdin_as_json(self) -> None:
        with (
            patch("src.core.config.get_settings", return_value=_settings()),
            patch.object(
                SkillScriptExecutor, "_run_sandbox_sync", return_value=_completed()
            ) as spawn,
        ):
            await SkillScriptExecutor.execute_source(
                source="pass", payload={"items": [{"id": "a"}]}, label="ephemeral"
            )

        stdin = json.loads(spawn.call_args.kwargs["stdin_payload"])
        assert stdin["items"] == [{"id": "a"}]

    async def test_no_skill_is_ever_resolved(self) -> None:
        """An ephemeral run must not touch the installed-skill cache."""
        with (
            patch("src.core.config.get_settings", return_value=_settings()),
            patch.object(SkillScriptExecutor, "_run_sandbox_sync", return_value=_completed()),
            patch("src.domains.skills.cache.SkillsCache.get_system_by_name") as by_name,
            patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user") as by_user,
        ):
            await SkillScriptExecutor.execute_source(source="pass", payload={}, label="ephemeral")

        by_name.assert_not_called()
        by_user.assert_not_called()


class TestTheBoundsHold:
    @pytest.mark.parametrize("exit_code", [125, 126, 127])
    async def test_a_script_using_a_docker_reserved_exit_code_still_started(
        self, exit_code: int
    ) -> None:
        """Run the actual launcher with a deterministic test script, without Docker."""

        with (
            patch("src.core.config.get_settings", return_value=_settings()),
            patch.object(SkillScriptExecutor, "_run_sandbox_sync", side_effect=_launch_test_python),
        ):
            result = await SkillScriptExecutor.execute_source(
                source=f"import sys; sys.exit({exit_code})", payload={}, label="ephemeral"
            )

        assert result.success is False
        assert result.execution_started is True
        assert result.exit_code == exit_code
        assert result.error == "Script failed"

    async def test_an_unreadable_result_after_dispatch_is_charged_conservatively(self) -> None:
        error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        with (
            patch("src.core.config.get_settings", return_value=_settings()),
            patch.object(SkillScriptExecutor, "_run_sandbox_sync", side_effect=error),
        ):
            result = await SkillScriptExecutor.execute_source(
                source="pass", payload={}, label="ephemeral"
            )

        assert result.success is False
        assert result.execution_started is True

    async def test_an_oversized_source_is_refused_before_the_daemon(self) -> None:
        with (
            patch("src.core.config.get_settings", return_value=_settings()),
            patch.object(SkillScriptExecutor, "_run_sandbox_sync") as spawn,
        ):
            result = await SkillScriptExecutor.execute_source(
                source="x" * (SKILLS_SCRIPT_SANDBOX_MAX_SOURCE_BYTES + 1),
                payload={},
                label="ephemeral",
            )

        assert result.success is False
        assert result.execution_started is False
        spawn.assert_not_called()

    async def test_an_oversized_payload_is_refused(self) -> None:
        with (
            patch(
                "src.core.config.get_settings",
                return_value=_settings(skills_script_max_input_kb=1),
            ),
            patch.object(SkillScriptExecutor, "_run_sandbox_sync") as spawn,
        ):
            result = await SkillScriptExecutor.execute_source(
                source="pass", payload={"blob": "y" * 4096}, label="ephemeral"
            )

        assert result.success is False
        assert result.execution_started is False
        assert "exceeds" in (result.error or "").lower()
        spawn.assert_not_called()

    async def test_a_failing_script_returns_its_stderr_not_an_exception(self) -> None:
        """The model must be able to READ its own traceback to repair the script."""
        broken = SimpleNamespace(
            returncode=1, stdout="", stderr="Traceback...\nNameError: name 'x' is not defined"
        )
        with (
            patch("src.core.config.get_settings", return_value=_settings()),
            patch.object(SkillScriptExecutor, "_run_sandbox_sync", return_value=broken),
        ):
            result = await SkillScriptExecutor.execute_source(
                source="print(x)", payload={}, label="ephemeral"
            )

        assert result.success is False
        assert result.execution_started is True
        assert "NameError" in (result.error or "")


class TestANetworkRun:
    """ADR-298: an ``EgressSpec`` puts the run on the sandbox network under
    its own, longer budget; without one the run is exactly what it was."""

    async def test_the_spec_reaches_the_argv_and_the_budget_is_the_network_one(self) -> None:
        spec = EgressSpec(
            network="lia-sandbox",
            proxy_url="http://egress:3128",
            ca_volume="lia-egress-ca",
            ca_dir="/etc/lia-egress/ca",
            ca_file="/etc/lia-egress/ca/ca.crt",
            tokens={"LIA_KEY_BRAVE_SEARCH": "sbx_x"},
        )
        with (
            patch("src.core.config.get_settings", return_value=_settings()),
            patch.object(
                SkillScriptExecutor, "_run_sandbox_sync", return_value=_completed()
            ) as spawn,
        ):
            result = await SkillScriptExecutor.execute_source(
                source="pass", payload={}, label="ephemeral", timeout_seconds=60, egress=spec
            )
        assert result.success is True
        argv = spawn.call_args.kwargs["cmd"]
        assert argv[argv.index("--network") + 1] == "lia-sandbox"
        assert "--env" in argv and "LIA_KEY_BRAVE_SEARCH=sbx_x" in argv
        # The wall clock leaves the container its startup grace, as before.
        assert spawn.call_args.kwargs["timeout"] > 60

    async def test_without_a_spec_nothing_changes(self) -> None:
        with (
            patch("src.core.config.get_settings", return_value=_settings()),
            patch.object(
                SkillScriptExecutor, "_run_sandbox_sync", return_value=_completed()
            ) as spawn,
        ):
            await SkillScriptExecutor.execute_source(source="pass", payload={}, label="ephemeral")
        argv = spawn.call_args.kwargs["cmd"]
        assert argv[argv.index("--network") + 1] == "none"
        assert "-v" not in argv
        assert not any(arg.startswith("HTTPS_PROXY=") for arg in argv)
