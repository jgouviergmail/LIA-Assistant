"""The document preferences: one door to read a stored choice, one vocabulary on both sides.

A stored value is read through ``illustrations_of`` / ``animations_of``: a value
nobody can interpret (a former vocabulary, a hand edit) becomes the owner's
default instead of an error at the moment a document is generated. The settings
screen offers exactly the choices the API accepts (ADR-184's rule), held here
against the TypeScript list it renders.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.core.document_preferences import (
    DOCUMENT_ANIMATIONS_DEFAULT,
    DOCUMENT_ILLUSTRATIONS_DEFAULT,
    DocumentAnimations,
    DocumentIllustrations,
    DocumentPreferences,
    animations_of,
    document_preferences,
    illustrations_of,
)

pytestmark = pytest.mark.unit

_WEB_VOCABULARY = (
    Path(__file__).resolve().parents[4] / "web" / "src" / "lib" / "document-preferences.ts"
)


class TestTheOwnersDefaults:
    def test_a_document_is_illustrated_where_lia_judges_it_serves(self) -> None:
        assert DOCUMENT_ILLUSTRATIONS_DEFAULT is DocumentIllustrations.AUTO

    def test_only_a_deck_to_be_presented_is_animated(self) -> None:
        assert DOCUMENT_ANIMATIONS_DEFAULT is DocumentAnimations.PRESENTED

    def test_an_account_read_without_preferences_gets_both_and_no_images(self) -> None:
        assert DocumentPreferences() == DocumentPreferences(
            illustrations=DocumentIllustrations.AUTO,
            animations=DocumentAnimations.PRESENTED,
            images_allowed=False,
        )


class TestTheOneDoor:
    @pytest.mark.parametrize("choice", list(DocumentIllustrations))
    def test_every_illustration_choice_reads_as_itself(self, choice: DocumentIllustrations) -> None:
        assert illustrations_of(choice.value) is choice

    @pytest.mark.parametrize("choice", list(DocumentAnimations))
    def test_every_animation_choice_reads_as_itself(self, choice: DocumentAnimations) -> None:
        assert animations_of(choice.value) is choice

    @pytest.mark.parametrize("stored", [None, "", "sometimes", "AUTO", " auto"])
    def test_an_illustration_value_nobody_wrote_reads_as_the_default(
        self, stored: str | None
    ) -> None:
        assert illustrations_of(stored) is DOCUMENT_ILLUSTRATIONS_DEFAULT

    @pytest.mark.parametrize("stored", [None, "", "on_request", "PRESENTED", "read"])
    def test_an_animation_value_nobody_wrote_reads_as_the_default(self, stored: str | None) -> None:
        # « on_request » belongs to the OTHER vocabulary: the doors never cross.
        assert animations_of(stored) is DOCUMENT_ANIMATIONS_DEFAULT

    def test_the_builder_reads_both_through_the_doors(self) -> None:
        preferences = document_preferences(
            illustrations="never", animations="weekly", images_allowed=True
        )

        assert preferences == DocumentPreferences(
            illustrations=DocumentIllustrations.NEVER,
            animations=DOCUMENT_ANIMATIONS_DEFAULT,
            images_allowed=True,
        )

    def test_the_builder_carries_the_image_intents_as_stored(self) -> None:
        preferences = document_preferences(
            illustrations="auto",
            animations="always",
            images_allowed=True,
            image_quality="high",
            image_size="1024x1536",
        )

        assert (preferences.image_quality, preferences.image_size) == ("high", "1024x1536")

    @pytest.mark.parametrize(
        ("illustrations", "images_allowed", "illustrates"),
        [
            (DocumentIllustrations.AUTO, True, True),
            (DocumentIllustrations.ON_REQUEST, True, True),
            (DocumentIllustrations.NEVER, True, False),
            (DocumentIllustrations.AUTO, False, False),
        ],
    )
    def test_a_document_carries_pictures_only_when_both_say_yes(
        self, illustrations: DocumentIllustrations, images_allowed: bool, illustrates: bool
    ) -> None:
        preferences = DocumentPreferences(
            illustrations=illustrations, images_allowed=images_allowed
        )
        assert preferences.illustrates is illustrates

    def test_the_builder_never_grants_images_itself(self) -> None:
        preferences = document_preferences(
            illustrations="auto", animations="always", images_allowed=False
        )

        assert preferences.images_allowed is False


class TestTheFrontendMirror:
    """The settings screen offers exactly the choices the API accepts, in its order."""

    @staticmethod
    def _offered(name: str) -> list[str]:
        source = _WEB_VOCABULARY.read_text(encoding="utf-8")
        declared = re.search(rf"{name} = \[([^\]]*)\] as const", source)
        assert declared is not None, f"{name} moved: update this contract test"
        return re.findall(r"'([a-z_]+)'", declared.group(1))

    def test_the_illustration_choices_are_the_backend_vocabulary(self) -> None:
        offered = self._offered("DOCUMENT_ILLUSTRATIONS")

        assert offered == [choice.value for choice in DocumentIllustrations]

    def test_the_animation_choices_are_the_backend_vocabulary(self) -> None:
        offered = self._offered("DOCUMENT_ANIMATIONS")

        assert offered == [choice.value for choice in DocumentAnimations]
