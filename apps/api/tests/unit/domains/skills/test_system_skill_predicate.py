"""Glue tests for the canonical system-skill predicate (ADR-137 post-release fix).

The defect these tests close: the history-rehydration filter read
``entry.get("is_system")`` on SkillsCache entries — a key that only exists on
the DB ``skills`` table, never on cache entries (the loader stamps ``scope``).
The filter therefore matched nothing, every rehydrated widget was demoted, and
the desktop probe refused the map iframe. The unit tests of the pure functions
all passed, because they fed a synthetic frozenset: the cache→filter glue was
covered by nothing.

These tests deliberately go through the REAL loader on a temp directory tree
(``load_from_disk`` → ``scan_skills_directory`` → ``parse_skill_file``), never
a hand-built dict or a mocked cache, so the entry shape asserted here is the
shape production sees.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.domains.agents.data_registry.message_widgets import rehydrate_message_widgets
from src.domains.skills.cache import SkillsCache

_SYSTEM_SKILL = "sys-map"
_USER_SKILL = "my-notes"
_USER_ID = "11111111-2222-3333-4444-555555555555"


def _write_skill(base: Path, name: str) -> None:
    """Create a minimal valid SKILL.md under ``base/<name>/``."""
    skill_dir = base / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: A test skill.\n---\n\n# {name}\n\nInstructions.\n",
        encoding="utf-8",
    )


@pytest.fixture()
def loaded_cache(tmp_path: Path) -> Iterator[None]:
    """Load a real system + user skill tree into SkillsCache, then restore it.

    Saving/restoring the class-level state keeps the singleton intact for the
    other tests of the worker (loadscope parallelism shares the process).
    """
    system_dir = tmp_path / "system"
    users_dir = tmp_path / "users"
    _write_skill(system_dir, _SYSTEM_SKILL)
    _write_skill(users_dir / _USER_ID, _USER_SKILL)

    saved_skills = SkillsCache._skills
    saved_loaded = SkillsCache._loaded
    try:
        SkillsCache.load_from_disk(str(system_dir), str(users_dir))
        yield
    finally:
        SkillsCache._skills = saved_skills
        SkillsCache._loaded = saved_loaded


def _entry(name: str) -> dict[str, Any]:
    entry = SkillsCache.get_by_name(name)
    assert entry is not None, f"loader did not produce entry for {name!r}"
    return entry


class TestLoaderEntryShape:
    """Pin the real entry shape the predicate is written against."""

    def test_entries_carry_scope_not_is_system(self, loaded_cache: None) -> None:
        """The loader stamps ``scope``; ``is_system`` must NOT appear.

        If a future loader change ever adds an ``is_system`` key, this pin
        forces the author to reconcile it with ``entry_is_system`` instead of
        letting two divergent sources of truth coexist.
        """
        for name in (_SYSTEM_SKILL, _USER_SKILL):
            entry = _entry(name)
            assert "scope" in entry
            assert "is_system" not in entry

    def test_scopes_reflect_directory_of_origin(self, loaded_cache: None) -> None:
        assert _entry(_SYSTEM_SKILL)["scope"] == "admin"
        assert _entry(_USER_SKILL)["scope"] == "user"


class TestEntryIsSystem:
    """The canonical predicate, exercised on loader-produced entries."""

    def test_admin_scope_is_system(self, loaded_cache: None) -> None:
        assert SkillsCache.entry_is_system(_entry(_SYSTEM_SKILL)) is True

    def test_user_scope_is_not_system(self, loaded_cache: None) -> None:
        assert SkillsCache.entry_is_system(_entry(_USER_SKILL)) is False

    def test_missing_scope_is_not_system(self) -> None:
        """Strict on malformed entries: no scope → no privileges."""
        assert SkillsCache.entry_is_system({}) is False

    def test_write_path_lookup_gives_user_skill_no_privileges(self, loaded_cache: None) -> None:
        """The run_skill_script write path: user skill resolved → not system.

        Guards the latent escalation: the old code defaulted the missing
        ``is_system`` key to True, which would have granted user-imported
        skills ``credentialless`` + ``allow-same-origin`` on their frame.
        """
        resolved = SkillsCache.get_by_name_for_user(_USER_SKILL, _USER_ID)
        assert resolved is not None
        assert SkillsCache.entry_is_system(resolved) is False


class TestGetSystemSkillNames:
    """The read-path filter, from the real cache — the exact prod defect."""

    def test_only_system_skills_are_listed(self, loaded_cache: None) -> None:
        names = SkillsCache.get_system_skill_names(_USER_ID)
        assert _SYSTEM_SKILL in names
        assert _USER_SKILL not in names

    def test_shadowing_user_skill_is_not_system_for_its_owner(self, tmp_path: Path) -> None:
        """A user skill that shadows a system name loses system status FOR
        THAT USER — the same override semantics as the write path.

        A global name-based set would re-grant `credentialless` +
        `allow-same-origin` at rehydration to a widget produced by
        user-owned code. For every other user the name still resolves to
        the system skill.
        """
        system_dir = tmp_path / "system"
        users_dir = tmp_path / "users"
        _write_skill(system_dir, _SYSTEM_SKILL)
        _write_skill(users_dir / _USER_ID, _SYSTEM_SKILL)  # shadow, same name

        saved_skills = SkillsCache._skills
        saved_loaded = SkillsCache._loaded
        try:
            SkillsCache.load_from_disk(str(system_dir), str(users_dir))
            assert _SYSTEM_SKILL not in SkillsCache.get_system_skill_names(_USER_ID)
            assert _SYSTEM_SKILL in SkillsCache.get_system_skill_names("someone-else")
        finally:
            SkillsCache._skills = saved_skills
            SkillsCache._loaded = saved_loaded

    def test_rehydration_keeps_system_privileges(self, loaded_cache: None) -> None:
        """Loader → cache → rehydration: a system-skill widget stays system.

        This is the full glue chain that was uncovered: with the broken
        filter, ``system_skill_names`` was empty and this widget came back
        demoted, which made the desktop probe refuse the iframe.
        """
        metadata = {
            "widgets": {
                "skill_app_abc123": {
                    "type": "SKILL_APP",
                    "payload": {
                        "skill_name": _SYSTEM_SKILL,
                        "frame_url": "https://www.google.com/maps/embed?pb=x",
                        "is_system_skill": True,
                    },
                },
                "skill_app_def456": {
                    "type": "SKILL_APP",
                    "payload": {
                        "skill_name": _USER_SKILL,
                        "frame_url": "https://example.com/frame",
                        "is_system_skill": True,
                    },
                },
            }
        }
        rehydrated = rehydrate_message_widgets(
            metadata, system_skill_names=SkillsCache.get_system_skill_names(_USER_ID)
        )
        assert rehydrated["skill_app_abc123"]["payload"]["is_system_skill"] is True
        assert rehydrated["skill_app_def456"]["payload"]["is_system_skill"] is False
