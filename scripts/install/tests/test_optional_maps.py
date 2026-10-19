"""Optional Maps setup stays private, paired, injection-safe and resumable."""

import dataclasses
from pathlib import Path

import pytest

from scripts.install import envgen
from scripts.install.__main__ import run_install
from scripts.install.answers import InstallInputError, collect_secret_answers
from scripts.install.questions import build_questions
from scripts.install.run_context import EXIT_OK
from scripts.install.tests.flow_fakes import ANSWERS, _answers_file, _bundle, _deps, _IO, _Runner
from scripts.install.tests.test_answers import BASE_PUBLIC, SECRETS, _collect, _ScriptedIO

MAP_KEY = "fictional_maps_browser_key_123456"
MAP_ID = "0123456789abcdef"


def test_maps_answers_are_hidden_and_never_enter_public_installer_state() -> None:
    io = _ScriptedIO(BASE_PUBLIC, {**SECRETS, "maps_browser_key": MAP_KEY, "maps_map_id": MAP_ID})
    public, private = _collect(io)
    assert {"maps_browser_key", "maps_map_id"}.issubset(io.secret_served)
    assert not {"maps_browser_key", "maps_map_id"}.intersection(io.public_served)
    assert private.maps_settings == {
        "GOOGLE_MAPS_BROWSER_API_KEY": MAP_KEY,
        "GOOGLE_MAPS_MAP_ID": MAP_ID,
    }
    assert MAP_KEY not in repr(private) and MAP_KEY not in repr(dataclasses.asdict(public))
    assert MAP_KEY not in "".join(io.printed)


@pytest.mark.parametrize("key,map_id", [(MAP_KEY, ""), ("", MAP_ID)])
def test_half_a_maps_configuration_fails_before_artifacts_are_written(
    key: str, map_id: str
) -> None:
    io = _ScriptedIO(BASE_PUBLIC, {**SECRETS, "maps_browser_key": key, "maps_map_id": map_id})
    with pytest.raises(InstallInputError, match="incomplete_maps_configuration"):
        _collect(io)


def test_skipping_maps_preserves_existing_operator_values_and_emits_no_unrelated_key(
    tmp_path: Path,
) -> None:
    path = tmp_path / ".env"
    path.write_text(
        f"GOOGLE_MAPS_BROWSER_API_KEY={MAP_KEY}\nGOOGLE_MAPS_MAP_ID={MAP_ID}\nOTHER_PRIVATE=preserve\n",
        encoding="utf-8",
    )
    before = path.read_bytes()
    assert envgen.maps_environment(path, {}) == {
        "GOOGLE_MAPS_BROWSER_API_KEY": MAP_KEY,
        "GOOGLE_MAPS_MAP_ID": MAP_ID,
    }
    assert path.read_bytes() == before


def test_resuming_bootstrap_does_not_ask_for_maps_already_kept_in_private_env() -> None:
    io = _ScriptedIO({}, SECRETS)
    private = collect_secret_answers(
        build_questions(), io=io.adapter(), non_interactive=False, answers_path=None
    )
    assert not {"maps_browser_key", "maps_map_id"}.intersection(io.secret_served)
    assert not private.maps_settings


def test_complete_install_writes_maps_only_to_private_env_not_state_logs_or_bootstrap(
    tmp_path: Path,
) -> None:
    root = _bundle(tmp_path)
    runner = _Runner()
    io = _IO()
    answers = dict(ANSWERS, maps_browser_key=MAP_KEY, maps_map_id=MAP_ID)
    code = run_install(
        ["--non-interactive", "--answers", str(_answers_file(root, answers))],
        _deps(root, io, runner),
    )
    assert code == EXIT_OK
    assert f"GOOGLE_MAPS_BROWSER_API_KEY={MAP_KEY}" in (root / ".env").read_text("utf-8")
    assert f"GOOGLE_MAPS_MAP_ID={MAP_ID}" in (root / ".env").read_text("utf-8")
    for path in (root / ".install-state.json", root / "install.log"):
        assert MAP_KEY not in path.read_text("utf-8")
    assert MAP_KEY not in "".join(io.printed)
    assert all(MAP_KEY not in str(call.get("stdin")) for call in runner.calls)


@pytest.mark.parametrize("map_id", ["DEMO_MAP_ID", "abc\nINJECTED=1", "bad map id"])
def test_provided_maps_values_cannot_inject_env_lines_or_use_a_demo_id(
    tmp_path: Path, map_id: str
) -> None:
    with pytest.raises(ValueError):
        envgen.maps_environment(
            tmp_path / ".env",
            {"GOOGLE_MAPS_BROWSER_API_KEY": MAP_KEY, "GOOGLE_MAPS_MAP_ID": map_id},
        )
