"""Debian slim must retain real alternative slave pages before package postinst.

Production ARM64 builds installed the lzma/open executable alternatives while
skipping eleven associated manpage links. A later Bash/pager restoration cannot
repair that earlier xz-utils postinst. Check ordering and persistence of the
dpkg exceptions; actual signed-package contents are exercised by the build proof.
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

_MANPAGE_TARGETS = (
    "xz",
    "unxz",
    "xzcat",
    "xzmore",
    "xzless",
    "xzdiff",
    "xzcmp",
    "xzgrep",
    "xzegrep",
    "xzfgrep",
    "xdg-open",
)


def _runtime_instructions() -> list[str]:
    text = (repo_root_or_skip() / "apps/api/Dockerfile.prod").read_text(encoding="utf-8")
    joined = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    instructions = [
        line.strip() for line in joined.replace("\\\n", " ").splitlines() if line.strip()
    ]
    final_stage = max(i for i, line in enumerate(instructions) if line.startswith("FROM "))
    return instructions[final_stage:]


def _prerequisite_index(instructions: list[str]) -> int:
    return next(
        i for i, line in enumerate(instructions) if "apt-get install" in line and "xz-utils" in line
    )


@pytest.mark.parametrize("target", _MANPAGE_TARGETS)
def test_slave_manpage_payload_is_retained_before_runtime_package_postinst(target: str) -> None:
    instructions = _runtime_instructions()
    before_postinst = "\n".join(instructions[: _prerequisite_index(instructions)])
    assert (
        f"path-include /usr/share/man/man1/{target}.1.gz" in before_postinst
    ), f"{target} is a real xz-utils/xdg-utils alternative target; dpkg must retain it before postinst"


def test_alternative_payload_policy_survives_later_bash_pager_bootstrap() -> None:
    instructions = _runtime_instructions()
    early = instructions[: _prerequisite_index(instructions)]
    owners = [line for line in early if "path-include /usr/share/man/man1/xz.1.gz" in line]
    assert len(owners) == 1, "runtime alternatives need one early persistent dpkg policy"
    config = re.search(r">\s*(/etc/dpkg/dpkg\.cfg\.d/[^\s;]+)", owners[0])
    assert config, "retain the real package payload through a dpkg configuration file"
    later = instructions[_prerequisite_index(instructions) :]
    assert not any(
        re.search(rf"(?<!>)>\s*{re.escape(config.group(1))}(?:\s|;|$)", line) for line in later
    ), "the later Bash/pager bootstrap must not truncate the xz/open exceptions"


def test_runtime_prerequisite_install_does_not_probe_interactive_debconf_frontends() -> None:
    instructions = _runtime_instructions()
    install = instructions[_prerequisite_index(instructions)]
    assert (
        "DEBIAN_FRONTEND=noninteractive apt-get install" in install
    ), "the non-TTY image build must choose debconf's real noninteractive frontend explicitly"
