"""The optional anti-robot check stays private, paired, production-safe and resumable (ADR-364).

Turnstile guards the password doors of an instance reached on a public domain; on a plain
LAN install the questions are not asked. Its two keys travel like the Maps pair: both or
neither, hidden at the prompt, written to the private `.env` only, never re-asked on a
resume, and an existing configuration survives a run that skips them. Cloudflare's
testing keys are refused — in production they would void the check.
"""

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

SITE_KEY = "0x4AAAAAAAfictionalSiteKey"
SECRET_KEY = "0x4AAAAAAAfictionalSecretKey00"
KEYS = {"turnstile_site_key", "turnstile_secret_key"}
DOMAINS = {"exposure": "proxy", "web_domain": "lia.example.org", "api_domain": "api.example.org"}
PROXY_PUBLIC = {**{k: v for k, v in BASE_PUBLIC.items() if k != "server_host"}, **DOMAINS}


def _proxy(site: str, secret: str) -> _ScriptedIO:
    return _ScriptedIO(
        PROXY_PUBLIC, {**SECRETS, "turnstile_site_key": site, "turnstile_secret_key": secret}
    )


def test_the_keys_are_asked_only_when_lia_is_reached_on_a_domain() -> None:
    lan = _ScriptedIO(BASE_PUBLIC, SECRETS)
    _collect(lan)
    assert not KEYS.intersection(lan.secret_served)

    proxy = _proxy(SITE_KEY, SECRET_KEY)
    public, private = _collect(proxy)
    assert KEYS.issubset(proxy.secret_served)
    assert not KEYS.intersection(proxy.public_served)
    # The keys only: the switch is derived when the env is written, and never
    # registered as a secret to redact.
    assert private.turnstile_settings == {
        "TURNSTILE_SITE_KEY": SITE_KEY,
        "TURNSTILE_SECRET_KEY": SECRET_KEY,
    }
    assert SECRET_KEY not in repr(private) and SECRET_KEY not in repr(dataclasses.asdict(public))
    assert SECRET_KEY not in "".join(proxy.printed)


def test_both_keys_left_empty_skip_the_check() -> None:
    _public, private = _collect(_proxy("", ""))
    assert not private.turnstile_settings


@pytest.mark.parametrize("site,secret", [(SITE_KEY, ""), ("", SECRET_KEY)])
def test_half_a_configuration_fails_before_artifacts_are_written(site: str, secret: str) -> None:
    with pytest.raises(InstallInputError, match="incomplete_turnstile_configuration"):
        _collect(_proxy(site, secret))


@pytest.mark.parametrize(
    "site,secret",
    [
        # Cloudflare's documented testing keys: always-pass, always-block, forced challenge.
        ("1x00000000000000000000AA", SECRET_KEY),
        ("3x00000000000000000000FF", SECRET_KEY),
        (SITE_KEY, "1x0000000000000000000000000000000AA"),
        (SITE_KEY, "2x0000000000000000000000000000000AA"),
        # An answer that would write a second line into the private `.env`.
        (SITE_KEY, "abc\nINJECTED=1"),
        ("bad key", SECRET_KEY),
    ],
)
def test_testing_keys_and_injected_lines_are_refused(
    tmp_path: Path, site: str, secret: str
) -> None:
    with pytest.raises(ValueError):
        envgen.turnstile_environment(
            tmp_path / ".env", {"TURNSTILE_SITE_KEY": site, "TURNSTILE_SECRET_KEY": secret}
        )


def test_skipping_keeps_the_operators_existing_configuration(tmp_path: Path) -> None:
    path = tmp_path / ".env"
    path.write_text(
        f"TURNSTILE_ENABLED=true\nTURNSTILE_SITE_KEY={SITE_KEY}\n"
        f"TURNSTILE_SECRET_KEY={SECRET_KEY}\nOTHER_PRIVATE=preserve\n",
        encoding="utf-8",
    )
    before = path.read_bytes()
    assert envgen.turnstile_environment(path, {}) == {
        "TURNSTILE_ENABLED": "true",
        "TURNSTILE_SITE_KEY": SITE_KEY,
        "TURNSTILE_SECRET_KEY": SECRET_KEY,
    }
    assert path.read_bytes() == before


def test_a_fresh_install_without_keys_leaves_the_check_off(tmp_path: Path) -> None:
    assert envgen.turnstile_environment(tmp_path / ".env", {}) == {
        "TURNSTILE_ENABLED": "false",
        "TURNSTILE_SITE_KEY": "",
        "TURNSTILE_SECRET_KEY": "",
    }


def test_resuming_bootstrap_does_not_ask_for_keys_already_kept_in_private_env() -> None:
    io = _ScriptedIO({}, SECRETS)
    private = collect_secret_answers(
        build_questions(), io=io.adapter(), non_interactive=False, answers_path=None
    )
    assert not KEYS.intersection(io.secret_served)
    assert not private.turnstile_settings


def test_a_complete_install_writes_the_keys_only_to_the_private_env(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    runner = _Runner()
    io = _IO()
    answers = {k: v for k, v in ANSWERS.items() if k != "server_host"}
    answers.update(DOMAINS, turnstile_site_key=SITE_KEY, turnstile_secret_key=SECRET_KEY)
    code = run_install(
        ["--non-interactive", "--answers", str(_answers_file(root, answers))],
        _deps(root, io, runner),
    )
    assert code == EXIT_OK
    private_env = (root / ".env").read_text("utf-8")
    assert "TURNSTILE_ENABLED=true" in private_env
    assert f"TURNSTILE_SITE_KEY={SITE_KEY}" in private_env
    assert f"TURNSTILE_SECRET_KEY={SECRET_KEY}" in private_env
    for path in (root / ".install-state.json", root / "install.log"):
        assert SECRET_KEY not in path.read_text("utf-8")
    assert SECRET_KEY not in "".join(io.printed)
    assert all(SECRET_KEY not in str(call.get("stdin")) for call in runner.calls)
