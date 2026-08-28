"""Environment generation contract (B03/B04/B11).

- generated secrets have the exact required shapes (Fernet 44-char urlsafe
  base64 of 32 bytes) and are pairwise distinct;
- reconfiguration REUSES existing generated secrets from the private .env
  and rejects placeholders/missing/duplicates — it never silently rotates;
- no provider key is ever rendered to .env;
- LAN renders http origin + non-secure cookies; proxy/caddy render https +
  secure cookies; NEXT_PUBLIC_* stay empty (host-neutral images, B03);
- .env writes are atomic, private, and back up the previous file.
"""

from __future__ import annotations

import base64
from dataclasses import replace
import os
import sys
from pathlib import Path

import pytest

from scripts.install.envgen import (
    GENERATED_SECRET_KEYS,
    EnvGenError,
    derive_environment,
    generate_secrets,
    load_existing_generated_secrets,
    render_env,
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
