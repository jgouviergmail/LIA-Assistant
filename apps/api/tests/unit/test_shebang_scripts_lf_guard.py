"""A script the host executes is checked out with LF, whatever its name.

Measured on production, 2026-09-24 → 27. The daily operations report
(``infrastructure/logwatch``) went out as an 878-byte error mail, four mornings
in a row, instead of its 100-400 kB report. Deploying from a fresh worktree on
Windows (``core.autocrlf=true``) had written its three extensionless scripts —
the cron entry and two service filters — with CRLF: they had no ``eol=lf``
attribute, because the ``*.sh`` rule cannot name a file without an extension,
and bash refused them from the first line (``$'\\r': command not found``,
``set: pipefail: invalid option name``).

Two readers had keyed on the NAME: ``.gitattributes`` (``*.sh``) and the
deployment's own LF normalisation (``-Filter *.sh``). The CONTENT says what a
file is: this guard reads every tracked file that starts with a shebang and
refuses one whose attribute does not force LF — the attribute, not a working
copy, decides what a fresh checkout writes.
"""

from __future__ import annotations

import subprocess

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()

#: The scripts whose CRLF copies killed the report (the regression's names).
LOGWATCH_SCRIPTS = (
    "infrastructure/logwatch/cron/00logwatch",
    "infrastructure/logwatch/scripts/services/cloudflared",
    "infrastructure/logwatch/scripts/services/docker-lia",
)


def _tracked_shebang_scripts() -> list[str]:
    """Every git-tracked file whose first two bytes are ``#!``."""
    listing = subprocess.run(
        ["git", "ls-files", "-z"], capture_output=True, check=True, cwd=REPO_ROOT
    ).stdout.split(b"\0")
    scripts: list[str] = []
    for raw in listing:
        if not raw:
            continue
        relative = raw.decode("utf-8")
        path = REPO_ROOT / relative
        if not path.is_file():  # tracked but deleted in the working tree
            continue
        with path.open("rb") as handle:
            if handle.read(2) == b"#!":
                scripts.append(relative)
    return scripts


def _eol_attributes(paths: list[str]) -> dict[str, str]:
    """The ``eol`` attribute git resolves for each path (``unspecified`` when none).

    NUL-separated bytes both ways (``-z``): in text mode on Windows, ``subprocess``
    writes ``\\r\\n`` for ``\\n``, git then looks up paths ending in a carriage
    return, and every one of them reads as ``unspecified``.
    """
    answer = subprocess.run(
        ["git", "check-attr", "-z", "--stdin", "eol"],
        input=b"\0".join(path.encode("utf-8") for path in paths),
        capture_output=True,
        check=True,
        cwd=REPO_ROOT,
    ).stdout.split(b"\0")
    # Records of three fields: path, attribute, value.
    return {
        answer[index].decode("utf-8"): answer[index + 2].decode("utf-8")
        for index in range(0, len(answer) - 2, 3)
    }


class TestEveryScriptIsCheckedOutWithLF:
    def test_every_tracked_shebang_script_forces_lf(self) -> None:
        scripts = _tracked_shebang_scripts()
        assert len(scripts) > 50, "the scan found almost no script — the guard has lost its subject"

        resolved = _eol_attributes(scripts)
        not_lf = sorted(path for path in scripts if resolved.get(path) != "lf")

        assert not not_lf, (
            f"scripts a fresh Windows checkout would write with CRLF: {not_lf}. "
            "Give each an explicit `text eol=lf` rule in .gitattributes — a `*.sh` "
            "pattern cannot name a file without an extension, and bash refuses a "
            "CRLF script from its first line."
        )

    def test_the_logwatch_scripts_that_broke_the_report_are_covered(self) -> None:
        resolved = _eol_attributes(list(LOGWATCH_SCRIPTS))

        assert {path: resolved.get(path) for path in LOGWATCH_SCRIPTS} == dict.fromkeys(
            LOGWATCH_SCRIPTS, "lf"
        )
