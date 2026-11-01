"""No agent tool path may write a routine's MCP pre-approval (spec D9, Review Focus 5).

The pre-approval lets a routine's runs confirm a server's tools themselves, so an
instruction a third party slipped into the agent's input must never reach it: the
agent's routine tools — the chat's automation tool and the Studio's — build only
the schemas the field is kept OUT of. What the agent may still do is change, run
or switch on a routine that carries one; its confirmation card then SAYS so, and a
pre-approval changed after the card makes the command stale.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from src.domains.agents.application.routine_create_schemas import RoutineCreateRequest
from src.domains.agents.application.routine_operations import routine_snapshot
from src.domains.agents.application.routine_update_schemas import RoutineUpdateChanges
from src.domains.scheduled_actions.schemas import ScheduledActionCreate, ScheduledActionUpdate

pytestmark = [pytest.mark.unit]

_FIELD = "mcp_preapproved_servers"


class TestNoAgentSchemaCarriesIt:
    @pytest.mark.parametrize(
        "schema",
        [ScheduledActionCreate, ScheduledActionUpdate, RoutineCreateRequest, RoutineUpdateChanges],
    )
    def test_the_schemas_the_agent_builds_have_no_such_field(self, schema: Any) -> None:
        assert _FIELD not in schema.model_fields

    def test_a_studio_edit_naming_it_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            RoutineUpdateChanges.model_validate({"title": "x", _FIELD: ["notes"]})

    def test_the_agent_tools_call_schemas_refuse_it(self) -> None:
        from src.domains.agents.tools.application_routine_tools import (
            create_lia_routine_tool,
            update_lia_routine_tool,
        )
        from src.domains.agents.tools.automation_tools import create_scheduled_action_tool

        for tool in (create_lia_routine_tool, update_lia_routine_tool):
            schema = tool.tool_call_schema.model_json_schema()
            assert _FIELD not in str(schema), f"{tool.name} publishes the pre-approval"
        assert _FIELD not in create_scheduled_action_tool.args


def _row(**over: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "id": uuid.uuid4(),
        "title": "Tidy",
        "action_prompt": "tidy my notes",
        "recurrence": {
            "freq": "daily",
            "anchor_date": "2026-11-02",
            "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
        },
        "trigger_kind": "time",
        "condition_config": None,
        "requires_approval": False,
        "execution_mode": "react",
        "is_enabled": True,
        "user_timezone": "Europe/Paris",
        "created_at": datetime(2026, 10, 1, tzinfo=UTC),
        "mcp_preapproved_servers": None,
    }
    base.update(over)
    return SimpleNamespace(**base)


class TestTheCardKnowsIt:
    def test_a_preapproval_changed_after_the_card_makes_the_command_stale(self) -> None:
        """The snapshot the Studio compares at execution covers the ticked servers."""
        before = _row()
        after = _row(id=before.id, mcp_preapproved_servers=["notes"])

        assert routine_snapshot(before) != routine_snapshot(after)

    @pytest.mark.parametrize("language", ["fr", "en", "es", "de", "it", "zh-CN"])
    def test_switching_a_routine_on_names_what_it_confirms_for_itself(self, language: str) -> None:
        """The real card of the state command, through the renderer the chat draws."""
        from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
        from src.domains.agents.application.action_preparation import build_action_content
        from src.domains.agents.application.draft_rendering import render_application_preview
        from src.domains.agents.application.routine_schemas import (
            RoutineSnapshot,
            RoutineStatePatch,
            RoutineStateValues,
        )
        from src.domains.agents.application.routine_spec import ROUTINE_STATE_OPERATION

        expected = RoutineSnapshot(
            id=uuid.uuid4(), title="Tidy", enabled=False, configuration_digest="a" * 64
        )
        names = ("Notes", "Excalidraw")
        previous, desired = (
            RoutineStatePatch(
                routine_state=RoutineStateValues(
                    expected=expected, enabled=enabled, mcp_preapproval=names
                )
            )
            for enabled in (False, True)
        )
        draft = build_action_content(
            uuid.uuid4(),
            ROUTINE_STATE_OPERATION,
            desired,
            previous.model_dump(mode="json"),
            desired.model_dump(mode="json"),
        )
        labels = DRAFT_PREVIEW_LABELS[language]

        lines = render_application_preview(
            draft.model_dump(mode="json"), labels, lambda value: value or ""
        )

        shown = [(getattr(line, "label", None), getattr(line, "value", None)) for line in lines]
        assert (labels["application_routine_mcp_preapproval"], "Notes, Excalidraw") in shown

    def test_its_card_shows_the_preapproved_servers(self) -> None:
        from src.domains.agents.application.routine_card_rows import preapproval_rows

        rows = preapproval_rows(
            ("Notes", "Excalidraw"), {"application_routine_mcp_preapproval": "L"}
        )

        assert [(row.label, row.value) for row in rows] == [("L", "Notes, Excalidraw")]
        assert preapproval_rows((), {"application_routine_mcp_preapproval": "L"}) == []
