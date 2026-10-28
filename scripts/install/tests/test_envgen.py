"""Environment generation contract (B03/B04/B11).

- generated secrets have the exact required shapes (Fernet 44-char urlsafe
  base64 of 32 bytes) and are pairwise distinct;
- reconfiguration REUSES existing generated secrets from the private .env
  and rejects placeholders/missing/duplicates — it never silently rotates;
- no provider key is ever rendered to .env;
- LAN renders http origin + non-secure cookies; proxy/caddy render https +
  secure cookies; NEXT_PUBLIC_* stay empty (host-neutral images, B03);
- .env writes are atomic, private, and back up the previous file;
- a reconfiguration rewrites only what an answer decides: a value the
  operator tuned survives, and the diagnostics webhook secret in force stays.
"""

from __future__ import annotations

import base64
from dataclasses import replace
import os
import re
import sys
from pathlib import Path

import pytest

from scripts.install import envgen
from scripts.install.envgen import (
    ANSWER_DERIVED_KEYS,
    GENERATED_SECRET_KEYS,
    EnvChange,
    EnvGenError,
    derive_environment,
    derived_changes,
    describe_change,
    docker_socket_gid,
    generate_secrets,
    load_existing_generated_secrets,
    private_backup,
    render_env,
    render_reconfigured_env,
    replace_private,
    with_docker_gid,
    write_atomic_private,
)
from scripts.install.model import Exposure, InstallMode, PublicAnswers

SECRET_CANARY = "sk-PROVIDER-CANARY-123"


def _public(exposure: Exposure = Exposure.LAN) -> PublicAnswers:
    return PublicAnswers(
        language="en",
        mode=InstallMode.LOCAL,
        exposure=exposure,
        admin_email="admin@ops.tld",
        admin_name="Ops",
        default_language="fr",
        observability=False,
        skill_sandbox=False,
        server_host="192.168.1.50" if exposure is Exposure.LAN else None,
        web_domain=None if exposure is Exposure.LAN else "lia.example.org",
        api_domain=None if exposure is Exposure.LAN else "api.example.org",
        caddy_email="acme@example.org" if exposure is Exposure.CADDY else None,
        manifest_path=None,
    )


def test_generated_secrets_have_required_shapes_and_are_distinct() -> None:
    secrets = generate_secrets()
    assert set(secrets) == set(GENERATED_SECRET_KEYS)
    fernet = secrets["FERNET_KEY"]
    assert len(fernet) == 44
    assert len(base64.urlsafe_b64decode(fernet)) == 32
    assert len(secrets["SECRET_KEY"]) >= 32
    assert len(set(secrets.values())) == len(secrets), "duplicate secret values"


def test_reconfiguration_reuses_existing_secrets(tmp_path: Path) -> None:
    generated = generate_secrets()
    env_path = tmp_path / ".env"
    env_path.write_text(
        "".join(f"{k}={v}\n" for k, v in generated.items()), encoding="utf-8"
    )
    if os.name == "posix":
        env_path.chmod(0o600)
    loaded = load_existing_generated_secrets(env_path, GENERATED_SECRET_KEYS)
    assert dict(loaded) == dict(generated)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda v: v.pop("FERNET_KEY"), "generated_secret_missing:FERNET_KEY"),
        (
            lambda v: v.update(FERNET_KEY="CHANGE_ME_FERNET_KEY"),
            "generated_secret_placeholder:FERNET_KEY",
        ),
        (
            lambda v: v.update(REDIS_PASSWORD=v["POSTGRES_PASSWORD"]),
            "generated_secret_duplicate:REDIS_PASSWORD",
        ),
    ],
)
def test_reconfiguration_rejects_broken_secret_sets(
    tmp_path: Path, mutation, code: str
) -> None:
    values = dict(generate_secrets())
    mutation(values)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8"
    )
    if os.name == "posix":
        env_path.chmod(0o600)
    with pytest.raises(EnvGenError) as excinfo:
        load_existing_generated_secrets(env_path, GENERATED_SECRET_KEYS)
    assert str(excinfo.value) == code


def test_lan_environment_is_http_and_not_secure() -> None:
    env = derive_environment(_public(Exposure.LAN), generate_secrets())
    assert env["APP_URL_SERVER"] == "http://192.168.1.50:3000"
    assert env["FRONTEND_URL"] == "http://192.168.1.50:3000"
    assert env["SESSION_COOKIE_SECURE"] == "false"
    assert env["DEFAULT_LANGUAGE"] == "fr"
    assert env["NEXT_PUBLIC_API_URL"] == ""
    assert env["NEXT_PUBLIC_APP_URL"] == ""


@pytest.mark.parametrize("exposure", [Exposure.PROXY, Exposure.CADDY])
def test_domain_environments_are_https_and_secure(exposure: Exposure) -> None:
    env = derive_environment(_public(exposure), generate_secrets())
    assert env["APP_URL_SERVER"] == "https://lia.example.org"
    assert env["SESSION_COOKIE_SECURE"] == "true"
    assert "http://" not in env["CORS_ORIGINS"]


def test_no_provider_key_reaches_the_environment() -> None:
    env = derive_environment(_public(), generate_secrets())
    rendered = render_env("", env)
    for needle in ("OPENAI_API_KEY", "DEEPSEEK_API_KEY", SECRET_CANARY):
        assert needle not in rendered
        assert needle not in env


def test_render_env_replaces_and_appends_without_inline_comments() -> None:
    base = (
        "# header comment\n"
        "SECRET_KEY=CHANGE_ME_SECRET_KEY_MIN_32_CHARS\n"
        "KEEP_ME=untouched\n"
    )
    rendered = render_env(base, {"SECRET_KEY": "real-value", "NEW_KEY": ""})
    lines = rendered.splitlines()
    assert "SECRET_KEY=real-value" in lines
    assert "KEEP_ME=untouched" in lines
    assert "NEW_KEY=" in lines
    for line in lines:
        # An inline comment after a value becomes part of the VALUE under
        # docker compose --env-file: forbidden (learned in T5).
        if "=" in line and not line.lstrip().startswith("#"):
            assert "#" not in line.split("=", 1)[1], line


def test_write_atomic_private_backs_up_and_survives_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / ".env"
    target.write_text("ORIGINAL=1\n", encoding="utf-8")
    backup = write_atomic_private(target, "REPLACED=1\n")
    assert target.read_text(encoding="utf-8") == "REPLACED=1\n"
    assert backup is not None and backup.read_text(encoding="utf-8") == "ORIGINAL=1\n"
    assert backup.name.startswith(".env.backup.")
    if os.name == "posix":
        assert (target.stat().st_mode & 0o777) == 0o600

    def _boom(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(OSError):
        write_atomic_private(target, "NEVER=1\n")
    assert target.read_text(encoding="utf-8") == "REPLACED=1\n", "target intact"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
def test_existing_env_must_be_private_to_be_reused(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("SECRET_KEY=x\n", encoding="utf-8")
    env_path.chmod(0o644)
    with pytest.raises(EnvGenError) as excinfo:
        load_existing_generated_secrets(env_path, ("SECRET_KEY",))
    assert str(excinfo.value) == "env_file_not_private"


def test_self_diagnostics_enabled_with_observability_wires_the_webhook() -> None:
    """Opting in with the observability profile turns alerts into incidents."""
    public = replace(_public(Exposure.LAN), observability=True, self_diagnostics=True)
    env = derive_environment(public, generate_secrets())
    assert env["DIAGNOSTICS_ENABLED"] == "true"
    assert len(env["DIAGNOSTICS_WEBHOOK_SECRET"]) >= 32
    assert (
        env["ALERTMANAGER_LIA_WEBHOOK_URL"]
        == "http://api:8000/api/v1/internal/diagnostics/alert-webhook"
    )


def test_self_diagnostics_without_observability_keeps_probes_only() -> None:
    """No Alertmanager on this install: the flag works, the webhook stays off."""
    public = replace(_public(Exposure.LAN), observability=False, self_diagnostics=True)
    env = derive_environment(public, generate_secrets())
    assert env["DIAGNOSTICS_ENABLED"] == "true"
    assert env["ALERTMANAGER_LIA_WEBHOOK_URL"] == ""


def test_self_diagnostics_defaults_to_disabled() -> None:
    env = derive_environment(_public(Exposure.LAN), generate_secrets())
    assert env["DIAGNOSTICS_ENABLED"] == "false"
    assert env["ALERTMANAGER_LIA_WEBHOOK_URL"] == ""


def test_live_mode_follows_the_wizard_answer_and_defaults_to_disabled() -> None:
    # ADR-299: the flag is the whole provisioning — the person's own key opens
    # the sessions, so the installer writes nothing else for it.
    env = derive_environment(_public(Exposure.LAN), generate_secrets())
    assert env["LIVE_ENABLED"] == "false"
    public = replace(_public(Exposure.LAN), live_mode=True)
    env = derive_environment(public, generate_secrets())
    assert env["LIVE_ENABLED"] == "true"


def test_personal_radio_follows_the_wizard_answer_and_defaults_to_disabled() -> None:
    env = derive_environment(_public(Exposure.LAN), generate_secrets())
    assert env["RADIO_ENABLED"] == "false"
    public = replace(_public(Exposure.LAN), personal_radio=True)
    env = derive_environment(public, generate_secrets())
    assert env["RADIO_ENABLED"] == "true"


def test_speaking_avatar_is_an_opt_in_without_an_instance_credential() -> None:
    env = derive_environment(_public(), generate_secrets())
    assert env["AVATAR_ENABLED"] == "false"
    assert env["AVATAR_MINTS_PER_HOUR"] == "6"
    assert env["AVATAR_SESSION_LENGTH_SECONDS"] == "3600"
    assert env["AVATAR_IDLE_SECONDS"] == "3600"
    assert env["AVATAR_HTTP_TIMEOUT_SECONDS"] == "10"
    assert env["AVATAR_CONNECT_TIMEOUT_SECONDS"] == "15"
    assert env["AVATAR_PRESENCE_TIMEOUT_SECONDS"] == "120"
    enabled = derive_environment(
        replace(_public(), speaking_avatar=True), generate_secrets()
    )
    assert enabled["AVATAR_ENABLED"] == "true"
    assert not any("SIMLI" in key for key in enabled)


def _values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    return values


def _answer_variants() -> list[PublicAnswers]:
    lan = _public()
    return [
        _public(Exposure.PROXY),
        _public(Exposure.CADDY),
        replace(lan, server_host="10.0.0.9"),
        replace(lan, default_language="en"),
        replace(lan, observability=True),
        replace(lan, self_diagnostics=True),
        replace(lan, observability=True, self_diagnostics=True),
        replace(lan, skill_sandbox=True),
        replace(lan, live_mode=True),
        replace(lan, personal_radio=True),
        replace(lan, speaking_avatar=True),
        replace(lan, world=True),
    ]


def test_every_value_an_answer_moves_is_declared_answer_derived() -> None:
    # Undeclared, a value an answer decides would never follow a
    # reconfiguration; declared but never moving, a tuned value would be reset.
    generated = generate_secrets()
    base = derive_environment(_public(), generated)
    moved: set[str] = set()
    for answers in _answer_variants():
        derived = derive_environment(answers, generated)
        moved |= {key for key, value in derived.items() if value != base.get(key)}
    assert moved <= ANSWER_DERIVED_KEYS, sorted(moved - ANSWER_DERIVED_KEYS)
    assert ANSWER_DERIVED_KEYS <= moved, sorted(ANSWER_DERIVED_KEYS - moved)


def test_world_follows_operator_choice_and_preserves_tuned_admission() -> None:
    generated = generate_secrets()
    disabled = derive_environment(_public(), generated)
    enabled = derive_environment(replace(_public(), world=True), generated)
    assert disabled["WORLD_ENABLED"] == "false"
    assert enabled["WORLD_ENABLED"] == "true"
    current = "WORLD_ENABLED=false\nWORLD_CAPACITY=3\nWORLD_NAMESPACE=operator-instance\n"
    candidate = render_reconfigured_env(current, enabled)
    assert "WORLD_ENABLED=true\n" in candidate
    assert "WORLD_CAPACITY=3\n" in candidate
    assert "WORLD_NAMESPACE=operator-instance\n" in candidate


def test_a_reconfigured_env_moves_only_what_the_answers_decide() -> None:
    generated = generate_secrets()
    current = render_env("", derive_environment(_public(), generated))
    tuned = current.replace("LOG_LEVEL=INFO", "LOG_LEVEL=DEBUG").replace(
        "FISHAUDIO_MAX_CONCURRENCY=5", "FISHAUDIO_MAX_CONCURRENCY=2"
    )
    tuned += "OPERATOR_LINE=kept\n"
    candidate = replace(_public(), server_host="10.0.0.9", live_mode=True)

    values = _values(render_reconfigured_env(tuned, derive_environment(candidate, generated)))
    assert values["LOG_LEVEL"] == "DEBUG"
    assert values["FISHAUDIO_MAX_CONCURRENCY"] == "2"
    assert values["OPERATOR_LINE"] == "kept"
    assert values["APP_URL_SERVER"] == "http://10.0.0.9:3000"
    assert values["LIVE_ENABLED"] == "true"
    for key in GENERATED_SECRET_KEYS:
        assert values[key] == generated[key]


def test_a_reconfigured_env_writes_the_defaults_a_file_lacks() -> None:
    # A file written by an older installer gains the values it never had.
    rendered = render_reconfigured_env(
        "LOG_LEVEL=DEBUG\n",
        {"LOG_LEVEL": "INFO", "FISHAUDIO_MAX_CONCURRENCY": "5"},
    )
    assert _values(rendered) == {"LOG_LEVEL": "DEBUG", "FISHAUDIO_MAX_CONCURRENCY": "5"}


def test_the_diagnostics_webhook_secret_in_force_is_kept_until_turned_off() -> None:
    wired = replace(_public(), observability=True, self_diagnostics=True)
    generated = generate_secrets()
    current = render_env("", derive_environment(wired, generated))
    in_force = _values(current)["DIAGNOSTICS_WEBHOOK_SECRET"]
    assert in_force

    moved = render_reconfigured_env(
        current, derive_environment(replace(wired, server_host="10.0.0.9"), generated)
    )
    assert _values(moved)["DIAGNOSTICS_WEBHOOK_SECRET"] == in_force

    off = render_reconfigured_env(
        current, derive_environment(replace(wired, self_diagnostics=False), generated)
    )
    assert _values(off)["DIAGNOSTICS_WEBHOOK_SECRET"] == ""
    assert _values(off)["ALERTMANAGER_LIA_WEBHOOK_URL"] == ""


def test_a_write_that_fails_halfway_leaves_no_partial_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The temporary copy was created outside the guard: a write that failed
    # left a partial `.env.tmp-<pid>` — every secret in it — that nobody removed.
    target = tmp_path / ".env"
    target.write_text("FERNET_KEY=in-force\n", encoding="utf-8")

    def _disk_full(descriptor: int) -> None:
        raise OSError("No space left on device")

    monkeypatch.setattr(envgen.os, "fsync", _disk_full)
    with pytest.raises(OSError):
        replace_private(target, b"FERNET_KEY=in-force\nLOG_LEVEL=INFO\n")
    assert target.read_text(encoding="utf-8") == "FERNET_KEY=in-force\n"
    assert list(tmp_path.glob("*.tmp-*")) == [], "no partial copy left behind"


def test_the_changes_listed_are_the_derived_values_that_move_against_the_file() -> None:
    current = "LOG_LEVEL=DEBUG\nCORS_ORIGINS=http://a:3000,http://b:3000\nLIVE_ENABLED=false\n"
    candidate = (
        "LOG_LEVEL=INFO\nCORS_ORIGINS=http://a:3000\nLIVE_ENABLED=false\nAVATAR_ENABLED=false\n"
    )
    assert derived_changes(current, candidate) == (
        EnvChange("AVATAR_ENABLED", None, "false"),
        EnvChange("CORS_ORIGINS", "http://a:3000,http://b:3000", "http://a:3000"),
    ), "LOG_LEVEL is no answer's: it is never listed"
    assert derived_changes(current, current) == ()


def test_a_listed_change_never_shows_a_secret() -> None:
    assert describe_change(EnvChange("CORS_ORIGINS", "http://a:3000", None)) == (
        "CORS_ORIGINS: http://a:3000 -> (absent)"
    )
    assert describe_change(EnvChange("DIAGNOSTICS_WEBHOOK_SECRET", "", "s3cr3t")) == (
        "DIAGNOSTICS_WEBHOOK_SECRET: (empty) -> (hidden)"
    )


def test_the_docker_socket_group_is_read_where_there_is_a_socket(tmp_path: Path) -> None:
    socket = tmp_path / "docker.sock"
    socket.write_text("", encoding="utf-8")
    assert docker_socket_gid(socket) == str(os.stat(socket).st_gid)
    assert docker_socket_gid(tmp_path / "absent.sock") is None
    assert docker_socket_gid(None) is None


@pytest.mark.parametrize(
    ("env_text", "expected"),
    [
        ("LOG_LEVEL=INFO\n", "1001"),
        ("DOCKER_GID=\nLOG_LEVEL=INFO\n", "1001"),  # an empty value is the fallback's
        ("DOCKER_GID=4242\n", "4242"),  # the operator's value stays
    ],
)
def test_docker_gid_is_written_only_where_the_file_holds_none(
    env_text: str, expected: str
) -> None:
    rendered = with_docker_gid(env_text, "1001")
    assert _values(rendered)["DOCKER_GID"] == expected
    assert with_docker_gid(env_text, None) == env_text


def test_two_backups_within_one_second_keep_both_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(envgen.time, "time", lambda: 1_700_000_000.0)
    target = tmp_path / ".env"
    target.write_text("A=1\n", encoding="utf-8")
    first = private_backup(target)
    target.write_text("A=2\n", encoding="utf-8")
    second = private_backup(target)
    assert first != second
    assert first.read_text(encoding="utf-8") == "A=1\n"
    assert second.read_text(encoding="utf-8") == "A=2\n"


@pytest.mark.parametrize("observability", (False, True))
def test_fresh_environment_covers_compose_interpolations(observability: bool) -> None:
    root = Path(__file__).resolve().parents[3]
    public = replace(_public(), observability=observability)
    values = _values(
        render_env(
            (root / ".env.min.prod.example").read_text(encoding="utf-8"),
            derive_environment(public, generate_secrets()),
        )
    )
    required = set(
        re.findall(
            r"(?<!\$)\$\{([A-Z][A-Z0-9_]*)\}",
            (root / "docker-compose.prod.yml").read_text(encoding="utf-8"),
        )
    )
    missing = required - values.keys()
    assert not missing, sorted(missing)


def test_optional_compose_credentials_remain_empty_when_not_enabled() -> None:
    values = derive_environment(_public(), generate_secrets())
    root = Path(__file__).resolve().parents[3]
    firebase = set(
        re.findall(
            r"\$\{(NEXT_PUBLIC_FIREBASE_[A-Z_]+)\}",
            (root / "docker-compose.prod.yml").read_text(encoding="utf-8"),
        )
    )
    assert firebase <= values.keys()
    assert all(values[key] == "" for key in firebase)
    assert values.get("GRAFANA_ADMIN_USER") == ""
    assert values.get("GRAFANA_ADMIN_PASSWORD") == ""


def test_observability_names_this_host_on_every_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(envgen.socket, "gethostname", lambda: "lia-host")
    public = replace(_public(), observability=True)
    named = derive_environment(public, generate_secrets())
    assert named["OBSERVABILITY_HOST"] == "lia-host"
    unnamed = derive_environment(_public(), generate_secrets())
    assert unnamed["OBSERVABILITY_HOST"] == ""


@pytest.mark.parametrize("observability", (False, True))
def test_an_operators_alert_host_survives_reconfiguration(
    observability: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(envgen.socket, "gethostname", lambda: "lia-host")
    public = replace(_public(), observability=observability)
    current = "OBSERVABILITY_HOST=edge-01\n"
    values = _values(
        render_reconfigured_env(current, derive_environment(public, generate_secrets()))
    )
    assert values["OBSERVABILITY_HOST"] == "edge-01"


def test_observability_generates_a_distinct_strong_grafana_password() -> None:
    public = replace(_public(), observability=True)
    first = derive_environment(public, generate_secrets())
    second = derive_environment(public, generate_secrets())
    assert first.get("GRAFANA_ADMIN_USER") == "admin"
    assert len(first.get("GRAFANA_ADMIN_PASSWORD", "")) >= 32
    different = first.get("GRAFANA_ADMIN_PASSWORD") != second.get("GRAFANA_ADMIN_PASSWORD")
    assert different


@pytest.mark.parametrize(
    "current",
    ("", "GRAFANA_ADMIN_USER=\nGRAFANA_ADMIN_PASSWORD=\n"),
)
def test_enabling_observability_fills_missing_or_empty_grafana_credentials(
    current: str,
) -> None:
    public = replace(_public(), observability=True)
    candidate = render_reconfigured_env(current, derive_environment(public, generate_secrets()))
    values = _values(candidate)
    assert values.get("GRAFANA_ADMIN_USER") == "admin"
    assert len(values.get("GRAFANA_ADMIN_PASSWORD", "")) >= 32


@pytest.mark.parametrize("observability", (False, True))
def test_existing_grafana_credentials_survive_reconfiguration(
    observability: bool,
) -> None:
    password = generate_secrets()["SECRET_KEY"]
    current = "GRAFANA_ADMIN_USER=operator-grafana\nGRAFANA_ADMIN_PASSWORD=" + password + "\n"
    public = replace(_public(), observability=observability)
    values = _values(
        render_reconfigured_env(current, derive_environment(public, generate_secrets()))
    )
    assert values["GRAFANA_ADMIN_USER"] == "operator-grafana"
    unchanged = values["GRAFANA_ADMIN_PASSWORD"] == password
    assert unchanged


def test_grafana_password_is_hidden_in_reconfiguration_confirmation() -> None:
    password = generate_secrets()["SECRET_KEY"]
    line = describe_change(EnvChange("GRAFANA_ADMIN_PASSWORD", None, password))
    leaked = password in line
    assert not leaked
    assert "(hidden)" in line


@pytest.mark.parametrize("empty_literal", ('""', "''"))
@pytest.mark.parametrize("empty_keys", ("both", "user", "password"))
def test_activation_fills_quoted_empty_grafana_credentials(
    empty_literal: str, empty_keys: str
) -> None:
    retained_password = generate_secrets()["SECRET_KEY"]
    current_values = {
        "GRAFANA_ADMIN_USER": empty_literal if empty_keys != "password" else "operator",
        "GRAFANA_ADMIN_PASSWORD": empty_literal if empty_keys != "user" else retained_password,
    }
    current = "".join(f"{key}={value}\n" for key, value in current_values.items())
    values = derive_environment(
        replace(_public(), observability=True), generate_secrets(), current_env=current
    )
    assert values["GRAFANA_ADMIN_USER"] == ("admin" if empty_keys != "password" else "operator")
    if empty_keys != "user":
        assert len(values["GRAFANA_ADMIN_PASSWORD"]) >= 32
        assert values["GRAFANA_ADMIN_PASSWORD"] not in ('""', "''")
    else:
        assert values["GRAFANA_ADMIN_PASSWORD"] == retained_password


@pytest.mark.parametrize("empty_literal", ('""', "''"))
@pytest.mark.parametrize("empty_keys", ("both", "user", "password"))
def test_reconfiguration_does_not_restore_quoted_empty_grafana_credentials(
    empty_literal: str, empty_keys: str
) -> None:
    retained_password = generate_secrets()["SECRET_KEY"]
    current_values = {
        "GRAFANA_ADMIN_USER": empty_literal if empty_keys != "password" else "operator",
        "GRAFANA_ADMIN_PASSWORD": empty_literal if empty_keys != "user" else retained_password,
    }
    current = "".join(f"{key}={value}\n" for key, value in current_values.items())
    proposed = derive_environment(replace(_public(), observability=True), generate_secrets())
    candidate = _values(render_reconfigured_env(current, proposed))
    assert candidate["GRAFANA_ADMIN_USER"] == (
        proposed["GRAFANA_ADMIN_USER"] if empty_keys != "password" else "operator"
    )
    assert candidate["GRAFANA_ADMIN_PASSWORD"] == (
        proposed["GRAFANA_ADMIN_PASSWORD"] if empty_keys != "user" else retained_password
    )


@pytest.mark.parametrize("observability", (False, True))
@pytest.mark.parametrize(
    ("username", "password"),
    (
        ('"operator"', "'nonempty$literal'"),
        ("'operator with spaces'", '"nonempty ${NOT_EVALUATED}"'),
        ('" "', "' '"),
    ),
)
def test_nonempty_quoted_grafana_credentials_remain_exactly_as_written(
    observability: bool, username: str, password: str
) -> None:
    current_values = {
        "GRAFANA_ADMIN_USER": username,
        "GRAFANA_ADMIN_PASSWORD": password,
    }
    current = "".join(f"{key}={value}\n" for key, value in current_values.items())
    proposed = derive_environment(
        replace(_public(), observability=observability),
        generate_secrets(),
        current_env=current,
    )
    candidate = render_reconfigured_env(current, proposed)
    for key, value in current_values.items():
        assert proposed[key] == value
        assert _values(candidate)[key] == value
        assert f"{key}={value}\n" in candidate
