"""LIA self-host installer entry point (ADR-215, B01).

Invoked by ``install.sh`` as ``python3 -B -m scripts.install``. Every
side-effecting dependency (terminal I/O, command runner, URL opener, clock,
filesystem root) is injected through ``Deps`` so the complete flow is
provable hermetically.

Exact fresh-install order (B08/B12):

    resolve mode -> bundle-tree gate -> preflight -> questions -> generate
    -> [--dry-run stops here] -> capture rollback -> acquire -> validate
    Settings -> start (seeds armed) -> /ready -> disarm seeds -> stdin
    bootstrap -> recreate API --no-build -> second /ready -> verifier
    -> record state -> report
"""

from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
import time
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from scripts.install import deploy, rollback
from scripts.install.answers import (
    InstallInputError,
    collect_answers,
    collect_secret_answers,
)
from scripts.install.compose import (
    build_invocation,
    render_caddyfile,
    render_install_override,
)
from scripts.install.envgen import (
    GENERATED_SECRET_KEYS,
    EnvGenError,
    derive_environment,
    generate_secrets,
    load_existing_generated_secrets,
    render_env,
    write_atomic_private,
)
from scripts.install.host_paths import (
    HostPathError,
    prepare_host_paths,
    required_host_paths,
)
from scripts.install.log import InstallLog
from scripts.install.manifest import hash_file
from scripts.install.model import (
    Clock,
    Exposure,
    InstallMode,
    IOAdapter,
    PublicAnswers,
    SecretAnswers,
    UrlOpener,
)
from scripts.install.preflight import (
    PreflightError,
    resolve_install_mode,
)
from scripts.install.questions import build_questions
from scripts.install.report import render_report
from scripts.install.seed_bundle import compute_seed_bundle_sha256
from scripts.install.state import (
    STATE_SCHEMA_VERSION,
    InstallState,
    ResumeDecision,
    ResumeInputs,
    StateError,
    Step,
    decide_resume,
    load_state,
    save_state,
    with_step_completed,
)

INSTALLER_VERSION = "1"
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
    """Injected side-effect surface (real in main(), fakes in tests)."""

    root: Path
    io: IOAdapter
    runner: deploy.Runner
    opener: UrlOpener
    clock: Clock
    env: Mapping[str, str] = field(default_factory=dict)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="install.sh", description="LIA self-host installer (ADR-215)."
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--local-build", action="store_true")
    mode_group.add_argument("--prebuilt", action="store_true")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reconfigure", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--answers", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    return parser


def _requested_mode(args: argparse.Namespace) -> InstallMode | None:
    if args.local_build:
        return InstallMode.LOCAL
    if args.prebuilt:
        return InstallMode.PREBUILT
    return None


def _generated_fingerprints(root: Path) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for name in (ENV_FILE, OVERRIDE_FILE):
        path = root / name
        if path.is_file():
            fingerprints[name] = hash_file(path)
    return fingerprints


def _generate_artifacts(
    deps: Deps,
    public: PublicAnswers,
    *,
    seed_intent: bool,
    generated: Mapping[str, str],
    sandbox_api_image: str | None,
) -> str:
    """Render .env / override / Caddyfile and prepare host paths."""
    seed_digest = compute_seed_bundle_sha256(deps.root)
    environment = derive_environment(public, generated)
    base_path = deps.root / ".env.min.prod"
    base = base_path.read_text(encoding="utf-8") if base_path.is_file() else ""
    write_atomic_private(deps.root / ENV_FILE, render_env(base, dict(environment)))
    write_atomic_private(
        deps.root / OVERRIDE_FILE,
        render_install_override(
            public,
            seed_intent=seed_intent,
            seed_bundle_sha256=seed_digest,
            sandbox_api_image=sandbox_api_image,
        ),
    )
    if public.exposure is Exposure.CADDY:
        caddy_dir = deps.root / "infrastructure" / "caddy"
        caddy_dir.mkdir(parents=True, exist_ok=True)
        write_atomic_private(
            caddy_dir / "Caddyfile",
            render_caddyfile(public, template_root=deps.root),
        )
    invocation = build_invocation(public, root=deps.root)
    prepare_host_paths(required_host_paths(invocation, root=deps.root))
    return seed_digest


def _disarm_seeds(
    deps: Deps,
    public: PublicAnswers,
    seed_digest: str,
    sandbox_api_image: str | None,
) -> None:
    """Atomically rewrite the override with APPLY_SEEDS=false.

    Runs right after the FIRST /ready: a later resume must never re-enter
    the seed gate with a non-empty marker. Failure stops before bootstrap.
    """
    write_atomic_private(
        deps.root / OVERRIDE_FILE,
        render_install_override(
            public,
            seed_intent=False,
            seed_bundle_sha256=seed_digest,
            sandbox_api_image=sandbox_api_image,
        ),
    )


def _fresh_state(
    public: PublicAnswers, seed_digest: str, root: Path
) -> InstallState:
    return InstallState(
        schema_version=STATE_SCHEMA_VERSION,
        installer_version=INSTALLER_VERSION,
        mode=public.mode,
        public_answers=public,
        release_id=None,
        bundle_tree_sha256=None,
        source_context_tree_sha256=None,
        image_digests={},
        seed_bundle_sha256=seed_digest,
        completed=(),
        attempts={},
        last_error_code=None,
        generated_sha256=_generated_fingerprints(root),
        bootstrap_complete=False,
        project_name="lia",
    )


def _collect(
    deps: Deps, args: argparse.Namespace, mode: InstallMode, manifest: Path | None
) -> tuple[PublicAnswers, SecretAnswers]:
    return collect_answers(
        build_questions(),
        io=deps.io,
        non_interactive=args.non_interactive,
        answers_path=args.answers,
        mode=mode,
        manifest_path=manifest,
    )


def _deploy_sequence(
    deps: Deps,
    log: InstallLog,
    public: PublicAnswers,
    secrets: SecretAnswers,
    state: InstallState,
    seed_digest: str,
    sandbox_api_image: str | None,
) -> InstallState:
    invocation = build_invocation(public, root=deps.root)
    # An install whose bootstrap never completed is still a FIRST install
    # for rollback purposes: quiesce-only, nothing worth aliasing yet.
    prior = state if state.bootstrap_complete else None
    point = rollback.capture_rollback_point(invocation, prior, deps.runner)
    try:
        log.write("step_started", step="acquire")
        deploy.acquire(invocation, deps.runner)
        log.write("step_started", step="validate_settings")
        deploy.validate_settings(invocation, deps.runner)
        log.write("step_started", step="start", seeds="armed")
        deploy.start(invocation, deps.runner, seed_intent=True)
        deploy.wait_ready(READY_URL, deps.opener, deps.clock)
        _disarm_seeds(deps, public, seed_digest, sandbox_api_image)
        log.write("seeds_disarmed")
        log.write("step_started", step="bootstrap")
        deploy.run_bootstrap(invocation, public, secrets, deps.runner)
        deploy.restart_api_without_build(invocation, deps.runner)
        deploy.wait_ready(READY_URL, deps.opener, deps.clock)
        log.write("step_started", step="verify")
        deploy.run_verifier(
            invocation,
            admin_email=public.admin_email,
            seed_bundle_sha256=seed_digest,
            runner=deps.runner,
        )
    except deploy.StepFailed as exc:
        log.write("step_failed", code=exc.code)
        rollback.restore_or_quiesce(point, invocation, deps.runner)
        raise
    state = replace(
        state,
        bootstrap_complete=True,
        generated_sha256=_generated_fingerprints(deps.root),
        last_error_code=None,
    )
    for step in (
        Step.ACQUIRE,
        Step.VALIDATE,
        Step.START,
        Step.BOOTSTRAP,
        Step.VERIFY,
    ):
        state = with_step_completed(state, step)
    return state


def run_install(argv: Sequence[str], deps: Deps) -> int:
    """The complete injected flow; returns a process exit code."""
    parser = build_arg_parser()
    try:
        args = parser.parse_args(list(argv))
    except SystemExit:
        return EXIT_USAGE
    if args.reconfigure and (
        args.resume
        or args.local_build
        or args.prebuilt
        or args.answers
        or args.non_interactive
    ):
        deps.io.print_fn("reconfigure_flags_exclusive")
        return EXIT_USAGE

    state_path = deps.root / STATE_FILE
    log = InstallLog(deps.root / LOG_FILE)

    try:
        requested = _requested_mode(args)
        if args.manifest is not None and requested is InstallMode.PREBUILT:
            manifest_root = args.manifest.parent
        else:
            manifest_root = deps.root
        mode, manifest_path = resolve_install_mode(
            requested=requested, bundle_root=manifest_root
        )

        if args.check_only:
            deps.io.print_fn(f"check_ok mode={mode.value}")
            return EXIT_OK

        try:
            previous_state = load_state(state_path)
        except StateError as exc:
            deps.io.print_fn(str(exc))
            return EXIT_PREFLIGHT

        if previous_state is None and (deps.root / ENV_FILE).is_file() and not (
            args.dry_run
        ):
            # An unmanaged .env without state is someone else's deployment.
            deps.io.print_fn("unsupported_takeover_existing_env")
            return EXIT_PREFLIGHT

        if args.resume:
            if previous_state is None:
                deps.io.print_fn("resume_without_state")
                return EXIT_PREFLIGHT
            observed = ResumeInputs(
                release_id=previous_state.release_id,
                bundle_tree_sha256=previous_state.bundle_tree_sha256,
                source_context_tree_sha256=(
                    previous_state.source_context_tree_sha256
                ),
                image_digests=dict(previous_state.image_digests),
                seed_bundle_sha256=compute_seed_bundle_sha256(deps.root),
                generated_sha256=_generated_fingerprints(deps.root),
            )
            decision = decide_resume(previous_state, observed)
            if decision is ResumeDecision.STOP_MISMATCH:
                deps.io.print_fn("resume_stop_mismatch")
                return EXIT_PREFLIGHT
            public = previous_state.public_answers
            mode = public.mode
            if decision is ResumeDecision.REPROMPT_SECRETS:
                secrets = collect_secret_answers(
                    build_questions(),
                    io=deps.io,
                    non_interactive=args.non_interactive,
                    answers_path=args.answers,
                )
                seed_digest = previous_state.seed_bundle_sha256
                sandbox_image = None
                log.add_secret(secrets.admin_password)
                for value in secrets.provider_keys.values():
                    log.add_secret(value)
                new_state = _deploy_sequence(
                    deps, log, public, secrets, previous_state, seed_digest, sandbox_image
                )
                save_state(state_path, new_state)
            deps.io.print_fn(
                render_report(
                    public,
                    release_summary=_release_summary(public),
                    backup_dir=deps.root.parent / "lia-data" / "postgres-backups",
                    optional_unkeyed={},
                )
            )
            return EXIT_OK

        # Fresh install / dry-run path.
        public, secrets = _collect(deps, args, mode, manifest_path)
        log.add_secret(secrets.admin_password)
        for value in secrets.provider_keys.values():
            log.add_secret(value)

        generated = _load_or_generate_secrets(deps)
        sandbox_image = None
        seed_digest = _generate_artifacts(
            deps,
            public,
            seed_intent=True,
            generated=generated,
            sandbox_api_image=sandbox_image,
        )
        state = _fresh_state(public, seed_digest, deps.root)
        state = with_step_completed(
            with_step_completed(state, Step.PREFLIGHT), Step.QUESTIONS
        )
        state = with_step_completed(state, Step.GENERATE)
        save_state(state_path, state)
        log.write("artifacts_generated", mode=mode.value)

        if args.dry_run:
            deps.io.print_fn("dry_run_complete")
            return EXIT_OK

        state = _deploy_sequence(
            deps, log, public, secrets, state, seed_digest, sandbox_image
        )
        state = with_step_completed(state, Step.REPORT)
        save_state(state_path, state)
        deps.io.print_fn(
            render_report(
                public,
                release_summary=_release_summary(public),
                backup_dir=deps.root.parent / "lia-data" / "postgres-backups",
                optional_unkeyed={},
            )
        )
        return EXIT_OK

    except KeyboardInterrupt:
        log.write("interrupted")
        deps.io.print_fn("interrupted — resume with ./install.sh --resume")
        return EXIT_INTERRUPTED
    except (InstallInputError, EnvGenError, HostPathError, PreflightError) as exc:
        log.write("input_error", code=str(exc))
        deps.io.print_fn(str(exc))
        return EXIT_USAGE if isinstance(exc, InstallInputError) else EXIT_PREFLIGHT
    except deploy.StepFailed as exc:
        deps.io.print_fn(str(exc))
        return EXIT_STEP_FAILED


def _release_summary(public: PublicAnswers) -> str:
    if public.mode is InstallMode.PREBUILT and public.manifest_path is not None:
        return f"prebuilt ({public.manifest_path.name})"
    return "local build"


def _load_or_generate_secrets(deps: Deps) -> Mapping[str, str]:
    env_path = deps.root / ENV_FILE
    if env_path.is_file():
        return load_existing_generated_secrets(env_path, GENERATED_SECRET_KEYS)
    return generate_secrets()


def _real_deps() -> Deps:
    def _runner(
        argv: Sequence[str],
        *,
        stdin: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> deploy.CommandResult:
        completed = subprocess.run(
            list(argv),
            input=stdin,
            capture_output=True,
            text=True,
            env=dict(env) if env is not None else None,
        )
        return deploy.CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    class _RealClock:
        @staticmethod
        def monotonic() -> float:
            return time.monotonic()

        @staticmethod
        def sleep(seconds: float) -> None:
            time.sleep(seconds)

    def _opener(request: urllib.request.Request, *, timeout: float) -> object:
        return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310

    return Deps(
        root=Path.cwd(),
        io=IOAdapter(
            input_fn=input, getpass_fn=getpass.getpass, print_fn=print
        ),
        runner=_runner,
        opener=_opener,
        clock=_RealClock(),
    )


def main() -> int:
    return run_install(sys.argv[1:], _real_deps())


if __name__ == "__main__":
    sys.exit(main())
