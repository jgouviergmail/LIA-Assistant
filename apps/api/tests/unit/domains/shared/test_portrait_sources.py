"""The seam the portrait reads its four sources through (2026-09-16, part B).

``journals`` cannot import ``memories``, ``interests``, ``habits`` or
``relations``: two of them already import ``journals`` (the portrait block),
so the reverse edge would close a runtime cycle the coupling ratchet refuses.
The seam inverts the dependency the way ``consultation_sink`` and
``peer_release_sink`` do: each source INSTALLS its reader, ``journals`` reads
the registry, and the boot refuses a registry that is not complete.

What this pins: the closed vocabulary of keys, the install contract (a wrong
key refused, a genuine conflict refused, an idempotent re-import allowed), the
completeness assert, and the shape a reader answers with.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.domains.shared import portrait_sources as seam
from src.domains.shared.portrait_sources import (
    PORTRAIT_SOURCE_KEYS,
    FreshnessProbe,
    PortraitSourceSection,
    SourceBudget,
    assert_portrait_sources_complete,
    install_portrait_source,
    installed_portrait_sources,
)

pytestmark = pytest.mark.unit


async def _reader(*, user_id: UUID, language: str, budget: SourceBudget) -> PortraitSourceSection:
    return PortraitSourceSection(key="memories", status="empty", text="", used=0, total=0)


async def _other(*, user_id: UUID, language: str, budget: SourceBudget) -> PortraitSourceSection:
    return PortraitSourceSection(key="memories", status="empty", text="", used=0, total=0)


PROBE = FreshnessProbe(table="memories", user_column="user_id", stamp_column="updated_at")


@pytest.fixture(autouse=True)
def _clean_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seam, "_REGISTRY", {})


def test_the_vocabulary_is_the_four_sources_in_the_prompts_order() -> None:
    assert PORTRAIT_SOURCE_KEYS == ("memories", "interests", "habits", "relation_debriefs")


def test_a_source_installs_once_and_an_idempotent_reimport_is_allowed() -> None:
    install_portrait_source("memories", _reader, PROBE)
    install_portrait_source("memories", _reader, PROBE)
    assert installed_portrait_sources()["memories"] == (_reader, PROBE)


def test_a_second_reader_for_one_key_is_a_conflict() -> None:
    install_portrait_source("memories", _reader, PROBE)
    with pytest.raises(RuntimeError, match="memories"):
        install_portrait_source("memories", _other, PROBE)


def test_an_unknown_key_is_refused() -> None:
    with pytest.raises(RuntimeError, match="bookmarks"):
        install_portrait_source("bookmarks", _reader, PROBE)


def test_the_completeness_assert_names_what_is_missing() -> None:
    install_portrait_source("memories", _reader, PROBE)
    with pytest.raises(RuntimeError) as failure:
        assert_portrait_sources_complete()
    message = str(failure.value)
    assert "interests" in message and "habits" in message and "relation_debriefs" in message
    assert "memories" not in message.split("missing")[-1]


def test_the_registry_is_read_in_the_declared_order() -> None:
    for key in reversed(PORTRAIT_SOURCE_KEYS):
        install_portrait_source(key, _reader, PROBE)
    assert_portrait_sources_complete()
    assert tuple(installed_portrait_sources()) == PORTRAIT_SOURCE_KEYS


async def test_a_section_carries_its_status_its_count_and_its_exact_total() -> None:
    section = await _reader(user_id=uuid4(), language="fr", budget=SourceBudget(3, 100))
    assert section.status == "empty" and section.text == ""
    assert (section.used, section.total) == (0, 0)
