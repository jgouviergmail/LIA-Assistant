"""Core installer data model (ADR-215, B01/B10/B13).

Stdlib-only (Python >= 3.10): these types are shared by the questionnaire,
artifact generation, state, and deploy orchestration. Enums use
``class Name(str, Enum)`` — never ``enum.StrEnum`` — to keep 3.10 support.

The provider tuple below is the WIZARD's copy of the derived post-seed
current-core provider set (B10-bis). The wizard cannot import backend code,
so the backend test ``test_installer_wizard_backend_alignment.py`` pins this
tuple (and the password-rule mirror) to the live backend derivation — drift
turns CI red.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

#: Languages the WIZARD itself speaks (terminal prompts).
WIZARD_LANGUAGES: tuple[str, ...] = ("en", "fr")

#: Languages the APPLICATION supports (User.language backend-canonical codes).
APP_LANGUAGES: tuple[str, ...] = ("fr", "en", "es", "de", "it", "zh-CN")

#: Wizard copy of ``required_current_core_provider_ids()`` — see module doc.
REQUIRED_PROVIDER_IDS: tuple[str, ...] = ("deepseek", "openai")


class InstallMode(str, Enum):
    """How application images are obtained."""

    LOCAL = "local"
    PREBUILT = "prebuilt"


class Exposure(str, Enum):
    """How the installation is reached."""

    LAN = "lan"
    PROXY = "proxy"
    CADDY = "caddy"


class VerifyOutcome(str, Enum):
    """Advisory provider-key verification result (never blocks installs)."""

    VALID = "valid"
    INVALID = "invalid"
    UNVERIFIED = "unverified"


class QuestionKind(str, Enum):
    """Input widget class for one question."""

    CHOICE = "choice"
    TEXT = "text"
    BOOL = "bool"
    SECRET = "secret"


@dataclass(frozen=True)
class PasswordRules:
    """Wizard-side mirror of the backend password policy (pre-check only).

    The backend ``validate_password_strict`` remains the single authority at
    bootstrap; this mirror exists so an operator learns about a hopeless
    password at the prompt instead of after the stack is up.
    """

    min_length: int = 10
    max_length: int = 128
    min_uppercase: int = 2
    min_digits: int = 2
    min_special: int = 2
    special_chars: str = "!@#$%^&*()_+-=[]{}|;':\",./<>?`~"


PASSWORD_RULES = PasswordRules()


@dataclass(frozen=True)
class Question:
    """One declarative questionnaire entry.

    Attributes:
        key: Canonical answer key (also the ``--answers`` file key and the
            stable ``[key]`` prompt prefix).
        kind: Input widget class.
        message_id: i18n prompt id (must exist in every wizard language).
        secret: True routes the answer through ``getpass_fn`` and keeps it
            out of ``PublicAnswers``/state.
        choices: Allowed values for CHOICE questions.
        default: Value used when the operator answers with an empty line.
        validator: Optional shape pre-check for the raw string value.
        applies: Optional predicate on already-collected answers; an
            inapplicable question is silently skipped.
        message_args: Static interpolation pairs for the prompt message.
    """

    key: str
    kind: QuestionKind
    message_id: str
    secret: bool = False
    choices: tuple[str, ...] = ()
    default: str | None = None
    validator: Callable[[str], bool] | None = None
    applies: Callable[[Mapping[str, Any]], bool] | None = None
    message_args: tuple[tuple[str, str], ...] = ()

    def applies_to(self, answers: Mapping[str, Any]) -> bool:
        """Whether this question is asked given the answers so far."""
        return self.applies is None or self.applies(answers)


@dataclass(frozen=True)
class PublicAnswers:
    """Every non-secret installation choice (persisted in installer state)."""

    language: str
    mode: InstallMode
    exposure: Exposure
    admin_email: str
    admin_name: str
    default_language: str
    observability: bool
    skill_sandbox: bool
    server_host: str | None
    web_domain: str | None
    api_domain: str | None
    caddy_email: str | None
    manifest_path: Path | None
    # Self-diagnostics opt-in (ADR-247). Defaulted so older persisted states
    # deserialize unchanged; the wizard always asks explicitly.
    self_diagnostics: bool = False


@dataclass(frozen=True)
class SecretAnswers:
    """Ephemeral secrets: stdin-only downstream, never persisted or logged."""

    admin_password: str
    provider_keys: Mapping[str, str]


@dataclass
class IOAdapter:
    """Injected terminal I/O so every flow is testable without a TTY."""

    input_fn: Callable[[str], str]
    getpass_fn: Callable[[str], str]
    print_fn: Callable[[str], None]


class UrlOpener(Protocol):
    """Injected ``urllib``-style opener (hermetic tests, fake providers)."""

    def __call__(self, request: Any, *, timeout: float) -> Any: ...


class Clock(Protocol):
    """Injected time source for readiness waits."""

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


@dataclass(frozen=True)
class HostPathRequirement:
    """One host path the installer must prepare before Compose runs."""

    path: Path
    kind: str  # "dir" | "file"
    mode: int | None = None


@dataclass(frozen=True)
class ComposeInvocation:
    """The exact Compose file/profile selection for one installation."""

    files: tuple[Path, ...]
    profiles: tuple[str, ...] = ()
    mode: InstallMode = InstallMode.LOCAL
    project_name: str | None = None
    env: Mapping[str, str] = field(default_factory=dict)

    def prefix(self) -> list[str]:
        """``docker compose`` argv prefix; every ``-f`` is its own element."""
        argv = ["docker", "compose"]
        if self.project_name:
            argv += ["-p", self.project_name]
        for file in self.files:
            argv += ["-f", str(file)]
        for profile in self.profiles:
            argv += ["--profile", profile]
        return argv
