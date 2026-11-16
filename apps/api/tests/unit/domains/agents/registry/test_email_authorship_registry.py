"""Every e-mail text the catalogue offers is settled by the authorship door, or left with a reason.

A tool with a ``body`` the door does not know would let the agent write in the person's
name with no writer and no voice — the defect of 2026-11-15 (ADR-383 amendment).
"""

from __future__ import annotations

import pytest

from src.domains.agents.emails.authorship import TEXTS_LEFT_AS_GIVEN, WRITING_TOOLS
from src.domains.agents.registry.catalogue import ToolManifest

pytestmark = pytest.mark.unit


def test_every_tool_carrying_a_text_is_declared(manifests: dict[str, ToolManifest]) -> None:
    with_text = {
        name
        for name, manifest in manifests.items()
        if any(parameter.name == "body" for parameter in manifest.parameters)
    }

    assert with_text == WRITING_TOOLS | set(TEXTS_LEFT_AS_GIVEN)


def test_a_text_is_settled_or_left_never_both() -> None:
    assert not WRITING_TOOLS & set(TEXTS_LEFT_AS_GIVEN)
    assert all(reason.strip() for reason in TEXTS_LEFT_AS_GIVEN.values())
