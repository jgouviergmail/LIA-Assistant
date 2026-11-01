"""A routine's MCP pre-approval: written by its form alone, strict on write, forgiving on read (D9).

The routine form ticks the servers whose confirmations a run may give itself. The
REST route is the only writer: the schemas the agent's routine tools build carry no
such field. A write names only servers the account can call — its own enabled
servers, the administrator's servers it has not switched off — and anything else is
refused with a code the web app translates. A read never fails: a key gone stale
since it was stored is returned as stored, a malformed value as nothing.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError as PydanticValidationError

from src.core.exceptions import BaseAPIException
from src.domains.scheduled_actions.schemas import (
    ScheduledActionCreate,
    ScheduledActionFormCreate,
    ScheduledActionFormUpdate,
    ScheduledActionUpdate,
)
from src.domains.scheduled_actions.service import ScheduledActionService

pytestmark = pytest.mark.unit

_CALLABLE = {"7f3a0c1e-0000-4000-8000-000000000001": "Notes", "excalidraw": "Excalidraw"}


def _service(row: SimpleNamespace) -> ScheduledActionService:
    def _apply(target: SimpleNamespace, data: dict[str, Any]) -> SimpleNamespace:
        for key, value in data.items():
            setattr(target, key, value)
        return target

    service = ScheduledActionService(MagicMock())
    service.repository = MagicMock()
    service.repository.update = AsyncMock(side_effect=_apply)
    return service


def _row(**over: Any) -> SimpleNamespace:
    base: dict[str, Any] = {"id": uuid.uuid4(), "user_id": uuid.uuid4()}
    return SimpleNamespace(**{**base, "mcp_preapproved_servers": None, **over})


class TestOnlyTheFormWrites:
    def test_the_shared_schemas_carry_no_preapproval(self) -> None:
        """The agent's routine tools build these: none of them can name a server."""
        assert "mcp_preapproved_servers" not in ScheduledActionCreate.model_fields
        assert "mcp_preapproved_servers" not in ScheduledActionUpdate.model_fields

    def test_the_form_schemas_carry_it(self) -> None:
        created = ScheduledActionFormCreate.model_validate(
            {
                "title": "Tidy",
                "action_prompt": "tidy my notes",
                "recurrence": {
                    "freq": "daily",
                    "anchor_date": "2026-11-02",
                    "times": {"mode": "at", "at": [{"hour": 8, "minute": 0}]},
                },
                "mcp_preapproved_servers": ["excalidraw"],
            }
        )
        updated = ScheduledActionFormUpdate.model_validate({"mcp_preapproved_servers": None})

        assert created.mcp_preapproved_servers == ["excalidraw"]
        assert "mcp_preapproved_servers" in updated.model_fields_set
        assert "mcp_preapproved_servers" not in updated.routine_changes().model_dump(
            exclude_unset=True
        ), "the routine's own changes never carry the pre-approval"

    @pytest.mark.parametrize("value", [[""], ["x" * 256], "excalidraw"])
    def test_a_malformed_key_is_refused_before_the_service(self, value: object) -> None:
        with pytest.raises(PydanticValidationError):
            ScheduledActionFormUpdate.model_validate({"mcp_preapproved_servers": value})


class TestTheWriteIsStrict:
    async def test_write_refuses_an_unknown_or_foreign_server_key(self) -> None:
        row = _row()
        service = _service(row)

        with (
            patch(
                "src.domains.scheduled_actions.service.callable_mcp_servers",
                new=AsyncMock(return_value=_CALLABLE),
            ),
            pytest.raises(BaseAPIException) as refused,
        ):
            await service.set_mcp_preapproval(
                row, SimpleNamespace(id=row.user_id), ["excalidraw", "someone-elses-server"]
            )

        assert refused.value.status_code == 400
        assert refused.value.detail == {
            "code": "routine_mcp_server_not_callable",
            "servers": ["someone-elses-server"],
        }
        assert row.mcp_preapproved_servers is None, "nothing is written"

    async def test_a_callable_selection_is_stored_once_each_in_order(self) -> None:
        row = _row()
        service = _service(row)

        with patch(
            "src.domains.scheduled_actions.service.callable_mcp_servers",
            new=AsyncMock(return_value=_CALLABLE),
        ):
            await service.set_mcp_preapproval(
                row,
                SimpleNamespace(id=row.user_id),
                ["excalidraw", "7f3a0c1e-0000-4000-8000-000000000001", "excalidraw"],
            )

        assert row.mcp_preapproved_servers == [
            "7f3a0c1e-0000-4000-8000-000000000001",
            "excalidraw",
        ]

    @pytest.mark.parametrize("cleared", [None, []])
    async def test_an_empty_selection_is_no_preapproval(self, cleared: list[str] | None) -> None:
        row = _row(mcp_preapproved_servers=["excalidraw"])
        service = _service(row)
        callable_servers = AsyncMock(return_value=_CALLABLE)

        with patch(
            "src.domains.scheduled_actions.service.callable_mcp_servers", new=callable_servers
        ):
            await service.set_mcp_preapproval(row, SimpleNamespace(id=row.user_id), cleared)

        assert row.mcp_preapproved_servers is None, "SQL NULL, never an empty list"
        callable_servers.assert_not_awaited()


class TestTheReadIsForgiving:
    @pytest.mark.parametrize(
        ("stored", "read"),
        [
            (None, []),
            (["gone-server"], ["gone-server"]),
            ({"not": "a list"}, []),
            (["ok", 3, None], ["ok"]),
        ],
    )
    def test_a_stored_value_is_read_without_failing(self, stored: object, read: list[str]) -> None:
        """A key gone stale is returned as stored; a malformed value reads as nothing."""
        from tests.unit.domains.scheduled_actions.test_schemas import _response

        assert _response(None, mcp_preapproved_servers=stored).mcp_preapproved_servers == read


class TestTheCardNamesWhatItConfirms:
    """The Studio card names the servers a routine confirms for itself (spec D9)."""

    async def test_each_key_is_named_and_a_stale_one_keeps_its_key(self) -> None:
        from src.domains.scheduled_actions import mcp_preapproval

        row: Any = SimpleNamespace(mcp_preapproved_servers=["k-notes", "gone", "excalidraw"])
        callable_now = AsyncMock(return_value={"k-notes": "Notes", "excalidraw": "Excalidraw"})

        with patch.object(mcp_preapproval, "callable_mcp_servers", callable_now):
            names = await mcp_preapproval.preapproval_names(MagicMock(), MagicMock(), row)

        assert names == ("Notes", "gone", "Excalidraw"), "a stale tick is shown, never hidden"

    async def test_nothing_ticked_names_nothing_and_reads_nothing(self) -> None:
        from src.domains.scheduled_actions import mcp_preapproval

        callable_now = AsyncMock()
        with patch.object(mcp_preapproval, "callable_mcp_servers", callable_now):
            names = await mcp_preapproval.preapproval_names(
                MagicMock(), MagicMock(), SimpleNamespace(mcp_preapproved_servers=None)
            )

        assert names == ()
        callable_now.assert_not_awaited()
