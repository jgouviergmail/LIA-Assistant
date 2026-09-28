"""The gallery's wire shapes are spelled once on each side, and the two agree.

``apps/web/src/types/generated-assets.ts`` says the backend guard reading it
would fail on a drift — and until ADR-316 no such guard existed, so the promise
was a comment. A field added to a response model and not to the web type is a
card that silently ignores it; one added on the web side only is a field that
is always ``undefined``. This reads each interface and compares it with the
model the API serializes — every response of the gallery, not only its cards
(ADR-319 added the keeping usage and the keep route's answer).
"""

from __future__ import annotations

import re

import pytest
from pydantic import BaseModel

from src.domains.attachments.schemas import (
    GeneratedAssetKeepUsage,
    GeneratedAssetListResponse,
    GeneratedAssetsDeleteResponse,
    GeneratedAssetsKeepResponse,
    GeneratedAssetSummary,
)
from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

_TYPES = repo_root_or_skip() / "apps" / "web" / "src" / "types" / "generated-assets.ts"
_FIELD = re.compile(r"^\s{2}(?P<name>[a-z_]+)\??:", re.MULTILINE)

# Web interface name → the model the API serializes for it.
_PAIRS: dict[str, type[BaseModel]] = {
    "GeneratedAsset": GeneratedAssetSummary,
    "GeneratedAssetKeepUsage": GeneratedAssetKeepUsage,
    "GeneratedAssetList": GeneratedAssetListResponse,
    "GeneratedAssetsDeleteResult": GeneratedAssetsDeleteResponse,
    "GeneratedAssetsKeepResult": GeneratedAssetsKeepResponse,
}


def _web_fields(interface: str) -> set[str]:
    pattern = re.compile(rf"export interface {interface} \{{(?P<body>.*?)\n\}}", re.DOTALL)
    match = pattern.search(_TYPES.read_text(encoding="utf-8"))
    assert match, f"{interface} interface not found — the parser would pass vacuously"
    return set(_FIELD.findall(match.group("body")))


def test_the_parser_reads_the_interface() -> None:
    assert {"id", "title", "expires_at"} <= _web_fields("GeneratedAsset")


@pytest.mark.parametrize("interface", sorted(_PAIRS))
def test_the_web_type_names_every_field_the_api_sends(interface: str) -> None:
    assert _web_fields(interface) == set(_PAIRS[interface].model_fields)
