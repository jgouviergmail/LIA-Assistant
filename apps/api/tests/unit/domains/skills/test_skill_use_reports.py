"""A turn that uses a skill reports it to the usage door, with its run (lot 14).

The ReAct loop activates a skill through ``activate_skill_tool``: a skill it
found is counted under the run's identity, once per turn at the source (the
door's run check is the second net), a name that resolves to nothing is not.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from src.core.context import bind_skill_context, reset_skill_context
from src.domains.agents.utils.rate_limiting import _rate_limit_tracker
from src.domains.skills import tools as skill_tools
from src.domains.skills.cache import SkillsCache
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

_ME = "11111111-1111-4111-8111-111111111111"


@pytest.fixture()
def skills(tmp_path: Path) -> Iterator[None]:
    """My own ``notes``, bound for the request."""
    folder = tmp_path / "users" / _ME / "notes"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        "---\nname: notes\ndescription: Test skill notes.\n---\n\nDo notes things.\n",
        encoding="utf-8",
    )
    (tmp_path / "system").mkdir()
    saved = SkillsCache._skills, SkillsCache._loaded
    tokens = bind_skill_context({"notes"}, frozenset())
    _rate_limit_tracker.clear()
    try:
        SkillsCache.load_from_disk(str(tmp_path / "system"), str(tmp_path / "users"))
        yield
    finally:
        _rate_limit_tracker.clear()
        reset_skill_context(tokens)
        SkillsCache._skills, SkillsCache._loaded = saved


def _runtime(run_id: str, state: dict[str, Any] | None = None) -> Any:
    runtime = make_tool_runtime(
        user_id=UUID(_ME), thread_id="t", conversation_id="t", store=MagicMock(), state=state
    )
    runtime.config["metadata"] = {"run_id": run_id}
    return runtime


@pytest.fixture()
def reports(monkeypatch: pytest.MonkeyPatch) -> list[tuple[UUID, str, str]]:
    seen: list[tuple[UUID, str, str]] = []

    def schedule(user_id: UUID, skill_name: str, *, run_id: str) -> None:
        seen.append((user_id, skill_name, run_id))

    monkeypatch.setattr(skill_tools, "schedule_skill_use", schedule)
    return seen


async def test_a_skill_the_loop_activates_is_counted_under_its_run(
    skills: None, reports: list[tuple[UUID, str, str]]
) -> None:
    result = await skill_tools.activate_skill_tool.coroutine(
        name="notes", runtime=_runtime("run-7")
    )

    assert result.success is True
    assert reports == [(UUID(_ME), "notes", "run-7")]


async def test_a_name_that_resolves_to_nothing_is_not_counted(
    skills: None, reports: list[tuple[UUID, str, str]]
) -> None:
    result = await skill_tools.activate_skill_tool.coroutine(
        name="absent", runtime=_runtime("run-7")
    )

    assert result.success is False
    assert reports == []


async def test_a_skill_this_turn_already_activated_is_reported_once(
    skills: None, reports: list[tuple[UUID, str, str]]
) -> None:
    """A run reports a skill once at the source: the door's run check is the second net."""
    result = await skill_tools.activate_skill_tool.coroutine(
        name="notes", runtime=_runtime("run-7", {"react_activated_skills": ["notes"]})
    )

    assert result.success is True
    assert reports == []
