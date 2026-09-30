"""A skill name is unique per ACCOUNT, not per instance (ADR-327, lot 0).

Two people may each keep a skill called ``pdf``; a system skill of that name is
shadowed, for its owner only, by their own. Every lookup names its scope: the
any-scope ``SkillsCache.get_by_name`` (first match, whoever owned it) is gone,
because with per-account names it would hand one person another person's skill.

The cache tests go through the REAL loader on a temp tree (the shape production
sees). The import conflicts live in ``test_import_service.py``; the database
rules in ``tests/integration/domains/skills/test_per_account_skill_names.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from src.domains.skills.cache import SkillsCache
from src.domains.skills.import_service import SkillImportService

pytestmark = pytest.mark.unit

_ALICE = "11111111-1111-4111-8111-111111111111"
_BOB = "22222222-2222-4222-8222-222222222222"
_CAROL = "33333333-3333-4333-8333-333333333333"


def _write_skill(base: Path, name: str, description: str = "A test skill.") -> None:
    skill_dir = base / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n# {name}\n\nBody.\n",
        encoding="utf-8",
    )


@pytest.fixture()
def two_owners_tree(tmp_path: Path) -> Iterator[None]:
    """System ``brief``; Alice owns ``pdf`` and ``brief``; Bob owns ``pdf``."""
    system_dir = tmp_path / "system"
    users_dir = tmp_path / "users"
    _write_skill(system_dir, "brief", "System briefing.")
    _write_skill(users_dir / _ALICE, "pdf", "Alice's pdf.")
    _write_skill(users_dir / _ALICE, "brief", "Alice's own briefing.")
    _write_skill(users_dir / _BOB, "pdf", "Bob's pdf.")

    saved_skills, saved_loaded = SkillsCache._skills, SkillsCache._loaded
    try:
        SkillsCache.load_from_disk(str(system_dir), str(users_dir))
        yield
    finally:
        SkillsCache._skills, SkillsCache._loaded = saved_skills, saved_loaded


class TestCacheKeepsEveryOwnersSkill:
    def test_same_name_in_two_accounts_are_two_entries(self, two_owners_tree: None) -> None:
        pdfs = [s for s in SkillsCache.get_all() if s["name"] == "pdf"]
        assert sorted(s["owner_id"] for s in pdfs) == [_ALICE, _BOB]
        assert len({s["id"] for s in pdfs}) == 2

    def test_each_person_resolves_their_own(self, two_owners_tree: None) -> None:
        alice = SkillsCache.get_by_name_for_user("pdf", _ALICE)
        bob = SkillsCache.get_by_name_for_user("pdf", _BOB)
        assert alice is not None and alice["description"] == "Alice's pdf."
        assert bob is not None and bob["description"] == "Bob's pdf."

    def test_someone_else_never_reaches_it(self, two_owners_tree: None) -> None:
        assert SkillsCache.get_by_name_for_user("pdf", _CAROL) is None

    def test_own_skill_shadows_the_system_one_for_its_owner_only(
        self, two_owners_tree: None
    ) -> None:
        assert SkillsCache.get_by_name_for_user("brief", _ALICE)["scope"] == "user"
        assert SkillsCache.get_by_name_for_user("brief", _BOB)["scope"] == "admin"

    def test_system_lookup_never_returns_a_person_s_skill(self, two_owners_tree: None) -> None:
        assert SkillsCache.get_system_by_name("brief")["scope"] == "admin"
        assert SkillsCache.get_system_by_name("pdf") is None

    def test_exact_lookup_names_its_owner(self, two_owners_tree: None) -> None:
        assert SkillsCache.get_exact("pdf", _BOB)["description"] == "Bob's pdf."
        assert SkillsCache.get_exact("pdf", None) is None
        assert SkillsCache.get_exact("brief", None)["scope"] == "admin"

    def test_the_any_scope_lookup_is_gone(self) -> None:
        """First-match-any-scope would hand one person another person's skill."""
        assert not hasattr(SkillsCache, "get_by_name")

    def test_always_loaded_reads_the_skill_the_name_resolves_to(self, tmp_path: Path) -> None:
        """A shadowed system skill must not be injected beside its owner's own."""
        system_dir, users_dir = tmp_path / "system", tmp_path / "users"
        for base in (system_dir, users_dir / _ALICE):
            skill_dir = base / "brief"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\nname: brief\ndescription: Loaded every turn.\nalways_loaded: true\n---\n",
                encoding="utf-8",
            )
        saved = SkillsCache._skills, SkillsCache._loaded
        try:
            SkillsCache.load_from_disk(str(system_dir), str(users_dir))
            alice = SkillsCache.get_always_loaded(_ALICE)
            bob = SkillsCache.get_always_loaded(_BOB)
            nobody = SkillsCache.get_always_loaded(None)
        finally:
            SkillsCache._skills, SkillsCache._loaded = saved
        assert [s["scope"] for s in alice] == ["user"]
        assert [s["scope"] for s in bob] == ["admin"]
        assert [s["scope"] for s in nobody] == ["admin"]

    def test_for_user_lists_one_entry_per_name(self, two_owners_tree: None) -> None:
        names = sorted(s["name"] for s in SkillsCache.get_for_user(_ALICE))
        assert names == ["brief", "pdf"]
        brief = next(s for s in SkillsCache.get_for_user(_ALICE) if s["name"] == "brief")
        assert brief["scope"] == "user"


class TestAdminImportNeverBlockedByAPersonsName:
    def test_the_user_name_squat_check_is_gone(self) -> None:
        """A person holding a name must not block the administrator's system skill."""
        assert not hasattr(SkillImportService, "_check_admin_conflict")
