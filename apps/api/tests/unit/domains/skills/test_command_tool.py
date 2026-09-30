"""``run_skill_command``: a skill runs its own command, offline (ADR-327 lot 2).

The container is replaced by a recorded ``run_command`` (its own contract is
pinned by ``test_command_sandbox``) and the storage by a recorded delivery
(``test_command_outputs``); everything the TOOL decides is real: the bounds
it publishes and enforces, the scope of an isolated runner, the gates, the
bundle it builds from the skill folder and the turn's files, and what it tells
the model — as external content when the skill was written elsewhere.
"""

from __future__ import annotations

import io
import tarfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from src.core.constants import EXTERNAL_CONTENT_OPEN_TAG, SKILL_COMMAND_MAX_CHARS
from src.core.context import (
    SkillTurnFile,
    bind_skill_context,
    record_skill_turn_files,
    reset_skill_context,
)
from src.domains.skills.cache import SkillsCache
from src.domains.skills.command_bundle import CommandOutput, OutputFile, UnreadableOutput
from src.domains.skills.command_outputs import DeliveredFile, Delivery
from src.domains.skills.command_sandbox import SandboxTimeout, SandboxUnavailable
from src.domains.skills.command_tool import run_skill_command
from src.domains.skills.trust import isolated_to
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

_ME = "11111111-1111-4111-8111-111111111111"
_CONVERSATION = "22222222-2222-4222-8222-222222222222"


def _write(base: Path, name: str) -> None:
    folder = base / name
    (folder / "scripts").mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill {name}.\n---\n\nRun things.\n",
        encoding="utf-8",
    )
    (folder / "scripts" / "fill.sh").write_text("echo filled\n", encoding="utf-8")


@pytest.fixture()
def skills(tmp_path: Path) -> Iterator[Path]:
    """My own ``notes`` (authored) and ``pdf`` (third-party), a stored upload, all bound."""
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
                attachment_id="a1", filename="My form.pdf", file_path=f"{_ME}/stored.pdf", size=8
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
    return make_tool_runtime(
        user_id=UUID(_ME), thread_id=_CONVERSATION, conversation_id=_CONVERSATION, store=MagicMock()
    )


def _output(exit_code: int | None = 0, **overrides: Any) -> CommandOutput:
    values: dict[str, Any] = {
        "exit_code": exit_code,
        "stdout": "filled\n",
        "stderr": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "files": (OutputFile("report.pdf", b"%PDF"),),
        "skipped": (("x.exe", "too_large"),),
    }
    values.update(overrides)
    return CommandOutput(**values)


_DELIVERY = Delivery(
    delivered=(DeliveredFile(name="report.pdf", size=4, family="document"),),
    skipped=(("notes.bin", "type_not_allowed"),),
)


async def _call(
    name: str = "notes",
    command: str = "bash scripts/fill.sh",
    *,
    output: CommandOutput | Exception | None = None,
) -> tuple[Any, AsyncMock, AsyncMock]:
    run = (
        AsyncMock(side_effect=output)
        if isinstance(output, Exception)
        else AsyncMock(return_value=output or _output())
    )
    deliver = AsyncMock(return_value=_DELIVERY)
    with (
        patch("src.domains.skills.command_tool.run_command", run),
        patch("src.domains.skills.command_tool.deliver_outputs", deliver),
    ):
        result = await run_skill_command.coroutine(
            skill_name=name, command=command, runtime=_runtime()
        )
    return result, run, deliver


class TestWhatIsRefused:
    async def test_an_empty_command_names_the_missing_parameter(self, skills: Path) -> None:
        result, run, _ = await _call(command="   ")
        assert (result.success, result.error_code) == (False, "MISSING_REQUIRED_PARAM")
        run.assert_not_awaited()

    async def test_a_command_past_its_published_bound_is_refused_with_it(
        self, skills: Path
    ) -> None:
        result, run, _ = await _call(command="x" * (SKILL_COMMAND_MAX_CHARS + 1))
        assert result.error_code == "INVALID_INPUT"
        assert str(SKILL_COMMAND_MAX_CHARS) in result.message
        run.assert_not_awaited()

    async def test_a_runner_isolated_on_another_skill_is_refused(self, skills: Path) -> None:
        with isolated_to("pdf"):
            result, run, _ = await _call("notes")
        assert result.error_code == "FORBIDDEN"
        run.assert_not_awaited()

    async def test_disabled_scripts_disable_commands(self, skills: Path) -> None:
        from src.core.config import settings

        with patch.object(settings, "skills_scripts_enabled", False):
            result, run, _ = await _call()
        assert result.error_code == "FEATURE_DISABLED"
        run.assert_not_awaited()

    async def test_only_the_container_sandbox_runs_a_command(self, skills: Path) -> None:
        from src.core.config import settings

        with patch.object(settings, "skills_script_sandbox", "subprocess"):
            result, run, _ = await _call()
        assert result.error_code == "FEATURE_DISABLED"
        run.assert_not_awaited()

    async def test_an_unknown_skill_is_not_found(self, skills: Path) -> None:
        result, run, _ = await _call("nope")
        assert result.error_code == "NOT_FOUND"
        run.assert_not_awaited()

    async def test_a_bundle_past_its_budget_names_it(self, skills: Path) -> None:
        from src.core.config import settings

        with patch.object(settings, "skill_command_max_input_mb", 0):
            result, run, _ = await _call()
        assert result.error_code == "CONSTRAINT_VIOLATION"
        run.assert_not_awaited()


class TestWhatRuns:
    async def test_the_skill_folder_and_the_turns_files_travel_in(self, skills: Path) -> None:
        _, run, _ = await _call()
        bundle = run.await_args.kwargs["bundle"]
        with tarfile.open(fileobj=io.BytesIO(bundle)) as tar:
            names = set(tar.getnames())
        assert {"skill/SKILL.md", "skill/scripts/fill.sh", "input/My form.pdf"} <= names
        assert run.await_args.kwargs["command"] == "bash scripts/fill.sh"

    async def test_a_turn_file_past_the_file_bound_stays_out_and_is_named(
        self, skills: Path
    ) -> None:
        from src.core.config import settings

        record_skill_turn_files(
            [
                SkillTurnFile(
                    attachment_id="a2", filename="film.mov", file_path=f"{_ME}/x", size=2**40
                )
            ]
        )
        with patch.object(settings, "skill_command_max_file_mb", 1):
            result, run, _ = await _call()
        with tarfile.open(fileobj=io.BytesIO(run.await_args.kwargs["bundle"])) as tar:
            assert "input/film.mov" not in tar.getnames()
        assert "film.mov" in result.message

    async def test_a_command_that_ran_reports_its_text_its_files_and_its_inputs(
        self, skills: Path
    ) -> None:
        result, _, deliver = await _call()
        assert result.success
        assert "filled" in result.message
        assert "report.pdf" in result.message and "notes.bin" in result.message
        assert "x.exe" in result.message
        assert "../input/My form.pdf" in result.message
        assert EXTERNAL_CONTENT_OPEN_TAG not in result.message
        assert deliver.await_args.kwargs["conversation_id"] == _CONVERSATION
        assert result.structured_data["exit_code"] == 0

    async def test_a_failing_command_is_a_script_error_with_both_streams(
        self, skills: Path
    ) -> None:
        result, _, deliver = await _call(output=_output(2, stderr="boom"))
        assert (result.success, result.error_code) == (False, "SCRIPT_ERROR")
        assert "boom" in result.message and "filled" in result.message
        # What it wrote before failing is still the person's.
        deliver.assert_awaited_once()

    async def test_a_command_past_its_own_budget_is_a_timeout(self, skills: Path) -> None:
        result, _, _ = await _call(output=_output(124))
        assert result.error_code == "TIMEOUT"

    async def test_a_run_past_every_grace_is_a_timeout(self, skills: Path) -> None:
        result, _, deliver = await _call(output=SandboxTimeout("c"))
        assert result.error_code == "TIMEOUT"
        deliver.assert_not_awaited()

    async def test_no_sandbox_is_said_as_such(self, skills: Path) -> None:
        result, _, _ = await _call(output=SandboxUnavailable("125"))
        assert result.error_code == "DEPENDENCY_ERROR"

    async def test_an_output_that_is_not_the_bootstraps_is_named_unreadable(
        self, skills: Path
    ) -> None:
        result, _, deliver = await _call(output=UnreadableOutput("garbage"))
        assert result.error_code == "SCRIPT_ERROR"
        assert "could not be read" in result.message
        deliver.assert_not_awaited()

    async def test_a_turn_file_is_carried_at_its_real_size(self, skills: Path) -> None:
        # The recorded size said 8 bytes; the file on disk says otherwise.
        record_skill_turn_files(
            [
                SkillTurnFile(
                    attachment_id="a3", filename="big.pdf", file_path=f"{_ME}/stored.pdf", size=1
                )
            ]
        )
        _, run, _ = await _call()
        with tarfile.open(fileobj=io.BytesIO(run.await_args.kwargs["bundle"])) as tar:
            member = tar.getmember("input/big.pdf")
        assert member.size == len(b"%PDF-1.7")

    async def test_a_file_gone_before_it_is_read_is_named(self, skills: Path) -> None:
        record_skill_turn_files(
            [
                SkillTurnFile(
                    attachment_id="a4", filename="gone.pdf", file_path=f"{_ME}/nope.pdf", size=3
                )
            ]
        )
        result, _, _ = await _call()
        assert "gone.pdf (unavailable)" in result.message


class TestThirdParty:
    async def test_outside_its_runner_a_third_party_command_reads_as_external(
        self, skills: Path
    ) -> None:
        result, _, _ = await _call("pdf")
        assert EXTERNAL_CONTENT_OPEN_TAG in result.message

    async def test_inside_its_own_runner_it_is_plain(self, skills: Path) -> None:
        with isolated_to("pdf"):
            result, _, _ = await _call("pdf")
        assert result.success
        assert EXTERNAL_CONTENT_OPEN_TAG not in result.message
