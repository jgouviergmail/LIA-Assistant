"""The boot claims the four portrait sources and refuses a mute seam (part B).

The installation is an import side effect of four modules; the boot imports
them EXPLICITLY (ADR-270) and then proves the registry is complete — a
declared source with no reader stops the boot with the completeness error
the other ADR-085 asserts raise.
"""

from __future__ import annotations

import pytest

from src.domains.shared import portrait_sources as seam
from src.domains.shared.portrait_sources import PORTRAIT_SOURCE_KEYS
from src.infrastructure.startup import registries
from src.infrastructure.startup.errors import StartupCompletenessError

pytestmark = pytest.mark.unit


def test_the_boot_installs_every_declared_source(monkeypatch: pytest.MonkeyPatch) -> None:
    # Import the four modules FIRST, so their import-time side effect has
    # already run when the registry is emptied: the step must install on its
    # own, not rely on an import that will not run again.
    import src.domains.habits.portrait_source  # noqa: F401
    import src.domains.interests.portrait_source  # noqa: F401
    import src.domains.memories.portrait_source  # noqa: F401
    import src.domains.relations.debrief.portrait_source  # noqa: F401

    monkeypatch.setattr(seam, "_REGISTRY", {})
    registries._install_portrait_sources()
    assert tuple(seam.installed_portrait_sources()) == PORTRAIT_SOURCE_KEYS


def test_a_missing_source_stops_the_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seam, "_REGISTRY", {})
    monkeypatch.setattr(seam, "PORTRAIT_SOURCE_KEYS", (*PORTRAIT_SOURCE_KEYS, "bookmarks"))
    with pytest.raises(StartupCompletenessError, match="bookmarks"):
        registries._install_portrait_sources()
