"""A skill folder read from GitHub at a commit, verified and bounded (ADR-327)."""

from __future__ import annotations

import pytest

from src.domains.skill_library.errors import (
    AMBIGUOUS,
    NOT_FOUND,
    RATE_LIMITED,
    SOURCE_INVALID,
    TOO_LARGE,
    UNREACHABLE,
    LibraryRefusal,
)
from src.domains.skill_library.github import (
    GithubAddress,
    blob_sha,
    folder_of,
    parse_address,
    read_tree,
    resolve_commit,
    safe_relative,
    skill_folders,
)
from src.domains.skill_library.resolver import check_budget, download, locate, read_at_commit
from tests.unit.domains.skill_library.fakes import FakeHub, manifest

pytestmark = pytest.mark.unit

REPO = "acme/skills"


class TestAPastedAddress:
    @pytest.mark.parametrize(
        ("address", "expected"),
        [
            ("acme/skills", GithubAddress("acme/skills")),
            ("https://github.com/acme/skills", GithubAddress("acme/skills")),
            ("https://github.com/acme/skills.git", GithubAddress("acme/skills")),
            (
                "https://github.com/acme/skills/tree/main/skills/pdf",
                GithubAddress("acme/skills", "main", "skills/pdf"),
            ),
            (
                "https://github.com/acme/skills/blob/v2/skills/pdf/SKILL.md",
                GithubAddress("acme/skills", "v2", "skills/pdf"),
            ),
            (
                "https://github.com/acme/skills/blob/main/SKILL.md",
                GithubAddress("acme/skills", "main", None),
            ),
        ],
    )
    def test_names_its_repository_ref_and_folder(
        self, address: str, expected: GithubAddress
    ) -> None:
        assert parse_address(address) == expected

    @pytest.mark.parametrize(
        "address",
        [
            "http://github.com/acme/skills",
            "https://gitlab.com/acme/skills",
            "https://github.com/acme",
            "acme",
            "ac me/skills",
            "https://github.com/acme/skills/tree/main/../../etc",
            "acme/..",
        ],
    )
    def test_anything_else_is_refused(self, address: str) -> None:
        with pytest.raises(LibraryRefusal) as refused:
            parse_address(address)
        assert refused.value.code == SOURCE_INVALID


class TestPaths:
    @pytest.mark.parametrize("path", ["../x", "/etc/passwd", "a/../b", "a\\b", "c:x", "a//b", ""])
    def test_an_unsafe_path_is_never_kept(self, path: str) -> None:
        assert safe_relative(path) is False

    def test_a_nested_path_is(self) -> None:
        assert safe_relative("skills/pdf/scripts/run.py") is True


class TestGitIdentity:
    def test_a_blob_sha_is_git_s_own(self) -> None:
        # `printf hello | git hash-object --stdin`
        assert blob_sha(b"hello") == "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0"


def _listing(hub: FakeHub, commit: str) -> dict[str, object]:
    listing = hub._listing(REPO, commit)
    assert listing is not None
    return listing


class TestAFolderAtACommit:
    def test_its_files_its_tree_sha_and_what_is_skipped(self, hub: FakeHub) -> None:
        commit = hub.publish(
            REPO,
            "v1",
            {
                "skills/pdf/SKILL.md": manifest("pdf"),
                "skills/pdf/scripts/run.py": b"print(1)",
                "skills/docx/SKILL.md": manifest("docx"),
            },
        )
        hub.extra_entries[(REPO, commit)] = [
            {"path": "skills/pdf/link", "mode": "120000", "type": "blob", "sha": "0" * 40},
            {"path": "skills/pdf/vendor", "mode": "160000", "type": "commit", "sha": "1" * 40},
        ]
        folder = folder_of(_listing(hub, commit), REPO, "HEAD", commit, "skills/pdf")

        assert {f.path for f in folder.files} == {"SKILL.md", "scripts/run.py"}
        assert folder.skipped == ("link", "vendor")
        assert folder.tree_sha == hub.tree_sha(REPO, commit, "skills/pdf")

    def test_a_folder_without_a_manifest_is_not_a_skill(self, hub: FakeHub) -> None:
        commit = hub.publish(REPO, "v1", {"docs/README.md": b"x", "SKILL.md": manifest("root")})
        with pytest.raises(LibraryRefusal) as refused:
            folder_of(_listing(hub, commit), REPO, "HEAD", commit, "docs")
        assert refused.value.code == NOT_FOUND

    def test_every_folder_holding_a_manifest_is_listed(self, hub: FakeHub) -> None:
        commit = hub.publish(
            REPO, "v1", {"SKILL.md": manifest("root"), "a/b/SKILL.md": manifest("b")}
        )
        assert skill_folders(_listing(hub, commit)) == ["", "a/b"]


class TestGithubReads:
    async def test_a_ref_resolves_to_its_commit(self, hub: FakeHub) -> None:
        commit = hub.publish(REPO, "v1", {"SKILL.md": manifest("root")}, ref="main")
        async with hub.client() as client:
            assert await resolve_commit(client, REPO, "main") == commit

    async def test_a_truncated_listing_is_refused(self, hub: FakeHub) -> None:
        commit = hub.publish(REPO, "v1", {"SKILL.md": manifest("root")})
        hub.truncated = True
        async with hub.client() as client:
            with pytest.raises(LibraryRefusal) as refused:
                await read_tree(client, REPO, commit)
        assert refused.value.code == TOO_LARGE

    async def test_a_spent_allowance_says_when_it_returns(self, hub: FakeHub) -> None:
        hub.rate_limited = True
        async with hub.client() as client:
            with pytest.raises(LibraryRefusal) as refused:
                await resolve_commit(client, REPO, "HEAD")
        assert refused.value.code == RATE_LIMITED
        assert refused.value.detail == {"reset_at": 1900000000}

    async def test_a_file_whose_bytes_changed_is_refused(self, hub: FakeHub) -> None:
        commit = hub.publish(REPO, "v1", {"SKILL.md": manifest("root"), "x.md": b"x"})
        hub.corrupt.add("x.md")
        folder = folder_of(_listing(hub, commit), REPO, "HEAD", commit, "")
        async with hub.client() as client:
            with pytest.raises(LibraryRefusal) as refused:
                await download(client, folder)
        assert refused.value.code == UNREACHABLE

    async def test_a_token_reaches_the_api_and_nothing_else(
        self, hub: FakeHub, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "skill_library_github_token", "ghp_secret")
        commit = hub.publish(REPO, "v1", {"SKILL.md": manifest("root")})
        async with hub.client() as client:
            await read_at_commit(
                client,
                repository=REPO,
                ref="HEAD",
                commit_sha=commit,
                path="",
                portal=None,
                audit_id=None,
            )
        sent = {s.host: s.headers.get("authorization") for s in hub.seen}
        assert sent["api.github.com"] == "Bearer ghp_secret"
        assert sent["raw.githubusercontent.com"] is None
        assert sent["add-skill.vercel.sh"] is None


class TestLocatingAPortalSkill:
    async def test_a_folder_named_like_it_wins(self, hub: FakeHub) -> None:
        commit = hub.publish(
            REPO, "v1", {"skills/pdf/SKILL.md": manifest("pdf"), "x/SKILL.md": manifest("x")}
        )
        async with hub.client() as client:
            found = await locate(
                client,
                _listing(hub, commit),
                repository=REPO,
                ref="HEAD",
                commit_sha=commit,
                skill_id="pdf",
            )
        assert found == "skills/pdf"

    async def test_otherwise_the_manifest_names_it(self, hub: FakeHub) -> None:
        commit = hub.publish(
            REPO, "v1", {"a/SKILL.md": manifest("docx-tools"), "b/SKILL.md": manifest("other")}
        )
        async with hub.client() as client:
            found = await locate(
                client,
                _listing(hub, commit),
                repository=REPO,
                ref="HEAD",
                commit_sha=commit,
                skill_id="docx-tools",
            )
        assert found == "a"

    async def test_two_manifests_of_that_name_must_be_chosen_between(self, hub: FakeHub) -> None:
        commit = hub.publish(REPO, "v1", {"a/SKILL.md": manifest("t"), "b/SKILL.md": manifest("t")})
        async with hub.client() as client:
            with pytest.raises(LibraryRefusal) as refused:
                await locate(
                    client,
                    _listing(hub, commit),
                    repository=REPO,
                    ref="HEAD",
                    commit_sha=commit,
                    skill_id="t",
                )
        assert refused.value.code == AMBIGUOUS
        assert refused.value.detail == {"folders": ["a", "b"]}


class TestTheBudgetIsCheckedBeforeAnyDownload:
    def test_too_many_files(self, hub: FakeHub, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "skills_zip_max_files", 2)
        files = {"SKILL.md": manifest("root"), "a.md": b"a", "b.md": b"b"}
        commit = hub.publish(REPO, "v1", files)
        with pytest.raises(LibraryRefusal) as refused:
            check_budget(folder_of(_listing(hub, commit), REPO, "HEAD", commit, ""))
        assert refused.value.detail == {"max_files": 2}

    def test_too_many_bytes(self, hub: FakeHub, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.core.config import settings

        monkeypatch.setattr(settings, "skills_zip_max_decompressed_kb", 1)
        commit = hub.publish(REPO, "v1", {"SKILL.md": manifest("root"), "big.md": b"x" * 2048})
        with pytest.raises(LibraryRefusal) as refused:
            check_budget(folder_of(_listing(hub, commit), REPO, "HEAD", commit, ""))
        assert refused.value.detail == {"max_kb": 1}
