"""Hermetic reconfiguration flow (``--reconfigure``, ADR-215).

Injected runner + filesystem root + opener + clock prove, without Docker, that
``--reconfigure`` swaps the routing files of a bootstrapped install without
seeds, bootstrap or image build, keeps the generated secrets and the
operator's own ``.env`` lines and values, reaches Caddy from LAN, makes Caddy
reread changed routes, stops the services of a profile turned off, and puts
the previous files and stack back — verified ready — when the new one does
not come back or the operator interrupts it, a hang-up and a termination
included; an answer-derived value that would change is listed (a secret
hidden) and replaced only once confirmed; turning the sandbox on writes the
Docker socket's group; an interrupt at a question changes nothing; a failed
restore logs the candidate's own failure first and prints the commands that
bring the previous stack back.
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path

import pytest

from scripts.install.__main__ import run_install
from scripts.install.deploy import CommandResult
from scripts.install.model import IOAdapter
from scripts.install.reconfigure import RECONFIGURE_DIR
from scripts.install.run_context import (
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_PREFLIGHT,
    EXIT_STEP_FAILED,
    EXIT_USAGE,
    Deps,
)
from scripts.install.state import load_state
from scripts.install.tests.flow_fakes import (
    ANSWERS,
    _answers_file,
    _bundle,
    _Clock,
    _deps,
    _IO,
    _Opener,
    _Runner,
)


def test_reconfigure_flag_exclusions(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    io = _IO()
    code = run_install(["--reconfigure", "--resume"], _deps(root, io))
    assert code == 2
    assert "reconfigure_flags_exclusive" in io.printed


def _installed(tmp_path: Path) -> Path:
    root = _bundle(tmp_path)
    assert (
        run_install(
            ["--non-interactive", "--answers", str(_answers_file(root))],
            _deps(root, _IO(), _Runner()),
        )
        == EXIT_OK
    )
    return root


def _env_values(root: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (root / ".env").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    return values


def test_reconfigure_without_state_stops(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    io = _IO(public={})
    code = run_install(["--reconfigure"], _deps(root, io))
    assert code == EXIT_PREFLIGHT
    assert "reconfigure_without_state" in io.printed


def test_reconfigure_before_the_bootstrap_points_at_resume(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    assert (
        run_install(
            ["--dry-run", "--non-interactive", "--answers", str(_answers_file(root))],
            _deps(root, _IO()),
        )
        == EXIT_OK
    )
    io = _IO(public={})
    code = run_install(["--reconfigure"], _deps(root, io))
    assert code == EXIT_PREFLIGHT
    assert any("./install.sh --resume" in line for line in io.printed)


def test_reconfigure_swaps_routing_without_seeds_bootstrap_or_build(
    tmp_path: Path,
) -> None:
    root = _installed(tmp_path)
    before = _env_values(root)
    with (root / ".env").open("a", encoding="utf-8") as env:
        env.write("OPERATOR_TUNED_LIMIT=42\n")
    io = _IO(public={**CONFIRM, "observability": "yes"})
    runner = _Runner()
    code = run_install(["--reconfigure"], _deps(root, io, runner))
    assert code == EXIT_OK, io.printed
    assert any(prompt.startswith("[apply_env_changes]") for prompt in io.input_prompts)
    assert any("GRAFANA_ADMIN_PASSWORD: (empty) -> (hidden)" in line for line in io.printed)

    joined = runner.joined()
    assert not any("bootstrap_install" in line for line in joined)
    assert not any(line.endswith("build api web") for line in joined)
    assert any("--env-file" in line and line.endswith("config --quiet") for line in joined)
    assert any(
        "--profile observability" in line and line.endswith("up -d --no-build --remove-orphans")
        for line in joined
    ), joined

    after = _env_values(root)
    for key in ("SECRET_KEY", "FERNET_KEY", "POSTGRES_PASSWORD", "REDIS_PASSWORD"):
        assert after[key] == before[key], f"{key} must never rotate"
    assert after["OPERATOR_TUNED_LIMIT"] == "42"
    override = (root / "docker-compose.install.yml").read_text(encoding="utf-8")
    assert "APPLY_SEEDS=false" in override
    assert not (root / RECONFIGURE_DIR).exists(), "the staged .env holds secrets"

    state = load_state(root / ".install-state.json")
    assert state is not None and state.public_answers.observability is True
    assert any("LIA reconfiguration complete." in line for line in io.printed)
    assert io.secret_prompts == [], "a reconfiguration asks no secret"


def test_reconfigure_restores_the_previous_files_when_the_stack_does_not_come_back(
    tmp_path: Path,
) -> None:
    root = _installed(tmp_path)
    env_before = (root / ".env").read_text(encoding="utf-8")
    override_before = (root / "docker-compose.install.yml").read_text(encoding="utf-8")

    io = _IO(public={"exposure": "lan", "server_host": "192.168.1.77", **CONFIRM})
    runner = _Runner()
    code = run_install(
        ["--reconfigure"],
        Deps(
            root=root,
            io=io.adapter(),
            runner=runner,
            opener=_ReadyOnceRestored(runner),
            clock=_Clock(),
        ),
    )
    assert code == EXIT_STEP_FAILED
    assert (root / ".env").read_text(encoding="utf-8") == env_before
    assert (root / "docker-compose.install.yml").read_text(encoding="utf-8") == override_before
    state = load_state(root / ".install-state.json")
    assert state is not None and state.public_answers.server_host == "192.168.1.50"
    assert any("readiness_timeout" in line and "--reconfigure again" in line for line in io.printed)
    assert not (root / RECONFIGURE_DIR).exists()


def test_a_restore_that_never_comes_back_ready_names_the_backups(tmp_path: Path) -> None:
    root = _installed(tmp_path)
    env_before = (root / ".env").read_text(encoding="utf-8")

    io = _IO(public={"server_host": "192.168.1.77", **CONFIRM})
    code = run_install(
        ["--reconfigure"],
        Deps(root=root, io=io.adapter(), runner=_Runner(), opener=_NeverReady(), clock=_Clock()),
    )
    assert code == EXIT_STEP_FAILED
    # The files are back even though the stack is not; their copies stay beside them.
    assert (root / ".env").read_text(encoding="utf-8") == env_before
    assert list(root.glob(".env.backup.*"))
    assert any("reconfigure_restore_failed" in line and ".backup." in line for line in io.printed)
    assert not any("--reconfigure again" in line for line in io.printed)


class _NeverReady:
    def __call__(self, request, *, timeout):
        raise OSError("connection refused")


#: The answer to the confirmation a reconfiguration asks once it lists the
#: answer-derived `.env` values that change (Enter answers no).
CONFIRM = {"apply_env_changes": "yes"}


class _ReadyOnceRestored:
    """Never ready under the candidate; ready once the previous stack is up again."""

    def __init__(self, runner: _Runner) -> None:
        self._runner = runner

    def __call__(self, request, *, timeout):
        ups = [line for line in self._runner.joined() if line.endswith(_UP)]
        if len(ups) < 2:
            raise OSError("connection refused")
        return _Opener()(request, timeout=timeout)


_UP = "up -d --no-build --remove-orphans"

CADDY = {
    "exposure": "caddy",
    "web_domain": "lia.example.org",
    "api_domain": "api.lia.example.org",
    "caddy_email": "ops@example.org",
}


def _installed_with(tmp_path: Path, **answers: str) -> Path:
    root = _bundle(tmp_path)
    assert (
        run_install(
            ["--non-interactive", "--answers", str(_answers_file(root, dict(ANSWERS, **answers)))],
            _deps(root, _IO(), _Runner()),
        )
        == EXIT_OK
    )
    return root


def test_a_lan_install_moves_behind_caddy(tmp_path: Path) -> None:
    # The Caddyfile a new exposure needs cannot exist before the swap writes it:
    # this used to stop on `host_path_missing_file` before any command ran.
    root = _installed(tmp_path)
    io = _IO(public={**CADDY, **CONFIRM})
    runner = _Runner()
    code = run_install(["--reconfigure"], _deps(root, io, runner))
    assert code == EXIT_OK, io.printed

    caddyfile = (root / "infrastructure" / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    assert "lia.example.org" in caddyfile and "api.lia.example.org" in caddyfile
    assert "  caddy:" in (root / "docker-compose.install.yml").read_text(encoding="utf-8")
    assert _env_values(root)["APP_URL_SERVER"] == "https://lia.example.org"
    # A Caddy that did not run yet reads its file when it starts.
    assert not any(line.endswith("restart caddy") for line in runner.joined())


def test_caddy_rereads_its_routes_when_a_domain_changes(tmp_path: Path) -> None:
    root = _installed_with(tmp_path, **CADDY)
    io = _IO(public={"web_domain": "chat.example.org", **CONFIRM})
    runner = _Runner()
    code = run_install(["--reconfigure"], _deps(root, io, runner))
    assert code == EXIT_OK, io.printed

    joined = runner.joined()
    up = next(index for index, line in enumerate(joined) if line.endswith(_UP))
    # Compose recreates no Caddy for a bind-mounted file it does not hash, and
    # Caddy reads that file once: without the restart, the old domain stays served.
    assert joined[up + 1].endswith("restart caddy"), joined
    caddyfile = (root / "infrastructure" / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    assert "chat.example.org" in caddyfile


def test_turning_observability_off_stops_its_services(tmp_path: Path) -> None:
    from scripts.install.compose import OBSERVABILITY_SERVICES

    root = _installed_with(tmp_path, observability="yes")
    io = _IO(public={"observability": "no"})
    runner = _Runner()
    code = run_install(["--reconfigure"], _deps(root, io, runner))
    assert code == EXIT_OK, io.printed

    joined = runner.joined()
    retire = [line for line in joined if " rm --stop --force " in line]
    assert len(retire) == 1, joined
    # From the invocation that still knows them: Compose never counts a
    # disabled profile's containers as orphans.
    assert "--profile observability" in retire[0]
    assert retire[0].endswith("rm --stop --force " + " ".join(OBSERVABILITY_SERVICES))
    up = next(index for index, line in enumerate(joined) if line.endswith(_UP))
    assert "--profile observability" not in joined[up]


def test_an_interrupt_while_waiting_puts_the_previous_configuration_back(
    tmp_path: Path,
) -> None:
    root = _installed(tmp_path)
    env_before = (root / ".env").read_text(encoding="utf-8")

    class _InterruptedOnce:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, request, *, timeout):
            self.calls += 1
            if self.calls == 1:
                raise KeyboardInterrupt
            return _Opener()(request, timeout=timeout)

    io = _IO(public={"server_host": "192.168.1.77", **CONFIRM})
    runner = _Runner()
    code = run_install(
        ["--reconfigure"],
        Deps(root=root, io=io.adapter(), runner=runner, opener=_InterruptedOnce(), clock=_Clock()),
    )
    assert code == EXIT_INTERRUPTED
    assert (root / ".env").read_text(encoding="utf-8") == env_before
    assert len([line for line in runner.joined() if line.endswith(_UP)]) == 2, "previous stack back"
    assert any("--reconfigure again" in line for line in io.printed)
    assert not any("--resume" in line for line in io.printed)
    assert not (root / RECONFIGURE_DIR).exists(), "the staged .env holds secrets"
    state = load_state(root / ".install-state.json")
    assert state is not None and state.public_answers.server_host == "192.168.1.50"


def test_values_the_operator_tuned_survive_a_reconfiguration(tmp_path: Path) -> None:
    root = _installed(tmp_path)
    env = (root / ".env").read_text(encoding="utf-8")
    for key, value in (("LOG_LEVEL", "DEBUG"), ("FISHAUDIO_MAX_CONCURRENCY", "2")):
        assert f"\n{key}=" in env, key
        env = "\n".join(
            f"{key}={value}" if line.startswith(f"{key}=") else line for line in env.split("\n")
        )
    (root / ".env").write_text(env, encoding="utf-8")

    io = _IO(public={"server_host": "192.168.1.77", **CONFIRM})
    assert run_install(["--reconfigure"], _deps(root, io, _Runner())) == EXIT_OK, io.printed
    after = _env_values(root)
    assert after["LOG_LEVEL"] == "DEBUG"
    assert after["FISHAUDIO_MAX_CONCURRENCY"] == "2"
    assert after["APP_URL_SERVER"] == "http://192.168.1.77:3000", "what the answer decides moves"


@pytest.mark.parametrize(
    "flags",
    [
        ["--resume"],
        ["--local-build"],
        ["--prebuilt"],
        ["--answers", "answers.env"],
        ["--non-interactive"],
        ["--dry-run"],
        ["--check-only"],
        ["--manifest", "lia-self-host-manifest.json"],
    ],
)
def test_reconfigure_refuses_every_flag_of_another_run(tmp_path: Path, flags: list[str]) -> None:
    root = _bundle(tmp_path)
    io = _IO()
    runner = _Runner()
    code = run_install(["--reconfigure", *flags], _deps(root, io, runner))
    assert code == 2
    assert "reconfigure_flags_exclusive" in io.printed
    assert runner.calls == []


def test_every_question_shows_the_answer_enter_keeps(tmp_path: Path) -> None:
    root = _installed(tmp_path)
    io = _IO(public={})
    assert run_install(["--reconfigure"], _deps(root, io, _Runner())) == EXIT_OK, io.printed
    host = next(prompt for prompt in io.input_prompts if prompt.startswith("[server_host]"))
    assert host.endswith("[192.168.1.50]: ")


def test_a_missing_release_manifest_is_a_stable_code(tmp_path: Path) -> None:
    from scripts.install.tests.test_preflight import _manifest_payload

    root = _bundle(tmp_path)
    manifest = root / "lia-self-host-manifest.json"
    manifest.write_text(json.dumps(_manifest_payload("passed")), encoding="utf-8")
    assert (
        run_install(
            ["--prebuilt", "--non-interactive", "--answers", str(_answers_file(root))],
            _deps(root, _IO(), _Runner()),
        )
        == EXIT_OK
    )
    manifest.unlink()  # a bundle folder cleaned up after the install

    io = _IO(public={})
    runner = _Runner()
    code = run_install(["--reconfigure"], _deps(root, io, runner))
    assert code == EXIT_PREFLIGHT
    assert any(line.startswith("manifest_unreadable") for line in io.printed)
    assert runner.calls == []
    assert not (root / RECONFIGURE_DIR).exists()


def test_a_resume_after_a_reconfiguration_finds_nothing_to_stop_on(
    tmp_path: Path,
) -> None:
    root = _installed(tmp_path)
    assert (
        run_install(
            ["--reconfigure"],
            _deps(root, _IO(public={**CONFIRM, "observability": "yes"}), _Runner()),
        )
        == EXIT_OK
    )
    io = _IO()
    assert run_install(["--resume"], _deps(root, io, _Runner())) == EXIT_OK, io.printed
    assert "resume_stop_mismatch" not in io.printed


def test_turning_the_sandbox_on_obtains_its_image_before_the_swap(tmp_path: Path) -> None:
    root = _installed(tmp_path)
    io = _IO(public={"skill_sandbox": "yes"})
    runner = _Runner()
    assert run_install(["--reconfigure"], _deps(root, io, runner)) == EXIT_OK, io.printed
    joined = runner.joined()
    build = next(index for index, line in enumerate(joined) if "Dockerfile.sandbox" in line)
    check = next(index for index, line in enumerate(joined) if line.endswith("config --quiet"))
    assert build < check, joined
    assert "docker-compose.skill-sandbox.yml" in joined[check]


def test_an_interrupt_at_a_question_changes_nothing_and_never_points_at_resume(
    tmp_path: Path,
) -> None:
    # The questions ran outside the reconfiguration's interrupt handling: Ctrl-C
    # there advised `--resume`, which belongs to an unfinished installation.
    root = _installed(tmp_path)
    env_before = (root / ".env").read_text(encoding="utf-8")
    io = _IO(public={})
    adapter = io.adapter()

    def _interrupted(prompt: str) -> str:
        raise KeyboardInterrupt

    runner = _Runner()
    code = run_install(
        ["--reconfigure"],
        Deps(
            root=root,
            io=IOAdapter(
                input_fn=_interrupted, getpass_fn=adapter.getpass_fn, print_fn=adapter.print_fn
            ),
            runner=runner,
            opener=_Opener(),
            clock=_Clock(),
        ),
    )
    assert code == EXIT_INTERRUPTED
    assert any("nothing changed" in line and "--reconfigure again" in line for line in io.printed)
    assert not any("--resume" in line for line in io.printed)
    assert runner.calls == []
    assert (root / ".env").read_text(encoding="utf-8") == env_before
    assert not (root / RECONFIGURE_DIR).exists()


def _ups(runner: _Runner) -> int:
    return sum(1 for line in runner.joined() if line.endswith(_UP))


class _SignalledAtTheFirstUp(_Runner):
    """Runs every command; at the candidate's `up`, the handler of ``signum`` fires."""

    def __init__(self, signum: int) -> None:
        super().__init__()
        self._signum = signum

    def __call__(self, argv, *, stdin=None, env=None):
        result = super().__call__(argv, stdin=stdin, env=env)
        if " ".join(argv).endswith(_UP) and _ups(self) == 1:
            handler = signal.getsignal(self._signum)
            assert callable(handler), "the signal would end the run with nothing restored"
            handler(self._signum, None)
        return result


@pytest.mark.parametrize("name", [n for n in ("SIGTERM", "SIGHUP") if hasattr(signal, n)])
def test_a_termination_after_the_swap_puts_the_previous_configuration_back(
    tmp_path: Path, name: str
) -> None:
    # Left to its default action, a closed SSH session (SIGHUP) or a `kill`
    # (SIGTERM) ended the process where it stood: after the swap, with the new
    # files in place and nothing restored.
    signum = getattr(signal, name)
    handler_before = signal.getsignal(signum)
    root = _installed(tmp_path)
    env_before = (root / ".env").read_text(encoding="utf-8")
    io = _IO(public={"server_host": "192.168.1.77", **CONFIRM})
    runner = _SignalledAtTheFirstUp(signum)
    code = run_install(["--reconfigure"], _deps(root, io, runner))
    assert code == EXIT_INTERRUPTED
    assert (root / ".env").read_text(encoding="utf-8") == env_before
    assert _ups(runner) == 2, "the previous stack was brought back up"
    assert any("--reconfigure again" in line for line in io.printed)
    assert signal.getsignal(signum) == handler_before, "the previous handler is back"


def test_a_failed_restore_logs_what_stopped_the_candidate_before_restoring(
    tmp_path: Path,
) -> None:
    # The restore's own failure was all the log held: the candidate's — the one
    # to fix — survived only as the exception's context.
    root = _installed(tmp_path)

    class _PortTaken(_Runner):
        def __call__(self, argv, *, stdin=None, env=None):
            super().__call__(argv, stdin=stdin, env=env)
            if not " ".join(argv).endswith(_UP):
                return CommandResult(0, "", "")
            ups = [line for line in self.joined() if line.endswith(_UP)]
            if len(ups) == 1:
                return CommandResult(1, "", "Bind for 0.0.0.0:3000 failed: port is already allocated")
            return CommandResult(1, "", "the restore was refused too")

    io = _IO(public={"server_host": "192.168.1.77", **CONFIRM})
    code = run_install(["--reconfigure"], _deps(root, io, _PortTaken()))
    assert code == EXIT_STEP_FAILED
    log = (root / "install.log").read_text(encoding="utf-8")
    assert "port is already allocated" in log
    assert log.index("port is already allocated") < log.index("code=reconfigure_restore_failed")


def test_a_failed_restore_prints_the_previous_compose_selection(tmp_path: Path) -> None:
    # `liac up -d --no-build` named neither a prebuilt install's images file nor
    # the sandbox overlay: run as written, it brought back another stack.
    from scripts.install.tests.test_preflight import _manifest_payload

    root = _bundle(tmp_path)
    (root / "lia-self-host-manifest.json").write_text(
        json.dumps(_manifest_payload("passed")), encoding="utf-8"
    )
    answers = dict(ANSWERS, skill_sandbox="yes")
    assert (
        run_install(
            ["--prebuilt", "--non-interactive", "--answers", str(_answers_file(root, answers))],
            _deps(root, _IO(), _Runner()),
        )
        == EXIT_OK
    )
    io = _IO(public={"server_host": "192.168.1.77", **CONFIRM})
    code = run_install(
        ["--reconfigure"],
        Deps(root=root, io=io.adapter(), runner=_Runner(), opener=_NeverReady(), clock=_Clock()),
    )
    assert code == EXIT_STEP_FAILED
    line = next(line for line in io.printed if line.startswith("reconfigure_restore_failed"))
    up = next(command for command in line.splitlines() if command.strip().endswith(_UP))
    for layer in (
        "docker-compose.prod.yml",
        "docker-compose.install.yml",
        "docker-compose.skill-sandbox.yml",
        "docker-compose.images.yml",
    ):
        assert layer in up, (layer, up)


TWO_ORIGINS = "http://192.168.1.50:3000,http://lia.lan:3000"


def _edit_env(root: Path, key: str, value: str) -> None:
    lines = (root / ".env").read_text(encoding="utf-8").split("\n")
    assert any(line.startswith(f"{key}=") for line in lines), key
    (root / ".env").write_text(
        "\n".join(f"{key}={value}" if line.startswith(f"{key}=") else line for line in lines),
        encoding="utf-8",
    )


def test_a_value_edited_by_hand_is_listed_and_kept_unless_confirmed(tmp_path: Path) -> None:
    # The questions default to the RECORDED answers, from which these values are
    # rewritten: pressing Enter everywhere reset a hand edit in silence.
    root = _installed(tmp_path)
    _edit_env(root, "CORS_ORIGINS", TWO_ORIGINS)
    io = _IO(public={})
    runner = _Runner()
    code = run_install(["--reconfigure"], _deps(root, io, runner))
    assert code == EXIT_USAGE
    assert f"  CORS_ORIGINS: {TWO_ORIGINS} -> http://192.168.1.50:3000" in io.printed
    assert any(
        prompt.startswith("[apply_env_changes]") and prompt.endswith("[no]: ")
        for prompt in io.input_prompts
    )
    assert any(line.startswith("reconfigure_declined") for line in io.printed)
    assert _env_values(root)["CORS_ORIGINS"] == TWO_ORIGINS
    assert runner.calls == [], "nothing validated, swapped or started"
    assert not (root / RECONFIGURE_DIR).exists()
    state = load_state(root / ".install-state.json")
    assert state is not None and state.public_answers.server_host == "192.168.1.50"


def test_a_confirmed_change_replaces_the_value_edited_by_hand(tmp_path: Path) -> None:
    root = _installed(tmp_path)
    _edit_env(root, "CORS_ORIGINS", TWO_ORIGINS)
    io = _IO(public=dict(CONFIRM))
    assert run_install(["--reconfigure"], _deps(root, io, _Runner())) == EXIT_OK, io.printed
    assert _env_values(root)["CORS_ORIGINS"] == "http://192.168.1.50:3000"


def test_the_confirmation_never_prints_a_secret(tmp_path: Path) -> None:
    root = _installed_with(tmp_path, observability="yes")
    io = _IO(public={"self_diagnostics": "yes", **CONFIRM})
    assert run_install(["--reconfigure"], _deps(root, io, _Runner())) == EXIT_OK, io.printed
    secret = _env_values(root)["DIAGNOSTICS_WEBHOOK_SECRET"]
    assert secret
    assert secret not in "\n".join(io.printed + io.input_prompts)
    assert "  DIAGNOSTICS_WEBHOOK_SECRET: (empty) -> (hidden)" in io.printed


def test_turning_the_sandbox_on_writes_the_docker_socket_group(tmp_path: Path) -> None:
    # Left unset, the overlay falls back to a group the host's socket may not
    # have: on a production host, the API could not use the socket.
    root = _installed(tmp_path)
    socket = tmp_path / "docker.sock"
    socket.write_text("", encoding="utf-8")
    io = _IO(public={"skill_sandbox": "yes"})
    assert (
        run_install(["--reconfigure"], _deps(root, io, _Runner(), docker_socket=socket)) == EXIT_OK
    ), io.printed
    gid = str(os.stat(socket).st_gid)
    assert _env_values(root)["DOCKER_GID"] == gid

    # Not answer-derived: a later reconfiguration keeps it, socket or not.
    io = _IO(public={**CONFIRM, "observability": "yes"})
    assert run_install(["--reconfigure"], _deps(root, io, _Runner())) == EXIT_OK, io.printed
    assert _env_values(root)["DOCKER_GID"] == gid


def test_a_docker_gid_in_force_is_kept_and_no_socket_writes_none(tmp_path: Path) -> None:
    kept = _installed(tmp_path / "kept")
    with (kept / ".env").open("a", encoding="utf-8") as env:
        env.write("DOCKER_GID=4242\n")
    socket = tmp_path / "docker.sock"
    socket.write_text("", encoding="utf-8")
    io = _IO(public={"skill_sandbox": "yes"})
    assert (
        run_install(["--reconfigure"], _deps(kept, io, _Runner(), docker_socket=socket))
        == EXIT_OK
    ), io.printed
    assert _env_values(kept)["DOCKER_GID"] == "4242"

    bare = _installed(tmp_path / "bare")
    io = _IO(public={"skill_sandbox": "yes"})
    absent = tmp_path / "no-docker.sock"
    assert (
        run_install(["--reconfigure"], _deps(bare, io, _Runner(), docker_socket=absent))
        == EXIT_OK
    ), io.printed
    assert "DOCKER_GID" not in _env_values(bare)


def test_observability_credentials_survive_disable_and_reenable(tmp_path: Path) -> None:
    root = _installed_with(tmp_path, observability="yes")
    original = _env_values(root)
    assert len(original.get("GRAFANA_ADMIN_PASSWORD", "")) >= 32
    for choice in ("no", "yes"):
        io = _IO(public={"observability": choice})
        assert run_install(["--reconfigure"], _deps(root, io, _Runner())) == EXIT_OK
        current = _env_values(root)
        unchanged = all(
            current[key] == original[key]
            for key in ("GRAFANA_ADMIN_USER", "GRAFANA_ADMIN_PASSWORD")
        )
        assert unchanged
        assert not any(prompt.startswith("[apply_env_changes]") for prompt in io.input_prompts)


def test_new_observability_credentials_require_the_existing_env_change_consent(
    tmp_path: Path,
) -> None:
    root = _installed(tmp_path)
    before = (root / ".env").read_text(encoding="utf-8")
    io = _IO(public={"observability": "yes"})
    assert run_install(["--reconfigure"], _deps(root, io, _Runner())) == EXIT_USAGE
    assert (root / ".env").read_text(encoding="utf-8") == before
    assert any(line.startswith("reconfigure_declined") for line in io.printed)
