"""Reconfiguration primitives of the deploy layer (ADR-215).

``reconfigure_existing`` refuses an identity change before any command,
validates the candidate files, swaps them in one atomic replace per file and
brings the candidate up; any failure or interrupt after the swap — a hang-up or
a termination included — restores the previous files and stack, verified
ready, and a restore that cannot says so. A read that fails anywhere, or an
interrupt right after a replace, never leaves a new file unrestored; what
stopped the candidate is handed over before the restore runs; the bring-up
commands carry the whole Compose selection.
"""

from __future__ import annotations

import dataclasses
import os
import signal
import stat
from pathlib import Path

import pytest

from scripts.install.compose import build_invocation
from scripts.install.deploy import CommandResult, StepFailed
from scripts.install.model import Exposure, InstallMode, PublicAnswers
from scripts.install.tests.deploy_fakes import DIGEST, _invocation, _public, _Runner


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

    # Validation passes, the candidate's `up` refuses, the restore's own succeeds.
    runner = _Runner([_OK, CommandResult(1, "", "boom")])
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
    assert excinfo.value.code == "reconfigure_failed"
    assert target.read_text(encoding="utf-8").endswith("# current\n"), "restored"
    assert runner.calls[-1]["argv"][-4:] == _UP, "the previous stack brought back up"


_OK = CommandResult(0, "", "")
_UP = ["up", "-d", "--no-build", "--remove-orphans"]


def test_a_restore_whose_stack_refuses_says_so(tmp_path: Path) -> None:
    import dataclasses

    from scripts.install.deploy import reconfigure_existing

    refused = CommandResult(1, "", "boom")
    candidates = _candidates(tmp_path)
    target = next(iter(candidates))
    with pytest.raises(StepFailed) as excinfo:
        reconfigure_existing(
            current=_install_state(),
            candidate_public=dataclasses.replace(_public(), observability=True),
            candidate_files=candidates,
            invocation=_invocation(),
            runner=_Runner([_OK, refused, refused]),
        )
    assert excinfo.value.code == "reconfigure_restore_failed"
    # The files are back though the stack is not; the copy stays beside them.
    assert target.read_text(encoding="utf-8").endswith("# current\n")
    assert list(tmp_path.glob("docker-compose.install.yml.backup.*"))


def test_a_restored_stack_that_never_serves_fails_the_restore(tmp_path: Path) -> None:
    from scripts.install.deploy import reconfigure_existing

    waits: list[int] = []

    def never_ready() -> None:
        waits.append(1)
        raise StepFailed("readiness_timeout")

    with pytest.raises(StepFailed) as excinfo:
        reconfigure_existing(
            current=_install_state(),
            candidate_public=_public(),
            candidate_files=_candidates(tmp_path),
            invocation=_invocation(),
            runner=_Runner(),
            wait_ready_fn=never_ready,
        )
    assert excinfo.value.code == "reconfigure_restore_failed"
    assert len(waits) == 2, "the candidate, then the restored stack"


def test_an_interrupt_after_the_swap_restores_before_propagating(tmp_path: Path) -> None:
    from scripts.install.deploy import reconfigure_existing

    waits: list[int] = []

    def interrupted_then_ready() -> None:
        waits.append(1)
        if len(waits) == 1:
            raise KeyboardInterrupt

    runner = _Runner()
    candidates = _candidates(tmp_path)
    target = next(iter(candidates))
    with pytest.raises(KeyboardInterrupt):
        reconfigure_existing(
            current=_install_state(),
            candidate_public=_public(),
            candidate_files=candidates,
            invocation=_invocation(),
            runner=runner,
            wait_ready_fn=interrupted_then_ready,
        )
    assert target.read_text(encoding="utf-8").endswith("# current\n")
    assert [call["argv"][-4:] for call in runner.calls].count(_UP) == 2
    assert len(waits) == 2, "the restored stack was waited for"


def test_a_swap_stopped_halfway_puts_back_what_it_replaced(tmp_path: Path) -> None:
    from scripts.install.deploy import swap_in

    first = tmp_path / "first.yml"
    first.write_text("first: current\n", encoding="utf-8")
    first_candidate = tmp_path / "first.candidate"
    first_candidate.write_text("first: candidate\n", encoding="utf-8")
    second = tmp_path / "second.yml"
    second.write_text("second: current\n", encoding="utf-8")
    never_staged = tmp_path / "second.candidate"

    with pytest.raises(FileNotFoundError):
        swap_in({first: first_candidate, second: never_staged})
    assert first.read_text(encoding="utf-8") == "first: current\n"
    assert second.read_text(encoding="utf-8") == "second: current\n"


def test_the_restore_removes_what_the_candidate_created_and_stops_what_it_started(
    tmp_path: Path,
) -> None:
    import dataclasses

    from scripts.install.compose import OBSERVABILITY_SERVICES
    from scripts.install.deploy import reconfigure_existing

    created = tmp_path / "Caddyfile"
    staged = tmp_path / "Caddyfile.candidate"
    staged.write_text("routes\n", encoding="utf-8")
    candidates = {**_candidates(tmp_path), created: staged}
    candidate_public = dataclasses.replace(_public(), observability=True)
    runner = _Runner([_OK, CommandResult(1, "", "boom")])
    with pytest.raises(StepFailed):
        reconfigure_existing(
            current=_install_state(),
            candidate_public=candidate_public,
            candidate_files=candidates,
            invocation=build_invocation(candidate_public, root=Path(".")),
            runner=runner,
            previous_invocation=_invocation(),
        )
    assert not created.exists(), "a file the reconfiguration created has no previous version"
    joined = [" ".join(call["argv"]) for call in runner.calls]
    restore_up, retire = joined[2], joined[3]
    assert "--profile observability" not in restore_up and restore_up.endswith(" ".join(_UP))
    assert "--profile observability" in retire
    assert retire.endswith("rm --stop --force " + " ".join(OBSERVABILITY_SERVICES))


def test_caddy_is_left_alone_when_its_routes_did_not_change(tmp_path: Path) -> None:
    import dataclasses

    from scripts.install.deploy import reconfigure_existing

    caddy = dataclasses.replace(
        _public(),
        exposure=Exposure.CADDY,
        server_host=None,
        web_domain="lia.example.org",
        api_domain="api.lia.example.org",
        caddy_email="ops@example.org",
    )
    caddyfile = tmp_path / "Caddyfile"
    caddyfile.write_text("same routes\n", encoding="utf-8")
    staged = tmp_path / "Caddyfile.candidate"
    staged.write_text("same routes\n", encoding="utf-8")
    runner = _Runner()
    reconfigure_existing(
        current=dataclasses.replace(_install_state(), public_answers=caddy),
        candidate_public=dataclasses.replace(caddy, observability=True),
        candidate_files={caddyfile: staged},
        invocation=build_invocation(caddy, root=Path(".")),
        runner=runner,
    )
    assert not any(call["argv"][-2:] == ["restart", "caddy"] for call in runner.calls)


@pytest.mark.skipif(os.name != "posix", reason="POSIX file modes")
def test_every_copy_of_a_replaced_file_is_private(tmp_path: Path) -> None:
    from scripts.install.deploy import swap_in

    target = tmp_path / ".env"
    target.write_text("FERNET_KEY=secret\n", encoding="utf-8")
    target.chmod(0o644)
    staged = tmp_path / "candidate.env"
    staged.write_text("FERNET_KEY=secret\nLOG_LEVEL=INFO\n", encoding="utf-8")
    previous_umask = os.umask(0o022)
    try:
        swap = swap_in({target: staged})
    finally:
        os.umask(previous_umask)
    assert stat.S_IMODE(swap.backups[target].stat().st_mode) == 0o600
    assert stat.S_IMODE(target.stat().st_mode) == 0o600


def _caddy_public() -> PublicAnswers:
    return dataclasses.replace(
        _public(),
        exposure=Exposure.CADDY,
        server_host=None,
        web_domain="lia.example.org",
        api_domain="api.lia.example.org",
        caddy_email="ops@example.org",
    )


def _caddy_case(root: Path) -> tuple[dict[Path, Path], dict[Path, str]]:
    """An override and a Caddyfile in force, each with a different candidate."""
    root.mkdir()
    previous = {
        root / "docker-compose.install.yml": "services: {}\n# current\n",
        root / "Caddyfile": "old.example.org\n",
    }
    files: dict[Path, Path] = {}
    for target, content in previous.items():
        target.write_text(content, encoding="utf-8")
        staged = target.with_name(f"{target.name}.candidate")
        staged.write_text(
            content.replace("current", "candidate").replace("old", "new"), encoding="utf-8"
        )
        files[target] = staged
    return files, previous


def test_a_failed_read_anywhere_leaves_the_previous_files_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whichever read fails, the previous files are what the disk holds.

    Whether Caddy must reread its routes used to be decided by reading the
    files AFTER the swap and outside the restore's reach: one failed read there
    left the new routes in place under a line saying the previous ones were.
    """
    from scripts.install.deploy import reconfigure_existing

    caddy = _caddy_public()
    state = dataclasses.replace(_install_state(), public_answers=caddy)
    candidate = dataclasses.replace(caddy, observability=True)
    real_read = Path.read_bytes
    reads: list[Path] = []

    def counting(self: Path) -> bytes:
        reads.append(self)
        return real_read(self)

    files, _previous = _caddy_case(tmp_path / "clean")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", counting)
        reconfigure_existing(
            current=state,
            candidate_public=candidate,
            candidate_files=files,
            invocation=build_invocation(candidate, root=tmp_path),
            runner=_Runner(),
        )
    assert len(reads) >= 4, "the files compared and copied are read"

    for failing in range(1, len(reads) + 1):
        files, previous = _caddy_case(tmp_path / f"read-{failing}")
        seen: list[Path] = []

        def failing_read(self: Path, _at: int = failing) -> bytes:
            seen.append(self)
            if len(seen) == _at:
                raise OSError("read failed")
            return real_read(self)

        with monkeypatch.context() as patch:
            patch.setattr(Path, "read_bytes", failing_read)
            with pytest.raises(OSError):
                reconfigure_existing(
                    current=state,
                    candidate_public=candidate,
                    candidate_files=files,
                    invocation=build_invocation(candidate, root=tmp_path),
                    runner=_Runner(),
                )
        for target, content in previous.items():
            assert target.read_text(encoding="utf-8") == content, (failing, target.name)


def test_an_interrupt_right_after_a_file_is_replaced_puts_it_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The swap recorded a target once its replace had returned: an interrupt
    # between the two left the new file with nothing to put it back.
    from scripts.install import deploy

    first = tmp_path / "first.yml"
    first.write_text("first: current\n", encoding="utf-8")
    first_candidate = tmp_path / "first.candidate"
    first_candidate.write_text("first: candidate\n", encoding="utf-8")
    second = tmp_path / "second.yml"
    second.write_text("second: current\n", encoding="utf-8")
    second_candidate = tmp_path / "second.candidate"
    second_candidate.write_text("second: candidate\n", encoding="utf-8")
    real_replace = deploy.replace_private
    replaced: list[Path] = []

    def replaced_then_interrupted(path: Path, data: bytes) -> None:
        real_replace(path, data)
        replaced.append(path)
        if len(replaced) == 1:
            raise KeyboardInterrupt

    monkeypatch.setattr(deploy, "replace_private", replaced_then_interrupted)
    with pytest.raises(KeyboardInterrupt):
        deploy.swap_in({first: first_candidate, second: second_candidate})
    assert first.read_text(encoding="utf-8") == "first: current\n"
    assert second.read_text(encoding="utf-8") == "second: current\n"


def test_what_stopped_the_candidate_is_handed_over_before_the_restore_runs(
    tmp_path: Path,
) -> None:
    from scripts.install.deploy import reconfigure_existing

    runner = _Runner(
        [_OK, CommandResult(1, "", "port is already allocated"), CommandResult(1, "", "refused")]
    )
    noted: list[tuple[str, str, int]] = []

    def note(error: BaseException) -> None:
        assert isinstance(error, StepFailed)
        noted.append((error.code, error.detail, len(runner.calls)))

    with pytest.raises(StepFailed) as excinfo:
        reconfigure_existing(
            current=_install_state(),
            candidate_public=dataclasses.replace(_public(), observability=True),
            candidate_files=_candidates(tmp_path),
            invocation=_invocation(),
            runner=runner,
            before_restore=note,
        )
    assert excinfo.value.code == "reconfigure_restore_failed"
    # Validation and the candidate's `up` ran; the restore's first command had not.
    assert noted == [("reconfigure_failed", "port is already allocated", 2)]
    assert len(runner.calls) == 3


def test_a_note_that_fails_never_keeps_the_restore_from_running(tmp_path: Path) -> None:
    from scripts.install.deploy import reconfigure_existing

    runner = _Runner([_OK, CommandResult(1, "", "boom")])
    candidates = _candidates(tmp_path)
    target = next(iter(candidates))

    def broken_note(error: BaseException) -> None:
        raise KeyboardInterrupt  # a second Ctrl-C while the cause is written

    with pytest.raises(KeyboardInterrupt):
        reconfigure_existing(
            current=_install_state(),
            candidate_public=dataclasses.replace(_public(), observability=True),
            candidate_files=candidates,
            invocation=_invocation(),
            runner=runner,
            before_restore=broken_note,
        )
    assert target.read_text(encoding="utf-8").endswith("# current\n"), "restored"
    assert runner.calls[-1]["argv"][-4:] == _UP


_TERMINATIONS = [name for name in ("SIGTERM", "SIGHUP") if hasattr(signal, name)]


@pytest.mark.parametrize("name", _TERMINATIONS)
def test_a_termination_is_an_interrupt_only_while_the_handlers_hold(name: str) -> None:
    from scripts.install.deploy import interrupt_on_termination

    signum = getattr(signal, name)
    before = signal.getsignal(signum)
    with interrupt_on_termination():
        handler = signal.getsignal(signum)
        assert callable(handler)
        with pytest.raises(KeyboardInterrupt):
            handler(signum, None)
    assert signal.getsignal(signum) == before


@pytest.mark.skipif(os.name != "posix", reason="a delivered POSIX signal")
@pytest.mark.parametrize("name", _TERMINATIONS)
def test_a_delivered_termination_raises_the_interrupt(name: str) -> None:
    from scripts.install.deploy import interrupt_on_termination

    signum = getattr(signal, name)
    with interrupt_on_termination():
        assert callable(signal.getsignal(signum)), "never deliver it unhandled"
        with pytest.raises(KeyboardInterrupt):
            signal.raise_signal(signum)


def test_the_bring_up_commands_carry_the_whole_selection_and_retire_what_it_drops() -> None:
    from scripts.install.compose import OBSERVABILITY_SERVICES
    from scripts.install.deploy import bring_up_commands

    root = Path("/srv/lia")
    sandboxed = dataclasses.replace(_public(InstallMode.PREBUILT), skill_sandbox=True)
    previous = build_invocation(sandboxed, root=root)
    candidate = build_invocation(dataclasses.replace(sandboxed, observability=True), root=root)

    up, restart, retire = bring_up_commands(previous, replaced=candidate, restart_caddy=True)
    assert up == previous.prefix() + _UP
    assert str(root / "docker-compose.images.yml") in up
    assert str(root / "docker-compose.skill-sandbox.yml") in up
    assert restart == previous.prefix() + ["restart", "caddy"]
    assert retire == candidate.prefix() + ["rm", "--stop", "--force", *OBSERVABILITY_SERVICES]
    assert bring_up_commands(previous, replaced=previous, restart_caddy=False) == (up,)
