"""Unit tests for plugin zip detection and staging (ADR-225).

The staging layer mirrors the skills pipeline S3 hardening (zip bomb, member
count, zip-slip) with two plugin-specific behaviors:

- the package root is located by ``plugin.json`` (§5.1) — at the archive root
  or under a single wrapper directory — and re-anchored on extraction;
- prefix matching is POSIX-safe by construction: the wrapped-zip cases ARE
  the regression tests for the ``Path.parent`` backslash bug found in the
  skills ``_stage_zip`` during the ADR-225 analysis (empty extraction on
  Windows hosts).
"""

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.plugins.staging import stage_plugin_zip, zip_contains_plugin_manifest

pytestmark = pytest.mark.unit

_SETTINGS = SimpleNamespace(plugins_zip_max_files=50, plugins_zip_max_decompressed_kb=1024)

_MANIFEST = b'{"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", "name": "my-plugin"}'
_SKILL_MD = b"---\nname: alpha\ndescription: First skill.\n---\nBody\n"


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arc, data in members.items():
            zf.writestr(arc, data)
    return buf.getvalue()


class TestDetection:
    def test_manifest_at_archive_root_is_a_plugin(self) -> None:
        content = _zip_bytes({"plugin.json": _MANIFEST, "mcp.json": b"{}"})

        assert zip_contains_plugin_manifest(content) is True

    def test_manifest_under_single_wrapper_dir_is_a_plugin(self) -> None:
        content = _zip_bytes({"my-plugin/plugin.json": _MANIFEST})

        assert zip_contains_plugin_manifest(content) is True

    def test_skill_only_zip_is_not_a_plugin(self) -> None:
        content = _zip_bytes({"alpha/SKILL.md": _SKILL_MD})

        assert zip_contains_plugin_manifest(content) is False

    def test_deeply_nested_manifest_is_not_a_plugin_root(self) -> None:
        content = _zip_bytes({"a/b/plugin.json": _MANIFEST})

        assert zip_contains_plugin_manifest(content) is False

    def test_invalid_zip_bytes_are_not_a_plugin(self) -> None:
        assert zip_contains_plugin_manifest(b"not a zip at all") is False


class TestStaging:
    def test_flat_zip_extracts_the_whole_tree(self, tmp_path: Path) -> None:
        content = _zip_bytes(
            {
                "plugin.json": _MANIFEST,
                "mcp.json": b"{}",
                "skills/alpha/SKILL.md": _SKILL_MD,
                "skills/alpha/references/notes.md": b"# notes",
            }
        )

        root = stage_plugin_zip(content, tmp_path, _SETTINGS)

        assert (root / "plugin.json").read_bytes() == _MANIFEST
        assert (root / "mcp.json").is_file()
        assert (root / "skills" / "alpha" / "SKILL.md").read_bytes() == _SKILL_MD
        assert (root / "skills" / "alpha" / "references" / "notes.md").is_file()

    def test_wrapped_zip_is_reanchored_at_the_plugin_root(self, tmp_path: Path) -> None:
        # Regression test for the POSIX-prefix bug: on Windows a Path.parent
        # derived prefix (backslashes) never matches zip member names.
        content = _zip_bytes(
            {
                "my-plugin/plugin.json": _MANIFEST,
                "my-plugin/skills/alpha/SKILL.md": _SKILL_MD,
            }
        )

        root = stage_plugin_zip(content, tmp_path, _SETTINGS)

        assert (root / "plugin.json").read_bytes() == _MANIFEST
        assert (root / "skills" / "alpha" / "SKILL.md").read_bytes() == _SKILL_MD
        assert not (root / "my-plugin").exists()

    def test_members_outside_the_wrapper_root_are_dropped(self, tmp_path: Path) -> None:
        content = _zip_bytes(
            {
                "my-plugin/plugin.json": _MANIFEST,
                "rogue/escape.txt": b"outside the plugin root",
            }
        )

        root = stage_plugin_zip(content, tmp_path, _SETTINGS)

        assert (root / "plugin.json").is_file()
        assert not (root / "escape.txt").exists()
        assert not (root.parent / "rogue").exists()

    def test_zip_slip_member_is_rejected(self, tmp_path: Path) -> None:
        content = _zip_bytes({"plugin.json": _MANIFEST, "../evil.txt": b"boom"})

        with pytest.raises(BaseAPIException):
            stage_plugin_zip(content, tmp_path, _SETTINGS)

    def test_member_count_bomb_is_rejected(self, tmp_path: Path) -> None:
        members: dict[str, bytes] = {"plugin.json": _MANIFEST}
        members.update({f"f{i}.txt": b"x" for i in range(_SETTINGS.plugins_zip_max_files + 1)})

        with pytest.raises(BaseAPIException):
            stage_plugin_zip(_zip_bytes(members), tmp_path, _SETTINGS)

    def test_decompressed_size_bomb_is_rejected(self, tmp_path: Path) -> None:
        big = b"0" * (_SETTINGS.plugins_zip_max_decompressed_kb * 1024 + 1)

        with pytest.raises(BaseAPIException):
            stage_plugin_zip(
                _zip_bytes({"plugin.json": _MANIFEST, "big.bin": big}), tmp_path, _SETTINGS
            )

    def test_missing_manifest_is_rejected(self, tmp_path: Path) -> None:
        content = _zip_bytes({"skills/alpha/SKILL.md": _SKILL_MD})

        with pytest.raises(BaseAPIException):
            stage_plugin_zip(content, tmp_path, _SETTINGS)

    def test_invalid_zip_bytes_are_rejected(self, tmp_path: Path) -> None:
        with pytest.raises(BaseAPIException):
            stage_plugin_zip(b"not a zip", tmp_path, _SETTINGS)


def test_settings_thresholds_are_read_not_hardcoded(tmp_path: Path) -> None:
    """The guards must follow the injected settings, not module constants."""
    tight: Any = SimpleNamespace(plugins_zip_max_files=2, plugins_zip_max_decompressed_kb=1024)
    content = _zip_bytes({"plugin.json": _MANIFEST, "a.txt": b"a", "b.txt": b"b"})

    with pytest.raises(BaseAPIException):
        stage_plugin_zip(content, tmp_path, tight)
