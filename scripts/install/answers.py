"""Answer collection and validation (B11/B13).

Public answers travel through ``input_fn``; secrets travel STRICTLY through
``getpass_fn`` and end up only in ``SecretAnswers``. Non-interactive runs
read one private answers file (mode 0o600 on POSIX), never prompt, and fail
with stable value-free codes.
"""

from __future__ import annotations

import ipaddress
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from scripts.install.i18n import msg
from scripts.install.model import (
    PASSWORD_RULES,
    Exposure,
    InstallMode,
    IOAdapter,
    PublicAnswers,
    Question,
    QuestionKind,
    SecretAnswers,
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"
)
_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
    r"(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$"
)
_TRUE_VALUES = frozenset({"yes", "y", "true", "1"})
_FALSE_VALUES = frozenset({"no", "n", "false", "0"})
_MAX_INTERACTIVE_ATTEMPTS = 10

#: Special-use TLDs (RFC 2606/6761) the backend's EmailStr also refuses. The
#: wizard must reject them at QUESTION time: the bootstrap gate would only
#: fire after acquire + start, a very expensive way to learn your admin
#: address can never log in (v1.30.1 qualification: `admin@smoke.invalid`
#: bootstrapped, then 422 on every login).
_SPECIAL_USE_TLDS = frozenset({"invalid", "example", "test", "localhost"})


class InstallInputError(ValueError):
    """Malformed or incomplete installer input (stable value-free code)."""


def is_valid_email(value: str) -> bool:
    """Shape pre-check only; the backend remains the authority."""
    candidate = value.strip()
    if not _EMAIL_RE.fullmatch(candidate):
        return False
    return candidate.rsplit(".", 1)[-1].lower() not in _SPECIAL_USE_TLDS


def is_valid_domain(value: str) -> bool:
    """Public DNS name with at least one dot (no scheme, port, or path)."""
    return bool(_DOMAIN_RE.fullmatch(value.strip().lower()))


def is_valid_host(value: str) -> bool:
    """LAN hostname or IP address literal."""
    candidate = value.strip()
    try:
        ipaddress.ip_address(candidate)
        return True
    except ValueError:
        return bool(_HOSTNAME_RE.fullmatch(candidate.lower()))


def is_valid_password_shape(value: str) -> bool:
    """Mirror of the backend password policy (pre-check, see PasswordRules)."""
    rules = PASSWORD_RULES
    if not rules.min_length <= len(value) <= rules.max_length:
        return False
    if sum(1 for c in value if c.isupper()) < rules.min_uppercase:
        return False
    if sum(1 for c in value if c.isdigit()) < rules.min_digits:
        return False
    return sum(1 for c in value if c in rules.special_chars) >= rules.min_special


def load_answers_file(path: Path) -> Mapping[str, str]:
    """Read the non-interactive answers file once (never copied).

    Raises:
        InstallInputError: ``answers_file_missing`` or, on POSIX when the
            file is group/world accessible, ``answers_file_not_private``.
    """
    if not path.is_file():
        raise InstallInputError("answers_file_missing")
    if os.name == "posix":
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise InstallInputError("answers_file_not_private")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


def _parse(question: Question, raw: str) -> Any:
    """Convert a valid raw string to its typed value (None = invalid)."""
    value = raw.strip()
    if not value and question.default is not None:
        value = question.default
    if not value:
        return None
    if question.kind is QuestionKind.CHOICE:
        return value if value in question.choices else None
    if question.kind is QuestionKind.BOOL:
        lowered = value.lower()
        if lowered in _TRUE_VALUES:
            return True
        if lowered in _FALSE_VALUES:
            return False
        return None
    if question.validator is not None and not question.validator(value):
        return None
    return value


def _prompt(question: Question, language: str) -> str:
    text = msg(question.message_id, language, **dict(question.message_args))
    return f"[{question.key}] {text}: "


def _ask_interactive(question: Question, io: IOAdapter, language: str) -> Any:
    read = io.getpass_fn if question.secret else io.input_fn
    for _attempt in range(_MAX_INTERACTIVE_ATTEMPTS):
        parsed = _parse(question, read(_prompt(question, language)))
        if parsed is not None:
            return parsed
        io.print_fn(msg("error.invalid_value", language, key=question.key))
    raise InstallInputError(f"too_many_invalid_attempts:{question.key}")


def collect_secret_answers(
    questions: Sequence[Question],
    *,
    io: IOAdapter,
    non_interactive: bool,
    answers_path: Path | None,
) -> SecretAnswers:
    """Collect ONLY the secret answers (resume-before-bootstrap re-prompt).

    Public answers come from the recorded state; a resume must ask exactly
    the ephemeral secrets and nothing else.
    """
    file_values: Mapping[str, str] | None = None
    if non_interactive:
        if answers_path is None:
            raise InstallInputError("missing_answers_file")
        file_values = load_answers_file(answers_path)
    collected: dict[str, Any] = {}
    for question in questions:
        if not question.secret:
            continue
        if file_values is not None:
            raw = file_values.get(question.key)
            if raw is None:
                raise InstallInputError(f"missing_answer:{question.key}")
            parsed = _parse(question, raw)
            if parsed is None:
                raise InstallInputError(f"invalid_answer:{question.key}")
        else:
            parsed = _ask_interactive(question, io, "en")
        collected[question.key] = parsed
    return SecretAnswers(
        admin_password=str(collected["admin_password"]),
        provider_keys={
            key.removeprefix("provider_key_"): str(value)
            for key, value in collected.items()
            if key.startswith("provider_key_")
        },
    )


def collect_answers(
    questions: Sequence[Question],
    *,
    io: IOAdapter,
    non_interactive: bool,
    answers_path: Path | None,
    mode: InstallMode,
    manifest_path: Path | None,
) -> tuple[PublicAnswers, SecretAnswers]:
    """Collect every applicable answer and split public from secret.

    Args:
        questions: The declarative questionnaire (``build_questions()``).
        io: Injected terminal I/O.
        non_interactive: Read everything from ``answers_path``; never prompt.
        answers_path: Private answers file (required when non-interactive).
        mode: Resolved install mode (CLI concern, not a question).
        manifest_path: Resolved manifest path for prebuilt mode.

    Returns:
        ``(PublicAnswers, SecretAnswers)``.

    Raises:
        InstallInputError: Stable value-free codes (``missing_answers_file``,
            ``missing_answer:<key>``, ``invalid_answer:<key>``, ...).
    """
    file_values: Mapping[str, str] | None = None
    if non_interactive:
        if answers_path is None:
            raise InstallInputError("missing_answers_file")
        file_values = load_answers_file(answers_path)

    collected: dict[str, Any] = {}
    for question in questions:
        if not question.applies_to(collected):
            continue
        if file_values is not None:
            raw = file_values.get(question.key)
            if raw is None and question.default is not None:
                raw = question.default
            if raw is None:
                raise InstallInputError(f"missing_answer:{question.key}")
            parsed = _parse(question, raw)
            if parsed is None:
                raise InstallInputError(f"invalid_answer:{question.key}")
        else:
            language = str(collected.get("wizard_language", "en"))
            parsed = _ask_interactive(question, io, language)
        if question.key == "exposure":
            parsed = Exposure(str(parsed))
        collected[question.key] = parsed

    provider_keys = {
        key.removeprefix("provider_key_"): str(value)
        for key, value in collected.items()
        if key.startswith("provider_key_")
    }
    public = PublicAnswers(
        language=str(collected["wizard_language"]),
        mode=mode,
        exposure=collected["exposure"],
        admin_email=str(collected["admin_email"]),
        admin_name=str(collected["admin_name"]),
        default_language=str(collected["default_language"]),
        observability=bool(collected["observability"]),
        self_diagnostics=bool(collected.get("self_diagnostics", False)),
        skill_sandbox=bool(collected["skill_sandbox"]),
        server_host=(
            str(collected["server_host"]) if "server_host" in collected else None
        ),
        web_domain=(
            str(collected["web_domain"]) if "web_domain" in collected else None
        ),
        api_domain=(
            str(collected["api_domain"]) if "api_domain" in collected else None
        ),
        caddy_email=(
            str(collected["caddy_email"]) if "caddy_email" in collected else None
        ),
        manifest_path=manifest_path,
    )
    secrets = SecretAnswers(
        admin_password=str(collected["admin_password"]),
        provider_keys=provider_keys,
    )
    return public, secrets
