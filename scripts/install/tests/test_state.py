"""Versioned installer state and fail-closed resume contract (B13).

- state writes are atomic and private; a torn write can never half-commit;
- an unknown schema or unparsable file is a stable STOP code — no repair;
- every PublicAnswers field round-trips; secrets are structurally absent;
- fingerprint mismatches (release, bundle tree, source-context tree, image
  digests, seed bundle, generated files) each stop the resume;
- bootstrap incomplete → REPROMPT_SECRETS; bootstrap complete → never.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

import pytest

from scripts.install.model import Exposure, InstallMode, PublicAnswers
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
    with_attempt,
    with_step_completed,
)

SECRET_CANARY = "pw-CANARY-!$&{}[]"


def _public() -> PublicAnswers:
    return PublicAnswers(
        language="fr",
        mode=InstallMode.PREBUILT,
        exposure=Exposure.CADDY,
        admin_email="admin@ops.tld",
        admin_name="Ops",
        default_language="zh-CN",
        observability=True,
        skill_sandbox=True,
        server_host=None,
        web_domain="lia.example.org",
        api_domain="api.example.org",
        caddy_email="acme@example.org",
        manifest_path=Path("lia-self-host-manifest.json"),
    )


def _state(**overrides: object) -> InstallState:
    base = InstallState(
        schema_version=STATE_SCHEMA_VERSION,
        installer_version="1",
        mode=InstallMode.PREBUILT,
        public_answers=_public(),
        release_id="v1.28.0",
        bundle_tree_sha256="b" * 64,
        source_context_tree_sha256="c" * 64,
        image_digests={"api": "sha256:" + "a" * 64, "web": "sha256:" + "d" * 64},
        seed_bundle_sha256="e" * 64,
        completed=(Step.PREFLIGHT, Step.QUESTIONS),
        attempts={Step.QUESTIONS: 1},
        last_error_code=None,
        generated_sha256={".env": "f" * 64},
        bootstrap_complete=False,
        project_name="lia-prod",
    )
    return dataclasses.replace(base, **overrides)  # type: ignore[arg-type]


def _observed(state: InstallState) -> ResumeInputs:
    return ResumeInputs(
        release_id=state.release_id,
        bundle_tree_sha256=state.bundle_tree_sha256,
        source_context_tree_sha256=state.source_context_tree_sha256,
        image_digests=dict(state.image_digests),
        seed_bundle_sha256=state.seed_bundle_sha256,
        generated_sha256=dict(state.generated_sha256),
    )


def test_round_trip_preserves_every_field(tmp_path: Path) -> None:
    path = tmp_path / ".install-state.json"
    state = _state()
    save_state(path, state)
    loaded = load_state(path)
    assert loaded == state
    assert loaded is not None and loaded.public_answers == _public()
    if os.name == "posix":
        assert (path.stat().st_mode & 0o777) == 0o600


def test_missing_state_loads_as_none(tmp_path: Path) -> None:
    assert load_state(tmp_path / "absent.json") is None


def test_atomic_save_survives_a_failed_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / ".install-state.json"
    save_state(path, _state())
    before = path.read_bytes()

    def _boom(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError):
        save_state(path, _state(project_name="other"))
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ("{not json", "state_parse_error"),
        (json.dumps({"schema_version": 999}), "state_schema_unsupported"),
    ],
)
def test_broken_state_is_a_stable_stop_code(
    tmp_path: Path, content: str, code: str
) -> None:
    path = tmp_path / ".install-state.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(StateError) as excinfo:
        load_state(path)
    assert str(excinfo.value) == code


def test_state_json_is_structurally_secret_free(tmp_path: Path) -> None:
    path = tmp_path / ".install-state.json"
    save_state(path, _state())
    payload = path.read_text(encoding="utf-8")
    lowered = payload.lower()
    for forbidden in ("password", "provider_key", "secret_answers", "fernet"):
        assert forbidden not in lowered
    assert SECRET_CANARY not in payload
    field_names = {f.name for f in dataclasses.fields(InstallState)}
    assert not any("password" in name or "key" in name for name in field_names)


def test_helpers_are_immutable_and_track_attempts() -> None:
    state = _state()
    advanced = with_step_completed(state, Step.GENERATE)
    assert Step.GENERATE in advanced.completed
    assert Step.GENERATE not in state.completed
    retried = with_attempt(state, Step.START)
    assert retried.attempts[Step.START] == 1
    assert with_attempt(retried, Step.START).attempts[Step.START] == 2


def test_resume_matching_state_before_bootstrap_reprompts_secrets() -> None:
    state = _state(bootstrap_complete=False)
    assert decide_resume(state, _observed(state)) is ResumeDecision.REPROMPT_SECRETS


def test_resume_after_bootstrap_never_asks_secrets() -> None:
    state = _state(bootstrap_complete=True)
    assert decide_resume(state, _observed(state)) is ResumeDecision.CONTINUE


@pytest.mark.parametrize(
    "mutation",
    [
        {"release_id": "v9.9.9"},
        {"bundle_tree_sha256": "0" * 64},
        {"source_context_tree_sha256": "0" * 64},
        {"image_digests": {"api": "sha256:" + "0" * 64}},
        {"seed_bundle_sha256": "0" * 64},
        {"generated_sha256": {".env": "0" * 64}},
    ],
)
def test_any_fingerprint_mismatch_stops_the_resume(mutation: dict) -> None:
    state = _state(bootstrap_complete=True)
    observed = dataclasses.replace(_observed(state), **mutation)
    assert decide_resume(state, observed) is ResumeDecision.STOP_MISMATCH
