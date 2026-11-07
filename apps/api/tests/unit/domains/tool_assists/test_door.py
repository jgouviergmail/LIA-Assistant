"""The one door of the assists (ADR-372).

A click asks a model: it is an act of LIA's, so both ceilings are asked first, the spend reaches
the ledger whatever happens, what was read is filed, and the person is told in stable words. A
result served from a cache opened nothing and cost nothing, and files nothing.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.core.constants import INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE
from src.core.exceptions import BaseAPIException
from src.core.exceptions_domains import UsageLimitExceededError
from src.domains.tool_assists import door
from src.domains.tool_assists.catalogue import ToolAssist
from src.domains.tool_assists.door import AssistRun, run_assist
from src.domains.workbench.errors import ITEM_GONE, refuse

pytestmark = pytest.mark.unit

MODEL = "a-model"


PERSON: UUID = uuid4()
LANGUAGE = "fr"


def _spent(run: AssistRun, tokens_in: int = 100, tokens_out: int = 20) -> None:
    """A model answered: what the provider reports reaches the run's callback."""
    usage = {"input_tokens": tokens_in, "output_tokens": tokens_out, "total_tokens": 120}
    message = AIMessage(content="ok", usage_metadata=usage)
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    for handler in run.config["callbacks"]:
        handler.on_llm_end(result, run_id=uuid4())


@pytest.fixture
def ledger(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Everything the door files, kept instead of written."""
    filed: dict[str, list[Any]] = {"bills": [], "reads": [], "limits": []}

    async def fake_track(**fields: Any) -> str:
        filed["bills"].append(fields)
        return str(fields["run_id"])

    async def allow(user_id: object, *, layer: str) -> None:
        filed["limits"].append(layer)

    monkeypatch.setattr("src.infrastructure.proactive.tracking.track_proactive_tokens", fake_track)
    monkeypatch.setattr(door, "enforce_usage_limit", allow)
    monkeypatch.setattr(
        door, "record_surface_consultations", lambda **fields: filed["reads"].append(fields)
    )
    monkeypatch.setattr(door, "slot_model", lambda slot: MODEL)
    return filed


async def _answering(run: AssistRun) -> str:
    async with run.reading():
        _spent(run)
    return "the answer"


def _code(refused: pytest.ExceptionInfo[BaseAPIException]) -> str:
    detail = refused.value.detail
    assert isinstance(detail, dict)
    return str(detail["code"])


async def test_an_answer_comes_with_what_it_cost(ledger: dict[str, list[Any]]) -> None:
    done = await run_assist(ToolAssist.MAIL_REPLY, PERSON, LANGUAGE, _answering)

    assert done.value == "the answer"
    assert done.usage is not None
    assert done.usage.tokens_in == 100
    assert done.usage.tokens_out == 20


async def test_a_source_is_filed_for_what_became_of_it(ledger: dict[str, list[Any]]) -> None:
    async def stopped_at_the_contact(run: AssistRun) -> str:
        async with run.reading("contacts"):
            _spent(run)
        return "the answer"

    await run_assist(ToolAssist.CONTACT_COMPLETE, PERSON, LANGUAGE, stopped_at_the_contact)

    (read,) = ledger["reads"]
    assert read["opened"] == ["contacts"]
    assert read["failed"] == []


async def test_only_the_source_that_refused_is_filed_as_failed(
    ledger: dict[str, list[Any]],
) -> None:
    async def lost_on_the_mailbox(run: AssistRun) -> str:
        async with run.reading("contacts"):
            pass
        async with run.reading("mail"):
            raise RuntimeError("the mailbox went away")

    with pytest.raises(BaseAPIException):
        await run_assist(ToolAssist.CONTACT_COMPLETE, PERSON, LANGUAGE, lost_on_the_mailbox)

    (read,) = ledger["reads"]
    assert read["opened"] == ["contacts", "mail"]
    assert read["failed"] == ["mail"]


async def test_a_voice_asks_the_ceilings_itself(ledger: dict[str, list[Any]]) -> None:
    async def spoken(run: AssistRun) -> str:
        run.served = True
        return "the audio"

    await run_assist(ToolAssist.READ_ALOUD, PERSON, LANGUAGE, spoken)

    assert ledger["limits"] == []


async def test_what_a_voice_said_is_no_held_answer(ledger: dict[str, list[Any]]) -> None:
    async def spoken(run: AssistRun) -> str:
        run.served = True
        return "the audio"

    done = await run_assist(ToolAssist.READ_ALOUD, PERSON, LANGUAGE, spoken)

    assert done.usage is None
    assert done.held is False
    assert ledger["bills"] == []


async def test_a_file_read_by_sight_is_billed_on_the_slot_that_read_it(
    ledger: dict[str, list[Any]],
) -> None:
    async def by_sight(run: AssistRun) -> str:
        _spent(run)
        run.slot = "vision_analysis"
        return "the reading"

    await run_assist(ToolAssist.FILE_SUMMARY, PERSON, LANGUAGE, by_sight)

    (bill,) = ledger["bills"]
    assert bill["llm_type"] == "vision_analysis"


async def test_a_failure_after_reading_by_sight_stays_on_that_slot(
    ledger: dict[str, list[Any]],
) -> None:
    async def by_sight(run: AssistRun) -> str:
        _spent(run)
        run.slot = "vision_analysis"
        raise RuntimeError("no usable answer")

    with pytest.raises(BaseAPIException):
        await run_assist(ToolAssist.FILE_SUMMARY, PERSON, LANGUAGE, by_sight)

    (bill,) = ledger["bills"]
    assert bill["llm_type"] == "vision_analysis"
    assert bill["failed"] is True


async def test_the_spend_reaches_the_ledger_under_the_person_and_the_slot(
    ledger: dict[str, list[Any]],
) -> None:
    await run_assist(ToolAssist.MAIL_REPLY, PERSON, LANGUAGE, _answering)

    (bill,) = ledger["bills"]
    assert bill["user_id"] == PERSON
    assert bill["task_type"] == "tool_assist"
    assert bill["source"] == "user"
    assert bill["llm_type"] == "email_agent"
    assert bill["failed"] is False
    assert bill["tokens_in"] == 100


async def test_both_ceilings_are_asked_before_anything_is_read(
    ledger: dict[str, list[Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    reached: list[str] = []

    async def spent(user_id: object, *, layer: str) -> None:
        raise UsageLimitExceededError(limit_name="cycle_tokens", reason="spent")

    async def work(run: AssistRun) -> str:
        reached.append("work")
        return "never"

    monkeypatch.setattr(door, "enforce_usage_limit", spent)

    with pytest.raises(BaseAPIException) as refused:
        await run_assist(ToolAssist.MAIL_REPLY, PERSON, LANGUAGE, work)

    assert _code(refused) == "assist_quota"
    assert refused.value.status_code == 429
    assert reached == []
    assert ledger["bills"] == []


async def test_the_instance_s_pause_is_told_apart_and_says_how_long(
    ledger: dict[str, list[Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def paused(user_id: object, *, layer: str) -> None:
        raise UsageLimitExceededError(
            limit_name="instance",
            reason="paused",
            error_code=INSTANCE_BUDGET_EXHAUSTED_ERROR_CODE,
            retry_after_seconds=600,
        )

    monkeypatch.setattr(door, "enforce_usage_limit", paused)

    with pytest.raises(BaseAPIException) as refused:
        await run_assist(ToolAssist.MAIL_REPLY, PERSON, LANGUAGE, _answering)

    assert _code(refused) == "assist_paused"
    assert refused.value.headers == {"Retry-After": "600"}


async def test_a_ceiling_closed_during_the_work_is_the_same_refusal(
    ledger: dict[str, list[Any]],
) -> None:
    async def closed(run: AssistRun) -> str:
        raise UsageLimitExceededError(limit_name="cycle_tokens", reason="spent")

    with pytest.raises(BaseAPIException) as refused:
        await run_assist(ToolAssist.MAIL_REPLY, PERSON, LANGUAGE, closed)

    assert _code(refused) == "assist_quota"


async def test_a_failed_model_call_is_said_and_what_it_cost_is_billed(
    ledger: dict[str, list[Any]],
) -> None:
    async def broken(run: AssistRun) -> str:
        _spent(run)
        raise RuntimeError("the model said something unreadable")

    with pytest.raises(BaseAPIException) as refused:
        await run_assist(ToolAssist.MAIL_REPLY, PERSON, LANGUAGE, broken)

    assert _code(refused) == "assist_failed"
    assert refused.value.status_code == 502
    (bill,) = ledger["bills"]
    assert bill["failed"] is True


async def test_a_message_gone_stays_the_refusal_it_is(ledger: dict[str, list[Any]]) -> None:
    async def gone(run: AssistRun) -> str:
        async with run.reading():
            refuse(ITEM_GONE)

    with pytest.raises(BaseAPIException) as refused:
        await run_assist(ToolAssist.MAIL_REPLY, PERSON, LANGUAGE, gone)

    assert _code(refused) == "item_gone"
    (read,) = ledger["reads"]
    assert read["failed"] == ["mail"]


async def test_what_was_read_is_filed_on_the_run_it_was_read_for(
    ledger: dict[str, list[Any]],
) -> None:
    await run_assist(ToolAssist.MAIL_REPLY, PERSON, LANGUAGE, _answering)

    (read,) = ledger["reads"]
    (bill,) = ledger["bills"]
    assert read["surface"] == "tool_assist"
    assert read["opened"] == ["mail"]
    assert read["failed"] == []
    assert read["run_id"] == bill["run_id"]


async def test_a_result_already_held_files_nothing_and_says_it_cost_nothing_now(
    ledger: dict[str, list[Any]],
) -> None:
    async def held(run: AssistRun) -> str:
        return "the digest of yesterday"

    done = await run_assist(ToolAssist.MAIL_SUMMARY, PERSON, LANGUAGE, held)

    assert done.value == "the digest of yesterday"
    assert done.usage is None
    assert ledger["bills"] == []
    assert ledger["reads"] == []


async def test_words_of_the_person_s_own_read_no_source(ledger: dict[str, list[Any]]) -> None:
    async def rewriting(run: AssistRun) -> str:
        _spent(run)
        return "better words"

    await run_assist(ToolAssist.TEXT_REWRITE, PERSON, LANGUAGE, rewriting)

    assert ledger["reads"] == []
    assert len(ledger["bills"]) == 1


@pytest.mark.parametrize("cut_after_spending", [True, False])
async def test_leaving_mid_way_bills_what_was_spent_and_propagates(
    ledger: dict[str, list[Any]], cut_after_spending: bool
) -> None:
    started = asyncio.Event()

    async def slow(run: AssistRun) -> str:
        if cut_after_spending:
            _spent(run)
        started.set()
        await asyncio.sleep(60)
        return "never"

    task = asyncio.create_task(run_assist(ToolAssist.MAIL_REPLY, PERSON, LANGUAGE, slow))
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(ledger["bills"]) == (1 if cut_after_spending else 0)


def _counted(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(
        door, "count_assist", lambda assist, outcome: seen.append((assist, outcome))
    )
    return seen


@pytest.mark.parametrize(
    ("work", "outcome"),
    [
        (_answering, "ok"),
    ],
)
async def test_every_outcome_is_counted_under_closed_labels(
    ledger: dict[str, list[Any]],
    monkeypatch: pytest.MonkeyPatch,
    work: Callable[[AssistRun], Any],
    outcome: str,
) -> None:
    seen = _counted(monkeypatch)

    await run_assist(ToolAssist.MAIL_REPLY, PERSON, LANGUAGE, work)

    assert seen == [("mail_reply", outcome)]


async def test_a_refusal_is_counted_as_one(
    ledger: dict[str, list[Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _counted(monkeypatch)

    async def gone(run: AssistRun) -> str:
        refuse(ITEM_GONE)

    with pytest.raises(BaseAPIException):
        await run_assist(ToolAssist.MAIL_REPLY, PERSON, LANGUAGE, gone)

    assert seen == [("mail_reply", "refused")]


async def test_a_held_result_is_counted_apart(
    ledger: dict[str, list[Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _counted(monkeypatch)

    async def held(run: AssistRun) -> str:
        return "yesterday's"

    await run_assist(ToolAssist.MAIL_SUMMARY, PERSON, LANGUAGE, held)

    assert seen == [("mail_summary", "held")]
