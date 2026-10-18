"""Deploy orchestration contract (B08/B12/B14).

A recording runner proves every argv byte: local builds, prebuilt pulls and
never builds, secrets travel ONLY through stdin, the API is recreated
without build after bootstrap (the real worker barrier), and every failure
raises a StepFailed whose text carries a stable code plus the resume
command and never a secret. The reconfiguration primitives have their own
suite, ``test_deploy_reconfigure.py``; both use the fakes of ``deploy_fakes.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.install.compose import SKILL_SANDBOX_LOCAL_IMAGE
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
from scripts.install.model import InstallMode, SecretAnswers
from scripts.install.tests.deploy_fakes import DIGEST, _invocation, _public, _Runner

PASSWORD = "pw-CANARY-77!aa"
PROVIDER_KEY = "sk-CANARY-99!bb"


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
    assert len(runner.calls) == 1


def test_prebuilt_acquire_pulls_the_sandbox_by_its_locked_digest() -> None:
    runner = _Runner()
    reference = "ghcr.io/o/r/sandbox@sha256:" + "a" * 64
    acquire(_invocation(InstallMode.PREBUILT), runner, sandbox_image=reference)
    assert runner.calls[1]["argv"] == ["docker", "pull", reference]
    assert not any("build" in call["argv"] for call in runner.calls)


def test_local_acquire_builds_the_sandbox_under_the_base_files_tag() -> None:
    runner = _Runner()
    root = Path("/srv/lia")
    acquire(_invocation(InstallMode.LOCAL), runner, sandbox_build_root=root)
    assert runner.calls[1]["argv"] == [
        "docker",
        "build",
        "-t",
        SKILL_SANDBOX_LOCAL_IMAGE,
        "-f",
        str(root / "apps/api/Dockerfile.sandbox"),
        str(root / "apps/api"),
    ]


def test_no_sandbox_selected_obtains_no_sandbox_image() -> None:
    runner = _Runner()
    acquire(_invocation(InstallMode.LOCAL), runner)
    assert len(runner.calls) == 1


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


def test_the_degraded_report_is_the_result_line_among_log_lines() -> None:
    from scripts.install.deploy import bootstrap_degraded_report

    stdout = "\n".join(
        [
            json.dumps({"event": "admin_ready", "level": "info"}),
            json.dumps({"status": "bootstrapped", "optional_unkeyed": {"voice_tts": "elevenlabs"}}),
            # A log line printed after the result, carrying a `status` of its own.
            json.dumps({"event": "cache_published", "status": "ok"}),
        ]
    )
    assert bootstrap_degraded_report(stdout) == {"voice_tts": "elevenlabs"}


def test_an_unreadable_bootstrap_output_reports_no_list() -> None:
    from scripts.install.deploy import bootstrap_degraded_report

    assert bootstrap_degraded_report("") is None
    assert bootstrap_degraded_report("Traceback (most recent call last):\n  boom") is None
    assert bootstrap_degraded_report(json.dumps({"status": "bootstrapped"})) is None


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
        """A git clone ships no archive: never touch its apps/, return None."""
        from scripts.install.deploy import materialize_source_context

        root = tmp_path / "clone"
        (root / "apps").mkdir(parents=True)
        sentinel = root / "apps" / "sentinel"
        sentinel.write_text("keep me")

        assert materialize_source_context(root) is None
        assert sentinel.read_text() == "keep me"

    def test_extracts_despite_a_pre_created_host_path_scaffold(
        self, tmp_path
    ) -> None:
        """prepare_host_paths pre-creates apps/api/config BEFORE this step.

        The v1.30.1 qualification run proved the old ``apps/ exists`` guard
        fatal: `_generate_artifacts` mkdir'ed `apps/api/config` (a bind-mount
        requirement), the guard concluded "git clone" and skipped extraction,
        and `compose build` died on a missing `apps/web`. An empty scaffold
        is not a source tree — only the archive's absence means "clone".
        """
        from scripts.install.deploy import materialize_source_context

        root = self._bundle_root(tmp_path)
        (root / "apps" / "api" / "config").mkdir(parents=True)

        digest = materialize_source_context(root)

        assert isinstance(digest, str) and len(digest) == 64
        assert (root / "apps" / "web" / "Dockerfile.prod").is_file()
        assert (root / "apps" / "api" / "config").is_dir()

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

    def test_reextraction_is_deterministic_on_resume(self, tmp_path) -> None:
        """A resumed install re-extracts and lands on the SAME tree digest.

        Re-extraction (not a skip) is deliberate: it self-heals a partial
        extraction after a mid-step crash, and its determinism is what makes
        the recorded ``source_context_tree_sha256`` trustworthy.
        """
        from scripts.install.deploy import materialize_source_context

        root = self._bundle_root(tmp_path)
        first = materialize_source_context(root)
        second = materialize_source_context(root)

        assert first is not None and second == first
