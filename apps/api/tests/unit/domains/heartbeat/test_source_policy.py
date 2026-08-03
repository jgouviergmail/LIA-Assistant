"""Which sources may interrupt the user, and which the reader can silence.

"LIA may USE this service when I ask" and "LIA may INTERRUPT me from it" were
the same switch: the only documented way to stop receiving mail-driven nudges
was to disconnect the mail connector — which also removed the tool the user
asks with. The two are now separate: this policy gates the heartbeat's context
aggregation ONLY (``ContextAggregator.aggregate`` has exactly one caller, the
proactive task), so the agent's tools are untouched.

Three properties are pinned:

- the registry and the aggregator agree in BOTH directions — a source the
  aggregator fetches but the registry ignores can never be silenced, and a
  registry entry the aggregator does not know silences nothing;
- the default is "everything on", so an account that never opened the setting
  behaves exactly as before, and a source added later is on until refused;
- only registry keys are accepted, so a typo cannot silently disable nothing
  (or, worse, everything).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.domains.heartbeat import source_policy
from src.domains.heartbeat.source_policy import (
    HEARTBEAT_SOURCE_DEPENDENCIES,
    HEARTBEAT_SOURCE_KEYS,
    assert_source_registry_complete,
    disabled_sources_for,
    is_source_enabled,
    sanitize_disabled_sources,
    unmet_dependencies,
)

pytestmark = pytest.mark.unit


def _user(disabled: object = None) -> SimpleNamespace:
    return SimpleNamespace(heartbeat_disabled_sources=disabled)


class TestRegistry:
    def test_covers_the_eleven_sources_a_notification_can_come_from(self) -> None:
        assert HEARTBEAT_SOURCE_KEYS == frozenset(
            {
                "calendar",
                "tasks",
                "emails",
                "weather",
                "interests",
                "memories",
                "journals",
                "health_signals",
                "birthdays",
                "open_loops",
                "departure",
            }
        )

    def test_the_completeness_assert_passes_on_the_shipped_registry(self) -> None:
        assert_source_registry_complete()


class TestDefaults:
    def test_an_untouched_account_has_every_source_enabled(self) -> None:
        """NULL means "never expressed a preference", not "nothing allowed"."""
        user = _user(None)

        assert disabled_sources_for(user) == frozenset()
        for key in HEARTBEAT_SOURCE_KEYS:
            assert is_source_enabled(user, key) is True

    def test_a_source_the_registry_does_not_own_is_never_gated(self) -> None:
        """Internal context (activity, anti-redundancy windows) is not a source.

        Those feed the decision's awareness of what was ALREADY sent; gating
        them would make the assistant repeat itself, not interrupt less.
        """
        user = _user(["calendar"])

        assert is_source_enabled(user, "recent_heartbeats") is True
        assert is_source_enabled(user, "activity") is True


class TestRefusal:
    def test_a_disabled_source_is_reported_disabled(self) -> None:
        user = _user(["emails", "weather"])

        assert is_source_enabled(user, "emails") is False
        assert is_source_enabled(user, "weather") is False
        assert is_source_enabled(user, "calendar") is True

    def test_every_source_can_be_disabled_at_once(self) -> None:
        """Silencing everything is legitimate — and must not crash the cycle."""
        user = _user(sorted(HEARTBEAT_SOURCE_KEYS))

        assert all(not is_source_enabled(user, key) for key in HEARTBEAT_SOURCE_KEYS)


class TestSanitize:
    def test_unknown_keys_are_refused_rather_than_stored(self) -> None:
        """A typo must not become a preference nobody can see or undo."""
        with pytest.raises(ValueError, match="unknown"):
            sanitize_disabled_sources(["calendar", "not-a-source"])

    def test_duplicates_and_order_do_not_matter(self) -> None:
        assert sanitize_disabled_sources(["emails", "emails", "calendar"]) == ["calendar", "emails"]

    def test_an_empty_selection_is_stored_as_empty_not_null(self) -> None:
        """Distinguishes "I re-enabled everything" from "never asked"."""
        assert sanitize_disabled_sources([]) == []

    def test_malformed_stored_data_degrades_to_everything_enabled(self) -> None:
        """A hand-edited JSONB must not silence a source by accident.

        Reading is tolerant on purpose — the write path is where the vocabulary
        is enforced. A dict, a string, or a list of numbers means the column
        cannot be trusted, and the safe reading is the historical behaviour.
        """
        for broken in ({"calendar": True}, "calendar", [1, 2], [None]):
            assert disabled_sources_for(_user(broken)) == frozenset()


class TestDependencies:
    """A source that silently needs another must say so.

    `fetch_departure_advice` opens with `if not calendar_events: return None`.
    Refusing `calendar` therefore makes the `departure` switch a no-op — the
    reader keeps a control that is on, and gets nothing, with no way to learn
    why. ADR-184: what the system enforces, its producer must be able to read.
    """

    def test_departure_declares_its_dependency_on_the_calendar(self) -> None:
        assert HEARTBEAT_SOURCE_DEPENDENCIES["departure"] == ("calendar",)

    def test_every_declared_dependency_is_a_real_source(self) -> None:
        # A dependency naming something the registry does not own would publish
        # a requirement nobody can satisfy.
        for source, requires in HEARTBEAT_SOURCE_DEPENDENCIES.items():
            assert source in HEARTBEAT_SOURCE_KEYS, source
            for required in requires:
                assert required in HEARTBEAT_SOURCE_KEYS, required

    def test_no_source_depends_on_itself(self) -> None:
        for source, requires in HEARTBEAT_SOURCE_DEPENDENCIES.items():
            assert source not in requires

    def test_the_completeness_assert_rejects_a_dependency_on_a_ghost(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            source_policy, "HEARTBEAT_SOURCE_DEPENDENCIES", {"departure": ("astrology",)}
        )
        with pytest.raises(RuntimeError, match="astrology"):
            source_policy.assert_source_registry_complete()

    def test_unmet_dependencies_are_reported_for_a_refusal_set(self) -> None:
        # Nothing refused: nothing to warn about.
        assert unmet_dependencies([]) == {}
        # Calendar refused: departure is on, and useless.
        assert unmet_dependencies(["calendar"]) == {"departure": ("calendar",)}

    def test_a_source_refused_alongside_its_dependency_is_not_reported(self) -> None:
        # The reader turned departure off too — there is nothing surprising
        # left to tell them, and saying it anyway would be noise.
        assert unmet_dependencies(["calendar", "departure"]) == {}
