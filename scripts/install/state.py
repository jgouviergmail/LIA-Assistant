"""Versioned installer state and fail-closed resume (B13).

State stores ONLY non-secret facts plus SHA-256 fingerprints. Writes are
atomic (sibling temp, fsync, ``os.replace``) and private. A parse error,
unknown schema, or any fingerprint mismatch is a stable STOP — the resume
path never repairs and never touches Compose after a mismatch. Secrets are
STRUCTURALLY absent: ``InstallState`` has no field that could carry one.
"""

from __future__ import annotations

import dataclasses
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from scripts.install.model import Exposure, InstallMode, PublicAnswers

STATE_SCHEMA_VERSION = 1


class Step(str, Enum):
    """Ordered installer steps (resume granularity)."""

    PREFLIGHT = "preflight"
    QUESTIONS = "questions"
    GENERATE = "generate"
    ACQUIRE = "acquire"
    VALIDATE = "validate"
    START = "start"
    BOOTSTRAP = "bootstrap"
    VERIFY = "verify"
    REPORT = "report"


class ResumeDecision(str, Enum):
    """What a resume may do given the observed world."""

    CONTINUE = "continue"
    REPROMPT_SECRETS = "reprompt_secrets"
    STOP_MISMATCH = "stop_mismatch"


class StateError(ValueError):
    """Unusable state file (stable value-free code); never auto-repaired."""


@dataclass(frozen=True)
class InstallState:
    """Everything a resume may trust — non-secret facts and fingerprints."""

    schema_version: int
    installer_version: str
    mode: InstallMode
    public_answers: PublicAnswers
    release_id: str | None
    bundle_tree_sha256: str | None
    source_context_tree_sha256: str | None
    image_digests: Mapping[str, str]
    seed_bundle_sha256: str
    completed: tuple[Step, ...]
    attempts: Mapping[Step, int]
    last_error_code: str | None
    generated_sha256: Mapping[str, str]
    bootstrap_complete: bool
    project_name: str


@dataclass(frozen=True)
class ResumeInputs:
    """What the resuming installer observes on the host right now."""

    release_id: str | None
    bundle_tree_sha256: str | None
    source_context_tree_sha256: str | None
    image_digests: Mapping[str, str] = field(default_factory=dict)
    seed_bundle_sha256: str = ""
    generated_sha256: Mapping[str, str] = field(default_factory=dict)


def _public_to_payload(public: PublicAnswers) -> dict[str, object]:
    return {
        "language": public.language,
        "mode": public.mode.value,
        "exposure": public.exposure.value,
        "admin_email": public.admin_email,
        "admin_name": public.admin_name,
        "default_language": public.default_language,
        "observability": public.observability,
        "skill_sandbox": public.skill_sandbox,
        "server_host": public.server_host,
        "web_domain": public.web_domain,
        "api_domain": public.api_domain,
        "caddy_email": public.caddy_email,
        "manifest_path": (
            str(public.manifest_path) if public.manifest_path is not None else None
        ),
    }


def _payload_to_public(payload: Mapping[str, object]) -> PublicAnswers:
    manifest_path = payload.get("manifest_path")
    return PublicAnswers(
        language=str(payload["language"]),
        mode=InstallMode(str(payload["mode"])),
        exposure=Exposure(str(payload["exposure"])),
        admin_email=str(payload["admin_email"]),
        admin_name=str(payload["admin_name"]),
        default_language=str(payload["default_language"]),
        observability=bool(payload["observability"]),
        skill_sandbox=bool(payload["skill_sandbox"]),
        server_host=(
            str(payload["server_host"]) if payload.get("server_host") else None
        ),
        web_domain=str(payload["web_domain"]) if payload.get("web_domain") else None,
        api_domain=str(payload["api_domain"]) if payload.get("api_domain") else None,
        caddy_email=(
            str(payload["caddy_email"]) if payload.get("caddy_email") else None
        ),
        manifest_path=Path(str(manifest_path)) if manifest_path else None,
    )


def save_state(path: Path, state: InstallState) -> None:
    """Atomically persist the state as private JSON."""
    payload = {
        "schema_version": state.schema_version,
        "installer_version": state.installer_version,
        "mode": state.mode.value,
        "public_answers": _public_to_payload(state.public_answers),
        "release_id": state.release_id,
        "bundle_tree_sha256": state.bundle_tree_sha256,
        "source_context_tree_sha256": state.source_context_tree_sha256,
        "image_digests": dict(state.image_digests),
        "seed_bundle_sha256": state.seed_bundle_sha256,
        "completed": [step.value for step in state.completed],
        "attempts": {step.value: count for step, count in state.attempts.items()},
        "last_error_code": state.last_error_code,
        "generated_sha256": dict(state.generated_sha256),
        "bootstrap_complete": state.bootstrap_complete,
        "project_name": state.project_name,
    }
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    if os.name == "posix":
        tmp.chmod(0o600)
    try:
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def load_state(path: Path) -> InstallState | None:
    """Load a previous state; absent file means a fresh install.

    Raises:
        StateError: ``state_parse_error`` or ``state_schema_unsupported`` —
            the caller must STOP, never repair.
    """
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StateError("state_parse_error") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != (
        STATE_SCHEMA_VERSION
    ):
        raise StateError("state_schema_unsupported")
    try:
        return InstallState(
            schema_version=int(payload["schema_version"]),
            installer_version=str(payload["installer_version"]),
            mode=InstallMode(str(payload["mode"])),
            public_answers=_payload_to_public(payload["public_answers"]),
            release_id=(
                str(payload["release_id"]) if payload.get("release_id") else None
            ),
            bundle_tree_sha256=(
                str(payload["bundle_tree_sha256"])
                if payload.get("bundle_tree_sha256")
                else None
            ),
            source_context_tree_sha256=(
                str(payload["source_context_tree_sha256"])
                if payload.get("source_context_tree_sha256")
                else None
            ),
            image_digests=dict(payload["image_digests"]),
            seed_bundle_sha256=str(payload["seed_bundle_sha256"]),
            completed=tuple(Step(value) for value in payload["completed"]),
            attempts={
                Step(key): int(value)
                for key, value in dict(payload["attempts"]).items()
            },
            last_error_code=(
                str(payload["last_error_code"])
                if payload.get("last_error_code")
                else None
            ),
            generated_sha256=dict(payload["generated_sha256"]),
            bootstrap_complete=bool(payload["bootstrap_complete"]),
            project_name=str(payload["project_name"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise StateError("state_parse_error") from exc


def with_step_completed(state: InstallState, step: Step) -> InstallState:
    """A copy with ``step`` recorded as completed (idempotent)."""
    if step in state.completed:
        return state
    return dataclasses.replace(state, completed=(*state.completed, step))


def with_attempt(state: InstallState, step: Step) -> InstallState:
    """A copy with ``step``'s attempt counter incremented."""
    attempts = dict(state.attempts)
    attempts[step] = attempts.get(step, 0) + 1
    return dataclasses.replace(state, attempts=attempts)


def decide_resume(state: InstallState, observed: ResumeInputs) -> ResumeDecision:
    """Fail-closed resume decision.

    Any fingerprint divergence between the recorded state and the observed
    world is a STOP — no repair, no Compose action. A matching world with an
    incomplete bootstrap re-prompts exactly the ephemeral secrets; a
    complete bootstrap never asks for a secret again.
    """
    checks = (
        (state.release_id, observed.release_id),
        (state.bundle_tree_sha256, observed.bundle_tree_sha256),
        (state.source_context_tree_sha256, observed.source_context_tree_sha256),
        (dict(state.image_digests), dict(observed.image_digests)),
        (state.seed_bundle_sha256, observed.seed_bundle_sha256),
        (dict(state.generated_sha256), dict(observed.generated_sha256)),
    )
    for recorded, current in checks:
        if recorded != current:
            return ResumeDecision.STOP_MISMATCH
    if not state.bootstrap_complete:
        return ResumeDecision.REPROMPT_SECRETS
    return ResumeDecision.CONTINUE
