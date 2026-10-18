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

import contextlib
import json
import signal
import urllib.request
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any, Protocol

from scripts.install.compose import (
    CADDYFILE_NAME,
    PROFILE_SERVICES,
    SKILL_SANDBOX_BUILD,
    SKILL_SANDBOX_LOCAL_IMAGE,
    up_suffix,
)
from scripts.install.envgen import private_backup, replace_private
from scripts.install.model import (
    Clock,
    ComposeInvocation,
    Exposure,
    InstallMode,
    PublicAnswers,
    SecretAnswers,
    UrlOpener,
)

if TYPE_CHECKING:
    from scripts.install.state import InstallState

RESUME_HINT = "./install.sh --resume"

_READY_POLL_INTERVAL_S = 3.0

#: Recreate what changed, never build: a reconfiguration ships no new image.
_UP_NO_BUILD = ["up", "-d", "--no-build", "--remove-orphans"]


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


#: Embedded source context shipped by the release bundle (build contexts for
#: the local mode; the outer bundle SHA-256 covers its integrity).
SOURCE_CONTEXT_MEMBER = "lia-self-host-source-context.tar.gz"


class SourceContextError(RuntimeError):
    """The embedded source context is unsafe or unreadable."""


def materialize_source_context(root: Path) -> str | None:
    """Extract the bundle's embedded source context for local builds.

    The Compose file demands ``./apps/api`` and ``apps/web/Dockerfile.prod``
    as build contexts; a git clone has them, the release bundle ships them
    inside :data:`SOURCE_CONTEXT_MEMBER` — and nothing extracted it, so every
    ``--local-build`` from a bundle died in ``acquire_failed`` within seconds
    (measured on the v1.30.1 qualification matrix). The archive's ABSENCE is
    the only no-op condition: an ``apps/`` guard is a trap, because
    ``prepare_host_paths`` mkdir's the ``apps/api/config`` bind-mount target
    before this step runs, so "``apps/`` exists" does NOT mean "source tree
    present" (that exact interleaving turned this function into a silent
    no-op on the v1.30.1 qualification matrix, take two). When the archive
    is present the extraction always runs — deliberately: it self-heals a
    partial extraction after a crash, overwrites nothing a bundle install
    owns less than the installer does, and lands on a deterministic digest.

    Extraction is fail-closed on hostile members (absolute paths, ``..``,
    links pointing outside the root) — Python 3.10 floor, so the check is
    manual rather than ``tarfile``'s 3.12+ data filter.

    Args:
        root: Installation root (the extracted bundle or a git clone).

    Returns:
        The canonical tree SHA-256 of the extracted files (sorted
        ``path\\0content`` chain), or ``None`` when nothing was extracted.

    Raises:
        SourceContextError: On an unsafe member or an unreadable archive.
    """
    import hashlib
    import tarfile

    archive = root / SOURCE_CONTEXT_MEMBER
    if not archive.is_file():
        return None

    resolved_root = root.resolve()
    digest = hashlib.sha256()
    try:
        with tarfile.open(archive, mode="r:gz") as tar:
            members = tar.getmembers()
            for member in members:
                target = (resolved_root / member.name).resolve()
                if not target.is_relative_to(resolved_root):
                    raise SourceContextError(f"unsafe member path: {member.name}")
                if member.islnk() or member.issym():
                    link_target = (target.parent / member.linkname).resolve()
                    if not link_target.is_relative_to(resolved_root):
                        raise SourceContextError(f"unsafe link target: {member.name}")
            # Belt (manual checks above) AND braces: the stdlib data filter
            # where available — keyword only on >= 3.12, the floor is 3.10.
            if hasattr(tarfile, "data_filter"):
                tar.extractall(path=resolved_root, members=members, filter="data")
            else:  # pragma: no cover - py3.10/3.11 path
                tar.extractall(path=resolved_root, members=members)
            for member in sorted(members, key=lambda m: m.name):
                if member.isfile():
                    digest.update(member.name.encode("utf-8") + b"\0")
                    digest.update((resolved_root / member.name).read_bytes())
    except tarfile.TarError as exc:
        raise SourceContextError(f"unreadable source context: {exc}") from exc
    return digest.hexdigest()


def acquire(
    invocation: ComposeInvocation,
    runner: Runner,
    *,
    sandbox_image: str | None = None,
    sandbox_build_root: Path | None = None,
) -> None:
    """Obtain the app images: local builds, prebuilt pulls (never builds).

    The skill sandbox image (ADR-327 lot 2) is no Compose service — a one-shot
    container fails ``up --wait`` — so it is obtained beside them: pulled by
    its locked digest in prebuilt mode, built under the tag the base file
    reads in local mode. Neither happens when the sandbox is not selected.

    Args:
        invocation: The Compose layers of this install.
        runner: How a command runs.
        sandbox_image: Prebuilt mode: the release's sandbox reference.
        sandbox_build_root: Local mode: the install root to build it from.
    """
    verb = "pull" if invocation.mode is InstallMode.PREBUILT else "build"
    _run_or_fail(
        runner, invocation.prefix() + [verb, "api", "web"], "acquire_failed"
    )
    acquire_sandbox(
        invocation.mode,
        runner,
        sandbox_image=sandbox_image,
        sandbox_build_root=sandbox_build_root,
    )


def acquire_sandbox(
    mode: InstallMode,
    runner: Runner,
    *,
    sandbox_image: str | None,
    sandbox_build_root: Path | None,
) -> None:
    """Obtain the skill sandbox image alone: pulled in prebuilt mode, built locally.

    Shared by the install and by a reconfiguration that switches the sandbox
    on: the image is no Compose service, so ``up`` would never obtain it.

    Args:
        mode: How this installation obtains its images.
        runner: How a command runs.
        sandbox_image: Prebuilt mode: the release's sandbox reference.
        sandbox_build_root: Local mode: the install root to build it from.
    """
    if mode is InstallMode.PREBUILT:
        if sandbox_image is not None:
            _run_or_fail(runner, ["docker", "pull", sandbox_image], "acquire_failed")
        return
    if sandbox_build_root is not None:
        context, dockerfile = SKILL_SANDBOX_BUILD
        _run_or_fail(
            runner,
            [
                "docker",
                "build",
                "-t",
                SKILL_SANDBOX_LOCAL_IMAGE,
                "-f",
                str(sandbox_build_root / dockerfile),
                str(sandbox_build_root / context),
            ],
            "acquire_failed",
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
    """Wait for the entrypoint, migrations and serving workers to become ready.

    The entrypoint now resolves the effective Uvicorn worker count from its
    arguments (reload serves from one process). The installer still gates on
    the application's /ready response, not a predicted worker count or a
    container's merely-running state.
    """
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
) -> dict[str, str] | None:
    """Feed the single JSON secrets document to the in-container bootstrap.

    Exit 3 (``bootstrapped_publication_failed``) is NOT fatal: the forced
    API recreation is the real worker barrier, publication is a hot-update
    nicety. Exit 2 is a payload contract violation; anything else fails.

    Returns:
        What the installation leaves degraded (capability → the provider whose
        key it waits for), as the bootstrap computed it from the keys it
        stored — ``None`` when its report cannot be read. The final report
        used to be handed an empty list, so it never named one.
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
    return bootstrap_degraded_report(result.stdout)


def bootstrap_degraded_report(stdout: str) -> dict[str, str] | None:
    """The ``optional_unkeyed`` map of the bootstrap's one result line.

    The API logs JSON lines on the same stdout, so the result is the line that
    carries both ``status`` and ``optional_unkeyed`` — never merely the last
    JSON line.

    Args:
        stdout: The bootstrap container's standard output.

    Returns:
        The map, or ``None`` when no result line is readable.
    """
    for line in reversed(stdout.splitlines()):
        try:
            document = json.loads(line)
        except ValueError:
            continue
        if not isinstance(document, dict) or "status" not in document:
            continue
        degraded = document.get("optional_unkeyed")
        if isinstance(degraded, dict) and all(
            isinstance(key, str) and isinstance(value, str) for key, value in degraded.items()
        ):
            return dict(degraded)
    return None


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


@dataclass(frozen=True)
class FileSwap:
    """What a reconfiguration changed on disk, to be put back exactly.

    Attributes:
        written: The targets replaced or created, in the order they were.
        backups: Target -> private copy of its previous content; a written
            target absent from it did not exist before the swap.
    """

    written: tuple[Path, ...]
    backups: Mapping[Path, Path]


def swap_in(candidate_files: Mapping[Path, Path]) -> FileSwap:
    """Replace each target by its candidate, one atomic replace per file.

    Every previous file is first copied beside itself, private from its first
    byte. A failure or an interrupt halfway puts back what was already
    replaced before propagating: no target is left half-written, and none the
    swap never reached is touched.

    A target is recorded BEFORE it is replaced, its copy already taken: an
    interrupt landing between the atomic replace and the record left the new
    file in place with nothing to put it back. Putting back a target the
    replace never reached rewrites the same bytes, or removes nothing.

    Args:
        candidate_files: Target -> staged candidate.

    Returns:
        The swap, for :func:`put_back`.
    """
    written: list[Path] = []
    backups: dict[Path, Path] = {}
    try:
        for target, candidate in candidate_files.items():
            if target.exists():
                backups[target] = private_backup(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            written.append(target)
            replace_private(target, candidate.read_bytes())
        swap = FileSwap(tuple(written), backups)
    except BaseException:
        try:
            put_back(FileSwap(tuple(written), backups))
        except BaseException as restore_error:
            raise StepFailed(
                "reconfigure_restore_failed", detail=type(restore_error).__name__
            ) from restore_error
        raise
    return swap


def put_back(swap: FileSwap) -> None:
    """Restore every file the swap wrote: its previous content, or nothing."""
    for target in reversed(swap.written):
        backup = swap.backups.get(target)
        if backup is None:
            target.unlink(missing_ok=True)
        else:
            replace_private(target, backup.read_bytes())


def _caddy_rereads_routes(
    previous: PublicAnswers,
    candidate: PublicAnswers,
    candidate_files: Mapping[Path, Path],
) -> bool:
    """Whether the candidate hands the running Caddy other routes than it serves.

    Decided BEFORE the swap, from the staged and the current bytes: decided
    after it and outside the restore's reach, a read that failed there left
    the new files in place under a message saying the previous ones were.

    Args:
        previous: The recorded answers.
        candidate: The new answers.
        candidate_files: Target -> staged candidate.

    Returns:
        ``True`` when Caddy runs on both sides and its file changes.
    """
    if previous.exposure is not Exposure.CADDY or candidate.exposure is not Exposure.CADDY:
        return False
    for target, staged in candidate_files.items():
        if target.name == CADDYFILE_NAME:
            return not target.is_file() or target.read_bytes() != staged.read_bytes()
    return False


def bring_up_commands(
    active: ComposeInvocation, *, replaced: ComposeInvocation, restart_caddy: bool
) -> tuple[list[str], ...]:
    """The Compose commands that make ``active`` the running stack in place of ``replaced``.

    ``up --no-build --remove-orphans``; a Caddy restart when its routes changed
    under it (it reads its bind-mounted file once, at start, and Compose hashes
    no file content); then the services of each profile ``replaced`` runs and
    ``active`` does not, removed by name from the invocation that still knows
    them — Compose never counts a disabled profile's containers as orphans, so
    ``--remove-orphans`` leaves them running, the Docker-socket and privileged
    ones of observability included. Their named volumes are kept.

    One sequence for the three readers: the reconfiguration (candidate in place
    of the installation), its restore (the reverse), and the line a restore
    that failed prints for the operator to run.

    Args:
        active: The selection that must run.
        replaced: The selection it replaces.
        restart_caddy: Whether Caddy must reread its routes.

    Returns:
        Each command's argv, in the order they run.
    """
    commands = [active.prefix() + _UP_NO_BUILD]
    if restart_caddy:
        commands.append(active.prefix() + ["restart", "caddy"])
    commands.extend(
        replaced.prefix() + ["rm", "--stop", "--force", *PROFILE_SERVICES[profile]]
        for profile in replaced.profiles
        if profile not in active.profiles
    )
    return tuple(commands)


def _bring_up(
    commands: Sequence[Sequence[str]],
    runner: Runner,
    *,
    code: str,
    wait_ready_fn: Callable[[], None] | None,
) -> None:
    """Run ``commands`` in order under ``code``, then wait until the stack serves."""
    for argv in commands:
        _run_or_fail(runner, argv, code)
    if wait_ready_fn is not None:
        wait_ready_fn()


def _identity_changed(previous: PublicAnswers, candidate: PublicAnswers) -> bool:
    """Whether the candidate touches what a reconfiguration may never change."""
    return (
        candidate.mode is not previous.mode
        or candidate.admin_email != previous.admin_email
        or candidate.admin_name != previous.admin_name
        or candidate.manifest_path != previous.manifest_path
    )


def _candidate_config_argv(
    invocation: ComposeInvocation, candidate_files: Mapping[Path, Path]
) -> list[str]:
    """``docker compose … config --quiet`` over the CANDIDATE files.

    Compose reads the project's ``.env`` beside the first file: a candidate
    ``.env`` is validated through ``--env-file``, or the check reads the old one.

    Args:
        invocation: The candidate's Compose selection.
        candidate_files: Target -> staged candidate.

    Returns:
        The validation command's argv.
    """
    argv = ["docker", "compose"]
    if invocation.project_name:
        argv += ["-p", invocation.project_name]
    for target, candidate in candidate_files.items():
        if target.name == ".env":
            argv += ["--env-file", str(candidate)]
    for file in invocation.files:
        argv += ["-f", str(candidate_files.get(file, file))]
    for profile in invocation.profiles:
        argv += ["--profile", profile]
    return argv + ["config", "--quiet"]


#: The signals a reconfiguration turns into an interrupt: a closed SSH session
#: (``SIGHUP``, absent on Windows) and a plain ``kill``.
_TERMINATION_SIGNAL_NAMES = ("SIGTERM", "SIGHUP")


def _raise_interrupt(signum: int, frame: FrameType | None) -> None:
    """Signal handler: the termination becomes the interrupt the restore handles."""
    del signum, frame
    raise KeyboardInterrupt


@contextlib.contextmanager
def interrupt_on_termination() -> Iterator[None]:
    """While open, a hang-up or a termination raises :class:`KeyboardInterrupt`.

    Left to their default action, both end the process wherever it stands —
    after the swap, with the new files in place and nothing restored — whereas
    an interrupt runs the restore (:func:`reconfigure_existing`). The handlers
    in force before are put back on exit.

    Yields:
        Nothing; the handlers hold for the ``with`` body.
    """
    previous: list[tuple[int, Callable[[int, FrameType | None], Any] | int | None]] = []
    for name in _TERMINATION_SIGNAL_NAMES:
        number = getattr(signal, name, None)
        if number is not None:
            previous.append((number, signal.signal(number, _raise_interrupt)))
    try:
        yield
    finally:
        for number, handler in reversed(previous):
            # A handler not installed from Python reads as None: the default stands in.
            signal.signal(number, handler if handler is not None else signal.SIG_DFL)


def reconfigure_existing(
    *,
    current: "InstallState",
    candidate_public: PublicAnswers,
    candidate_files: Mapping[Path, Path],
    invocation: ComposeInvocation,
    runner: Runner,
    previous_invocation: ComposeInvocation | None = None,
    wait_ready_fn: Callable[[], None] | None = None,
    before_restore: Callable[[BaseException], None] | None = None,
) -> FileSwap:
    """Non-destructive reconfiguration of a recorded installation.

    Allowed changes are the non-secret routing and capability choices
    (installer language, exposure, server host, web/API domains, Caddy
    email, default language, observability, self-diagnostics, skill
    sandbox, live mode, radio, speaking avatar). Mode, release identity, and
    admin identity are immutable; generated secrets are preserved by
    construction (the candidate ``.env`` reuses the ones in force); seeds and
    bootstrap are NEVER invoked.

    Sequence: verify identity -> static Compose validation of the candidate
    files (with the candidate ``.env``) -> decide whether Caddy must reread its
    routes, from the bytes on both sides -> swap them in (:func:`swap_in`) ->
    :func:`bring_up_commands` (``up -d --no-build --remove-orphans``, the Caddy
    restart, the services of a profile turned off) -> wait until ready. Any
    failure or interrupt after the swap restores the previous files and stack,
    verified, before propagating (:func:`restore_reconfiguration`).

    Args:
        current: The recorded installation.
        candidate_public: The new answers.
        candidate_files: Target -> staged candidate, every file the swap writes.
        invocation: The candidate's Compose selection.
        runner: How a command runs.
        previous_invocation: The recorded installation's Compose selection
            (``invocation`` when omitted).
        wait_ready_fn: Blocks until the stack serves, else raises; ``None``
            skips the wait.
        before_restore: Handed what stopped the candidate BEFORE the restore
            starts, so the cause is on record even when the restore then fails
            or never returns; the restore runs whatever it raises.

    Returns:
        The swap that is now in force.

    Raises:
        StepFailed: ``reconfigure_identity_changed`` or ``reconfigure_invalid``
            (nothing changed), ``reconfigure_failed`` or the readiness code
            (the previous configuration is back), or
            ``reconfigure_restore_failed``.
    """
    previous = current.public_answers
    if _identity_changed(previous, candidate_public):
        raise StepFailed("reconfigure_identity_changed")
    # Static validation on the CANDIDATE files before anything is replaced.
    _run_or_fail(
        runner, _candidate_config_argv(invocation, candidate_files), "reconfigure_invalid"
    )
    previous_invocation = previous_invocation or invocation
    reload_caddy = _caddy_rereads_routes(previous, candidate_public, candidate_files)
    swap: FileSwap | None = None
    try:
        swap = swap_in(candidate_files)
        _bring_up(
            bring_up_commands(
                invocation, replaced=previous_invocation, restart_caddy=reload_caddy
            ),
            runner,
            code="reconfigure_failed",
            wait_ready_fn=wait_ready_fn,
        )
    except BaseException as error:
        # `swap` is unset when the swap itself stopped: it put back what it wrote.
        if swap is not None:
            try:
                if before_restore is not None:
                    before_restore(error)
            finally:
                restore_reconfiguration(
                    swap,
                    previous_invocation=previous_invocation,
                    candidate_invocation=invocation,
                    reload_caddy=reload_caddy,
                    runner=runner,
                    wait_ready_fn=wait_ready_fn,
                )
        raise
    return swap


def restore_reconfiguration(
    swap: FileSwap,
    *,
    previous_invocation: ComposeInvocation,
    candidate_invocation: ComposeInvocation,
    reload_caddy: bool,
    runner: Runner,
    wait_ready_fn: Callable[[], None] | None = None,
) -> None:
    """Put the previous files back and bring the previous stack up, ready.

    A file the reconfiguration CREATED (a Caddyfile for a new exposure) had no
    previous version: it is removed. The services of a profile the candidate
    turned on are stopped, since Compose would leave them running. Nothing is
    assumed: every command must succeed and the restored stack must serve.

    Args:
        swap: What the reconfiguration wrote.
        previous_invocation: The recorded installation's Compose selection.
        candidate_invocation: The candidate's Compose selection.
        reload_caddy: Whether Caddy was handed other routes, and must reread.
        runner: How a command runs.
        wait_ready_fn: Blocks until the stack serves, else raises; ``None``
            skips the wait.

    Raises:
        StepFailed: ``reconfigure_restore_failed`` — whatever stopped the
            restore, an interrupt included: each replaced file's backup beside
            it is then the copy of the previous configuration.
    """
    try:
        put_back(swap)
        _bring_up(
            bring_up_commands(
                previous_invocation, replaced=candidate_invocation, restart_caddy=reload_caddy
            ),
            runner,
            code="reconfigure_restore_failed",
            wait_ready_fn=wait_ready_fn,
        )
    except StepFailed as exc:
        if exc.code == "reconfigure_restore_failed":
            raise
        raise StepFailed("reconfigure_restore_failed", detail=exc.code) from exc
    except BaseException as exc:
        raise StepFailed(
            "reconfigure_restore_failed", detail=type(exc).__name__
        ) from exc


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
