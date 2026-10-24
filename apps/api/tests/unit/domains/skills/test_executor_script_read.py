"""A skill's script is read in a worker thread before it reaches its container (AC-035)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.domains.skills.executor import ScriptResult, SkillScriptExecutor

pytestmark = pytest.mark.unit


async def _run(script: Path) -> ScriptResult:
    return await SkillScriptExecutor._execute_in_container(
        skill_name="proof-skill",
        script_name=script.name,
        script_path=script,
        stdin_payload="{}",
        timeout=5,
        max_output=1024,
        user_id=None,
        settings=settings,
    )


async def test_the_script_is_read_off_the_loop_and_handed_over_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = tmp_path / "proof.py"
    script.write_text("print('été')\n", encoding="utf-8")
    container = AsyncMock(return_value=ScriptResult(success=True, output="été", error=None))
    monkeypatch.setattr(SkillScriptExecutor, "_run_source_in_container", container)
    reads: list[int] = []
    real_read_text = Path.read_text

    def recording(path: Path, *args: Any, **kwargs: Any) -> str:
        reads.append(threading.get_ident())
        return real_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", recording)

    result = await _run(script)

    assert result.success
    assert container.await_args is not None
    assert container.await_args.kwargs["source"] == "print('été')\n"
    assert reads and threading.get_ident() not in reads


async def test_an_unreadable_script_is_a_named_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    container = AsyncMock()
    monkeypatch.setattr(SkillScriptExecutor, "_run_source_in_container", container)

    result = await _run(tmp_path / "missing.py")

    assert not result.success and result.error == "Script could not be read"
    container.assert_not_awaited()
