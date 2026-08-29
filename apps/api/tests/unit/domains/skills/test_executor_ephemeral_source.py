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
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.core.config import Settings, get_settings
from src.core.constants import SKILLS_SCRIPT_SANDBOX_MAX_SOURCE_BYTES
from src.domains.skills.executor import SkillScriptExecutor

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
        assert "sandbox" in (result.error or "").lower()
        spawn.assert_not_called(), "nothing may be spawned when the sandbox is not the container"


class TestTheSourceTravelsWithoutAFile:
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
            patch("src.domains.skills.cache.SkillsCache.get_by_name") as by_name,
            patch("src.domains.skills.cache.SkillsCache.get_by_name_for_user") as by_user,
        ):
            await SkillScriptExecutor.execute_source(source="pass", payload={}, label="ephemeral")

        by_name.assert_not_called()
        by_user.assert_not_called()


class TestTheBoundsHold:
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
        assert "NameError" in (result.error or "")
