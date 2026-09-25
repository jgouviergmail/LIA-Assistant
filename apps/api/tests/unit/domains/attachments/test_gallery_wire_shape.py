"""The gallery's wire shape is spelled once on each side, and the two agree.

``apps/web/src/types/generated-assets.ts`` says the backend guard reading it
would fail on a drift — and until ADR-316 no such guard existed, so the promise
was a comment. A field added to ``GeneratedAssetSummary`` and not to the web
type is a card that silently ignores it; one added on the web side only is a
field that is always ``undefined``. This reads the interface and compares.
"""

from __future__ import annotations

import re

import pytest

from src.domains.attachments.schemas import GeneratedAssetSummary
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

_TYPES = repo_root_or_skip() / "apps" / "web" / "src" / "types" / "generated-assets.ts"
_INTERFACE = re.compile(r"export interface GeneratedAsset \{(?P<body>.*?)\n\}", re.DOTALL)
_FIELD = re.compile(r"^\s{2}(?P<name>[a-z_]+)\??:", re.MULTILINE)


def _web_fields() -> set[str]:
    match = _INTERFACE.search(_TYPES.read_text(encoding="utf-8"))
    assert match, "GeneratedAsset interface not found — the parser would pass vacuously"
    return set(_FIELD.findall(match.group("body")))


def test_the_parser_reads_the_interface() -> None:
    assert {"id", "title", "expires_at"} <= _web_fields()


def test_the_web_type_names_every_field_the_api_sends() -> None:
    assert _web_fields() == set(GeneratedAssetSummary.model_fields)
