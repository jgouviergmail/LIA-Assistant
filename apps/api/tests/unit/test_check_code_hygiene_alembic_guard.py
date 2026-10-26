"""The Alembic single-head hygiene check fails on what alembic refuses.

Measured 2026-09-03: a migration reused an existing revision id. Alembic
raised ``CycleDetected`` at upgrade time, while this check — which keyed
revisions by id, so the duplicate collapsed and every revision became
somebody's parent — reported ``no revisions found`` as a PASS. A guard that
passes on the broken state is worse than no guard.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

TOOL_PATH = repo_root_or_skip() / "scripts" / "audit" / "check_code_hygiene.py"


def _load_tool():  # type: ignore[no-untyped-def]
    if not TOOL_PATH.exists():
        pytest.skip("guard needs the full repository checkout (scripts/audit).")
    spec = importlib.util.spec_from_file_location("check_code_hygiene", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their module through sys.modules at class creation.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(versions: Path, name: str, revision: str, down: str | None) -> None:
    down_line = f'down_revision: str | None = "{down}"' if down else "down_revision = None"
    (versions / f"{name}.py").write_text(
        f'"""m"""\nrevision: str = "{revision}"\n{down_line}\n', encoding="utf-8"
    )


def test_a_linear_chain_has_one_head(tmp_path: Path) -> None:
    _write(tmp_path, "0001_a", "aaa", None)
    _write(tmp_path, "0002_b", "bbb", "aaa")
    result = _load_tool().check_alembic_single_head(tmp_path)
    assert result.failed is False
    assert result.details == ["single head: bbb (0002_b.py)"]


def test_two_heads_fail(tmp_path: Path) -> None:
    _write(tmp_path, "0001_a", "aaa", None)
    _write(tmp_path, "0002_b", "bbb", "aaa")
    _write(tmp_path, "0003_c", "ccc", "aaa")
    result = _load_tool().check_alembic_single_head(tmp_path)
    assert result.failed is True
    assert len(result.details) == 2


def test_a_reused_revision_id_fails_instead_of_passing_as_empty(tmp_path: Path) -> None:
    _write(tmp_path, "0001_a", "aaa", None)
    _write(tmp_path, "0002_b", "bbb", "aaa")
    _write(tmp_path, "0003_c", "ccc", "bbb")
    # The reuse: a new file claims "bbb" again, chained after "ccc" — alembic
    # sees a cycle; before the fix this check saw zero heads and passed.
    _write(tmp_path, "0004_d", "bbb", "ccc")
    result = _load_tool().check_alembic_single_head(tmp_path)
    assert result.failed is True
    assert result.details == ["duplicate revision id: bbb (0002_b.py, 0004_d.py)"]


def test_zero_heads_is_a_failure(tmp_path: Path) -> None:
    result = _load_tool().check_alembic_single_head(tmp_path)
    assert result.failed is True
    assert "no head" in result.details[0]


@pytest.mark.parametrize("annotated", [False, True])
def test_a_merge_revision_consumes_both_parents(tmp_path: Path, annotated: bool) -> None:
    _write(tmp_path, "0001_a", "aaa", None)
    _write(tmp_path, "0002_b", "bbb", "aaa")
    _write(tmp_path, "0003_c", "ccc", "aaa")
    annotation = ": tuple[str, str]" if annotated else ""
    (tmp_path / "0004_merge.py").write_text(
        'revision: str = "ddd"\n' f'down_revision{annotation} = (\n    "bbb",\n    "ccc",\n)\n',
        encoding="utf-8",
    )
    result = _load_tool().check_alembic_single_head(tmp_path)
    assert result.failed is False
    assert result.details == ["single head: ddd (0004_merge.py)"]


def test_nonliteral_migration_links_fail_without_executing_source(tmp_path: Path) -> None:
    _write(tmp_path, "0001_a", "aaa", None)
    (tmp_path / "0002_bad.py").write_text(
        'revision = "bbb"\ndown_revision = str("aaa")\n'
        'raise AssertionError("Never import a migration during lint")\n',
        encoding="utf-8",
    )
    result = _load_tool().check_alembic_single_head(tmp_path)
    assert result.failed is True
    assert "invalid migration metadata" in result.details[0]
