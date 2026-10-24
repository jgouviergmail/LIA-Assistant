"""Every value an env template states is the code's default, or says why not (audit AC-036).

The owner's rule (2026-10-22): the database overrides the environment, which overrides the
code's constants. A template sits at the environment's level, so a value it states replaces
the constant for whoever copies it — and eight features shipped disabled in the templates
while the code enabled them, with nothing to say whether that was meant. A template now
states the default, leaves the key out, or annotates the line with
``differs from default: <reason>``, inline or on the comment line just above it.

The templates carry the values production has proven (owner decision 2026-10-23), so most
annotations say so: their list is where the code's defaults lag behind production. A field
whose default is empty (a key, an address, an identifier to fill in) is a deployment value
and is not compared.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any

import pytest
from pydantic_core import PydanticUndefined

from src.core.config import Settings
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

REPO_ROOT = repo_root_or_skip()
TEMPLATES = (".env.example", ".env.prod.example", ".env.min.prod.example")
ANNOTATION = "differs from default:"
#: Placeholders a deployment replaces: the test session's own values stand in for them.
SECRETS_TO_FILL_IN = frozenset({"DATABASE_URL", "REDIS_URL", "SECRET_KEY", "FERNET_KEY"})
_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
_NO_DEFAULT = object()


def _default(name: str) -> Any:
    default = Settings.model_fields[name].get_default(call_default_factory=True)
    return _NO_DEFAULT if default is PydanticUndefined else default


def _empty(default: Any) -> bool:
    return (
        default is _NO_DEFAULT
        or default in ("", None)
        or (isinstance(default, list | tuple | set | frozenset | dict) and not default)
    )


def _split(raw: str) -> tuple[str, str]:
    value, _, comment = raw.partition(" #")
    return value.strip().strip('"').strip("'"), comment


def _as_items(value: str) -> list[str] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item) for item in parsed] if isinstance(parsed, list) else None


def _same(value: str, default: Any) -> bool:
    if isinstance(default, bool):
        return value.lower() == str(default).lower()
    if isinstance(default, int | float):
        try:
            return float(value) == float(default)
        except ValueError:
            return False
    if isinstance(default, Enum):
        return value == str(default.value)
    if isinstance(default, list | tuple | set | frozenset):
        return _as_items(value) == [str(getattr(item, "value", item)) for item in default]
    return value == str(default)


def _unannotated(name: str) -> list[str]:
    fields = {field_name.upper(): field_name for field_name in Settings.model_fields}
    lines = (REPO_ROOT / name).read_text(encoding="utf-8").splitlines()
    offenders = []
    for index, line in enumerate(lines):
        match = _LINE.match(line)
        if match is None or match.group(1) not in fields:
            continue
        value, comment = _split(match.group(2))
        default = _default(fields[match.group(1)])
        if _empty(default) or _same(value, default):
            continue
        above = lines[index - 1] if index > 0 else ""
        if ANNOTATION in comment or (above.startswith("#") and ANNOTATION in above):
            continue
        offenders.append(f"{name}:{index + 1}: {match.group(1)}={value!r} (default {default!r})")
    return offenders


_CLAIM = re.compile(r"\(default:?\s*([^;)]+)")


def _claimed(text: str) -> list[str]:
    """The readings of a claim: whole (a list, a format), before its first comma (« 10,
    hard limit: 50 »), before its first blank (« 604800 = 7 days »)."""
    whole = text.strip().strip("`'\"")
    return [whole, whole.split(",")[0].strip(), whole.split()[0] if whole.split() else whole]


#: A claim the comparison cannot read as the setting does: a size with its unit, a user
#: named rather than numbered. Kept as prose; nothing else may escape the check.
_PROSE_CLAIMS = {
    "MCP_APP_MAX_HTML_SIZE",
    "SKILLS_SCRIPT_UNPRIVILEGED_UID",
    "SKILLS_SCRIPT_UNPRIVILEGED_GID",
}


def _false_claims(name: str) -> list[str]:
    """Comments stating « (default: X) » where X is not the code's default."""
    fields = {field_name.upper(): field_name for field_name in Settings.model_fields}
    lines = (REPO_ROOT / name).read_text(encoding="utf-8").splitlines()
    wrong = []
    for index, line in enumerate(lines):
        match = _LINE.match(line)
        if match is None or match.group(1) not in fields or match.group(1) in _PROSE_CLAIMS:
            continue
        _, comment = _split(match.group(2))
        claim = _CLAIM.search(comment)
        if claim is None:
            continue
        default = _default(fields[match.group(1)])
        if default is _NO_DEFAULT or any(_same(text, default) for text in _claimed(claim.group(1))):
            continue
        wrong.append(
            f"{name}:{index + 1}: {match.group(1)} claims {claim.group(1)!r}, the code {default!r}"
        )
    return wrong


@pytest.mark.parametrize("name", TEMPLATES)
def test_a_default_a_comment_states_is_the_code_s(name: str) -> None:
    """« Never restate a value the code owns » — and one restated must at least be true:
    35 comments per template stated a default the code had moved away from."""
    wrong = _false_claims(name)

    assert (
        wrong == []
    ), f"{len(wrong)} comment(s) state a default the code does not have:\n" + "\n".join(wrong)


@pytest.mark.parametrize("name", TEMPLATES)
def test_every_value_a_template_states_is_the_default_or_says_why(name: str) -> None:
    offenders = _unannotated(name)

    assert offenders == [], (
        f"{len(offenders)} value(s) differ from the code's default without saying why — state "
        f"the default, leave the key out, or annotate « # {ANNOTATION} <reason> »:\n"
        + "\n".join(offenders)
    )


@pytest.mark.parametrize("name", TEMPLATES)
def test_each_template_is_a_configuration_the_settings_accept(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its secrets filled in, a copied template boots: the values it states are ones the
    settings' validators accept together (the templates took production's on 2026-10-23)."""
    # The environment outranks the file: what the test session sets would hide the
    # template's own values (its DEBUG=true met a production template's ENVIRONMENT).
    for line in (REPO_ROOT / name).read_text(encoding="utf-8").splitlines():
        match = _LINE.match(line)
        if match is not None and match.group(1) not in SECRETS_TO_FILL_IN:
            monkeypatch.delenv(match.group(1), raising=False)
    # A webhook secret is the deployment's own: the placeholder is refused on purpose.
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "f" * 64)

    Settings(_env_file=REPO_ROOT / name, _env_file_encoding="utf-8")


def test_the_comparison_reads_lists_booleans_and_enums_as_the_settings_do() -> None:
    assert _same('["admin","power_user"]', ["admin", "power_user"])
    assert _same("admin,power_user", ("admin", "power_user"))
    assert _same("TRUE", True) and not _same("false", True)
    assert _same("20.0", 20) and not _same("20", 21)
