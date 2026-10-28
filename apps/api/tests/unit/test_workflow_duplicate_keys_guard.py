"""Guard: no GitHub Actions YAML file repeats a key inside one mapping.

Why
---
GitHub's workflow parser rejects a mapping that defines a key twice ("is
already defined") and the WHOLE file becomes an invalid workflow: none of its
jobs run and its required checks never report. PyYAML keeps the last value in
silence, so every other guard that reads workflows with ``yaml.safe_load``
accepts the file. Measured 2026-10-28: a merge left two ``TEST_REDIS_URL``
keys in the integration job of ``ci.yml`` while every local gate stayed green.
The scan reads the composed node graph, where both keys still exist.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
GITHUB_DIR = REPO_ROOT / ".github"

pytestmark = pytest.mark.unit

#: Anti-vacuity floor: workflows plus the composite action (2026-10-28).
MIN_EXPECTED_FILES = 9
#: A merge key (`<<`) imports defaults that explicit keys may then override.
MERGE_TAG = "tag:yaml.org,2002:merge"


def _duplicate_keys(node: yaml.Node | None) -> Iterator[str]:
    """Yield ``"key (line N)"`` for every key a mapping of ``node`` repeats."""
    if isinstance(node, yaml.MappingNode):
        seen: set[tuple[str, str]] = set()
        for key_node, value_node in node.value:
            if isinstance(key_node, yaml.ScalarNode) and key_node.tag != MERGE_TAG:
                identity = (key_node.tag, key_node.value)
                if identity in seen:
                    yield f"{key_node.value} (line {key_node.start_mark.line + 1})"
                seen.add(identity)
            yield from _duplicate_keys(value_node)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            yield from _duplicate_keys(item)


def _github_yaml_files() -> list[Path]:
    return sorted(p for p in GITHUB_DIR.rglob("*") if p.suffix in {".yml", ".yaml"})


def test_the_scan_sees_the_workflows() -> None:
    assert len(_github_yaml_files()) >= MIN_EXPECTED_FILES


@pytest.mark.parametrize(
    "path", _github_yaml_files(), ids=lambda p: p.relative_to(GITHUB_DIR).as_posix()
)
def test_no_mapping_defines_a_key_twice(path: Path) -> None:
    tree = yaml.compose(path.read_text(encoding="utf-8"), Loader=yaml.SafeLoader)
    assert list(_duplicate_keys(tree)) == []


def test_the_scan_finds_a_repeated_key_and_allows_merge_overrides() -> None:
    repeated = yaml.compose("env:\n  A: 1\n  A: 2\n", Loader=yaml.SafeLoader)
    assert list(_duplicate_keys(repeated)) == ["A (line 3)"]
    merged = yaml.compose("base: &b {a: 1}\nuse:\n  <<: *b\n  a: 2\n", Loader=yaml.SafeLoader)
    assert list(_duplicate_keys(merged)) == []
