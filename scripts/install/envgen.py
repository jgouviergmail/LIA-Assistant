"""Private environment generation (B03/B04/B11).

Core secrets are GENERATED (never asked), LLM provider keys are NEVER rendered to
``.env`` (they live encrypted in the database via the stdin bootstrap), and
reconfiguration reuses the existing generated secrets — silent rotation
would orphan every Fernet-encrypted row.
Optional Maps browser credentials are private inputs kept only in this file.
"""

from __future__ import annotations

import base64
import os
import secrets
import stat
import time
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from scripts.install.maps import MAPS_ENV_KEYS, validate_maps_settings
from scripts.install.model import Exposure, PublicAnswers
from scripts.install.turnstile import (
    TURNSTILE_ENV_KEYS,
    TURNSTILE_SWITCH,
    validate_turnstile_settings,
)

#: Secrets the installer generates on a fresh install and MUST reuse after.
GENERATED_SECRET_KEYS: tuple[str, ...] = (
    "SECRET_KEY",
    "FERNET_KEY",
    "POSTGRES_PASSWORD",
    "REDIS_PASSWORD",
)

#: The ``.env`` keys an answer decides — the only ones a reconfiguration
#: rewrites. Every other installer value is written where the file lacks it,
#: so a value tuned in place survives. Held complete by a test that varies
#: every answer and compares the derivations.
ANSWER_DERIVED_KEYS: frozenset[str] = frozenset(
    {
        "SESSION_COOKIE_SECURE",
        "APP_URL_SERVER",
        "FRONTEND_URL",
        "API_URL",
        "CORS_ORIGINS",
        "DEFAULT_LANGUAGE",
        "DIAGNOSTICS_ENABLED",
        "LIVE_ENABLED",
        "RADIO_ENABLED",
        "AVATAR_ENABLED",
        "WORLD_ENABLED",
        "GRAFANA_ADMIN_USER",
        "GRAFANA_ADMIN_PASSWORD",
        "DIAGNOSTICS_WEBHOOK_SECRET",
        "ALERTMANAGER_LIA_WEBHOOK_URL",
    }
)

#: Answer-derived values the console never prints: a confirmation names them.
SECRET_ANSWER_DERIVED_KEYS: frozenset[str] = frozenset(
    {"DIAGNOSTICS_WEBHOOK_SECRET", "GRAFANA_ADMIN_PASSWORD"}
)

#: The host's Docker socket, whose group the sandbox overlay hands the API
#: (``group_add: ${DOCKER_GID:-...}``).
DOCKER_SOCKET = Path("/var/run/docker.sock")
DOCKER_GID_KEY = "DOCKER_GID"

#: Backups of one file within one second take a numbered suffix; past this
#: many something is wrong with the directory, not with the clock.
_BACKUP_NAME_ATTEMPTS = 100


class EnvGenError(ValueError):
    """Environment generation/reuse failure (stable value-free code)."""


def generate_secrets() -> Mapping[str, str]:
    """Generate every backend secret with its exact required shape."""
    return {
        "SECRET_KEY": secrets.token_urlsafe(48),
        # Fernet: 44-char urlsafe base64 of exactly 32 bytes.
        "FERNET_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        "POSTGRES_PASSWORD": secrets.token_urlsafe(24),
        "REDIS_PASSWORD": secrets.token_urlsafe(24),
    }


def _parse_env(path: Path) -> dict[str, str]:
    return _parse_env_text(path.read_text(encoding="utf-8"))


def _parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def load_existing_generated_secrets(
    path: Path, required_keys: Collection[str]
) -> Mapping[str, str]:
    """Reload the generated secrets from an existing private ``.env``.

    Raises:
        EnvGenError: ``env_file_missing``, ``env_file_not_private`` (POSIX),
            ``generated_secret_missing:<KEY>``,
            ``generated_secret_placeholder:<KEY>``, or
            ``generated_secret_duplicate:<KEY>``.
    """
    if not path.is_file():
        raise EnvGenError("env_file_missing")
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise EnvGenError("env_file_not_private")
    values = _parse_env(path)
    result: dict[str, str] = {}
    for key in required_keys:
        value = values.get(key, "")
        if not value:
            raise EnvGenError(f"generated_secret_missing:{key}")
        if value.startswith("CHANGE_ME"):
            raise EnvGenError(f"generated_secret_placeholder:{key}")
        if value in result.values():
            raise EnvGenError(f"generated_secret_duplicate:{key}")
        result[key] = value
    return result


def _origin(public: PublicAnswers) -> str:
    if public.exposure is Exposure.LAN:
        return f"http://{public.server_host}:3000"
    return f"https://{public.web_domain}"


def maps_environment(path: Path, provided: Mapping[str, str]) -> Mapping[str, str]:
    """Keep skipped operator settings; only a validated complete pair replaces them."""
    validated = validate_maps_settings(provided)
    if validated:
        return validated
    existing = _parse_env(path) if path.is_file() else {}
    return {key: existing.get(key, "") for key in MAPS_ENV_KEYS}


def turnstile_environment(path: Path, provided: Mapping[str, str]) -> Mapping[str, str]:
    """Keep a skipped check as configured; a validated complete pair switches it on."""
    validated = validate_turnstile_settings(provided)
    if validated:
        return {TURNSTILE_SWITCH: "true", **validated}
    existing = _parse_env(path) if path.is_file() else {}
    return {
        TURNSTILE_SWITCH: existing.get(TURNSTILE_SWITCH, "false"),
        **{key: existing.get(key, "") for key in TURNSTILE_ENV_KEYS},
    }


def derive_environment(
    public: PublicAnswers, generated: Mapping[str, str], *, current_env: str = ""
) -> Mapping[str, str]:
    """Derive the complete non-provider-key environment for one install.

    ``NEXT_PUBLIC_*`` values stay EMPTY on purpose (B03): release images are
    host-neutral and same-origin; runtime origin travels through the
    server-only ``APP_URL_SERVER``.
    """
    origin = _origin(public)
    secure = public.exposure is not Exposure.LAN
    in_force = _parse_env_text(current_env)
    grafana_user = in_force.get("GRAFANA_ADMIN_USER", "")
    grafana_password = in_force.get("GRAFANA_ADMIN_PASSWORD", "")
    if public.observability:
        grafana_user = grafana_user or "admin"
        grafana_password = grafana_password or secrets.token_urlsafe(32)
    return {
        "ENVIRONMENT": "production",
        "DEBUG": "false",
        "LOG_LEVEL": "INFO",
        "OPENAI_ORGANIZATION_ID": "",
        "FIREBASE_PROJECT_ID": "",
        "NEXT_PUBLIC_FIREBASE_API_KEY": "",
        "NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN": "",
        "NEXT_PUBLIC_FIREBASE_PROJECT_ID": "",
        "NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET": "",
        "NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID": "",
        "NEXT_PUBLIC_FIREBASE_APP_ID": "",
        "NEXT_PUBLIC_FIREBASE_VAPID_KEY": "",
        "GRAFANA_ADMIN_USER": grafana_user,
        "GRAFANA_ADMIN_PASSWORD": grafana_password,
        **{key: generated[key] for key in GENERATED_SECRET_KEYS},
        "POSTGRES_USER": "lia",
        "POSTGRES_DB": "lia",
        "SESSION_COOKIE_SECURE": "true" if secure else "false",
        "SESSION_COOKIE_DOMAIN": "",
        "APP_URL_SERVER": origin,
        "FRONTEND_URL": origin,
        "API_URL": origin,
        "CORS_ORIGINS": origin,
        "NEXT_PUBLIC_API_URL": "",
        "NEXT_PUBLIC_APP_URL": "",
        "DEFAULT_LANGUAGE": public.default_language,
        "NODE_ENV": "production",
        # Self-diagnostics (ADR-247): the flag follows the wizard answer; the
        # Alertmanager webhook only exists when the observability profile runs
        # on this install (prod API serves plain HTTP on 8000).
        "DIAGNOSTICS_ENABLED": "true" if public.self_diagnostics else "false",
        # Live voice mode (ADR-299): a capability ceiling only — the person's
        # own provider key opens the sessions, nothing else is provisioned.
        "LIVE_ENABLED": "true" if public.live_mode else "false",
        # Radio has no companion Compose service: the API's on-demand antenna
        # and newsroom run inside its existing workers (ADR-324).
        "RADIO_ENABLED": "true" if public.personal_radio else "false",
        # Personal Simli connector: no instance key or additional service.
        # Finite bounds mirror AvatarSettings; backend alignment checks them.
        "AVATAR_ENABLED": "true" if public.speaking_avatar else "false",
        # Browser drawing and native SQL/Redis authority need no extra service
        # or credential. Native operator policy and participant consent remain.
        "WORLD_ENABLED": "true" if public.world else "false",
        "AVATAR_MINTS_PER_HOUR": "6",
        "AVATAR_SESSION_LENGTH_SECONDS": "3600",
        "AVATAR_IDLE_SECONDS": "3600",
        "AVATAR_HTTP_TIMEOUT_SECONDS": "10",
        "AVATAR_CONNECT_TIMEOUT_SECONDS": "15",
        "AVATAR_PRESENCE_TIMEOUT_SECONDS": "120",
        # Shared across workers and voice surfaces. A self-hoster using
        # ElevenLabs can lower this to the allowance of their own account.
        "ELEVENLABS_TTS_MAX_CONCURRENCY": "5",
        # Shared by Fish Audio synthesis, transcription and voice design; a
        # self-hoster lowers it to the allowance of their own account.
        "FISHAUDIO_MAX_CONCURRENCY": "5",
        "DIAGNOSTICS_WEBHOOK_SECRET": (
            secrets.token_urlsafe(32) if public.self_diagnostics and public.observability else ""
        ),
        "ALERTMANAGER_LIA_WEBHOOK_URL": (
            "http://api:8000/api/v1/internal/diagnostics/alert-webhook"
            if public.self_diagnostics and public.observability
            else ""
        ),
    }


def render_env(base: str, values: Mapping[str, str]) -> str:
    """Render ``.env`` content: replace known keys in ``base``, append rest.

    Inline comments are never emitted after a value — under
    ``docker compose`` an inline comment on an empty-valued variable BECOMES
    the value (T5 regression class).
    """
    remaining = dict(values)
    lines: list[str] = []
    for line in base.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in remaining:
                lines.append(f"{key}={remaining.pop(key)}")
                continue
        lines.append(line)
    if remaining:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# Values generated by the installer (ADR-215).")
        lines.extend(f"{key}={value}" for key, value in remaining.items())
    return "\n".join(lines) + "\n"


def render_reconfigured_env(current_env: str, environment: Mapping[str, str]) -> str:
    """The ``.env`` a reconfiguration installs: the CURRENT file, updated.

    Only the values an answer decides (:data:`ANSWER_DERIVED_KEYS`) are
    rewritten; every other installer value is written only where the file
    lacks it. Starting from the installed file keeps every line the operator
    added, and writing the defaults only where missing keeps every value they
    tuned in place — a log level, a provider's concurrency the guides tell
    them to lower. A diagnostics webhook secret already in force is kept
    rather than rotated under the containers that read it.

    Args:
        current_env: The installed ``.env`` content.
        environment: :func:`derive_environment` for the new answers, with the
            generated secrets in force.

    Returns:
        The candidate content.
    """
    in_force = _parse_env_text(current_env)
    values = {
        key: value
        for key, value in environment.items()
        if key in ANSWER_DERIVED_KEYS or key not in in_force
    }
    # A configured credential survives both disabling and re-enabling the profile.
    # Empty template values are unconfigured and may be filled on activation.
    for key in ("GRAFANA_ADMIN_USER", "GRAFANA_ADMIN_PASSWORD"):
        if in_force.get(key):
            values[key] = in_force[key]
    secret_in_force = in_force.get("DIAGNOSTICS_WEBHOOK_SECRET", "")
    if values.get("DIAGNOSTICS_WEBHOOK_SECRET") and secret_in_force:
        values["DIAGNOSTICS_WEBHOOK_SECRET"] = secret_in_force
    return render_env(current_env, values)


@dataclass(frozen=True)
class EnvChange:
    """One answer-derived ``.env`` value a reconfiguration would change.

    Attributes:
        key: The variable.
        before: Its value in the file in force, ``None`` when absent.
        after: Its value in the candidate, ``None`` when absent.
    """

    key: str
    before: str | None
    after: str | None


def derived_changes(current_env: str, candidate_env: str) -> tuple[EnvChange, ...]:
    """Every answer-derived value the candidate changes against the file in force.

    The questions default to the RECORDED answers while these values are
    rewritten from them: compared with the recorded answers, a value edited
    by hand (a second origin in ``CORS_ORIGINS``) would be replaced by a run
    that changed nothing — so the comparison is with the file in force.

    Args:
        current_env: The installed ``.env`` content.
        candidate_env: The candidate ``.env`` content.

    Returns:
        The changes, sorted by key; empty when no such value moves.
    """
    before = _parse_env_text(current_env)
    after = _parse_env_text(candidate_env)
    return tuple(
        EnvChange(key, before.get(key), after.get(key))
        for key in sorted(ANSWER_DERIVED_KEYS)
        if before.get(key) != after.get(key)
    )


def describe_change(change: EnvChange) -> str:
    """``KEY: before -> after`` for the console, which is not redacted.

    Args:
        change: One derived change.

    Returns:
        The line; a secret's value is never shown, only whether there is one.
    """
    return (
        f"{change.key}: {_shown(change.key, change.before)} -> "
        f"{_shown(change.key, change.after)}"
    )


def _shown(key: str, value: str | None) -> str:
    if value is None:
        return "(absent)"
    if not value:
        return "(empty)"
    return "(hidden)" if key in SECRET_ANSWER_DERIVED_KEYS else value


def docker_socket_gid(socket: Path | None) -> str | None:
    """The group owning the host's Docker socket, ``None`` where there is none.

    Without ``DOCKER_GID`` the sandbox overlay falls back to a fixed group,
    which is not every host's: on a host whose socket belongs to another one,
    the API cannot use the socket.

    Args:
        socket: The socket's path; ``None`` reads nothing.

    Returns:
        The group id, as ``.env`` writes it.
    """
    if socket is None:
        return None
    try:
        return str(os.stat(socket).st_gid)
    except FileNotFoundError:
        return None


def with_docker_gid(env_text: str, gid: str | None) -> str:
    """``env_text`` with ``DOCKER_GID`` set to ``gid`` where it holds none.

    Not answer-derived: a value already there — the operator's — is kept, and
    so is the one written here, by every later reconfiguration.

    Args:
        env_text: A ``.env`` content.
        gid: The socket's group, or ``None`` when there is no socket to read.

    Returns:
        The content, unchanged when ``gid`` is ``None`` or a value is set.
    """
    if gid is None or _parse_env_text(env_text).get(DOCKER_GID_KEY):
        return env_text
    return render_env(env_text, {DOCKER_GID_KEY: gid})


def _create_private(path: Path, data: bytes) -> None:
    """Create ``path`` holding ``data``, private from its first byte.

    ``write_bytes`` then ``chmod`` leaves the file, for a moment, at the
    umask's mode — for a copy of the ``.env``, every generated secret readable
    by the group and the world. ``O_EXCL`` refuses a path that already exists.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def private_backup(path: Path) -> Path:
    """Copy ``path`` beside itself, private from its first byte.

    Args:
        path: The file about to be replaced.

    Returns:
        The copy, ``<name>.backup.<epoch seconds>`` (suffixed when that name is
        taken, two writes within one second).

    Raises:
        EnvGenError: ``backup_name_exhausted`` when no free name is left.
    """
    stem = f"{path.name}.backup.{int(time.time())}"
    data = path.read_bytes()
    for attempt in range(_BACKUP_NAME_ATTEMPTS):
        backup = path.with_name(stem if attempt == 0 else f"{stem}.{attempt}")
        try:
            _create_private(backup, data)
        except FileExistsError:
            continue
        return backup
    raise EnvGenError("backup_name_exhausted")


def replace_private(path: Path, data: bytes) -> None:
    """Atomically replace ``path`` with ``data``, private from its first byte.

    A sibling temporary file, fsynced, then ``os.replace``: a reader never
    sees half a file, and a failure — an interrupt included — leaves the
    previous one untouched.
    """
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.unlink(missing_ok=True)
    try:
        # Inside the guard: a write that fails halfway (a full disk) must not
        # leave a partial copy of the file — a `.env` one holds every secret.
        _create_private(tmp, data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_atomic_private(path: Path, content: str) -> Path | None:
    """Atomically write a private file; back up any existing one first.

    Returns:
        The backup path when a previous file existed, else None. A failed
        write leaves the existing file untouched (:func:`replace_private`).
    """
    backup = private_backup(path) if path.is_file() else None
    replace_private(path, content.encode("utf-8"))
    return backup
