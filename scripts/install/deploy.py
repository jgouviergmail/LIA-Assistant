"""Deploy orchestration primitives (B08/B12/B14).

Every function receives an injected ``Runner`` so the full argv surface is
provable without a Docker daemon. Secrets travel exclusively through runner
stdin (one JSON document to the in-container bootstrap); every failure is a
``StepFailed`` whose message carries a stable code plus the exact resume
command and NEVER a secret.

The exact order is owned by ``__main__``:

    capture rollback -> acquire -> validate Settings -> start (seeds armed)
    -> /ready -> disarm seeds -> stdin bootstrap -> recreate API --no-build
    -> second /ready -> backend verifier -> record -> report
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from scripts.install.compose import up_suffix
from scripts.install.model import (
    Clock,
    ComposeInvocation,
    InstallMode,
    PublicAnswers,
    SecretAnswers,
    UrlOpener,
)

if TYPE_CHECKING:
    from scripts.install.state import InstallState

RESUME_HINT = "./install.sh --resume"

_READY_POLL_INTERVAL_S = 3.0


@dataclass(frozen=True)
class CommandResult:
    """One executed command's outcome."""

    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    """Injected command executor (records argv in tests)."""

    def __call__(
        self,
        argv: Sequence[str],
        *,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult: ...


#: Longest stderr tail carried on a failure (compose traces can be huge).
_DETAIL_TAIL_CHARS = 4_000


def _detail_tail(result: "CommandResult") -> str:
    """The command's error output, bounded and collapsed to one line.

    The tail (not the head): compose prints the actual cause last. Newlines
    become ``" | "`` because ``install.log`` is one redacted line per event.
    """
    raw = (result.stderr or result.stdout or "").strip()
    return " | ".join(raw[-_DETAIL_TAIL_CHARS:].splitlines())


class StepFailed(RuntimeError):
    """A deploy step failed with a stable, non-secret code.

    ``detail`` carries the failing command's bounded stderr tail for the
    REDACTING install log only — ``str(exc)`` stays code + resume hint,
    because the console output is not redacted (measured on the v1.30.1
    qualification: ``acquire_failed`` alone burned a full disposable matrix
    run to learn nothing).
    """

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code} — resume with {RESUME_HINT}")


def _run_or_fail(
    runner: Runner,
    argv: Sequence[str],
    code: str,
    *,
    stdin: str | None = None,
) -> CommandResult:
    result = runner(argv, stdin=stdin)
    if result.returncode != 0:
        raise StepFailed(code, detail=_detail_tail(result))
    return result


def acquire(invocation: ComposeInvocation, runner: Runner) -> None:
    """Obtain the app images: local builds, prebuilt pulls (never builds)."""
    verb = "pull" if invocation.mode is InstallMode.PREBUILT else "build"
    _run_or_fail(
        runner, invocation.prefix() + [verb, "api", "web"], "acquire_failed"
    )


def validate_settings(invocation: ComposeInvocation, runner: Runner) -> None:
    """Run the backend Settings validator inside a one-shot API container."""
    argv = invocation.prefix() + [
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "",
        "api",
        "python",
        "-m",
        "scripts.validate_settings",
    ]
    _run_or_fail(runner, argv, "settings_invalid")


def start(
    invocation: ComposeInvocation, runner: Runner, *, seed_intent: bool
) -> None:
    """Start the stack. ``seed_intent`` documents whether the generated
    override armed ``APPLY_SEEDS`` for this start (the file owns the value).
    """
    del seed_intent  # carried by the generated override, logged by the caller
    _run_or_fail(runner, invocation.prefix() + up_suffix(invocation), "start_failed")


def wait_ready(
    url: str, opener: UrlOpener, clock: Clock, timeout_s: int = 300
) -> None:
    """Poll ``url`` until HTTP 200 or raise ``readiness_timeout``."""
    deadline = clock.monotonic() + timeout_s
    while True:
        request = urllib.request.Request(url, method="GET")
        try:
            with opener(request, timeout=10.0) as response:
                if int(getattr(response, "status", 0)) == 200:
                    return
        except Exception:  # noqa: BLE001 - every failure is just "not ready yet"
            pass
        if clock.monotonic() >= deadline:
            raise StepFailed("readiness_timeout")
        clock.sleep(_READY_POLL_INTERVAL_S)


def run_bootstrap(
    invocation: ComposeInvocation,
    public: PublicAnswers,
    secrets: SecretAnswers,
    runner: Runner,
) -> None:
    """Feed the single JSON secrets document to the in-container bootstrap.

    Exit 3 (``bootstrapped_publication_failed``) is NOT fatal: the forced
    API recreation is the real worker barrier, publication is a hot-update
    nicety. Exit 2 is a payload contract violation; anything else fails.
    """
    payload = json.dumps(
        {
            "admin": {
                "email": public.admin_email,
                "password": secrets.admin_password,
                "full_name": public.admin_name,
            },
            "provider_keys": dict(secrets.provider_keys),
        }
    )
    argv = invocation.prefix() + [
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--entrypoint",
        "",
        "api",
        "python",
        "-m",
        "scripts.data.bootstrap_install",
    ]
    result = runner(argv, stdin=payload)
    if result.returncode == 2:
        raise StepFailed("bootstrap_input_error")
    if result.returncode not in (0, 3):
        raise StepFailed("bootstrap_failed")


def restart_api_without_build(
    invocation: ComposeInvocation, runner: Runner
) -> None:
    """Force-recreate the API so every worker reloads the committed keys."""
    argv = invocation.prefix() + [
        "up",
        "-d",
        "--no-deps",
        "--force-recreate",
        "--no-build",
        "api",
    ]
    _run_or_fail(runner, argv, "api_recreate_failed")


def reconfigure_existing(
    *,
    current: "InstallState",
    candidate_public: PublicAnswers,
    candidate_files: Mapping[Path, Path],
    invocation: ComposeInvocation,
    runner: Runner,
) -> None:
    """Non-destructive reconfiguration of a recorded installation.

    Allowed changes are the seven non-secret routing/capability fields
    (exposure, server host, web/API domains, Caddy email, observability,
    skill sandbox). Mode, release identity, and admin identity are
    immutable; generated secrets are preserved by construction (this path
    renders no ``.env`` secrets); seeds and bootstrap are NEVER invoked.

    Sequence: verify identity -> static Compose validation of the candidate
    files -> back up -> atomically replace -> ``up -d --no-build
    --remove-orphans`` -> on failure restore the previous files and re-raise
    as ``reconfigure_failed`` (the caller re-checks readiness).
    """
    previous = current.public_answers
    if (
        candidate_public.mode is not previous.mode
        or candidate_public.admin_email != previous.admin_email
        or candidate_public.admin_name != previous.admin_name
        or candidate_public.manifest_path != previous.manifest_path
    ):
        raise StepFailed("reconfigure_identity_changed")

    # Static validation on the CANDIDATE files before anything is replaced.
    candidate_argv = ["docker", "compose"]
    if invocation.project_name:
        candidate_argv += ["-p", invocation.project_name]
    for file in invocation.files:
        candidate_argv += ["-f", str(candidate_files.get(file, file))]
    _run_or_fail(
        runner, candidate_argv + ["config", "--quiet"], "reconfigure_invalid"
    )

    backups: dict[Path, Path] = {}
    for target, candidate in candidate_files.items():
        if target.exists():
            backup = target.with_name(f"{target.name}.backup.{int(time.time())}")
            backup.write_bytes(target.read_bytes())
            backups[target] = backup
        target.write_bytes(candidate.read_bytes())

    result = runner(
        invocation.prefix() + ["up", "-d", "--no-build", "--remove-orphans"]
    )
    if result.returncode != 0:
        for target, backup in backups.items():
            target.write_bytes(backup.read_bytes())
        runner(invocation.prefix() + ["up", "-d", "--no-build", "--remove-orphans"])
        raise StepFailed("reconfigure_failed")


def run_verifier(
    invocation: ComposeInvocation,
    *,
    admin_email: str,
    seed_bundle_sha256: str,
    runner: Runner,
) -> None:
    """Run the read-only installation verifier (exit 0 = every check green)."""
    argv = invocation.prefix() + [
        "run",
        "--rm",
        "--no-deps",
        "-T",
        "--entrypoint",
        "",
        "api",
        "python",
        "-m",
        "scripts.data.verify_installation",
        "--admin-email",
        admin_email,
        "--seed-bundle-sha256",
        seed_bundle_sha256,
    ]
    _run_or_fail(runner, argv, "verify_failed")
