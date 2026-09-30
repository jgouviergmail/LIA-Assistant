"""The sandbox image check (ADR-327 lot 2): its probe, and the footing it starts from.

The probe runs inside an image with no application code, so it is a
standard-library program; here it runs under the local interpreter against
expectations whose verdict is known. The ``docker run`` line must start the
image as a sandbox run does — otherwise a library readable by root only, or a
command that needs the network, would pass here and fail in a person's run.

A command is RUN, never merely found: measured 2026-09-30, ``npm`` and ``npx``
copied out of the Node stage were files where symlinks had been (``COPY``
dereferences them), so ``require('../lib/cli.js')`` failed on every call while
``shutil.which`` found both — a promise the image kept in name only.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.sandbox_egress.libraries_check import PROBE, expectations, probe_argv
from src.domains.skills.sandbox_toolbox import SANDBOX_COMMANDS, SANDBOX_LIBRARIES

pytestmark = pytest.mark.unit


def _probe(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-", *args],
        input=PROBE,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def test_a_kept_promise_passes(tmp_path: Path) -> None:
    done = _probe(
        "json",
        "--",
        f"{sys.executable}=--version",
        "--",
        "lia-no-such-command",
        "--",
        str(tmp_path / "absent"),
    )
    assert done.returncode == 0, done.stdout


def test_every_broken_promise_is_named(tmp_path: Path) -> None:
    present = tmp_path / "app"
    present.mkdir()
    done = _probe(
        "json",
        "lia_no_such_module",
        "--",
        "lia-no-such-command=--version",
        f"{sys.executable}=--lia-no-such-flag",
        "--",
        "--",
        str(present),
    )
    assert done.returncode == 1
    assert "library lia_no_such_module does not import" in done.stdout
    assert "command lia-no-such-command is missing" in done.stdout
    # Present, and failing when run: named with the probe that failed.
    assert f"command {sys.executable} fails its probe (--lia-no-such-flag" in done.stdout
    assert f"path {present} must not be in the image" in done.stdout


def test_the_expectations_carry_every_declared_promise() -> None:
    args = expectations()
    imports, commands, forbidden_commands, forbidden_paths = _split(args)
    assert imports == [library.import_name for library in SANDBOX_LIBRARIES]
    # Every command travels with the probe that runs it: ``name=flag``.
    probes = dict(item.split("=", 1) for item in commands)
    assert {command.name: command.probe for command in SANDBOX_COMMANDS}.items() <= probes.items()
    assert {"tar", "timeout", "truncate"} <= set(probes)
    assert all(flag for flag in probes.values())
    assert forbidden_commands == ["docker"] and forbidden_paths == ["/app"]


def test_the_image_starts_on_the_sandboxs_footing() -> None:
    argv = probe_argv("lia-skill-sandbox:local")
    joined = " ".join(argv)
    for flag in ("--network none", "--read-only", "--user 65534:65534"):
        assert flag in joined
    assert argv[argv.index("--entrypoint") + 1 : argv.index("--entrypoint") + 4] == [
        "python",
        "lia-skill-sandbox:local",
        "-",
    ]


def _split(args: list[str]) -> list[list[str]]:
    sections: list[list[str]] = [[]]
    for arg in args:
        if arg == "--":
            sections.append([])
        else:
            sections[-1].append(arg)
    return sections
