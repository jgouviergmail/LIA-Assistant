"""A tool's own confirmation — the first of four levels (spec 2026-10-30 D1, D6, H7).

*Always* asks before every call, reads included. *Never* follows the tool's declaration
without the question it asks: a tool whose declaration owes a confirmation keeps the
``confirm`` policy and is marked APPROVED IN ADVANCE — the loop does not ask, the gate
approves under a kind of its own — and a tool whose declaration owes nothing keeps owing
nothing. A *never* is bound to the declaration it was chosen against (annotations and
input schema, never the description): a changed declaration SUSPENDS it, and the levels
below decide again. A choice never changes what a tool IS (D8).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.registry.confirmation_rule import requires_confirmation
from src.infrastructure.mcp.confirmation import (
    ConfirmationReason,
    ConfirmationSource,
    ServerConfirmation,
    ServerToolConfirmations,
    StoredToolChoice,
    ToolChoice,
    ToolConfirmation,
    confirmation_reason,
    declaration_fingerprint,
    resolve_tool_confirmation,
    suspended_choices,
)
from src.infrastructure.mcp.registration import build_mcp_tool_manifest

pytestmark = pytest.mark.unit

_DESTRUCTIVE: dict[str, Any] = {
    "name": "delete_note",
    "description": "Deletes a note.",
    "input_schema": {"type": "object", "properties": {"id": {"type": "string"}}},
    "annotations": {"destructive_hint": True},
}
_READ: dict[str, Any] = {
    "name": "read_note",
    "description": "Reads a note.",
    "input_schema": {"type": "object"},
    "annotations": {"read_only_hint": True},
}
_ADDITIVE: dict[str, Any] = {
    "name": "add_note",
    "description": "Adds a note.",
    "input_schema": {"type": "object"},
    "annotations": {"read_only_hint": False, "destructive_hint": False},
}
_ASK = ServerConfirmation(True, ConfirmationSource.ACCOUNT)
_DECLARED = ServerConfirmation(False, ConfirmationSource.INSTANCE)


def _never(tool: dict[str, Any]) -> StoredToolChoice:
    return StoredToolChoice(ToolChoice.NEVER, declaration_fingerprint(tool))


def _manifest(tool: dict[str, Any], confirmation: ToolConfirmation) -> Any:
    return build_mcp_tool_manifest(
        adapter_name=f"mcp_user_x_{tool['name']}",
        agent_name="mcp_notes_agent",
        tool_name=tool["name"],
        description=tool["description"],
        input_schema=tool["input_schema"],
        semantic_keywords=[],
        hitl_required=confirmation.hitl_required,
        annotations=tool.get("annotations"),
        standing_approval=confirmation.standing_approval,
    )


class TestDeclarationFingerprint:
    def test_the_description_is_left_out(self) -> None:
        reworded = {**_DESTRUCTIVE, "description": "Removes a note for good."}

        assert declaration_fingerprint(reworded) == declaration_fingerprint(_DESTRUCTIVE)

    @pytest.mark.parametrize(
        "changed",
        [
            {**_DESTRUCTIVE, "annotations": {"destructive_hint": False}},
            {**_DESTRUCTIVE, "input_schema": {"type": "object", "properties": {}}},
        ],
    )
    def test_annotations_and_input_schema_are_the_declaration(
        self, changed: dict[str, Any]
    ) -> None:
        assert declaration_fingerprint(changed) != declaration_fingerprint(_DESTRUCTIVE)

    def test_key_order_and_absence_are_not_a_change(self) -> None:
        reordered = {
            "input_schema": {"properties": {"id": {"type": "string"}}, "type": "object"},
            "annotations": {"destructive_hint": True},
        }
        assert declaration_fingerprint(reordered) == declaration_fingerprint(_DESTRUCTIVE)
        assert declaration_fingerprint({"name": "x"}) == declaration_fingerprint(
            {"name": "x", "annotations": None, "input_schema": None}
        )

    def test_it_survives_the_catalogue_s_persistence(self) -> None:
        """The page binds a choice to the STORED catalogue, a run reads the pool's tools:
        the same declaration must give the same fingerprint on both sides."""
        import json
        from datetime import UTC, datetime

        from src.infrastructure.mcp.catalogue_snapshot import (
            build_snapshot,
            parse_catalogue_snapshot,
            snapshot_to_jsonb,
        )

        nested = {
            **_DESTRUCTIVE,
            "input_schema": {
                "type": "object",
                "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
                "required": ["tags"],
            },
            "annotations": {"destructive_hint": True, "idempotent_hint": False},
        }
        snapshot = build_snapshot(
            tools=[nested, _READ],
            configuration_fingerprint="cfg",
            discovered_at=datetime(2026, 10, 30, tzinfo=UTC),
            generation=1,
        )
        stored = json.loads(json.dumps(snapshot_to_jsonb(snapshot)))  # the JSONB column

        (read_back,) = [
            tool for tool in parse_catalogue_snapshot(stored).tools if tool["name"] == "delete_note"
        ]
        assert declaration_fingerprint(read_back) == declaration_fingerprint(nested)


class TestResolution:
    @pytest.mark.parametrize("server", [_ASK, _DECLARED])
    def test_without_a_choice_the_server_decides(self, server: ServerConfirmation) -> None:
        assert resolve_tool_confirmation(server.always, None, _DESTRUCTIVE) == ToolConfirmation(
            hitl_required=server.always, standing_approval=False, choice=None, suspended=False
        )

    @pytest.mark.parametrize("server", [_ASK, _DECLARED])
    def test_always_asks_whatever_the_levels_below(self, server: ServerConfirmation) -> None:
        stored = StoredToolChoice(ToolChoice.ALWAYS, "a declaration since changed")

        assert resolve_tool_confirmation(server.always, stored, _READ) == ToolConfirmation(
            hitl_required=True, standing_approval=False, choice=ToolChoice.ALWAYS, suspended=False
        )

    @pytest.mark.parametrize("server", [_ASK, _DECLARED])
    def test_never_wins_over_the_levels_below(self, server: ServerConfirmation) -> None:
        assert resolve_tool_confirmation(server.always, _never(_DESTRUCTIVE), _DESTRUCTIVE) == (
            ToolConfirmation(
                hitl_required=False,
                standing_approval=True,
                choice=ToolChoice.NEVER,
                suspended=False,
            )
        )

    def test_never_chosen_against_another_declaration_is_suspended(self) -> None:
        stored = StoredToolChoice(ToolChoice.NEVER, declaration_fingerprint(_READ))

        assert resolve_tool_confirmation(_ASK.always, stored, _DESTRUCTIVE) == ToolConfirmation(
            hitl_required=True, standing_approval=False, choice=None, suspended=True
        )

    def test_a_server_s_tools_are_resolved_by_their_own_names(self) -> None:
        confirmations = ServerToolConfirmations(
            _DECLARED.always, {"delete_note": _never(_DESTRUCTIVE)}
        )

        assert confirmations.for_tool(_DESTRUCTIVE).choice is ToolChoice.NEVER
        assert confirmations.for_tool({**_READ, "name": "delete_note_v2"}).choice is None


class TestTheCardCountsSuspendedChoices:
    def test_only_a_listed_never_made_against_another_declaration_counts(self) -> None:
        tools = [_DESTRUCTIVE, _READ, _ADDITIVE]
        choices = {
            "delete_note": StoredToolChoice(ToolChoice.NEVER, "another declaration"),
            "read_note": StoredToolChoice(ToolChoice.ALWAYS, "another declaration"),
            "add_note": _never(_ADDITIVE),
            "gone_tool": StoredToolChoice(ToolChoice.NEVER, "another declaration"),
        }

        assert suspended_choices(tools, choices) == 1
        assert suspended_choices(tools, {}) == 0
        assert suspended_choices([], choices) == 0


class TestTheManifest:
    def test_never_on_a_declared_destruction_is_approved_in_advance(self) -> None:
        manifest = _manifest(
            _DESTRUCTIVE, resolve_tool_confirmation(_ASK.always, _never(_DESTRUCTIVE), _DESTRUCTIVE)
        )

        assert manifest.permissions.hitl_required is False
        assert manifest.mutation_policy == "confirm", "what the declaration owes is kept"
        assert manifest.approved_in_advance is True
        assert requires_confirmation(manifest) is False, "the loop does not ask"

    @pytest.mark.parametrize("tool", [_READ, _ADDITIVE, {**_READ, "annotations": None}])
    def test_never_on_a_tool_owing_nothing_keeps_owing_nothing(self, tool: dict[str, Any]) -> None:
        manifest = _manifest(tool, resolve_tool_confirmation(_ASK.always, _never(tool), tool))
        plain = _manifest(tool, resolve_tool_confirmation(_DECLARED.always, None, tool))

        assert manifest.approved_in_advance is False
        assert manifest.mutation_policy == plain.mutation_policy
        assert requires_confirmation(manifest) is False

    def test_always_on_a_declared_read_asks_before_every_call(self) -> None:
        stored = StoredToolChoice(ToolChoice.ALWAYS, declaration_fingerprint(_READ))
        manifest = _manifest(_READ, resolve_tool_confirmation(_DECLARED.always, stored, _READ))

        assert manifest.approved_in_advance is False
        assert requires_confirmation(manifest) is True

    @pytest.mark.parametrize("tool", [_DESTRUCTIVE, _READ, _ADDITIVE])
    def test_a_choice_never_changes_what_a_tool_is(self, tool: dict[str, Any]) -> None:
        """D8: the category, read by the initiative and the safety net, is the declaration's."""
        never = _manifest(tool, resolve_tool_confirmation(_ASK.always, _never(tool), tool))
        always = _manifest(
            tool,
            resolve_tool_confirmation(
                _DECLARED.always, StoredToolChoice(ToolChoice.ALWAYS, ""), tool
            ),
        )
        plain = _manifest(tool, resolve_tool_confirmation(_DECLARED.always, None, tool))

        assert never.tool_category == always.tool_category == plain.tool_category


class TestTheReason:
    def test_the_tool_s_choice_is_its_reason(self) -> None:
        assert (
            confirmation_reason(_DECLARED, _READ["annotations"], ToolChoice.ALWAYS)
            is ConfirmationReason.TOOL_ALWAYS
        )
        assert (
            confirmation_reason(_ASK, _DESTRUCTIVE["annotations"], ToolChoice.NEVER)
            is ConfirmationReason.TOOL_NEVER
        )

    def test_without_a_choice_the_levels_below_give_it(self) -> None:
        assert (
            confirmation_reason(_ASK, _READ["annotations"], None)
            is ConfirmationReason.ACCOUNT_ALWAYS
        )
        assert (
            confirmation_reason(_DECLARED, _DESTRUCTIVE["annotations"])
            is ConfirmationReason.DECLARED_DESTRUCTIVE
        )
