"""Answer collection contract (B11/B13).

- interactive: public answers via input_fn, secrets STRICTLY via getpass_fn;
- invalid email/domain/host/password values re-prompt (interactive) or fail
  with a stable code (non-interactive);
- non-interactive requires the answers file; a missing secret is a stable
  error, never a prompt;
- the POSIX answers file must be private (0o600 — group/world access is
  rejected);
- every exposure branch yields a coherent PublicAnswers.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from scripts.install.answers import (
    InstallInputError,
    collect_answers,
    is_valid_email,
    load_answers_file,
)
from scripts.install.model import Exposure, InstallMode, IOAdapter
from scripts.install.questions import build_questions

ADMIN_PASSWORD = "Xx12!!abcdA9$Z"
BASE_PUBLIC = {
    "wizard_language": "en",
    "exposure": "lan",
    "server_host": "192.168.1.50",
    "admin_email": "admin@ops.tld",
    "admin_name": "Ops",
    "default_language": "fr",
    "observability": "no",
    "self_diagnostics": "no",
    "skill_sandbox": "no",
}
SECRETS = {
    "admin_password": ADMIN_PASSWORD,
    "provider_key_deepseek": "dk-secret",
    "provider_key_openai": "sk-secret",
}


class _ScriptedIO:
    """IOAdapter backed by per-key scripted answers; records which fn served."""

    def __init__(self, public: dict[str, str], secrets: dict[str, str]) -> None:
        self._public = dict(public)
        self._secrets = dict(secrets)
        self.public_served: list[str] = []
        self.secret_served: list[str] = []
        self.printed: list[str] = []
        self._retries: dict[str, list[str]] = {}

    def with_retry(self, key: str, bad_then_good: list[str]) -> "_ScriptedIO":
        self._retries[key] = list(bad_then_good)
        return self

    @staticmethod
    def _key_of(prompt: str) -> str:
        # Prompts carry the canonical answer key as a stable "[key] " prefix
        # (it doubles as the --answers file key for operators).
        assert prompt.startswith("["), f"prompt lacks its key prefix: {prompt!r}"
        return prompt[1:].split("]", 1)[0]

    def adapter(self) -> IOAdapter:
        def _input(prompt: str) -> str:
            key = self._key_of(prompt)
            self.public_served.append(key)
            if key in self._retries and self._retries[key]:
                return self._retries[key].pop(0)
            return self._public[key]

        def _getpass(prompt: str) -> str:
            key = self._key_of(prompt)
            self.secret_served.append(key)
            if key in self._retries and self._retries[key]:
                return self._retries[key].pop(0)
            return self._secrets[key]

        return IOAdapter(
            input_fn=_input, getpass_fn=_getpass, print_fn=self.printed.append
        )


def _collect(io: _ScriptedIO, **kwargs: object):
    return collect_answers(
        build_questions(),
        io=io.adapter(),
        non_interactive=bool(kwargs.pop("non_interactive", False)),
        answers_path=kwargs.pop("answers_path", None),  # type: ignore[arg-type]
        mode=InstallMode.LOCAL,
        manifest_path=None,
    )


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        ("admin@ops.tld", True),
        ("admin@qualification.lia", True),
        # Special-use TLDs (RFC 2606/6761): the backend's EmailStr refuses
        # them at LOGIN, so an admin bootstrapped with one can never sign
        # in — the wizard must reject the address at question time
        # (v1.30.1 qualification: admin@smoke.invalid, 422 on every login).
        ("admin@smoke.invalid", False),
        ("admin@demo.example", False),
        ("admin@ci.test", False),
        ("admin@box.localhost", False),
        ("not-an-email", False),
    ],
)
def test_email_validator_rejects_special_use_tlds(value: str, valid: bool) -> None:
    assert is_valid_email(value) is valid


def test_interactive_lan_flow_routes_secrets_through_getpass_only() -> None:
    io = _ScriptedIO(BASE_PUBLIC, SECRETS)
    public, secrets = _collect(io)
    assert public.exposure is Exposure.LAN
    assert public.server_host == "192.168.1.50"
    assert public.web_domain is None and public.api_domain is None
    assert secrets.admin_password == ADMIN_PASSWORD
    assert set(secrets.provider_keys) == {"deepseek", "openai"}
    assert set(io.secret_served) == {
        "admin_password",
        "provider_key_deepseek",
        "provider_key_openai",
    }
    assert not set(io.secret_served) & set(io.public_served)


@pytest.mark.parametrize(
    ("exposure", "extra"),
    [
        ("proxy", {"web_domain": "lia.example.org", "api_domain": "api.example.org"}),
        (
            "caddy",
            {
                "web_domain": "lia.example.org",
                "api_domain": "api.example.org",
                "caddy_email": "acme@example.org",
            },
        ),
    ],
)
def test_domain_exposures_collect_domains_not_host(
    exposure: str, extra: dict[str, str]
) -> None:
    public_answers = {**BASE_PUBLIC, "exposure": exposure, **extra}
    public_answers.pop("server_host")
    io = _ScriptedIO(public_answers, SECRETS)
    public, _secrets = _collect(io)
    assert public.exposure.value == exposure
    assert public.server_host is None
    assert public.web_domain == "lia.example.org"
    if exposure == "caddy":
        assert public.caddy_email == "acme@example.org"
    else:
        assert public.caddy_email is None


@pytest.mark.parametrize(
    ("key", "bad", "good"),
    [
        ("admin_email", "not-an-email", "admin@ops.tld"),
        ("server_host", "bad host!", "192.168.1.50"),
        ("admin_password", "weak", ADMIN_PASSWORD),
    ],
)
def test_interactive_invalid_values_reprompt(key: str, bad: str, good: str) -> None:
    io = _ScriptedIO(BASE_PUBLIC, SECRETS).with_retry(key, [bad, good])
    public, secrets = _collect(io)
    assert public.admin_email == "admin@ops.tld"
    assert secrets.admin_password == ADMIN_PASSWORD
    assert any("invalid" in line.lower() for line in io.printed)


def test_password_policy_mirrors_the_backend_shape() -> None:
    # 10+ chars, 2 uppers, 2 digits, 2 specials — backend stays the authority.
    io = _ScriptedIO(BASE_PUBLIC, SECRETS).with_retry(
        "admin_password", ["Alllowercase11!!x", "xx12!!abcdzz", ADMIN_PASSWORD]
    )
    _public, secrets = _collect(io)
    assert secrets.admin_password == ADMIN_PASSWORD


def _write_answers(path: Path, values: dict[str, str]) -> Path:
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    if os.name == "posix":
        path.chmod(0o600)
    return path


def test_non_interactive_reads_the_answers_file_and_never_prompts(
    tmp_path: Path,
) -> None:
    answers = _write_answers(tmp_path / "answers.env", {**BASE_PUBLIC, **SECRETS})
    io = _ScriptedIO({}, {})
    public, secrets = _collect(io, non_interactive=True, answers_path=answers)
    assert public.admin_email == "admin@ops.tld"
    assert secrets.provider_keys["openai"] == "sk-secret"
    assert io.public_served == [] and io.secret_served == []


def test_non_interactive_missing_secret_is_a_stable_error(tmp_path: Path) -> None:
    incomplete = {**BASE_PUBLIC, **SECRETS}
    incomplete.pop("provider_key_deepseek")
    answers = _write_answers(tmp_path / "answers.env", incomplete)
    with pytest.raises(InstallInputError) as excinfo:
        _collect(_ScriptedIO({}, {}), non_interactive=True, answers_path=answers)
    assert str(excinfo.value) == "missing_answer:provider_key_deepseek"
    assert "dk-secret" not in str(excinfo.value)


def test_non_interactive_requires_an_answers_path() -> None:
    with pytest.raises(InstallInputError) as excinfo:
        _collect(_ScriptedIO({}, {}), non_interactive=True, answers_path=None)
    assert str(excinfo.value) == "missing_answers_file"


def test_non_interactive_invalid_value_fails_instead_of_reprompting(
    tmp_path: Path,
) -> None:
    answers = _write_answers(
        tmp_path / "answers.env", {**BASE_PUBLIC, **SECRETS, "admin_email": "nope"}
    )
    with pytest.raises(InstallInputError) as excinfo:
        _collect(_ScriptedIO({}, {}), non_interactive=True, answers_path=answers)
    assert str(excinfo.value) == "invalid_answer:admin_email"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
def test_answers_file_must_be_private_on_posix(tmp_path: Path) -> None:
    answers = _write_answers(tmp_path / "answers.env", {**BASE_PUBLIC, **SECRETS})
    answers.chmod(0o644)
    with pytest.raises(InstallInputError) as excinfo:
        load_answers_file(answers)
    assert str(excinfo.value) == "answers_file_not_private"


def test_load_answers_file_missing_path_is_stable(tmp_path: Path) -> None:
    with pytest.raises(InstallInputError) as excinfo:
        load_answers_file(tmp_path / "absent.env")
    assert str(excinfo.value) == "answers_file_missing"
