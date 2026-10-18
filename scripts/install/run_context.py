"""What every installer run shares (ADR-215): its context, never its flow.

The injected side-effect surface (:class:`Deps`), the files an installation
writes beside itself, the process exit codes, and the facts each flow derives
the same way — the manifest pins, the generated files' fingerprints, the
report's release line and backup location. The install and resume flows
(``__main__``) and the reconfiguration (``reconfigure``) both read them here,
so neither flow imports the other.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from scripts.install import deploy
from scripts.install.compose import locked_services
from scripts.install.manifest import (
    SANDBOX_IMAGE_SERVICE,
    hash_file,
    load_manifest,
    render_image_lock,
)
from scripts.install.model import Clock, InstallMode, IOAdapter, PublicAnswers, UrlOpener

STATE_FILE = ".install-state.json"
LOG_FILE = "install.log"
ENV_FILE = ".env"
OVERRIDE_FILE = "docker-compose.install.yml"
READY_URL = "http://127.0.0.1:8000/ready"

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_PREFLIGHT = 3
EXIT_STEP_FAILED = 4
EXIT_INTERRUPTED = 130


@dataclass
class Deps:
    """Injected side-effect surface (real in main(), fakes in tests).

    Attributes:
        root: The installation root (the extracted bundle or a git clone).
        io: Terminal input, hidden input and output.
        runner: How a command runs.
        opener: How a URL is opened (the readiness probe).
        clock: The time source of the readiness waits.
        env: Environment the run may read.
        docker_socket: The host's Docker socket, whose group a reconfiguration
            turning the sandbox on writes as ``DOCKER_GID``; ``None`` reads
            nothing (the hermetic default).
    """

    root: Path
    io: IOAdapter
    runner: deploy.Runner
    opener: UrlOpener
    clock: Clock
    env: Mapping[str, str] = field(default_factory=dict)
    docker_socket: Path | None = None


def generated_fingerprints(root: Path) -> dict[str, str]:
    """The SHA-256 of each generated file present, as the state records it.

    Args:
        root: The installation root.

    Returns:
        File name -> digest, for the ``.env`` and the override that exist.
    """
    fingerprints: dict[str, str] = {}
    for name in (ENV_FILE, OVERRIDE_FILE):
        path = root / name
        if path.is_file():
            fingerprints[name] = hash_file(path)
    return fingerprints


def prebuilt_pins(public: PublicAnswers) -> tuple[str | None, str | None]:
    """Manifest-derived pins for prebuilt mode: image lock + sandbox image.

    Args:
        public: The installation's answers (mode, manifest, sandbox choice).

    Returns:
        ``(image_lock_yaml, sandbox_image)`` — both ``None`` outside
        prebuilt mode. The lock is the ``docker-compose.images.yml`` content
        `build_invocation` already references (``render_image_lock`` had
        ZERO call sites until the v1.30.1 qualification: every prebuilt
        install died on the missing Compose layer). The sandbox image is
        the manifest's own sandbox reference (ADR-327 lot 2) — the base
        file's ``lia-skill-sandbox:local`` fallback is a tag a prebuilt host
        never builds.
    """
    if public.mode is not InstallMode.PREBUILT or public.manifest_path is None:
        return None, None
    manifest = load_manifest(public.manifest_path, required_qualification="passed")
    lock = render_image_lock(manifest, locked_services(public))
    sandbox_image: str | None = None
    if public.skill_sandbox:
        # `load_manifest` validated it: every app image has an entry.
        sandbox_image = next(
            image.reference
            for image in manifest.images
            if image.service == SANDBOX_IMAGE_SERVICE
        )
    return lock, sandbox_image


def backup_dir(deps: Deps) -> Path:
    """Where the database backups land: beside the installation, never inside it."""
    return deps.root.parent / "lia-data" / "postgres-backups"


def release_summary(public: PublicAnswers) -> str:
    """How the report names the release: the manifest a prebuilt install came from."""
    if public.mode is InstallMode.PREBUILT and public.manifest_path is not None:
        return f"prebuilt ({public.manifest_path.name})"
    return "local build"
