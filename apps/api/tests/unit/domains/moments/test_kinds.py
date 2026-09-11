"""A kind is a detector, a revalidator, a headline and a label — or it is nothing.

ADR-085's doctrine, applied to the one registry the next three kinds will grow
through: a table keyed by an enum gets a boot-time completeness assert, checked
BOTH ways, because the two failure modes are different and both are silent.

- a member with no spec: the sweep would loop over kinds and quietly skip one,
  so a feature ships and never fires;
- a spec with no member: a kind is removed and its detector keeps running,
  filing rows nothing will ever serve.

The label matters as much as the code: the settings panel renders
``t(spec.label_key)`` for whatever the backend publishes, and i18next falls back
to the key itself — so a kind added backend-side alone puts a raw
``moments.kind_deadline_eve`` in front of a reader in all six languages at once,
with every gate green. Same shape as the heartbeat's own source-label guard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domains.moments.kinds import (
    MOMENT_KIND_SPECS,
    assert_moment_kind_registry_complete,
)
from src.domains.moments.models import MomentKind

pytestmark = pytest.mark.unit

LOCALES = ("en", "fr", "de", "es", "it", "zh")
_WEB_LOCALES = Path(__file__).resolve().parents[5] / "web" / "locales"


class TestTheRegistryIsComplete:
    def test_every_kind_has_a_spec(self) -> None:
        assert set(MOMENT_KIND_SPECS) == set(MomentKind)

    def test_a_spec_names_the_kind_it_is_filed_under(self) -> None:
        """A copy-paste that keeps the wrong member would route a detector to
        the wrong rows without a single test noticing."""
        for kind, spec in MOMENT_KIND_SPECS.items():
            assert spec.kind is kind

    def test_the_boot_assert_accepts_the_shipped_registry(self) -> None:
        assert_moment_kind_registry_complete()

    def test_the_boot_assert_refuses_a_kind_with_no_spec(self) -> None:
        pruned = dict(MOMENT_KIND_SPECS)
        pruned.pop(MomentKind.EVENT_FOLLOWUP)

        with pytest.raises(RuntimeError, match="event_followup"):
            assert_moment_kind_registry_complete(specs=pruned)

    def test_the_boot_assert_refuses_a_spec_with_no_kind(self) -> None:
        extended = dict(MOMENT_KIND_SPECS)
        extended["ghost_kind"] = MOMENT_KIND_SPECS[MomentKind.EVENT_FOLLOWUP]

        with pytest.raises(RuntimeError, match="ghost_kind"):
            assert_moment_kind_registry_complete(specs=extended)


class TestEveryPieceOfASpecIsReal:
    def test_a_kind_can_detect_and_revalidate(self) -> None:
        for spec in MOMENT_KIND_SPECS.values():
            assert callable(spec.detector), spec.kind
            assert callable(spec.revalidator), spec.kind

    def test_a_kind_states_what_just_became_true(self) -> None:
        """The headline opens the FRESH section: an empty one would tell the
        model it was woken for nothing."""
        for spec in MOMENT_KIND_SPECS.values():
            assert spec.headline.strip(), spec.kind

    def test_a_kind_is_named_after_itself_on_screen(self) -> None:
        for kind, spec in MOMENT_KIND_SPECS.items():
            assert spec.label_key == f"moments.kind_{kind.value}"

    def test_a_dependency_is_declared_so_the_panel_can_say_why(self) -> None:
        """ADR-184: what is enforced is published. A kind that yields nothing
        without a calendar must say so rather than offer a live dead switch."""
        assert MOMENT_KIND_SPECS[MomentKind.EVENT_FOLLOWUP].requires == ("calendar",)


class TestTheLabelExistsWhereItIsRendered:
    @pytest.mark.parametrize("locale", LOCALES)
    def test_every_kind_label_is_translated(self, locale: str) -> None:
        translations = json.loads(
            (_WEB_LOCALES / locale / "translation.json").read_text(encoding="utf-8")
        )
        moments = translations.get("moments") or {}

        missing = [
            spec.label_key
            for spec in MOMENT_KIND_SPECS.values()
            if not str(moments.get(spec.label_key.split(".", 1)[1], "")).strip()
        ]

        assert not missing, f"{locale}: untranslated moment labels {missing}"
