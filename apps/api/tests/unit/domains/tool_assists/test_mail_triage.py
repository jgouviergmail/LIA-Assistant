"""What the messages on screen weigh (ADR-372, lot 9).

A digest already held opens nothing and costs nothing; the others are read, at most so many at a
time, and condensed in one go. A message that could not be read keeps its place and is counted; a
page nothing could be read of is a refusal, and a closed ceiling says so.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.runnables import RunnableConfig

from src.core.exceptions import BaseAPIException
from src.domains.agents.emails.digest import DIGEST_FIELDS, DIGEST_STATUS_FIELD, EmailDigest
from src.domains.connectors.models import ConnectorType
from src.domains.tool_assists import mail_triage
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.mail_triage import triage_messages
from src.domains.workbench.errors import ITEM_GONE, refuse

pytestmark = pytest.mark.unit

HIGH = EmailDigest(gist="G", importance="high", category="work")


class _Client:
    """The provider: counts how many reads run at once."""

    def __init__(self, gone: frozenset[str] = frozenset()) -> None:
        self.gone = gone
        self.reads: list[str] = []
        self.running = 0
        self.widest = 0

    async def get_message(self, message_id: str, *, use_cache: bool) -> dict[str, Any]:
        self.running += 1
        self.widest = max(self.widest, self.running)
        await asyncio.sleep(0)
        self.running -= 1
        self.reads.append(message_id)
        if message_id in self.gone:
            refuse(ITEM_GONE)
        return {"id": message_id, "body": "Words"}


def _run() -> AssistRun:
    return AssistRun(
        user_id=uuid4(), language="fr", config=RunnableConfig(callbacks=[]), sections=("mail",)
    )


def _code(refused: pytest.ExceptionInfo[BaseAPIException]) -> str:
    detail = refused.value.detail
    assert isinstance(detail, dict)
    return str(detail["code"])


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> _Client:
    opened_client = _Client()

    @asynccontextmanager
    async def opened(tool: object, user_id: object) -> AsyncIterator[Any]:
        class _Open:
            client = opened_client
            connector_type = ConnectorType.GOOGLE_GMAIL

        yield _Open()

    monkeypatch.setattr(mail_triage, "open_tool_client", opened)
    return opened_client


@pytest.fixture
def cache(monkeypatch: pytest.MonkeyPatch) -> dict[str, EmailDigest]:
    """The digests already held."""
    held: dict[str, EmailDigest] = {}

    async def read(
        user_id: str, provider: str, message_id: str, language: str
    ) -> EmailDigest | None:
        return held.get(message_id)

    monkeypatch.setattr(mail_triage, "read_cached_digest", read)
    return held


@pytest.fixture
def digests(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The assistant's digest: every message condensed, unless told otherwise."""
    state: dict[str, Any] = {"status": "computed", "config": None, "seen": []}

    class _Service:
        async def digest_many(
            self,
            *,
            user_id: str,
            emails: list[dict[str, Any]],
            language: str,
            config: RunnableConfig,
        ) -> None:
            state["config"] = config
            state["seen"] = [email["id"] for email in emails]
            for email in emails:
                email[DIGEST_STATUS_FIELD] = state["status"]
                if state["status"] == "computed":
                    email.update({field: getattr(HIGH, field) for field in DIGEST_FIELDS})

    monkeypatch.setattr(mail_triage, "EmailDigestService", _Service)
    return state


async def test_what_is_held_opens_nothing_and_asks_nothing(
    client: _Client, cache: dict[str, EmailDigest], digests: dict[str, Any]
) -> None:
    cache["m1"] = HIGH
    run = _run()

    triage = await triage_messages(run, ["m1"])

    assert [(item.id, item.importance, item.category) for item in triage.items] == [
        ("m1", "high", "work")
    ]
    assert triage.skipped == 0
    assert client.reads == []
    assert run.opened is False
    assert digests["seen"] == []


async def test_only_what_is_missing_is_read_and_condensed_on_the_run(
    client: _Client, cache: dict[str, EmailDigest], digests: dict[str, Any]
) -> None:
    cache["m1"] = HIGH
    run = _run()

    triage = await triage_messages(run, ["m1", "m2"])

    assert client.reads == ["m2"]
    assert digests["seen"] == ["m2"]
    assert digests["config"] is run.config
    assert {item.id for item in triage.items} == {"m1", "m2"}
    assert run.opened is True


async def test_a_page_is_read_within_its_width(
    client: _Client,
    cache: dict[str, EmailDigest],
    digests: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mail_triage, "TOOL_ASSIST_TRIAGE_READS_MAX", 2)

    await triage_messages(_run(), [f"m{index}" for index in range(7)])

    assert client.widest <= 2
    assert len(client.reads) == 7


async def test_a_message_gone_since_the_listing_keeps_its_place_and_is_counted(
    client: _Client, cache: dict[str, EmailDigest], digests: dict[str, Any]
) -> None:
    client.gone = frozenset({"m2"})
    run = _run()

    triage = await triage_messages(run, ["m1", "m2"])

    assert [item.id for item in triage.items] == ["m1"]
    assert triage.skipped == 1
    assert run.failed is False


async def test_a_message_named_twice_is_read_and_counted_once(
    client: _Client, cache: dict[str, EmailDigest], digests: dict[str, Any]
) -> None:
    triage = await triage_messages(_run(), ["m1", "m1"])

    assert client.reads == ["m1"]
    assert triage.skipped == 0


async def test_a_page_nothing_could_be_read_of_stays_a_failed_read(
    client: _Client, cache: dict[str, EmailDigest], digests: dict[str, Any]
) -> None:
    client.gone = frozenset({"m1"})
    run = _run()

    with pytest.raises(BaseAPIException):
        await triage_messages(run, ["m1"])

    assert run.failed is True


async def test_a_message_the_digest_could_not_weigh_is_counted_too(
    client: _Client, cache: dict[str, EmailDigest], digests: dict[str, Any]
) -> None:
    cache["m1"] = HIGH
    digests["status"] = "failed"

    triage = await triage_messages(_run(), ["m1", "m2"])

    assert [item.id for item in triage.items] == ["m1"]
    assert triage.skipped == 1


@pytest.mark.parametrize(
    ("status", "code"),
    [("skipped_quota", "assist_quota"), ("failed", "assist_failed")],
)
async def test_a_page_nothing_could_be_read_of_is_a_refusal(
    client: _Client,
    cache: dict[str, EmailDigest],
    digests: dict[str, Any],
    status: str,
    code: str,
) -> None:
    digests["status"] = status

    with pytest.raises(BaseAPIException) as refused:
        await triage_messages(_run(), ["m1"])

    assert _code(refused) == code
