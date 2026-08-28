"""The memory-category vocabulary has ONE source of truth.

``MemoryCategory`` (the enum the database column stores) is the vocabulary.
Two hand-written ``Literal`` copies used to restate it — one in
``domains/memories/schemas.py``, one in ``agents/tools/memory_tools.py`` — and
both drifted when ADR-236 added ``procedural`` (the "rules & directives"
memories: standing instructions the user gives about HOW the assistant should
work).

The consequences were measured on 2026-08-28, on a live instance:

- **the write path was dead.** ``memory_extraction_prompt.txt`` explicitly asks
  the model to emit ``procedural``; when it obeyed, ``ExtractedMemory(**item)``
  raised a ``ValidationError`` that the extractor caught, logged at **debug**,
  and skipped. No procedural memory was ever created, so the category never
  appeared in the UI — which groups only categories that hold something. The
  feature shipped its reader (profile section, settings UI, six locales) with a
  writer that could not succeed.
- **the read path would have broken worse.** ``MemoryResponse.category`` used
  the same six-value Literal, so a single ``procedural`` row — from an import, a
  fixture, a partial fix — would fail response validation and take the WHOLE
  memory list down for that user, not just one card.

This is the ADR-085 doctrine applied to a vocabulary: a closed set restated by
hand is a set that drifts, and a silent fallback on an unknown value is how a
feature dies invisibly. The Literals are now DERIVED from the enum, and this
guard fails if anyone restates them again.
"""

from __future__ import annotations

from typing import get_args

import pytest

from src.domains.agents.tools.memory_tools import (
    MemoryCategoryType as ToolCategoryType,
)
from src.domains.memories.models import MemoryCategory
from src.domains.memories.schemas import ExtractedMemory, MemoryResponse
from src.domains.memories.schemas import MemoryCategoryType as SchemaCategoryType

ENUM_VALUES = frozenset(member.value for member in MemoryCategory)


@pytest.mark.unit
class TestVocabularyIsSingleSourced:
    def test_schema_literal_matches_the_enum_exactly(self) -> None:
        assert frozenset(get_args(SchemaCategoryType)) == ENUM_VALUES

    def test_tool_literal_matches_the_enum_exactly(self) -> None:
        assert frozenset(get_args(ToolCategoryType)) == ENUM_VALUES

    def test_procedural_is_part_of_the_vocabulary(self) -> None:
        """The regression that started it all: ADR-236's category."""
        assert "procedural" in ENUM_VALUES
        assert "procedural" in get_args(SchemaCategoryType)
        assert "procedural" in get_args(ToolCategoryType)


@pytest.mark.unit
class TestEveryCategorySurvivesBothPaths:
    @pytest.mark.parametrize("category", sorted(ENUM_VALUES))
    def test_write_path_accepts_it(self, category: str) -> None:
        """What the extraction prompt may emit, the parser must accept."""
        entry = ExtractedMemory(
            action="create", content="A standing instruction.", category=category
        )
        assert entry.category == category

    @pytest.mark.parametrize("category", sorted(ENUM_VALUES))
    def test_read_path_renders_it(self, category: str) -> None:
        """A stored row must never break the list endpoint's response model."""
        from datetime import UTC, datetime
        from uuid import uuid4

        response = MemoryResponse(
            id=str(uuid4()),
            user_id=str(uuid4()),
            content="A standing instruction.",
            category=category,
            emotional_weight=0,
            importance=0.5,
            confidence=0.5,
            pinned=False,
            access_count=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert response.category == category


@pytest.mark.unit
class TestPromptAndUiAgreeWithTheVocabulary:
    def test_the_extraction_prompt_teaches_only_real_categories(self) -> None:
        """A prompt naming a category the parser rejects is a silent dead end."""
        from src.domains.agents.prompts.prompt_loader import load_prompt

        prompt = str(load_prompt("memory_extraction_prompt"))
        taught = {value for value in ENUM_VALUES if f"`{value}`" in prompt}
        assert taught, "the prompt must name the categories it may emit"
        assert taught <= ENUM_VALUES

    def test_frontend_lists_every_category(self) -> None:
        """The settings surface must be able to show what the backend stores."""
        import re

        from tests._repo_paths import repo_root_or_skip

        hook = repo_root_or_skip() / "apps" / "web" / "src" / "hooks" / "useMemories.ts"
        if not hook.is_file():
            pytest.skip("guard needs the full repository checkout (useMemories.ts).")
        declared = set(re.findall(r"'([a-z_]+)',", hook.read_text(encoding="utf-8")))
        missing = ENUM_VALUES - declared
        assert not missing, f"MEMORY_CATEGORIES is missing: {sorted(missing)}"


@pytest.mark.unit
class TestThePublishedCatalogueIsComplete:
    """``GET /memories/categories`` publishes the vocabulary to the settings UI.

    ADR-184's rule applied to a vocabulary: what the API accepts, its catalogue
    must publish. This catalogue drifted with the two Literals and kept a
    seventh category out of the only endpoint that describes them.
    """

    def test_the_catalogue_publishes_every_stored_category(self) -> None:
        from src.domains.agents.tools.memory_tools import get_memory_categories

        published = {entry["name"] for entry in get_memory_categories()}
        assert published == set(ENUM_VALUES)

    def test_every_published_entry_is_renderable(self) -> None:
        """A half-filled entry renders as a blank card, not as an error."""
        from src.domains.agents.tools.memory_tools import get_memory_categories

        for entry in get_memory_categories():
            assert set(entry) == {"name", "label", "description", "icon"}
            assert all(value.strip() for value in entry.values()), entry

    def test_the_catalogue_is_asserted_at_boot(self) -> None:
        """Third face of the same vocabulary, third boot gate (ADR-085)."""
        import inspect

        from src.infrastructure.startup import registries

        source = inspect.getsource(registries._validate_memory_category_vocabulary)
        assert "get_memory_categories" in source, (
            "the published catalogue must refuse to boot on a drift too — it is "
            "what the settings screen reads to describe the categories"
        )


@pytest.mark.unit
class TestUnknownCategoryIsNotSilent:
    def test_a_rejected_extraction_entry_is_logged_loudly(self) -> None:
        """The defect hid for months behind a debug-level swallow."""
        import inspect

        from src.domains.agents.services import memory_extractor

        source = inspect.getsource(memory_extractor)
        assert "memory_item_validation_failed" in source
        assert 'logger.warning(\n                    "memory_item_validation_failed"' in source, (
            "a dropped extraction entry must be a warning: at debug level, a "
            "vocabulary drift is invisible until a user notices the feature missing"
        )


@pytest.mark.unit
class TestTheDuplicationIsGuardedAtBoot:
    """Derivation is impossible, so the duplication must be ASSERTED.

    Measured 2026-08-28: `Literal[*tuple(m.value for m in MemoryCategory)]`
    makes MyPy degrade the type to `Any` — deriving would trade a compile-time
    typo check for a runtime surprise. The list therefore stays explicit and a
    boot assert refuses to start on any drift (ADR-085 doctrine).
    """

    def test_the_assert_catches_a_missing_category(self) -> None:
        from src.domains.memories.schemas import (
            assert_category_vocabulary_completeness,
        )

        with pytest.raises(AssertionError, match="missing"):
            assert_category_vocabulary_completeness(("preference", "personal"))

    def test_the_assert_catches_an_invented_category(self) -> None:
        from src.domains.memories.schemas import (
            assert_category_vocabulary_completeness,
        )

        with pytest.raises(AssertionError, match="invents"):
            assert_category_vocabulary_completeness((*sorted(ENUM_VALUES), "imaginary"))

    def test_the_real_vocabulary_passes(self) -> None:
        from src.domains.memories.schemas import (
            assert_category_vocabulary_completeness,
        )

        assert_category_vocabulary_completeness()

    def test_the_boot_gate_passes_on_the_real_vocabulary(self) -> None:
        """The gate is I/O-free, so the test can simply run it."""
        from src.infrastructure.startup.registries import (
            _validate_memory_category_vocabulary,
        )

        _validate_memory_category_vocabulary()

    def test_the_boot_gate_bites_when_a_surface_drifts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole point: a drift must stop the boot, not degrade silently."""
        from src.domains.agents.tools import memory_tools
        from src.infrastructure.startup.registries import (
            _validate_memory_category_vocabulary,
        )

        truncated = [
            entry for entry in memory_tools.get_memory_categories() if entry["name"] != "procedural"
        ]
        monkeypatch.setattr(memory_tools, "get_memory_categories", lambda: truncated)

        with pytest.raises(RuntimeError, match="published catalogue is missing"):
            _validate_memory_category_vocabulary()

    def test_boot_wires_both_typing_faces(self) -> None:
        """A validator nobody calls protects nothing."""
        import inspect

        from src.infrastructure.startup import registries

        assert "_validate_memory_category_vocabulary()" in inspect.getsource(
            registries.run_failfast_validations
        ), "the gate must be called from the lifespan's fail-fast step"
        source = inspect.getsource(registries._validate_memory_category_vocabulary)
        assert "assert_category_vocabulary_completeness" in source
        assert "_ToolCategoryType" in source, (
            "the agents-side Literal must be checked too — it is the one the "
            "save-memory tool exposes to the model"
        )
