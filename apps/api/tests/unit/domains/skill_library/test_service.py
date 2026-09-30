"""Searching, previewing, installing and updating a library skill (ADR-327).

The network half runs against the fake hub; the account's state is stubbed
here at the service's own seams (``_installed_rows``, ``_conflict``,
``_register``, ``_installed_skill``) and exercised on real PostgreSQL by the
integration tests.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from src.domains.skill_library import service
from src.domains.skill_library.errors import (
    ALREADY_INSTALLED,
    AUDIT_BLOCKED,
    NAME_TAKEN,
    QUERY_INVALID,
    RENAMED,
    SOURCE_INVALID,
    LibraryRefusal,
)
from src.domains.skill_library.repository import InstalledSkill, SourceRecord
from src.domains.skill_library.resolver import ReadSkill
from src.domains.skill_library.schemas import LibraryInstallRequest, LibraryInstallResponse
from tests.unit.domains.skill_library.fakes import FakeHub, audit_of, entry, manifest

pytestmark = pytest.mark.unit

ME = uuid4()
REPO = "acme/skills"


def _installed(**overrides: Any) -> InstalledSkill:
    base: dict[str, Any] = {
        "skill_id": uuid4(),
        "name": "pdf",
        "portal": "skills_sh",
        "repository": REPO,
        "ref": "HEAD",
        "path": "skills/pdf",
        "registry_id": f"{REPO}/pdf",
        "commit_sha": "0" * 40,
        "tree_sha": "1" * 40,
    }
    return InstalledSkill(**{**base, **overrides})


@pytest.fixture()
def account(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The account's state at the service's seams; ``registered`` records installs."""
    state: dict[str, Any] = {"rows": [], "conflict": "none", "registered": []}

    async def rows(_user_id: UUID) -> list[InstalledSkill]:
        return list(state["rows"])

    async def conflict(_user_id: UUID, _name: str, _repo: str, _path: str) -> str:
        return str(state["conflict"])

    async def register(
        _user_id: UUID, read: ReadSkill, files: dict[str, bytes], record: SourceRecord
    ) -> LibraryInstallResponse:
        state["registered"].append((read, files, record))
        return LibraryInstallResponse(
            skill_id=uuid4(), name=read.name, commit_sha=record.commit_sha
        )

    async def installed_skill(_user_id: UUID, skill_id: UUID) -> InstalledSkill:
        return next(r for r in state["rows"] if r.skill_id == skill_id)

    monkeypatch.setattr(service, "_installed_rows", rows)
    monkeypatch.setattr(service, "_conflict", conflict)
    monkeypatch.setattr(service, "_register", register)
    monkeypatch.setattr(service, "_installed_skill", installed_skill)
    return state


class TestSearching:
    async def test_what_is_installed_and_what_cannot_be_are_marked(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        hub.search_results = [
            entry(REPO, "pdf"),
            entry(REPO, "docx"),
            {**entry(REPO, "site"), "source": "skills.example.org"},
        ]
        account["rows"] = [_installed(registry_id=None)]
        found = await service.search(ME, "  documents  ", None)

        by_id = {i.skill_id: i for i in found.items}
        assert by_id["pdf"].installed is True and by_id["docx"].installed is False
        assert by_id["site"].supported is False and by_id["pdf"].supported is True

    @pytest.mark.parametrize("query", ["a", " ", "x" * 101])
    async def test_a_text_out_of_bounds_is_refused(
        self, hub: FakeHub, account: dict[str, Any], query: str
    ) -> None:
        with pytest.raises(LibraryRefusal) as refused:
            await service.search(ME, query, None)
        assert refused.value.code == QUERY_INVALID
        assert hub.seen == []

    async def test_an_unknown_portal_is_refused(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        with pytest.raises(LibraryRefusal) as refused:
            await service.search(ME, "pdf", "elsewhere")
        assert refused.value.code == SOURCE_INVALID


class TestPreviewing:
    async def test_a_portal_skill_is_read_with_its_audits(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        commit = hub.publish(
            REPO,
            "v1",
            {"skills/pdf/SKILL.md": manifest("pdf"), "skills/pdf/scripts/x.py": b"print(1)"},
        )
        hub.audits = audit_of("pdf", snyk="low")
        answer = await service.preview(
            ME, repository=REPO, skill_id="pdf", portal="skills_sh", registry_id=f"{REPO}/pdf"
        )

        shown = answer.preview
        assert shown is not None and answer.choice is None
        assert (shown.name, shown.path, shown.commit_sha) == ("pdf", "skills/pdf", commit)
        assert shown.has_scripts is True and shown.blocked_by is None
        assert shown.audits is not None and shown.audits[0].risk == "low"

    async def test_an_audit_at_the_refusal_level_is_shown_as_blocking(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        hub.publish(REPO, "v1", {"SKILL.md": manifest("skills")})
        hub.audits = audit_of("skills", socket="critical")
        answer = await service.preview(ME, address=REPO)
        assert answer.preview is not None and answer.preview.blocked_by == "critical"

    async def test_several_skills_and_none_named_ask_for_a_choice(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        commit = hub.publish(REPO, "v1", {"a/SKILL.md": manifest("a"), "b/SKILL.md": manifest("b")})
        answer = await service.preview(ME, address=f"https://github.com/{REPO}")
        assert answer.preview is None and answer.choice is not None
        assert (answer.choice.folders, answer.choice.commit_sha) == (["a", "b"], commit)

    async def test_a_chosen_folder_is_read(self, hub: FakeHub, account: dict[str, Any]) -> None:
        hub.publish(REPO, "v1", {"a/SKILL.md": manifest("a"), "b/SKILL.md": manifest("b")})
        answer = await service.preview(ME, address=REPO, path="b")
        assert answer.preview is not None and answer.preview.name == "b"

    async def test_the_conflict_is_stated(self, hub: FakeHub, account: dict[str, Any]) -> None:
        hub.publish(REPO, "v1", {"SKILL.md": manifest("skills")})
        account["conflict"] = "name_taken"
        answer = await service.preview(ME, address=REPO)
        assert answer.preview is not None and answer.preview.conflict == "name_taken"


def _request(commit: str, **overrides: Any) -> LibraryInstallRequest:
    base: dict[str, Any] = {"repository": REPO, "path": "skills/pdf", "commit_sha": commit}
    return LibraryInstallRequest(**{**base, **overrides})


class TestInstalling:
    async def test_the_folder_is_installed_at_the_commit_the_preview_read(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        files = {"skills/pdf/SKILL.md": manifest("pdf"), "skills/pdf/r/a.md": b"ref"}
        first = hub.publish(REPO, "v1", files)
        hub.publish(REPO, "v2", {**files, "skills/pdf/r/a.md": b"newer"})  # the branch moved

        await service.install(ME, _request(first, portal="skills_sh", skill_id="pdf"))

        read, downloaded, record = account["registered"][0]
        assert downloaded == {"SKILL.md": manifest("pdf"), "r/a.md": b"ref"}
        assert (record.commit_sha, record.tree_sha) == (
            first,
            hub.tree_sha(REPO, first, "skills/pdf"),
        )
        assert (record.origin, record.portal, record.ref) == ("github", "skills_sh", "HEAD")

    async def test_an_audit_refuses_before_any_file_is_downloaded(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        commit = hub.publish(REPO, "v1", {"skills/pdf/SKILL.md": manifest("pdf")})
        hub.audits = audit_of("pdf", socket="high")
        with pytest.raises(LibraryRefusal) as refused:
            await service.install(ME, _request(commit))
        assert (refused.value.code, refused.value.detail) == (AUDIT_BLOCKED, {"risk": "high"})
        raw = [s.path for s in hub.seen if s.host == "raw.githubusercontent.com"]
        assert raw == [f"/{REPO}/{commit}/skills/pdf/SKILL.md"]  # the manifest, to name it
        assert account["registered"] == []

    async def test_a_folder_named_otherwise_is_still_audited_under_its_name(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        commit = hub.publish(REPO, "v1", {"skills/pdf/SKILL.md": manifest("pdf-tools")})
        hub.audits = audit_of("pdf-tools", socket="critical")
        with pytest.raises(LibraryRefusal) as refused:
            await service.install(ME, _request(commit, skill_id="decoy"))
        assert refused.value.code == AUDIT_BLOCKED

    @pytest.mark.parametrize(
        ("conflict", "code"), [("installed", ALREADY_INSTALLED), ("name_taken", NAME_TAKEN)]
    )
    async def test_a_taken_name_is_refused(
        self, hub: FakeHub, account: dict[str, Any], conflict: str, code: str
    ) -> None:
        commit = hub.publish(REPO, "v1", {"skills/pdf/SKILL.md": manifest("pdf")})
        account["conflict"] = conflict
        with pytest.raises(LibraryRefusal) as refused:
            await service.install(ME, _request(commit))
        assert refused.value.code == code
        assert account["registered"] == []

    async def test_a_path_leaving_the_repository_is_refused(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        with pytest.raises(LibraryRefusal) as refused:
            await service.install(ME, _request("a" * 40, path="../x"))
        assert refused.value.code == SOURCE_INVALID
        assert hub.seen == []


class TestUpdating:
    async def test_each_installed_skill_says_whether_it_moved(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        first = hub.publish(REPO, "v1", {"a/SKILL.md": manifest("a"), "b/SKILL.md": manifest("b")})
        tree_a, tree_b = hub.tree_sha(REPO, first, "a"), hub.tree_sha(REPO, first, "b")
        hub.publish(REPO, "v2", {"a/SKILL.md": manifest("a"), "b/SKILL.md": manifest("b", "New.")})
        account["rows"] = [
            _installed(name="a", path="a", tree_sha=tree_a),
            _installed(name="b", path="b", tree_sha=tree_b),
            _installed(name="gone", path="removed", tree_sha="2" * 40),
            _installed(name="lost", repository="acme/missing"),
        ]
        states = {i.name: i.update for i in (await service.installed(ME)).items}
        assert states == {"a": "current", "b": "available", "gone": "unknown", "lost": "unknown"}

    async def test_an_update_preview_lists_what_changes(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        first = hub.publish(
            REPO, "v1", {"p/SKILL.md": manifest("p"), "p/old.md": b"o", "p/keep.md": b"k"}
        )
        row = _installed(name="p", path="p", tree_sha=hub.tree_sha(REPO, first, "p"))
        account["rows"] = [row]
        hub.publish(
            REPO, "v2", {"p/SKILL.md": manifest("p", "New."), "p/new.md": b"n", "p/keep.md": b"k"}
        )

        answer = await service.update_preview(ME, row.skill_id)
        assert answer.changes.model_dump() == {
            "added": ["new.md"],
            "removed": ["old.md"],
            "modified": ["SKILL.md"],
        }

    async def test_a_renamed_version_is_not_an_update(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        row = _installed(name="p", path="p")
        account["rows"] = [row]
        commit = hub.publish(REPO, "v2", {"p/SKILL.md": manifest("p-renamed")})
        with pytest.raises(LibraryRefusal) as refused:
            await service.update(ME, row.skill_id, commit)
        assert (refused.value.code, refused.value.detail) == (RENAMED, {"name": "p-renamed"})

    async def test_an_update_installs_the_previewed_commit(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        row = _installed(name="p", path="p")
        account["rows"] = [row]
        commit = hub.publish(REPO, "v2", {"p/SKILL.md": manifest("p", "New.")})
        await service.update(ME, row.skill_id, commit)
        _read, _files, record = account["registered"][0]
        assert (record.commit_sha, record.registry_id) == (commit, row.registry_id)


class TestWhatReviewFound:
    """Cold review of lot 1: an unknown portal, a stored ref, a shared allowance."""

    async def test_an_unknown_portal_is_refused_before_any_request(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        with pytest.raises(LibraryRefusal) as refused:
            await service.install(ME, _request("a" * 40, portal="elsewhere"))
        assert refused.value.code == SOURCE_INVALID
        with pytest.raises(LibraryRefusal) as refused:
            await service.preview(ME, repository=REPO, skill_id="pdf", portal="elsewhere")
        assert refused.value.code == SOURCE_INVALID
        assert hub.seen == []

    @pytest.mark.parametrize("ref", ["../main", "has space", "a..b"])
    async def test_a_ref_that_is_no_ref_is_never_stored(
        self, hub: FakeHub, account: dict[str, Any], ref: str
    ) -> None:
        with pytest.raises(LibraryRefusal) as refused:
            await service.install(ME, _request("a" * 40, ref=ref))
        assert refused.value.code == SOURCE_INVALID
        assert hub.seen == []

    async def test_one_repository_is_read_once_however_many_skills_it_gave(
        self, hub: FakeHub, account: dict[str, Any]
    ) -> None:
        commit = hub.publish(REPO, "v1", {"a/SKILL.md": manifest("a"), "b/SKILL.md": manifest("b")})
        account["rows"] = [
            _installed(name="a", path="a", tree_sha=hub.tree_sha(REPO, commit, "a")),
            _installed(name="b", path="b", tree_sha=hub.tree_sha(REPO, commit, "b")),
        ]
        states = {i.name: i.update for i in (await service.installed(ME)).items}

        assert states == {"a": "current", "b": "current"}
        api_calls = [s.path for s in hub.seen if s.host == "api.github.com"]
        assert len(api_calls) == 2  # one head, one listing
