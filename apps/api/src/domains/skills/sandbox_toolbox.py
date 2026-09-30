"""What the skill sandbox image holds — declared once, proven in the image (ADR-327 lot 2).

Every sandbox run — a skill's script, a skill's command, the agent's ephemeral
Python (ADR-249) — starts from ``SKILLS_SCRIPT_SANDBOX_IMAGE``, and the model is
TOLD what it may use there. That is a promise, so it lives in one declaration:

- ``apps/api/Dockerfile.sandbox`` installs the Debian package of every command
  and ``requirements-sandbox.txt`` pins every library DIRECTLY (both guarded);
- ``task sandbox:libraries:check`` runs the built image as the sandbox does —
  no network, uid 65534, read-only — and imports every library, RUNS every
  command with its probe flag (a command found but broken is no promise kept:
  measured 2026-09-30 on npm copied as a file where a symlink had been), and
  refuses what the image must NOT hold: the Docker client (the road to the
  host) and the application's code.

Standard library only: the CI job that checks the image imports this module
with a bare interpreter, before any dependency is installed.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domains.agents.python_sandbox.libraries import PYTHON_SANDBOX_LIBRARIES, SandboxLibrary

__all__ = [
    "BOOTSTRAP_COMMANDS",
    "FORBIDDEN_COMMANDS",
    "FORBIDDEN_PATHS",
    "SANDBOX_COMMANDS",
    "SANDBOX_LIBRARIES",
    "SKILL_LIBRARIES",
    "SandboxCommand",
    "render_toolbox",
]


@dataclass(frozen=True, slots=True)
class SandboxCommand:
    """One command a skill may run.

    Attributes:
        name: What a command line types.
        package: The Debian package that brings it, ``""`` when the image builds
            it another way — the base image, or a stage pinned by digest (Node).
        use: One word or two on what it is for.
        probe: The flag the image check runs it with; exit 0 keeps the promise.
    """

    name: str
    package: str
    use: str
    probe: str = "--version"


#: What a skill's command may call — the tools the portal's skills name most.
#: The package managers, git and curl only reach anything on a networked run
#: (ADR-327 lot 3), through the egress proxy whose CA each one is pointed at.
#: Node comes from the official image's pinned stage (a test holds the major
#: named here equal to the Dockerfile's), npm and npx with it.
SANDBOX_COMMANDS: tuple[SandboxCommand, ...] = (
    SandboxCommand("bash", "", "shell"),
    SandboxCommand("python3", "", "Python 3.14"),
    SandboxCommand("pip", "", "Python packages"),
    SandboxCommand("node", "", "Node.js 24"),
    SandboxCommand("npm", "", "Node packages"),
    SandboxCommand("npx", "", "Node package runner"),
    SandboxCommand("git", "git", "repositories"),
    SandboxCommand("curl", "curl", "HTTP requests"),
    SandboxCommand("jq", "jq", "JSON"),
    SandboxCommand("zip", "zip", "archives", probe="-v"),
    SandboxCommand("unzip", "unzip", "archives", probe="-v"),
    SandboxCommand("pdftotext", "poppler-utils", "PDF text", probe="-v"),
    SandboxCommand("pdftoppm", "poppler-utils", "PDF pages as images", probe="-v"),
    SandboxCommand("pdfinfo", "poppler-utils", "PDF metadata", probe="-v"),
)

#: What the command bootstrap itself runs: never promised, always checked.
BOOTSTRAP_COMMANDS: tuple[str, ...] = ("tar", "timeout", "truncate", "mkdir")

#: What the image must NOT hold: the Docker client is the road to the host.
FORBIDDEN_COMMANDS: tuple[str, ...] = ("docker",)

#: Nor the application's code (and the secrets a mistake could bake into it).
FORBIDDEN_PATHS: tuple[str, ...] = ("/app",)

#: Libraries skills rely on beyond what the ephemeral Python promises: the
#: system QR skill (``segno``), and images and slides for the skills that
#: write documents. Not promised to the ephemeral Python, whose run hands back
#: text only.
SKILL_LIBRARIES: tuple[SandboxLibrary, ...] = (
    SandboxLibrary("segno", "segno", "QR codes", "Documents"),
    SandboxLibrary("PIL", "Pillow", "images", "Documents"),
    SandboxLibrary("pptx", "python-pptx", "PPTX read/write", "Documents"),
)

#: Every library the image holds for a sandbox run.
SANDBOX_LIBRARIES: tuple[SandboxLibrary, ...] = PYTHON_SANDBOX_LIBRARIES + SKILL_LIBRARIES


def render_toolbox() -> str:
    """What a skill runner is told the sandbox holds, in declaration order."""
    commands = ", ".join(command.name for command in SANDBOX_COMMANDS)
    libraries = ", ".join(library.import_name for library in SANDBOX_LIBRARIES)
    return f"Commands: {commands}.\nPython libraries: {libraries}."
