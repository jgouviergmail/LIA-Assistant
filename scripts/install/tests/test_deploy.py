"""Deploy orchestration contract (B08/B12/B14).

A recording runner proves every argv byte: local builds, prebuilt pulls and
never builds, secrets travel ONLY through stdin, the API is recreated
without build after bootstrap (the real worker barrier), and every failure
raises a StepFailed whose text carries a stable code plus the resume
command and never a secret.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.install.compose import build_invocation
from scripts.install.deploy import (
    CommandResult,
    StepFailed,
    acquire,
    restart_api_without_build,
    run_bootstrap,
    run_verifier,
    start,
    validate_settings,
    wait_ready,
)
from scripts.install.model import (
    Exposure,
    InstallMode,
    PublicAnswers,
    SecretAnswers,
)

PASSWORD = "pw-CANARY-77!aa"
PROVIDER_KEY = "sk-CANARY-99!bb"
DIGEST = "e" * 64


class _Runner:
    def __init__(self, results: list[CommandResult] | None = None) -> None:
        self.calls: list[dict] = []
        self._results = list(results or [])

    def __call__(self, argv, *, stdin=None, env=None):
        self.calls.append({"argv": list(argv), "stdin": stdin, "env": env})
        if self._results:
            return self._results.pop(0)
        return CommandResult(returncode=0, stdout="", stderr="")


def _public(mode: InstallMode = InstallMode.LOCAL) -> PublicAnswers:
    return PublicAnswers(
        language="en",
        mode=mode,
        exposure=Exposure.LAN,
        admin_email="admin@ops.tld",
        admin_name="Ops",
        default_language="fr",
        observability=False,
        skill_sandbox=False,
        server_host="192.168.1.50",
        web_domain=None,
        api_domain=None,
        caddy_email=None,
        manifest_path=None,
    )


def _invocation(mode: InstallMode = InstallMode.LOCAL):
    return build_invocation(_public(mode), root=Path("."))


def test_local_acquire_builds_api_and_web() -> None:
    runner = _Runner()
    acquire(_invocation(InstallMode.LOCAL), runner)
    argv = runner.calls[0]["argv"]
    assert argv[-3:] == ["build", "api", "web"]


def test_prebuilt_acquire_pulls_and_never_builds() -> None:
    runner = _Runner()
    acquire(_invocation(InstallMode.PREBUILT), runner)
    argv = runner.calls[0]["argv"]
    assert argv[-3:] == ["pull", "api", "web"]
    assert "build" not in argv


def test_settings_validation_uses_the_exact_run_suffix() -> None:
    runner = _Runner()
    validate_settings(_invocation(), runner)
    argv = runner.calls[0]["argv"]
    expected_suffix = [
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
    assert argv[-len(expected_suffix) :] == expected_suffix


def test_start_uses_up_and_prebuilt_appends_no_build() -> None:
    local_runner = _Runner()
    start(_invocation(InstallMode.LOCAL), local_runner, seed_intent=True)
    assert local_runner.calls[0]["argv"][-3:] == ["up", "-d", "--remove-orphans"]

    prebuilt_runner = _Runner()
    start(_invocation(InstallMode.PREBUILT), prebuilt_runner, seed_intent=False)
    assert prebuilt_runner.calls[0]["argv"][-1] == "--no-build"


def test_bootstrap_sends_one_json_stdin_and_no_secret_argv() -> None:
    runner = _Runner()
    secrets = SecretAnswers(
        admin_password=PASSWORD,
        provider_keys={"deepseek": PROVIDER_KEY, "openai": "sk-o"},
    )
    run_bootstrap(_invocation(), _public(), secrets, runner)
    call = runner.calls[0]
    joined = " ".join(call["argv"])
    assert PASSWORD not in joined and PROVIDER_KEY not in joined
    expected_suffix = [
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
    assert call["argv"][-len(expected_suffix) :] == expected_suffix
    payload = json.loads(call["stdin"])
    assert payload["admin"]["email"] == "admin@ops.tld"
    assert payload["admin"]["password"] == PASSWORD
    assert payload["provider_keys"] == {"deepseek": PROVIDER_KEY, "openai": "sk-o"}


def test_bootstrap_publication_failure_exit_3_is_not_fatal() -> None:
    runner = _Runner([CommandResult(3, '{"status": "bootstrapped_publication_failed"}', "")])
    secrets = SecretAnswers(admin_password=PASSWORD, provider_keys={})
    run_bootstrap(_invocation(), _public(), secrets, runner)  # must not raise


@pytest.mark.parametrize(
    ("returncode", "code"),
    [(2, "bootstrap_input_error"), (1, "bootstrap_failed")],
)
def test_bootstrap_failures_carry_stable_codes_and_resume_hint(
    returncode: int, code: str
) -> None:
    runner = _Runner([CommandResult(returncode, "", "boom")])
    secrets = SecretAnswers(admin_password=PASSWORD, provider_keys={})
    with pytest.raises(StepFailed) as excinfo:
        run_bootstrap(_invocation(), _public(), secrets, runner)
    message = str(excinfo.value)
    assert code in message
    assert "./install.sh --resume" in message
    assert PASSWORD not in message


def test_api_recreation_is_forced_and_never_builds() -> None:
    runner = _Runner()
    restart_api_without_build(_invocation(), runner)
    argv = runner.calls[0]["argv"]
    assert argv[-6:] == [
        "up",
        "-d",
        "--no-deps",
        "--force-recreate",
        "--no-build",
        "api",
    ]


def test_verifier_appends_exactly_the_two_public_arguments() -> None:
    runner = _Runner()
    run_verifier(
        _invocation(),
        admin_email="admin@ops.tld",
        seed_bundle_sha256=DIGEST,
        runner=runner,
    )
    argv = runner.calls[0]["argv"]
    assert argv[-4:] == ["--admin-email", "admin@ops.tld", "--seed-bundle-sha256", DIGEST]
    assert "-T" in argv


def test_verifier_failure_is_a_stable_step_failure() -> None:
    runner = _Runner([CommandResult(4, '{"passed": false}', "")])
    with pytest.raises(StepFailed) as excinfo:
        run_verifier(
            _invocation(),
            admin_email="admin@ops.tld",
            seed_bundle_sha256=DIGEST,
            runner=runner,
        )
    assert "verify_failed" in str(excinfo.value)


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class _ReadyOpener:
    def __init__(self, statuses: list[object]) -> None:
        self._statuses = statuses
        self.urls: list[str] = []

    def __call__(self, request, *, timeout):
        self.urls.append(getattr(request, "full_url", str(request)))
        outcome = self._statuses.pop(0) if self._statuses else 200

        class _Resp:
            status = outcome

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        if isinstance(outcome, Exception):
            raise outcome
        return _Resp()


def test_wait_ready_polls_until_200() -> None:
    opener = _ReadyOpener([ConnectionError("down"), 503, 200])
    clock = _Clock()
    wait_ready("http://127.0.0.1:8000/ready", opener, clock, timeout_s=300)
    assert len(opener.urls) == 3


def test_wait_ready_times_out_with_a_stable_code() -> None:
    opener = _ReadyOpener([ConnectionError("down")] * 1000)
    clock = _Clock()
    with pytest.raises(StepFailed) as excinfo:
        wait_ready("http://127.0.0.1:8000/ready", opener, clock, timeout_s=30)
    assert "readiness_timeout" in str(excinfo.value)
    assert clock.now >= 30


# ---------------------------------------------------------------------------
# Reconfiguration (non-destructive lifecycle)
# ---------------------------------------------------------------------------


def _install_state(mode: InstallMode = InstallMode.LOCAL):
    from scripts.install.state import STATE_SCHEMA_VERSION, InstallState

    return InstallState(
        schema_version=STATE_SCHEMA_VERSION,
        installer_version="1",
        mode=mode,
        public_answers=_public(mode),
        release_id=None,
        bundle_tree_sha256=None,
        source_context_tree_sha256=None,
        image_digests={},
        seed_bundle_sha256=DIGEST,
        completed=(),
        attempts={},
        last_error_code=None,
        generated_sha256={},
        bootstrap_complete=True,
        project_name="lia-prod",
    )


def _candidates(tmp_path: Path) -> dict[Path, Path]:
    target = tmp_path / "docker-compose.install.yml"
    target.write_text("services: {}\n# current\n", encoding="utf-8")
    candidate = tmp_path / "docker-compose.install.yml.candidate"
    candidate.write_text("services: {}\n# candidate\n", encoding="utf-8")
    return {target: candidate}


def test_reconfigure_rejects_identity_changes_before_any_command(
    tmp_path: Path,
) -> None:
    import dataclasses

    from scripts.install.deploy import reconfigure_existing

    runner = _Runner()
    candidate = dataclasses.replace(_public(), admin_email="other@ops.tld")
    with pytest.raises(StepFailed) as excinfo:
        reconfigure_existing(
            current=_install_state(),
            candidate_public=candidate,
            candidate_files=_candidates(tmp_path),
            invocation=_invocation(),
            runner=runner,
        )
    assert "reconfigure_identity_changed" in str(excinfo.value)
    assert runner.calls == []


def test_reconfigure_validates_replaces_and_recreates_without_build(
    tmp_path: Path,
) -> None:
    import dataclasses

    from scripts.install.deploy import reconfigure_existing

    runner = _Runner()
    candidates = _candidates(tmp_path)
    target = next(iter(candidates))
    candidate_public = dataclasses.replace(_public(), observability=True)
    reconfigure_existing(
        current=_install_state(),
        candidate_public=candidate_public,
        candidate_files=candidates,
        invocation=_invocation(),
        runner=runner,
    )
    assert target.read_text(encoding="utf-8").endswith("# candidate\n")
    joined = [" ".join(call["argv"]) for call in runner.calls]
    assert any("config --quiet" in call for call in joined), "static validation ran"
    up_call = runner.calls[-1]["argv"]
    assert up_call[-4:] == ["up", "-d", "--no-build", "--remove-orphans"]
    all_joined = " ".join(joined)
    assert "bootstrap_install" not in all_joined
    assert "build" not in up_call, "no build COMMAND (only the --no-build flag)"
    backups = list(tmp_path.glob("*.backup.*"))
    assert backups, "previous file backed up"


def test_reconfigure_failure_restores_the_previous_files(tmp_path: Path) -> None:
    import dataclasses

    from scripts.install.deploy import reconfigure_existing

    class _FailingUpRunner(_Runner):
        def __call__(self, argv, *, stdin=None, env=None):
            result = super().__call__(argv, stdin=stdin, env=env)
            if argv[-1] == "--remove-orphans":
                return CommandResult(1, "", "boom")
            return result

    runner = _FailingUpRunner()
    candidates = _candidates(tmp_path)
    target = next(iter(candidates))
    with pytest.raises(StepFailed) as excinfo:
        reconfigure_existing(
            current=_install_state(),
            candidate_public=dataclasses.replace(_public(), observability=True),
            candidate_files=candidates,
            invocation=_invocation(),
            runner=runner,
        )
    assert "reconfigure_failed" in str(excinfo.value)
    assert target.read_text(encoding="utf-8").endswith("# current\n"), "restored"


def test_step_failed_carries_the_redactable_stderr_tail() -> None:
    """The compose error must reach the private log, never the console.

    ``acquire_failed`` alone is undiagnosable: the v1.30.1 qualification
    burned a full matrix run to learn nothing because the runner captured
    compose's stderr and ``_run_or_fail`` discarded it. The detail rides on
    the exception (newlines collapsed — install.log is one line per event)
    for ``__main__`` to write through the REDACTING log; ``str(exc)`` stays
    code + resume hint only, because the console is not redacted.
    """
    stderr = "line one\nservice \"api\" refused\nsecret sk-XYZ\n"
    runner = _Runner([CommandResult(1, "", stderr)])
    with pytest.raises(StepFailed) as excinfo:
        acquire(_invocation(), runner)

    assert excinfo.value.code == "acquire_failed"
    assert "refused" in excinfo.value.detail
    assert "\n" not in excinfo.value.detail  # one-line-per-event log format
    assert "refused" not in str(excinfo.value)  # console stays code-only


def test_step_failed_detail_is_bounded() -> None:
    """A 100k-line compose trace must not flood the log: keep the TAIL."""
    stderr = "x" * 100_000 + " THE-ACTUAL-ERROR"
    runner = _Runner([CommandResult(1, "", stderr)])
    with pytest.raises(StepFailed) as excinfo:
        acquire(_invocation(), runner)

    assert len(excinfo.value.detail) <= 4_100
    assert "THE-ACTUAL-ERROR" in excinfo.value.detail


class TestMaterializeSourceContext:
    """Local builds from the BUNDLE must materialize the embedded source.

    The compose file demands `./apps/api` and `.` + `apps/web/Dockerfile.prod`
    as build contexts; the bundle ships them inside
    `lia-self-host-source-context.tar.gz` and NOTHING extracted it — the
    state field `source_context_tree_sha256` existed, forever None. Measured
    on the v1.30.1 qualification: `acquire_failed` in 4 seconds on every
    local leg, because `docker compose build` had no context to read.
    """

    @staticmethod
    def _bundle_root(tmp_path):
        import io
        import tarfile

        root = tmp_path / "work"
        root.mkdir()
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, payload in (
                ("apps/api/Dockerfile.prod", b"FROM scratch\n"),
                ("apps/web/Dockerfile.prod", b"FROM scratch\n"),
                ("apps/api/requirements.txt", b"fastapi\n"),
            ):
                data = io.BytesIO(payload)
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                tar.addfile(info, data)
        (root / "lia-self-host-source-context.tar.gz").write_bytes(buf.getvalue())
        return root

    def test_extracts_the_context_when_apps_is_absent(self, tmp_path) -> None:
        from scripts.install.deploy import materialize_source_context

        root = self._bundle_root(tmp_path)
        digest = materialize_source_context(root)

        assert (root / "apps" / "api" / "Dockerfile.prod").is_file()
        assert (root / "apps" / "web" / "Dockerfile.prod").is_file()
        assert isinstance(digest, str) and len(digest) == 64

    def test_noop_on_a_git_clone(self, tmp_path) -> None:
        """apps/ already present (git clone): never touch it, return None."""
        from scripts.install.deploy import materialize_source_context

        root = self._bundle_root(tmp_path)
        (root / "apps").mkdir()
        sentinel = root / "apps" / "sentinel"
        sentinel.write_text("keep me")

        assert materialize_source_context(root) is None
        assert sentinel.read_text() == "keep me"

    def test_noop_without_the_archive(self, tmp_path) -> None:
        from scripts.install.deploy import materialize_source_context

        root = tmp_path / "bare"
        root.mkdir()
        assert materialize_source_context(root) is None

    def test_hostile_member_paths_are_refused(self, tmp_path) -> None:
        """A traversal member must abort the extraction, not escape the root."""
        import io
        import tarfile

        import pytest as _pytest

        from scripts.install.deploy import SourceContextError, materialize_source_context

        root = tmp_path / "work"
        root.mkdir()
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            payload = b"evil"
            info = tarfile.TarInfo("../outside.txt")
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
        (root / "lia-self-host-source-context.tar.gz").write_bytes(buf.getvalue())

        with _pytest.raises(SourceContextError):
            materialize_source_context(root)
        assert not (tmp_path / "outside.txt").exists()

    def test_extraction_is_idempotent_via_the_apps_guard(self, tmp_path) -> None:
        """A resumed install re-enters cleanly: second call is a no-op."""
        from scripts.install.deploy import materialize_source_context

        root = self._bundle_root(tmp_path)
        first = materialize_source_context(root)
        second = materialize_source_context(root)

        assert first is not None and second is None
