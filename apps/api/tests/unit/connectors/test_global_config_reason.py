"""Disabling a connector type states its reason, in the administrator's language (ADR-323).

A field validator never runs on an omitted field, so ``{"is_enabled": false}``
passed with no reason at all, and every account holding the connector was told
it had been switched off without being told why.
"""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.i18n import _, language_scope
from src.domains.connectors.models import CONNECTOR_DISPLAY_NAMES
from src.domains.connectors.schemas import ConnectorGlobalConfigUpdate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("reason", [None, "", "   "])
def test_disabling_without_a_reason_is_refused(reason: str | None) -> None:
    with language_scope("en"), pytest.raises(ValidationError, match="requires a reason"):
        ConnectorGlobalConfigUpdate(is_enabled=False, disabled_reason=reason)


def test_an_omitted_reason_is_refused_too() -> None:
    with language_scope("en"), pytest.raises(ValidationError, match="requires a reason"):
        ConnectorGlobalConfigUpdate.model_validate({"is_enabled": False})


def test_the_refusal_speaks_the_declared_language() -> None:
    """The acting administrator reads it — the declared language, never the default."""
    msgid = "Disabling a connector requires a reason."
    declared = next(code for code in ("de", "it") if code != settings.default_language)
    with language_scope(declared), pytest.raises(ValidationError) as refused:
        ConnectorGlobalConfigUpdate.model_validate({"is_enabled": False})

    told = _(msgid, declared)
    assert told != _(msgid, settings.default_language)
    assert told in str(refused.value)


def test_enabling_needs_no_reason() -> None:
    assert ConnectorGlobalConfigUpdate(is_enabled=True).disabled_reason is None


def test_every_connector_is_named_alike_on_both_stacks() -> None:
    """The e-mail telling a person their connector was switched off names it the
    way the admin screen does: the backend said « Telephony », an English common
    noun in a localized sentence, where the screen said « ElevenLabs Telephony »."""
    from tests._repo_paths import repo_root_or_skip

    source = (repo_root_or_skip() / "apps/web/src/constants/connectors.ts").read_text(
        encoding="utf-8"
    )
    block = source.split("export const CONNECTOR_LABELS", 1)[1].split("};", 1)[0]
    web = dict(re.findall(r"^\s*(\w+): '([^']+)',", block, flags=re.MULTILINE))
    backend = {kind.value: label for kind, label in CONNECTOR_DISPLAY_NAMES.items()}

    shared = sorted(set(web) & set(backend))
    assert len(shared) > 20, shared  # the parse found the table
    assert {key: backend[key] for key in shared} == {key: web[key] for key in shared}


def test_a_stated_reason_is_kept_as_written() -> None:
    update = ConnectorGlobalConfigUpdate(is_enabled=False, disabled_reason="Maintenance")

    assert update.disabled_reason == "Maintenance"
