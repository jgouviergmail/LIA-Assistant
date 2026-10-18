"""The reconfiguration of a recorded installation (``--reconfigure``, ADR-215).

Order, on a recorded and bootstrapped install:

    questions (answers in force as defaults) -> stage candidate files ->
    confirm the answer-derived .env values that change -> [sandbox image when
    newly enabled] -> validate -> back up -> swap -> up --no-build -> /ready
    (else restore) -> record state -> report

A hang-up or a termination during it is an interrupt, as Ctrl-C is: before the
swap nothing changed, after it the previous files and stack come back first.
The command line and the mapping of a run's failures to its exit code stay with
the entry point (``__main__``), which this module never imports: what both
flows share lives in ``run_context``.
"""

from __future__ import annotations

import contextlib
import functools
import shlex
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

from scripts.install import deploy
from scripts.install.answers import ask_yes_no, collect_reconfiguration
from scripts.install.compose import (
    CADDYFILE_NAME,
    IMAGES_COMPOSE,
    build_invocation,
    render_caddyfile,
    render_install_override,
)
from scripts.install.envgen import (
    GENERATED_SECRET_KEYS,
    derive_environment,
    derived_changes,
    describe_change,
    docker_socket_gid,
    load_existing_generated_secrets,
    render_reconfigured_env,
    with_docker_gid,
    write_atomic_private,
)
from scripts.install.host_paths import prepare_host_paths, required_host_paths
from scripts.install.i18n import msg
from scripts.install.log import InstallLog
from scripts.install.model import ComposeInvocation, Exposure, PublicAnswers
from scripts.install.questions import (
    build_env_changes_confirmation,
    build_reconfiguration_questions,
)
from scripts.install.report import RECONFIGURED_HEADING, render_report
from scripts.install.run_context import (
    ENV_FILE,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_PREFLIGHT,
    EXIT_STEP_FAILED,
    EXIT_USAGE,
    OVERRIDE_FILE,
    READY_URL,
    STATE_FILE,
    Deps,
    backup_dir,
    generated_fingerprints,
    prebuilt_pins,
    release_summary,
)
from scripts.install.state import InstallState, StateError, load_state, save_state

#: Where a reconfiguration renders its candidate files (private, removed after).
RECONFIGURE_DIR = ".install-reconfigure"


def reconfigure_installation(deps: Deps, log: InstallLog) -> int:
    """Change the routing and capability choices of a recorded installation.

    Never re-seeds, never re-runs the bootstrap, never rebuilds the
    application images. ``--reconfigure`` used to fall through to a FRESH
    install over the running one — every question asked again, secrets
    included; the ``.env`` re-rendered from the template, dropping the
    operator's own lines; the seeds re-armed; the images rebuilt (pulled in
    prebuilt mode); the bootstrap re-run, the typed provider keys replacing
    the stored ones — while the non-destructive swap below sat unwired.

    A hang-up (a closed SSH session) or a termination is an interrupt while the
    questions are asked and the candidate applied (:func:`deploy.interrupt_on_termination`):
    left to their default action, both killed the process after the swap with
    nothing restored.

    Args:
        deps: The injected side effects.
        log: The redacting install log.

    Returns:
        A process exit code.
    """
    state = _reconfigurable_state(deps)
    if isinstance(state, str):
        deps.io.print_fn(state)
        return EXIT_PREFLIGHT
    with deploy.interrupt_on_termination():
        candidate = _ask_reconfiguration(deps, log, state.public_answers)
        if candidate is None:
            return EXIT_INTERRUPTED
        code = _apply_reconfiguration(deps, log, state, candidate)
    if code == EXIT_OK:
        _record_reconfiguration(deps, log, state, candidate)
    return code


def _reconfigurable_state(deps: Deps) -> InstallState | str:
    """The recorded, bootstrapped installation, else the line that refuses it."""
    try:
        state = load_state(deps.root / STATE_FILE)
    except StateError as exc:
        return str(exc)
    if state is None:
        return "reconfigure_without_state"
    if not state.bootstrap_complete:
        return "reconfigure_before_install_complete — resume with ./install.sh --resume"
    return state


def _ask_reconfiguration(
    deps: Deps, log: InstallLog, current: PublicAnswers
) -> PublicAnswers | None:
    """The candidate answers; ``None`` when the operator interrupted the questions.

    Nothing has changed at a question: the run is started again, never resumed
    (``--resume`` belongs to an unfinished installation).
    """
    try:
        return collect_reconfiguration(
            build_reconfiguration_questions(current), io=deps.io, current=current
        )
    except KeyboardInterrupt:
        log.write("interrupted", step="reconfigure_questions")
        deps.io.print_fn("interrupted — nothing changed; run ./install.sh --reconfigure again")
        return None


def _apply_reconfiguration(
    deps: Deps, log: InstallLog, state: InstallState, candidate: PublicAnswers
) -> int:
    """Stage, confirm, validate and swap the candidate; restore it on failure.

    Args:
        deps: The injected side effects.
        log: The redacting install log.
        state: The recorded installation.
        candidate: The new answers.

    Returns:
        ``EXIT_OK`` once the candidate serves; otherwise the exit code of a run
        that left the previous configuration in force, or could not bring it back.
    """
    current = state.public_answers
    previous_invocation = build_invocation(current, root=deps.root)
    invocation = build_invocation(candidate, root=deps.root)
    staging = deps.root / RECONFIGURE_DIR
    try:
        candidate_files = _stage_reconfiguration(deps, state, candidate, staging)
        if not _env_changes_confirmed(deps, log, candidate, candidate_files):
            deps.io.print_fn("reconfigure_declined — nothing changed")
            return EXIT_USAGE
        _prepare_unswapped_host_paths(invocation, candidate_files, deps.root)
        log.write("reconfigure_started", exposure=candidate.exposure.value)
        _acquire_new_sandbox(deps, current, candidate)
        deploy.reconfigure_existing(
            current=state,
            candidate_public=candidate,
            candidate_files=candidate_files,
            invocation=invocation,
            runner=deps.runner,
            previous_invocation=previous_invocation,
            wait_ready_fn=functools.partial(deploy.wait_ready, READY_URL, deps.opener, deps.clock),
            before_restore=functools.partial(_log_restore_cause, log),
        )
    except KeyboardInterrupt:
        # Raised before the swap, nothing changed; after it, the previous
        # files and stack were put back before the interrupt propagated.
        log.write("interrupted", step="reconfigure")
        deps.io.print_fn(
            "interrupted — the previous configuration is in force; "
            "run ./install.sh --reconfigure again"
        )
        return EXIT_INTERRUPTED
    except deploy.StepFailed as exc:
        log.write("step_failed", code=exc.code, detail=exc.detail)
        recovery = deploy.bring_up_commands(
            previous_invocation,
            replaced=invocation,
            restart_caddy=current.exposure is Exposure.CADDY,
        )
        deps.io.print_fn(_reconfigure_failure_line(exc.code, recovery))
        return EXIT_STEP_FAILED
    except OSError as exc:
        log.write("step_failed", code="reconfigure_io_error", detail=type(exc).__name__)
        deps.io.print_fn(_reconfigure_failure_line("reconfigure_io_error", ()))
        return EXIT_STEP_FAILED
    finally:
        # The staged `.env` carries every generated secret.
        shutil.rmtree(staging, ignore_errors=True)
    return EXIT_OK


def _stage_reconfiguration(
    deps: Deps,
    state: InstallState,
    candidate: PublicAnswers,
    staging: Path,
) -> dict[Path, Path]:
    """Render, beside the installation, every file a reconfiguration replaces.

    The ``.env`` starts from the INSTALLED file (operator lines survive) and
    keeps the generated secrets in force; turning the sandbox on writes
    ``DOCKER_GID`` from the host's Docker socket where the file holds none.
    The override keeps the seed gate closed and the recorded seed identity.

    Args:
        deps: The injected side effects.
        state: The recorded installation.
        candidate: The new answers.
        staging: The private directory the candidates are written to.

    Returns:
        Target -> staged candidate.
    """
    generated = load_existing_generated_secrets(deps.root / ENV_FILE, GENERATED_SECRET_KEYS)
    image_lock, sandbox_image = prebuilt_pins(candidate)
    # A run killed outright never reached its cleanup: what it left may be
    # another mode, and it holds the generated secrets.
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(mode=0o700)
    files: dict[Path, Path] = {}

    def _stage(target: Path, content: str) -> None:
        staged = staging / target.name
        write_atomic_private(staged, content)
        files[target] = staged

    env_path = deps.root / ENV_FILE
    env_text = render_reconfigured_env(
        env_path.read_text(encoding="utf-8"), derive_environment(candidate, generated)
    )
    if candidate.skill_sandbox and not state.public_answers.skill_sandbox:
        # Left unset, the overlay's fallback group is not every host's socket group.
        env_text = with_docker_gid(env_text, docker_socket_gid(deps.docker_socket))
    _stage(env_path, env_text)
    _stage(
        deps.root / OVERRIDE_FILE,
        render_install_override(
            candidate,
            seed_intent=False,
            seed_bundle_sha256=state.seed_bundle_sha256,
            sandbox_image=sandbox_image,
        ),
    )
    if image_lock is not None:
        _stage(deps.root / IMAGES_COMPOSE, image_lock)
    if candidate.exposure is Exposure.CADDY:
        _stage(
            deps.root / "infrastructure" / "caddy" / CADDYFILE_NAME,
            render_caddyfile(candidate, template_root=deps.root),
        )
    return files


def _env_changes_confirmed(
    deps: Deps,
    log: InstallLog,
    candidate: PublicAnswers,
    candidate_files: Mapping[Path, Path],
) -> bool:
    """Whether the answer-derived ``.env`` values that change may change.

    The questions default to the RECORDED answers while these values are
    rewritten from them: listed against the file in force, a value edited by
    hand is replaced only once the operator, having read the line, says yes.

    Args:
        deps: The injected side effects.
        log: The redacting install log.
        candidate: The new answers (their wizard language words the prompt).
        candidate_files: Target -> staged candidate, the ``.env`` among them.

    Returns:
        ``True`` when no such value changes or the operator confirmed.
    """
    env_path = deps.root / ENV_FILE
    changes = derived_changes(
        env_path.read_text(encoding="utf-8"),
        candidate_files[env_path].read_text(encoding="utf-8"),
    )
    if not changes:
        return True
    deps.io.print_fn(msg("info.env_changes", candidate.language))
    for change in changes:
        deps.io.print_fn(f"  {describe_change(change)}")
    confirmed = ask_yes_no(
        build_env_changes_confirmation(), io=deps.io, language=candidate.language
    )
    log.write(
        "reconfigure_env_changes",
        keys=",".join(change.key for change in changes),
        applied="yes" if confirmed else "no",
    )
    return confirmed


def _prepare_unswapped_host_paths(
    invocation: ComposeInvocation, candidate_files: Mapping[Path, Path], root: Path
) -> None:
    """Prepare the candidate's host paths, but those the swap itself writes.

    A file the swap writes — the Caddyfile of a new Caddy exposure — cannot
    exist before it: only what the swap leaves alone is asserted.
    """
    prepare_host_paths(
        tuple(
            requirement
            for requirement in required_host_paths(invocation, root=root)
            if requirement.path not in candidate_files
        )
    )


def _acquire_new_sandbox(deps: Deps, current: PublicAnswers, candidate: PublicAnswers) -> None:
    """Obtain the sandbox image when this reconfiguration turns the sandbox on.

    The image is no Compose service: ``up`` would never obtain it.
    """
    if candidate.skill_sandbox and not current.skill_sandbox:
        _lock, sandbox_image = prebuilt_pins(candidate)
        deploy.acquire_sandbox(
            candidate.mode,
            deps.runner,
            sandbox_image=sandbox_image,
            sandbox_build_root=deps.root,
        )


def _log_restore_cause(log: InstallLog, error: BaseException) -> None:
    """Record what stopped the candidate, BEFORE its restore starts.

    Logged after the restore, the cause was lost whenever the restore failed
    too — it survived only as the exception's context — or never returned.
    """
    if isinstance(error, deploy.StepFailed):
        code, detail = error.code, error.detail
    else:
        code, detail = type(error).__name__, ""
    # Best effort: a log that cannot be written must not hold the restore back.
    with contextlib.suppress(OSError):
        log.write("reconfigure_restoring", code=code, detail=detail)


def _record_reconfiguration(
    deps: Deps, log: InstallLog, state: InstallState, candidate: PublicAnswers
) -> None:
    """Record the new answers and file fingerprints, then print the report."""
    save_state(
        deps.root / STATE_FILE,
        replace(
            state,
            public_answers=candidate,
            generated_sha256=generated_fingerprints(deps.root),
            last_error_code=None,
        ),
    )
    log.write("reconfigure_complete")
    deps.io.print_fn(
        render_report(
            candidate,
            release_summary=release_summary(candidate),
            backup_dir=backup_dir(deps),
            # A reconfiguration touches no key: the Admin UI is the authority.
            optional_unkeyed=None,
            heading=RECONFIGURED_HEADING,
        )
    )


def _reconfigure_failure_line(code: str, recovery: Sequence[Sequence[str]]) -> str:
    """What the operator reads when a reconfiguration stops on ``code``.

    Args:
        code: The stable failure code.
        recovery: The commands that bring the previous stack back, printed when
            even the restore failed: the previous Compose selection exactly —
            images file, sandbox overlay and profiles included. No secret.

    Returns:
        The line.
    """
    if code == "reconfigure_restore_failed":
        commands = "\n".join(f"  {shlex.join(argv)}" for argv in recovery)
        return (
            "reconfigure_restore_failed — the previous configuration could not be "
            "brought back ready; each replaced file is kept beside it as "
            "<name>.backup.<time>. Copy each back over its file, then run:\n"
            f"{commands}\n"
            "and read install.log"
        )
    return (
        f"{code} — the previous configuration is in force; "
        "fix the cause and run ./install.sh --reconfigure again"
    )
