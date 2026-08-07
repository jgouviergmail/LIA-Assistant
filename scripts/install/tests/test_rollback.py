"""Bounded rollback contract (B14).

- an existing LOCAL install aliases both running image IDs BEFORE any build
  can overwrite the mutable lia-*:local tags; prebuilt keeps its immutable
  digests and creates no alias;
- restoring an existing install retags and recreates with --no-build;
- a FIRST install only stops its own project's services — never volumes,
  never generated backups;
- config backups are restored from the captured mapping.
"""

from __future__ import annotations

from pathlib import Path

from scripts.install.compose import build_invocation
from scripts.install.deploy import CommandResult
from scripts.install.model import Exposure, InstallMode, PublicAnswers
from scripts.install.rollback import (
    capture_rollback_point,
    restore_or_quiesce,
)
from scripts.install.state import (
    STATE_SCHEMA_VERSION,
    InstallState,
)

API_IMAGE_ID = "sha256:" + "1" * 64
WEB_IMAGE_ID = "sha256:" + "2" * 64


class _Runner:
    def __init__(self, results: dict[str, CommandResult] | None = None) -> None:
        self.calls: list[list[str]] = []
        self._results = results or {}

    def __call__(self, argv, *, stdin=None, env=None):
        self.calls.append(list(argv))
        joined = " ".join(argv)
        for needle, result in self._results.items():
            if needle in joined:
                return result
        return CommandResult(returncode=0, stdout="", stderr="")


def _public(mode: InstallMode) -> PublicAnswers:
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


def _state(mode: InstallMode, image_digests: dict[str, str]) -> InstallState:
    return InstallState(
        schema_version=STATE_SCHEMA_VERSION,
        installer_version="1",
        mode=mode,
        public_answers=_public(mode),
        release_id="v1.28.0" if mode is InstallMode.PREBUILT else None,
        bundle_tree_sha256=None,
        source_context_tree_sha256=None,
        image_digests=image_digests,
        seed_bundle_sha256="e" * 64,
        completed=(),
        attempts={},
        last_error_code=None,
        generated_sha256={},
        bootstrap_complete=True,
        project_name="lia-prod",
    )


def _invocation(mode: InstallMode):
    return build_invocation(
        _public(mode), root=Path("."), project_name="lia-prod"
    )


def test_first_install_capture_marks_first_and_aliases_nothing() -> None:
    runner = _Runner()
    point = capture_rollback_point(_invocation(InstallMode.LOCAL), None, runner)
    assert point.first_install is True
    assert point.rollback_aliases == {}
    assert not any("tag" in call for call in runner.calls)


def test_existing_local_install_aliases_both_running_image_ids() -> None:
    runner = _Runner(
        {
            "images --format": CommandResult(
                0, f"api {API_IMAGE_ID}\nweb {WEB_IMAGE_ID}\n", ""
            )
        }
    )
    state = _state(InstallMode.LOCAL, {})
    point = capture_rollback_point(_invocation(InstallMode.LOCAL), state, runner)
    assert point.first_install is False
    assert point.previous_images == {"api": API_IMAGE_ID, "web": WEB_IMAGE_ID}
    aliases = point.rollback_aliases
    assert set(aliases) == {"api", "web"}
    for service, alias in aliases.items():
        assert alias.startswith("lia-installer-rollback-lia-prod-")
        assert any(
            call[:3] == ["docker", "tag", point.previous_images[service]]
            and call[3] == alias
            for call in runner.calls
        ), (service, runner.calls)


def test_existing_prebuilt_install_keeps_digests_without_aliases() -> None:
    runner = _Runner()
    digests = {"api": "sha256:" + "a" * 64, "web": "sha256:" + "b" * 64}
    state = _state(InstallMode.PREBUILT, digests)
    point = capture_rollback_point(
        _invocation(InstallMode.PREBUILT), state, runner
    )
    assert point.previous_images == digests
    assert point.rollback_aliases == {}
    assert not any("tag" in call for call in runner.calls)


def test_first_install_quiesce_stops_only_the_project_without_volumes() -> None:
    runner = _Runner()
    point = capture_rollback_point(_invocation(InstallMode.LOCAL), None, runner)
    restore_or_quiesce(point, _invocation(InstallMode.LOCAL), runner)
    stop_call = runner.calls[-1]
    assert stop_call[-1] == "stop"
    assert "-p" in stop_call and "lia-prod" in stop_call
    joined = " ".join(" ".join(c) for c in runner.calls)
    assert "--volumes" not in joined
    assert "down" not in joined.split()


def test_existing_local_restore_retags_and_recreates_without_build(
    tmp_path: Path,
) -> None:
    backup = tmp_path / ".env.backup.1"
    backup.write_text("ORIGINAL=1\n", encoding="utf-8")
    target = tmp_path / ".env"
    target.write_text("BROKEN=1\n", encoding="utf-8")

    runner = _Runner(
        {
            "images --format": CommandResult(
                0, f"api {API_IMAGE_ID}\nweb {WEB_IMAGE_ID}\n", ""
            )
        }
    )
    state = _state(InstallMode.LOCAL, {})
    point = capture_rollback_point(_invocation(InstallMode.LOCAL), state, runner)
    point = type(point)(
        previous_images=point.previous_images,
        rollback_aliases=point.rollback_aliases,
        config_backups={target: backup},
        first_install=False,
    )
    restore_or_quiesce(point, _invocation(InstallMode.LOCAL), runner)
    assert target.read_text(encoding="utf-8") == "ORIGINAL=1\n"
    joined_calls = [" ".join(call) for call in runner.calls]
    assert any(
        f"docker tag {point.rollback_aliases['api']} lia-api:local" == call
        for call in joined_calls
    ), joined_calls
    up_call = runner.calls[-1]
    assert "--no-build" in up_call and "--force-recreate" in up_call
