"""Animation evidence comes from invocation, never a plan or a replayed effect."""

import asyncio
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.domains.agents.calendar.catalogue_manifests import (
    create_event_catalogue_manifest,
    get_events_catalogue_manifest,
)
from src.domains.agents.drafts.models import DraftType
from src.domains.agents.effects import runtime
from src.domains.agents.emails.catalogue_manifests import send_email_catalogue_manifest
from src.domains.agents.expressivity.activity import (
    DRAFT_FAMILIES,
    Activity,
    activity_family,
    activity_outcome,
    capture_activity,
    observe_activity,
)
from src.domains.agents.registry.catalogue import ToolManifest


@pytest.mark.parametrize(
    ("manifest", "family"),
    [
        (get_events_catalogue_manifest, "reading"),
        (create_event_catalogue_manifest, "organizing"),
        (send_email_catalogue_manifest, "communicating"),
    ],
)
def test_family_uses_the_catalogue_s_effective_category(
    manifest: ToolManifest, family: str
) -> None:
    assert activity_family(manifest) == family


def test_confirmed_draft_families_cover_the_execution_registry() -> None:
    assert set(DRAFT_FAMILIES) == {kind.value for kind in DraftType}
    assert DRAFT_FAMILIES[DraftType.EMAIL] == "communicating"


@pytest.fixture(autouse=True)
def observable_run() -> Iterator[None]:
    with capture_activity("test-run"):
        yield


async def test_decoration_failure_cannot_prevent_or_repeat_an_operation() -> None:
    calls = 0

    async def run() -> dict[str, bool]:
        nonlocal calls
        calls += 1
        return {"success": True}

    with patch("src.domains.agents.expressivity.activity.emit_activity", side_effect=ValueError):
        assert await observe_activity("reader", "read", run) == {"success": True}
    events: list[Activity] = []
    with patch("src.domains.agents.expressivity.activity.emit_activity", events.append):
        await observe_activity("reader", "read", run)
    assert calls == 2
    assert len(events) == 2  # The ownership context was released even on emitter failure.


async def test_unavailable_graph_context_cannot_prevent_or_repeat_the_operation() -> None:
    calls = 0
    result = {"success": True}

    async def run() -> dict[str, bool]:
        nonlocal calls
        calls += 1
        return result

    with patch(
        "src.domains.agents.expressivity.activity.runtime_context_if_running",
        side_effect=RuntimeError("context unavailable"),
    ):
        assert await observe_activity("reader", "read", run) is result
    assert calls == 1


@pytest.mark.parametrize(
    ("result", "policy", "expected"),
    [
        ({"success": True}, "read", "succeeded"),
        ({"success": False}, "draft", "failed"),
        ({"success": True}, "draft", "prepared"),
        ({"draft_id": "d"}, "read", "prepared"),
        ({"data": "opaque"}, "confirm", "unknown"),
        ("Success!", "confirm", "unknown"),
    ],
)
def test_outcome_requires_evidence(result: object, policy: str, expected: str) -> None:
    assert activity_outcome(result, policy) == expected


async def test_observation_surrounds_the_actual_await_and_keeps_result_identity() -> None:
    events: list[Activity] = []
    result = {"success": True}

    async def run() -> dict[str, bool]:
        assert [e.phase for e in events] == ["started"]
        return result

    with patch("src.domains.agents.expressivity.activity.emit_activity", events.append):
        assert await observe_activity("get_emails_tool", "read", run) is result
    assert [e.phase for e in events] == ["started", "finished"]
    assert events[1].outcome == "succeeded"
    assert events[0].invocation_id == events[1].invocation_id


async def test_parallel_invocations_keep_distinct_ownership_and_release_it() -> None:
    events: list[Activity] = []
    entered = 0
    both_entered = asyncio.Event()

    async def operation() -> dict[str, bool]:
        nonlocal entered
        entered += 1
        if entered == 2:
            both_entered.set()
        await asyncio.wait_for(both_entered.wait(), timeout=1)
        return {"success": True}

    with patch("src.domains.agents.expressivity.activity.emit_activity", events.append):
        await asyncio.gather(
            observe_activity("first", "read", operation),
            observe_activity("second", "read", operation),
        )
    assert len(events) == 4
    ids = {event.invocation_id for event in events}
    assert len(ids) == 2
    for identity in ids:
        assert [event.phase for event in events if event.invocation_id == identity] == [
            "started",
            "finished",
        ]


@pytest.mark.parametrize(
    "patch_data",
    [
        {"version": 2},
        {"run_id": ""},
        {"invocation_id": ""},
        {"arguments": {"secret": "do not publish"}},
        {"phase": "started", "outcome": "succeeded"},
        {"phase": "finished", "outcome": None},
    ],
)
def test_wire_rejects_incoherent_or_private_metadata(patch_data: dict[str, object]) -> None:
    payload = {
        "run_id": "r",
        "invocation_id": "i",
        "family": "reading",
        "intent": "read",
        "phase": "started",
    }
    with pytest.raises(ValidationError):
        Activity.model_validate({**payload, **patch_data})


@pytest.mark.parametrize("error", [ValueError("private content"), asyncio.CancelledError()])
async def test_failures_and_cancellation_close_without_swallowing(error: BaseException) -> None:
    events: list[Activity] = []

    async def run() -> None:
        raise error

    with patch("src.domains.agents.expressivity.activity.emit_activity", events.append):
        with pytest.raises(type(error)):
            await observe_activity("get_emails_tool", "read", run)
    assert events[-1].outcome in {"failed", "cancelled"}
    assert "private" not in events[-1].model_dump_json()


async def test_nested_calls_have_one_owner() -> None:
    events: list[Activity] = []

    async def inner() -> bool:
        return True

    async def outer() -> bool:
        return await observe_activity("nested", "read", inner)

    with patch("src.domains.agents.expressivity.activity.emit_activity", events.append):
        await observe_activity("parent", "read", outer)
    assert len(events) == 2


async def test_gate_does_not_emit_for_refused_capabilities() -> None:
    events: list[Activity] = []

    async def run() -> None:
        pytest.fail("an unconfirmed action must not run")

    with (
        patch.object(runtime, "resolve_policy", return_value="confirm"),
        patch.object(runtime, "_refuse_or_ask", return_value={"success": False}),
        patch("src.domains.agents.expressivity.activity.emit_activity", events.append),
    ):
        await runtime.gated("send", run)()
    assert events == []


async def test_gate_observes_actual_read() -> None:
    events: list[Activity] = []

    async def run() -> dict[str, bool]:
        return {"success": True}

    with (
        patch.object(runtime, "resolve_policy", return_value="read"),
        patch("src.domains.agents.expressivity.activity.emit_activity", events.append),
    ):
        await runtime.gated("reader", run)()
    assert [e.phase for e in events] == ["started", "finished"]
