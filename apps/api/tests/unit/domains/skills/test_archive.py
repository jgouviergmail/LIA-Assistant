"""The actual UI/native archive is bounded, deterministic and refuses symlink escapes."""

from io import BytesIO
from zipfile import ZipFile

import pytest

from src.core.config import settings
from src.domains.skills.archive import create_skill_archive

pytestmark = pytest.mark.unit


def test_archive_is_complete_and_stable_without_loading_instructions_into_metadata(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path))
    root = tmp_path / "owner" / "test-skill"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("Complete private instructions", encoding="utf-8")
    (root / "nested").mkdir()
    (root / "nested" / "asset.txt").write_bytes(b"resource")
    skill = {
        "name": "test-skill",
        "owner_id": "owner",
        "scope": "user",
        "source_path": str(root / "SKILL.md"),
    }
    first = create_skill_archive(skill)
    assert first == create_skill_archive(skill)
    with ZipFile(BytesIO(first)) as archive:
        assert archive.namelist() == ["test-skill/SKILL.md", "test-skill/nested/asset.txt"]
        assert archive.read("test-skill/SKILL.md") == b"Complete private instructions"


@pytest.mark.parametrize("scenario", ["outside", "too_many", "too_large", "symlink"])
def test_archive_refuses_foreign_path_symlink_and_growth(tmp_path, monkeypatch, scenario):
    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path / "users"))
    root = tmp_path / "users" / "owner" / "test-skill"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("approved", encoding="utf-8")
    skill = {
        "name": "test-skill",
        "owner_id": "owner",
        "scope": "user",
        "source_path": str(root / "SKILL.md"),
    }
    if scenario == "outside":
        skill["source_path"] = str(tmp_path / "SKILL.md")
        (tmp_path / "SKILL.md").write_text("foreign", encoding="utf-8")
    elif scenario == "too_many":
        monkeypatch.setattr(settings, "skills_zip_max_files", 1)
        (root / "extra.txt").write_text("extra", encoding="utf-8")
    elif scenario == "too_large":
        monkeypatch.setattr(settings, "skills_zip_max_decompressed_kb", 1)
        (root / "extra.txt").write_bytes(b"x" * 1025)
    else:
        try:
            (root / "link").symlink_to(tmp_path / "secret")
        except OSError:
            pytest.skip("symlink creation unavailable on host; exercise in Docker")
    with pytest.raises((ValueError, OSError)):
        create_skill_archive(skill)


def test_link_introduced_after_enumeration_is_refused_before_reading_foreign_bytes(
    tmp_path, monkeypatch
):
    from src.domains.skills import archive as module

    monkeypatch.setattr(settings, "skills_users_path", str(tmp_path))
    root = tmp_path / "owner" / "test-skill"
    root.mkdir(parents=True)
    original = root / "SKILL.md"
    original.write_text("approved", encoding="utf-8")
    foreign = tmp_path / "secret.txt"
    foreign.write_text("foreign secret", encoding="utf-8")
    skill = {
        "name": "test-skill",
        "owner_id": "owner",
        "scope": "user",
        "source_path": str(original),
    }
    resources = module._resources

    def change_after_scan(path):
        paths = resources(path)
        original.unlink()
        try:
            original.symlink_to(foreign)
        except OSError:
            pytest.skip("symlink creation unavailable; exercise in Docker")
        return paths

    monkeypatch.setattr(module, "_resources", change_after_scan)
    with pytest.raises((ValueError, OSError)):
        create_skill_archive(skill)
