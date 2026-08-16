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
  re-prompts exactly the three secrets;
- the final report reaches the operator without any secret;
- Ctrl-C surfaces the exact resume command.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.install.deploy import CommandResult
from scripts.install.model import IOAdapter
from scripts.install.__main__ import (
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_PREFLIGHT,
    Deps,
    run_install,
)
from scripts.install.state import load_state
from scripts.install.tests.conftest import REPO_ROOT

PASSWORD = "Xx12!!abcdA9$Z"
ANSWERS = {
    "wizard_language": "en",
    "exposure": "lan",
    "server_host": "192.168.1.50",
    "admin_email": "admin@ops.tld",
    "admin_name": "Ops",
    "default_language": "fr",
    "observability": "no",
    "skill_sandbox": "no",
    "admin_password": PASSWORD,
    "provider_key_deepseek": "dk-CANARY-11",
    "provider_key_openai": "sk-CANARY-22",
}


class _Runner:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, argv, *, stdin=None, env=None):
        self.calls.append({"argv": list(argv), "stdin": stdin})
        return CommandResult(0, "", "")

    def joined(self) -> list[str]:
        return [" ".join(call["argv"]) for call in self.calls]


class _Opener:
    def __call__(self, request, *, timeout):
        class _Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

        return _Resp()


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class _IO:
    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self.printed: list[str] = []
        self._secrets = dict(secrets or {})
        self.secret_prompts: list[str] = []
        self.input_prompts: list[str] = []

    def adapter(self) -> IOAdapter:
        def _input(prompt: str) -> str:
            self.input_prompts.append(prompt)
            raise AssertionError(f"unexpected interactive prompt: {prompt}")

        def _getpass(prompt: str) -> str:
            self.secret_prompts.append(prompt)
            key = prompt[1:].split("]", 1)[0]
            return self._secrets[key]

        return IOAdapter(
            input_fn=_input, getpass_fn=_getpass, print_fn=self.printed.append
        )


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "bundle"
    seeds = root / "infrastructure" / "database" / "seeds"
    seeds.mkdir(parents=True)
    for seed in (REPO_ROOT / "infrastructure" / "database" / "seeds").glob("*.sql"):
        shutil.copy(seed, seeds / seed.name)
    shutil.copy(
        REPO_ROOT / "infrastructure" / "caddy" / "Caddyfile.template",
        _mk(root / "infrastructure" / "caddy") / "Caddyfile.template",
    )
    shutil.copy(REPO_ROOT / ".env.min.prod.example", root / ".env.min.prod.example")
    for name in ("docker-compose.prod.yml", "docker-compose.skill-sandbox.yml"):
        shutil.copy(REPO_ROOT / name, root / name)
    return root


def _mk(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _answers_file(root: Path, values: dict[str, str] | None = None) -> Path:
    path = root / "answers.env"
    payload = values if values is not None else ANSWERS
    path.write_text(
        "".join(f"{k}={v}\n" for k, v in payload.items()), encoding="utf-8"
    )
    import os

    if os.name == "posix":
        path.chmod(0o600)
    return path


def _deps(root: Path, io: _IO | None = None, runner: _Runner | None = None) -> Deps:
    return Deps(
        root=root,
        io=(io or _IO()).adapter(),
        runner=runner or _Runner(),
        opener=_Opener(),
        clock=_Clock(),
    )


def test_local_dry_run_generates_everything_and_starts_nothing(
    tmp_path: Path,
) -> None:
    root = _bundle(tmp_path)
    io = _IO()
    runner = _Runner()
    code = run_install(
        ["--dry-run", "--non-interactive", "--answers", str(_answers_file(root))],
        Deps(root=root, io=io.adapter(), runner=runner, opener=_Opener(), clock=_Clock()),
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
        Deps(root=root, io=io.adapter(), runner=runner, opener=_Opener(), clock=_Clock()),
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
    Compose file — and the sandbox image stayed on the base file's
    ``lia-api:local`` fallback, a tag a prebuilt host never has.
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
    assert "SKILLS_SCRIPT_SANDBOX_IMAGE=ghcr.io/example/lia/api@sha256:" in override


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


def test_resume_before_bootstrap_reprompts_exactly_three_secrets(
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
        }
    )
    runner = _Runner()
    code = run_install(
        ["--resume"],
        Deps(root=root, io=io.adapter(), runner=runner, opener=_Opener(), clock=_Clock()),
    )
    assert code == EXIT_OK, io.printed
    prompted = [p[1:].split("]", 1)[0] for p in io.secret_prompts]
    assert sorted(prompted) == [
        "admin_password",
        "provider_key_deepseek",
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


def test_reconfigure_flag_exclusions(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    io = _IO()
    code = run_install(["--reconfigure", "--resume"], _deps(root, io))
    assert code == 2
    assert "reconfigure_flags_exclusive" in io.printed


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
