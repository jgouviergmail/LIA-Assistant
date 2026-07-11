"""Unit tests for the Draft Preview Renderer dispatch table (ADR-085 pattern).

Covers:

- Registry completeness: every ``DraftType`` has a registered renderer.
- ``assert_preview_renderer_completeness`` behavior (pass + fail message).
- Renderer invariants: every registered entry is callable.

The rendered OUTPUT is pinned separately, byte-identical, by the golden
characterization net in ``test_detailed_preview_characterization.py``.
"""

from __future__ import annotations

import pytest

from src.domains.agents.drafts.models import DraftType
from src.domains.agents.drafts.preview_renderer import (
    _PREVIEW_RENDERERS,
    assert_preview_renderer_completeness,
)


@pytest.mark.parametrize("draft_type", list(DraftType))
def test_every_draft_type_has_preview_renderer(draft_type: DraftType) -> None:
    """Every ``DraftType`` value has an entry in the renderer dispatch table."""
    assert (
        draft_type in _PREVIEW_RENDERERS
    ), f"DraftType.{draft_type.name} is missing from _PREVIEW_RENDERERS"


@pytest.mark.parametrize("draft_type", list(DraftType))
def test_registered_renderer_is_callable(draft_type: DraftType) -> None:
    """Every registered renderer is a callable."""
    assert callable(_PREVIEW_RENDERERS[draft_type])


def test_assert_preview_renderer_completeness_passes_with_full_registry() -> None:
    """The assertion runs without raising when every type is registered."""
    assert_preview_renderer_completeness()


def test_assert_preview_renderer_completeness_fails_when_type_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The assertion raises with a useful message when an entry is missing."""
    # Remove one entry under a monkeypatched copy so the registry itself is unchanged.
    incomplete = dict(_PREVIEW_RENDERERS)
    incomplete.pop(DraftType.REMINDER_DELETE)
    monkeypatch.setattr(
        "src.domains.agents.drafts.preview_renderer._PREVIEW_RENDERERS",
        incomplete,
    )

    with pytest.raises(AssertionError, match="reminder_delete"):
        assert_preview_renderer_completeness()
