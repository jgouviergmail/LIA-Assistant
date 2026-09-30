"""Prove the sandbox image holds what it promises, and nothing it must not (ADR-298, ADR-327).

Runs ON THE HOST, against the image a deployment pins::

    task sandbox:libraries:check [IMAGE=lia-skill-sandbox:local]

The sandbox image carries no application code (ADR-327 lot 2), so the check
travels IN: a standard-library probe on stdin, the expectations as arguments.
The image is started the way a sandbox run starts it — no network, uid 65534,
read-only root — and the probe imports every promised library, RUNS every
declared command with its probe flag (found is not working: npm copied as a
file where a symlink had been was found and broken, 2026-09-30), and refuses
the Docker client and the application's code.
It exits 1 naming every failure, so a promise the image cannot keep reds the
build rather than a person's run.

Standard library only on the host side too: CI's docker-build job runs it with
a bare interpreter.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence

from src.domains.skills.sandbox_toolbox import (
    BOOTSTRAP_COMMANDS,
    FORBIDDEN_COMMANDS,
    FORBIDDEN_PATHS,
    SANDBOX_COMMANDS,
    SANDBOX_LIBRARIES,
)

DEFAULT_IMAGE = "lia-skill-sandbox:local"
_SEPARATOR = "--"
_TIMEOUT_SECONDS = 300

#: What runs INSIDE the image: four lists separated by ``--`` — the imports,
#: the commands as ``name=flag`` (run, exit 0 expected), the forbidden
#: commands, the forbidden paths.
PROBE = r"""
import importlib, os, shutil, subprocess, sys

sections, current = [], []
for arg in sys.argv[1:]:
    if arg == "--":
        sections.append(current)
        current = []
    else:
        current.append(arg)
sections.append(current)
imports, commands, forbidden_commands, forbidden_paths = sections

failures = []
for name in imports:
    try:
        importlib.import_module(name)
    except Exception as exc:
        failures.append(f"library {name} does not import ({type(exc).__name__})")
for item in commands:
    name, _, flag = item.partition("=")
    if shutil.which(name) is None:
        failures.append(f"command {name} is missing")
        continue
    try:
        done = subprocess.run([name, flag], capture_output=True, timeout=30)
    except Exception as exc:
        failures.append(f"command {name} fails its probe ({flag}: {type(exc).__name__})")
        continue
    if done.returncode != 0:
        failures.append(f"command {name} fails its probe ({flag}: exit {done.returncode})")
for name in forbidden_commands:
    if shutil.which(name) is not None:
        failures.append(f"command {name} must not be in the image")
for path in forbidden_paths:
    if os.path.exists(path):
        failures.append(f"path {path} must not be in the image")

print(
    f"sandbox image: {len(imports)} libraries, {len(commands)} commands, "
    f"{len(forbidden_commands) + len(forbidden_paths)} absences checked"
)
for failure in failures:
    print(f"FAILED: {failure}")
sys.exit(1 if failures else 0)
"""


def expectations() -> list[str]:
    """The probe's arguments: imports, commands with their probe, forbidden commands and paths."""
    commands = [f"{command.name}={command.probe}" for command in SANDBOX_COMMANDS] + [
        f"{name}=--version" for name in BOOTSTRAP_COMMANDS
    ]
    return [
        *(library.import_name for library in SANDBOX_LIBRARIES),
        _SEPARATOR,
        *commands,
        _SEPARATOR,
        *FORBIDDEN_COMMANDS,
        _SEPARATOR,
        *FORBIDDEN_PATHS,
    ]


def probe_argv(image: str) -> list[str]:
    """The ``docker run`` line: the sandbox's own footing, the probe on stdin."""
    return [
        "docker",
        "run",
        "--rm",
        "--interactive",
        "--network",
        "none",
        "--read-only",
        "--user",
        "65534:65534",
        "--tmpfs",
        "/tmp:size=16m,mode=1777",
        "--entrypoint",
        "python",
        image,
        "-",
        *expectations(),
    ]


def main(argv: Sequence[str]) -> int:
    """Run the probe in ``argv[1]`` (or the default image); return its exit status."""
    image = argv[1] if len(argv) > 1 and argv[1] else DEFAULT_IMAGE
    done = subprocess.run(
        probe_argv(image),
        input=PROBE,
        text=True,
        capture_output=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    sys.stdout.write(done.stdout)
    if done.returncode:
        sys.stderr.write(done.stderr)
    return done.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv))
