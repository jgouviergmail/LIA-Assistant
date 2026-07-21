"""Interactive widgets persisted with their message — write and read paths.

Defect closed (2026-07-21): the widget payload lived ONLY in the browser's
React state, fed by the live SSE stream. The message persisted the sentinel but
not what it pointed at, so any session that had not received the stream
resolved it to nothing. Verified against the production database: assistant
``message_metadata`` carried exactly ``run_id`` / ``intention`` /
``psyche_state`` — no registry anywhere.
"""

from __future__ import annotations

from typing import Any

from src.domains.agents.data_registry.message_widgets import (
    MESSAGE_METADATA_WIDGETS_KEY,
    extract_persistable_widgets,
    rehydrate_message_widgets,
    with_persisted_widgets,
    with_rehydrated_widgets,
)


def _item(item_type: str, *, skill_name: str = "interactive-map", **payload: Any) -> dict[str, Any]:
    return {
        "id": "x",
        "type": item_type,
        "payload": {"skill_name": skill_name, **payload},
        "meta": {"source": "skill", "timestamp": "2026-07-21T09:13:00Z"},
    }


class TestExtractPersistableWidgets:
    def test_keeps_skill_and_mcp_widgets(self) -> None:
        registry = {
            "skill_app_1": _item("SKILL_APP", frame_url="https://x"),
            "mcp_app_1": _item("MCP_APP", skill_name="excalidraw"),
        }
        kept = extract_persistable_widgets(registry, max_bytes=65_536)
        assert set(kept) == {"skill_app_1", "mcp_app_1"}

    def test_drops_data_cards(self) -> None:
        registry = {
            "email_1": _item("EMAIL"),
            "weather_1": _item("WEATHER"),
            "skill_app_1": _item("SKILL_APP"),
        }
        assert set(extract_persistable_widgets(registry, max_bytes=65_536)) == {"skill_app_1"}

    def test_drops_drafts_deliberately(self) -> None:
        """A draft is HITL state with its own lifecycle; a stale persisted one
        would invite confirming an action the graph no longer knows about."""
        registry = {"draft_1": _item("DRAFT"), "skill_app_1": _item("SKILL_APP")}
        assert set(extract_persistable_widgets(registry, max_bytes=65_536)) == {"skill_app_1"}

    def test_drops_a_widget_over_budget_rather_than_truncating(self) -> None:
        registry = {"skill_app_big": _item("SKILL_APP", html_content="x" * 5_000)}
        assert extract_persistable_widgets(registry, max_bytes=1_024) == {}

    def test_keeps_a_widget_inside_budget(self) -> None:
        registry = {"skill_app_ok": _item("SKILL_APP", html_content="x" * 100)}
        assert set(extract_persistable_widgets(registry, max_bytes=65_536)) == {"skill_app_ok"}

    def test_empty_registry_is_a_no_op(self) -> None:
        assert extract_persistable_widgets(None, max_bytes=65_536) == {}
        assert extract_persistable_widgets({}, max_bytes=65_536) == {}


class TestWithPersistedWidgets:
    def test_attaches_the_widgets_under_the_metadata_key(self) -> None:
        widgets = {"skill_app_1": _item("SKILL_APP")}
        out = with_persisted_widgets({"run_id": "r", "intention": "action"}, widgets, run_id="r")
        assert out[MESSAGE_METADATA_WIDGETS_KEY] == widgets
        assert out["run_id"] == "r"

    def test_returns_the_input_by_identity_when_there_is_nothing_to_attach(self) -> None:
        """Branch-free at the call site: the archive path must not gain a
        conditional (it sits in an already very large streaming function)."""
        metadata = {"run_id": "r"}
        assert with_persisted_widgets(metadata, {}, run_id="r") is metadata

    def test_never_mutates_the_metadata_being_assembled(self) -> None:
        metadata = {"run_id": "r"}
        with_persisted_widgets(metadata, {"skill_app_1": _item("SKILL_APP")}, run_id="r")
        assert metadata == {"run_id": "r"}


class TestRehydrateMessageWidgets:
    def test_returns_the_stored_widgets(self) -> None:
        stored = {"skill_app_1": _item("SKILL_APP", is_system_skill=True)}
        metadata = {"run_id": "r", MESSAGE_METADATA_WIDGETS_KEY: stored}
        out = rehydrate_message_widgets(metadata, system_skill_names=frozenset({"interactive-map"}))
        assert set(out) == {"skill_app_1"}

    def test_recomputes_is_system_skill_from_the_current_set(self) -> None:
        """A skill demoted since the message was written must lose the flag —
        it grants the iframe `allow-same-origin` and `credentialless`."""
        stored = {"skill_app_1": _item("SKILL_APP", is_system_skill=True)}
        metadata = {MESSAGE_METADATA_WIDGETS_KEY: stored}

        out = rehydrate_message_widgets(metadata, system_skill_names=frozenset())

        assert out["skill_app_1"]["payload"]["is_system_skill"] is False
        # The stored structure is untouched — no read-time write-back.
        assert stored["skill_app_1"]["payload"]["is_system_skill"] is True

    def test_promotes_a_skill_that_is_system_now(self) -> None:
        stored = {"skill_app_1": _item("SKILL_APP", is_system_skill=False)}
        out = rehydrate_message_widgets(
            {MESSAGE_METADATA_WIDGETS_KEY: stored},
            system_skill_names=frozenset({"interactive-map"}),
        )
        assert out["skill_app_1"]["payload"]["is_system_skill"] is True

    def test_leaves_payloads_without_the_flag_alone(self) -> None:
        """MCP apps carry no `is_system_skill` — nothing to re-evaluate."""
        stored = {"mcp_app_1": {"id": "m", "type": "MCP_APP", "payload": {"tool_name": "t"}}}
        out = rehydrate_message_widgets(
            {MESSAGE_METADATA_WIDGETS_KEY: stored}, system_skill_names=frozenset()
        )
        assert out["mcp_app_1"]["payload"] == {"tool_name": "t"}

    def test_metadata_without_widgets_yields_nothing(self) -> None:
        assert rehydrate_message_widgets(None, system_skill_names=frozenset()) == {}
        assert rehydrate_message_widgets({"run_id": "r"}, system_skill_names=frozenset()) == {}
        assert (
            rehydrate_message_widgets(
                {MESSAGE_METADATA_WIDGETS_KEY: "not-a-dict"}, system_skill_names=frozenset()
            )
            == {}
        )


class TestWithRehydratedWidgets:
    def test_returns_a_new_dict_and_never_mutates_the_input(self) -> None:
        stored = {"skill_app_1": _item("SKILL_APP", is_system_skill=True)}
        metadata = {"run_id": "r", MESSAGE_METADATA_WIDGETS_KEY: stored}

        out = with_rehydrated_widgets(metadata, system_skill_names=frozenset())

        assert out is not metadata
        assert out is not None
        assert out["run_id"] == "r"
        assert (
            out[MESSAGE_METADATA_WIDGETS_KEY]["skill_app_1"]["payload"]["is_system_skill"] is False
        )
        # In-place JSONB mutation is a SQLAlchemy trap AND a read-time leak.
        assert (
            metadata[MESSAGE_METADATA_WIDGETS_KEY]["skill_app_1"]["payload"]["is_system_skill"]
            is True
        )

    def test_passes_metadata_without_widgets_straight_through(self) -> None:
        metadata = {"run_id": "r"}
        assert with_rehydrated_widgets(metadata, system_skill_names=frozenset()) is metadata
        assert with_rehydrated_widgets(None, system_skill_names=frozenset()) is None
