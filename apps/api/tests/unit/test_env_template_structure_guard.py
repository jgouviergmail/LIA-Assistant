"""CI guard: every env template is laid out by section, with an exact table of contents.

The templates grew by appending: four features (the speaking avatar, the application
tools, the SMS archive, the proactive discussions) had ended up inside the « DEV/TEST
TOOLING » section, and the demonstrator's templates had neither numbers nor an index
(reorganised 2026-10-21, owner request). A table of contents that disagrees with the
sections it lists sends a reader to the wrong place, so it is held equal here. And
every proactive-discussion setting is declared wherever that section exists: the
owner asked for each bound to be adjustable from the file.
"""

import re

import pytest

from src.core.config.proactive_discussions import ProactiveDiscussionSettings
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
TEMPLATES = [
    ".env.example",
    ".env.prod.example",
    ".env.min.prod.example",
    ".env.demo-instance.example",
    ".env.demo-instance.prod.example",
    "apps/api/.env.test",
]
# The full templates declare every discussion setting; the minimal one keeps the
# switch, the cadence and the three ceilings paid production needs.
COMPLETE_DISCUSSIONS = [
    ".env.example",
    ".env.prod.example",
    ".env.demo-instance.example",
    ".env.demo-instance.prod.example",
]
_ENTRY = re.compile(r"^# \[(\d+)\] (.+?)\s*$")
_KEY = re.compile(r"^([A-Z][A-Z0-9_]*)=", re.MULTILINE)


def _lines(name: str) -> list[str]:
    path = REPO_ROOT / name
    if not path.exists():
        pytest.skip(f"{name} not present in this checkout")
    return path.read_text(encoding="utf-8").splitlines()


def _is_rule(line: str) -> bool:
    return line.startswith("# ==") and set(line[2:].strip()) == {"="}


def _toc_and_sections(lines: list[str]) -> tuple[list[str], list[str]]:
    toc: list[str] = []
    sections: list[str] = []
    for index, line in enumerate(lines):
        if not _ENTRY.match(line):
            continue
        is_header = index > 0 and _is_rule(lines[index - 1])
        (sections if is_header else toc).append(line)
    return toc, sections


@pytest.mark.parametrize("name", TEMPLATES)
def test_the_table_of_contents_lists_exactly_the_sections(name: str) -> None:
    toc, sections = _toc_and_sections(_lines(name))
    assert sections, f"{name}: no numbered section"
    assert toc == sections, f"{name}: the table of contents disagrees with the sections"
    numbers = [int(_ENTRY.match(line).group(1)) for line in sections]
    assert numbers == sorted(set(numbers)), f"{name}: section numbers must strictly increase"


@pytest.mark.parametrize("name", TEMPLATES)
def test_no_key_is_declared_twice(name: str) -> None:
    keys = _KEY.findall("\n".join(_lines(name)))
    duplicates = sorted({key for key in keys if keys.count(key) > 1})
    assert duplicates == [], f"{name}: declared twice: {duplicates}"


@pytest.mark.parametrize("name", COMPLETE_DISCUSSIONS)
def test_every_proactive_discussion_setting_is_declared(name: str) -> None:
    declared = set(_KEY.findall("\n".join(_lines(name))))
    expected = {field.upper() for field in ProactiveDiscussionSettings.model_fields}
    assert sorted(expected - declared) == []
