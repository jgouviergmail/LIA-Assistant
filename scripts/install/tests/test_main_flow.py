"""Hermetic end-to-end installer flow (B01/B08/B12/B13/B14).

Injected runner + filesystem root + opener + clock prove, without Docker:

- a fresh all-default LOCAL dry run generates every artifact and starts
  nothing;
- an adjacent passed manifest flips the no-flag dry run to prebuilt while
  candidate/absent stay local;
- the full install sequence hits the exact ordered argv surface (acquire,
  settings validation, seeds armed start, disarm AFTER first /ready,
  bootstrap on stdin, forced API recreation, verifier);
- an existing unmanaged .env aborts as an unsupported takeover;
- resume without state stops; resume with matching state before bootstrap
  re-prompts exactly the secrets — the admin password and the provider keys,
  the optional Gemini key included (it may be skipped again);
- the final report reaches the operator without any secret, and names
  what the bootstrap reported degraded;
- Ctrl-C surfaces the exact resume command.

The ``--reconfigure`` flow has its own suite, ``test_reconfigure.py``; both
drive ``run_install`` with the fakes of ``flow_fakes.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.install.deploy import CommandResult
from scripts.install.__main__ import run_install
from scripts.install.run_context import EXIT_INTERRUPTED, EXIT_OK, EXIT_PREFLIGHT, Deps
from scripts.install.state import load_state
from scripts.install.tests.flow_fakes import (
    ANSWERS,
    PASSWORD,
    _answers_file,
    _bundle,
    _Clock,
    _deps,
    _IO,
    _Opener,
    _Runner,
)


def test_local_dry_run_generates_everything_and_starts_nothing(
    tmp_path: Path,
) -> None:
    root = _bundle(tmp_path)
    io = _IO()
    runner = _Runner()
    code = run_install(
        ["--dry-run", "--non-interactive", "--answers", str(_answers_file(root))],
        Deps(
            root=root, io=io.adapter(), runner=runner, opener=_Opener(), clock=_Clock()
        ),
    )
    assert code == EXIT_OK, io.printed
    assert (root / ".env").is_file()
    assert (root / "docker-compose.install.yml").is_file()
    assert (root / ".install-state.json").is_file()
    assert runner.calls == [], "dry run must start nothing"
    env_body = (root / ".env").read_text(encoding="utf-8")
    assert "dk-CANARY-11" not in env_body and PASSWORD not in env_body
    state = load_state(root / ".install-state.json")
    assert state is not None and not state.bootstrap_complete
    assert "dry_run_complete" in io.printed


def test_full_local_install_hits_the_exact_ordered_surface(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    io = _IO()
    runner = _Runner()
    code = run_install(
        ["--non-interactive", "--answers", str(_answers_file(root))],
        Deps(
            root=root, io=io.adapter(), runner=runner, opener=_Opener(), clock=_Clock()
        ),
    )
    assert code == EXIT_OK, io.printed
    joined = runner.joined()
    order = [
        next(i for i, call in enumerate(joined) if needle in call)
        for needle in (
            "build api web",
            "scripts.validate_settings",
            "up -d --remove-orphans",
            "scripts.data.bootstrap_install",
            "--force-recreate --no-build api",
            "scripts.data.verify_installation",
        )
    ]
    assert order == sorted(order), f"steps out of order: {joined}"
    bootstrap_call = next(
        call for call in runner.calls if "bootstrap_install" in " ".join(call["argv"])
    )
    payload = json.loads(bootstrap_call["stdin"])
    assert payload["provider_keys"] == {
        "deepseek": "dk-CANARY-11",
        "openai": "sk-CANARY-22",
    }
    override = (root / "docker-compose.install.yml").read_text(encoding="utf-8")
    assert "APPLY_SEEDS=false" in override, "seeds disarmed after first /ready"
    state = load_state(root / ".install-state.json")
    assert state is not None and state.bootstrap_complete
    report = "\n".join(io.printed)
    assert "http://192.168.1.50:3000" in report
    assert PASSWORD not in report and "dk-CANARY-11" not in report


def test_full_prebuilt_install_pins_images_and_sandbox(tmp_path: Path) -> None:
    """PREBUILT mode writes the digest lock and derives the sandbox image.

    Both were rendered by tested-but-unwired code until the v1.30.1
    qualification, take two: ``build_invocation`` referenced
    ``docker-compose.images.yml`` that nothing wrote (``render_image_lock``
    had ZERO call sites), so every prebuilt install died on a missing
    Compose file — and the sandbox image stayed on the base file's local
    fallback, a tag a prebuilt host never has. Since ADR-327 lot 2 the
    sandbox runs on the release's OWN sandbox image, pulled by its digest.
    """
    from scripts.install.tests.test_preflight import _manifest_payload

    root = _bundle(tmp_path)
    (root / "lia-self-host-manifest.json").write_text(
        json.dumps(_manifest_payload("passed")), encoding="utf-8"
    )
    answers = dict(ANSWERS, skill_sandbox="yes")
    io = _IO()
    runner = _Runner()
    code = run_install(
        [
            "--prebuilt",
            "--non-interactive",
            "--answers",
            str(_answers_file(root, answers)),
        ],
        _deps(root, io, runner),
    )
    assert code == EXIT_OK

    lock = (root / "docker-compose.images.yml").read_text(encoding="utf-8")
    assert "  api:\n    image: ghcr.io/example/lia/api@sha256:" in lock
    assert "  web:\n    image: ghcr.io/example/lia/web@sha256:" in lock

    joined = runner.joined()
    assert any(
        "docker-compose.images.yml" in line and line.endswith("pull api web")
        for line in joined
    ), joined
    override = (root / "docker-compose.install.yml").read_text(encoding="utf-8")
    assert "SKILLS_SCRIPT_SANDBOX_IMAGE=ghcr.io/example/lia/sandbox@sha256:" in override
    assert any(
        line.startswith("docker pull ghcr.io/example/lia/sandbox@sha256:")
        for line in joined
    ), joined


def test_unmanaged_env_aborts_as_takeover(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    (root / ".env").write_text("THEIRS=1\n", encoding="utf-8")
    io = _IO()
    code = run_install(
        ["--non-interactive", "--answers", str(_answers_file(root))],
        _deps(root, io),
    )
    assert code == EXIT_PREFLIGHT
    assert "unsupported_takeover_existing_env" in io.printed
    assert (root / ".env").read_text(encoding="utf-8") == "THEIRS=1\n"


def test_resume_without_state_stops(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    io = _IO()
    code = run_install(["--resume"], _deps(root, io))
    assert code == EXIT_PREFLIGHT
    assert "resume_without_state" in io.printed


def test_resume_before_bootstrap_reprompts_exactly_the_secrets(
    tmp_path: Path,
) -> None:
    root = _bundle(tmp_path)
    dry_io = _IO()
    assert (
        run_install(
            ["--dry-run", "--non-interactive", "--answers", str(_answers_file(root))],
            _deps(root, dry_io),
        )
        == EXIT_OK
    )
    io = _IO(
        {
            "admin_password": PASSWORD,
            "provider_key_deepseek": "dk-CANARY-11",
            "provider_key_openai": "sk-CANARY-22",
            # The optional key is asked again, and may be skipped again.
            "provider_key_gemini": "",
        }
    )
    runner = _Runner()
    code = run_install(
        ["--resume"],
        Deps(
            root=root, io=io.adapter(), runner=runner, opener=_Opener(), clock=_Clock()
        ),
    )
    assert code == EXIT_OK, io.printed
    prompted = [p[1:].split("]", 1)[0] for p in io.secret_prompts]
    assert sorted(prompted) == [
        "admin_password",
        "provider_key_deepseek",
        "provider_key_gemini",
        "provider_key_openai",
    ]
    assert io.input_prompts == [], "resume must never re-ask public answers"
    state = load_state(root / ".install-state.json")
    assert state is not None and state.bootstrap_complete


def test_keyboard_interrupt_prints_the_resume_command(tmp_path: Path) -> None:
    root = _bundle(tmp_path)

    class _InterruptingRunner(_Runner):
        def __call__(self, argv, *, stdin=None, env=None):
            raise KeyboardInterrupt

    io = _IO()
    code = run_install(
        ["--non-interactive", "--answers", str(_answers_file(root))],
        Deps(
            root=root,
            io=io.adapter(),
            runner=_InterruptingRunner(),
            opener=_Opener(),
            clock=_Clock(),
        ),
    )
    assert code == EXIT_INTERRUPTED
    assert any("./install.sh --resume" in line for line in io.printed)


def test_check_only_reports_the_resolved_mode_and_touches_nothing(
    tmp_path: Path,
) -> None:
    root = _bundle(tmp_path)
    io = _IO()
    runner = _Runner()
    code = run_install(["--check-only"], _deps(root, io, runner))
    assert code == EXIT_OK
    assert any("check_ok mode=local" in line for line in io.printed)
    assert runner.calls == []
    assert not (root / ".env").exists()
    assert not (root / ".install-state.json").exists()


class _BootstrapReportingRunner(_Runner):
    """The bootstrap prints a log line, then its one result document."""

    REPORT = {"semantic_search": "gemini", "voice_tts": "elevenlabs"}

    def __call__(self, argv, *, stdin=None, env=None):
        result = super().__call__(argv, stdin=stdin, env=env)
        if "scripts.data.bootstrap_install" in argv:
            stdout = "\n".join(
                [
                    json.dumps({"event": "admin_ready", "level": "info"}),
                    json.dumps(
                        {"status": "bootstrapped", "optional_unkeyed": self.REPORT}
                    ),
                ]
            )
            return CommandResult(0, stdout, "")
        return result


def test_the_report_names_what_the_bootstrap_left_degraded(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    io = _IO()
    code = run_install(
        ["--non-interactive", "--answers", str(_answers_file(root))],
        _deps(root, io, _BootstrapReportingRunner()),
    )
    assert code == EXIT_OK, io.printed
    report = "\n".join(io.printed)
    assert "semantic_search (gemini)" in report
    assert "voice_tts (elevenlabs)" in report
    state = load_state(root / ".install-state.json")
    assert state is not None
    assert state.degraded_capabilities == _BootstrapReportingRunner.REPORT


def test_a_given_gemini_key_reaches_the_bootstrap(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    runner = _Runner()
    answers = dict(ANSWERS, provider_key_gemini="gm-CANARY-33")
    code = run_install(
        ["--non-interactive", "--answers", str(_answers_file(root, answers))],
        _deps(root, _IO(), runner),
    )
    assert code == EXIT_OK
    call = next(c for c in runner.calls if "bootstrap_install" in " ".join(c["argv"]))
    assert json.loads(call["stdin"])["provider_keys"]["gemini"] == "gm-CANARY-33"
    assert "gm-CANARY-33" not in (root / ".env").read_text(encoding="utf-8")


def test_a_resume_that_reran_nothing_claims_no_stale_list(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    assert (
        run_install(
            ["--non-interactive", "--answers", str(_answers_file(root))],
            _deps(root, _IO(), _BootstrapReportingRunner()),
        )
        == EXIT_OK
    )
    io = _IO()
    assert run_install(["--resume"], _deps(root, io, _Runner())) == EXIT_OK, io.printed
    report = "\n".join(io.printed)
    # Keys may have been added in the Admin UI since: it is the authority.
    assert "semantic_search (gemini)" not in report
    assert "the Admin UI (LLM Configuration) shows" in report


def test_rerun_keeps_existing_grafana_password_before_acquire(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    answers = _answers_file(root, {**ANSWERS, "observability": "yes"})
    arguments = ["--non-interactive", "--answers", str(answers)]
    assert run_install(["--dry-run", *arguments], _deps(root, _IO())) == EXIT_OK

    def password() -> str:
        for line in (root / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith("GRAFANA_ADMIN_PASSWORD="):
                return line.partition("=")[2]
        return ""

    original = password()
    assert original

    class StopBeforeAcquire(_Runner):
        acquired = False

        def __call__(self, argv, *, stdin=None, env=None):
            if list(argv[-3:]) == ["build", "api", "web"]:
                self.acquired = True
                unchanged = password() == original
                assert unchanged
                raise KeyboardInterrupt
            return super().__call__(argv, stdin=stdin, env=env)

    runner = StopBeforeAcquire()
    deps = Deps(root=root, io=_IO().adapter(), runner=runner, opener=_Opener(), clock=_Clock())
    assert run_install(arguments, deps) == EXIT_INTERRUPTED
    assert runner.acquired
    unchanged = password() == original
    assert unchanged
