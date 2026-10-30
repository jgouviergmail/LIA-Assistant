"""One confirmation creates one event, whichever provider lost its answer (S1).

The oracle is the 2026-10-28 simulation: the real ``GoogleCalendarClient.create_event``
against a server that creates the event and then answers after the read timeout made
three events and reported a failure. Each provider now creates under an identity
derived from the effect's key (ADR-263) and resends it — Google an event ``id`` it
refuses once held (409, measured live on 2026-10-29) and the client reads back,
Microsoft a ``transactionId`` Graph deduplicates on, Apple a ``uid`` fixed before its
retry loop — so the same scenario ends with one event and a success on all three.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.core.exceptions import ConnectorAPIError, ExternalServiceError
from src.domains.connectors.clients import retry_policy
from src.domains.connectors.clients.apple_calendar_client import AppleCalendarClient
from src.domains.connectors.clients.google_calendar_client import GoogleCalendarClient
from src.domains.connectors.clients.microsoft_calendar_client import MicrosoftCalendarClient
from src.domains.connectors.clients.retry_policy import provider_idempotency_id
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

_EVENT = {
    "summary": "Dentist",
    "start_datetime": "2026-11-02T10:00:00",
    "end_datetime": "2026-11-02T11:00:00",
    "timezone": "UTC",
}
_KEY = "draft:0123456789abcdef"


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="test-token",
        refresh_token="test-refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class _GoogleCalendar:
    """Creates the event, then loses the first answer; serves an event by its id."""

    def __init__(self, *, lose_creation: bool = True) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.posts: list[dict[str, Any]] = []
        self.lose_creation = lose_creation

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST":
            body = httpx.Response(200, content=request.content).json()
            self.posts.append(body)
            if self.lose_creation:
                self.events[body["id"]] = {**body, "status": "confirmed"}
                raise httpx.ReadTimeout("created, answer lost", request=request)
            return httpx.Response(200, json={**body, "status": "confirmed"})
        event_id = path.rsplit("/", 1)[-1]
        if event_id in self.events:
            return httpx.Response(200, json=self.events[event_id])
        return httpx.Response(404, json={"error": {"code": 404}})


class _Forgetful(dict):
    """An event store that drops what it is given (the create never committed)."""

    def __setitem__(self, key: str, value: Any) -> None:
        return None


class _Graph:
    """Creates the event, loses the first answer, deduplicates on ``transactionId``."""

    def __init__(self) -> None:
        self.events: dict[str, dict[str, Any]] = {}
        self.posts: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = httpx.Response(200, content=request.content).json()
        self.posts.append(body)
        existing = self.events.get(body.get("transactionId", ""))
        if existing is not None:
            return httpx.Response(201, json=existing)
        event = {**body, "id": f"graph-{len(self.events) + 1}"}
        if "transactionId" in body:
            self.events[body["transactionId"]] = event
        else:
            self.events[event["id"]] = event
        raise httpx.ReadTimeout("created, answer lost", request=request)


class _CalDav:
    """A calendar collection: a save stores under its uid, the first answer is lost."""

    def __init__(self) -> None:
        self.saves: list[dict[str, Any]] = []
        self.objects: dict[str, dict[str, Any]] = {}

    async def save_event(self, **kwargs: Any) -> Any:
        self.saves.append(kwargs)
        uid = kwargs.get("uid") or f"server-minted-{len(self.saves)}"
        self.objects[uid] = kwargs
        if len(self.saves) == 1:
            raise TimeoutError("stored, answer lost")
        saved = MagicMock()
        saved.vobject_instance = None
        saved.uid = uid
        return saved


async def _create_on_google(server: _GoogleCalendar, **options: Any) -> dict[str, Any]:
    client = GoogleCalendarClient(uuid4(), _credentials(), MagicMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(server)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await client.create_event(**_EVENT, **options)


async def _create_on_microsoft(server: _Graph, **options: Any) -> dict[str, Any]:
    client = MicrosoftCalendarClient(uuid4(), _credentials(), MagicMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(server)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await client.create_event(**_EVENT, **options)


async def _create_on_apple(server: _CalDav, **options: Any) -> dict[str, Any]:
    client = AppleCalendarClient(uuid4(), MagicMock(), MagicMock())
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    with (
        patch.object(client, "_rate_limit", AsyncMock()),
        patch.object(client, "_get_circuit_breaker", return_value=breaker),
        patch.object(client, "_get_calendar", AsyncMock(return_value=server)),
        patch(
            "src.domains.connectors.clients.apple_calendar_client.normalize_vevent",
            side_effect=lambda event: {"id": event.uid},
        ),
        patch("asyncio.sleep", AsyncMock()),
    ):
        return await client.create_event(**_EVENT, **options)


class _GoogleInFlight:
    """What Google did on 2026-10-29 (live measurement on a real calendar).

    The create's answer is lost while Google is still writing the event: a read made
    at once answers 404, and the event is there three seconds later. Google refuses an
    id it already holds — live or deleted — with a 409.
    """

    def __init__(self, *, visible_after_reads: int = 2, keep_first_post: bool = True) -> None:
        self.posts: list[dict[str, Any]] = []
        self.reads = 0
        self.events: dict[str, dict[str, Any]] = {}
        self.visible_after_reads = visible_after_reads
        self.keep_first_post = keep_first_post

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            body = httpx.Response(200, content=request.content).json()
            self.posts.append(body)
            if body["id"] in self.events:
                return httpx.Response(409, json={"error": {"code": 409, "reason": "duplicate"}})
            if len(self.posts) == 1:
                if self.keep_first_post:
                    self.events[body["id"]] = {**body, "status": "confirmed"}
                raise httpx.ReadTimeout("answer lost while writing", request=request)
            self.events[body["id"]] = {**body, "status": "confirmed"}
            self.visible_after_reads = 0
            return httpx.Response(200, json={**body, "status": "confirmed"})
        self.reads += 1
        event_id = request.url.path.rsplit("/", 1)[-1]
        if event_id in self.events and self.reads > self.visible_after_reads:
            return httpx.Response(200, json=self.events[event_id])
        return httpx.Response(404, json={"error": {"code": 404}})


async def test_google_create_read_timeout_reconciled_by_get() -> None:
    """The lost create is sent again under its own id: Google refuses the id it holds,
    and the event is read back — one event, a success."""
    server = _GoogleCalendar()

    created = await _create_on_google(server, idempotency_key=_KEY)

    assert {post["id"] for post in server.posts} == {provider_idempotency_id(_KEY, "google")}
    assert len(server.events) == 1
    assert created["id"] == provider_idempotency_id(_KEY, "google")


async def test_a_google_create_still_being_written_when_read_is_read_again() -> None:
    """Measured live: the read made at once answers 404 while the event is being
    written; it is read again before the act is declared failed."""
    server = _GoogleInFlight(visible_after_reads=2)

    created = await _create_on_google(server, idempotency_key=_KEY)

    assert created["id"] == provider_idempotency_id(_KEY, "google")
    assert len(server.events) == 1
    assert server.reads == 3


async def test_a_google_create_lost_before_google_kept_it_is_made_by_its_resend() -> None:
    """Graph and CalDAV resend a create that carries its identity; Google refuses an id
    it holds (measured), so its create is resent too, and the act is made."""
    server = _GoogleInFlight(keep_first_post=False)

    created = await _create_on_google(server, idempotency_key=_KEY)

    assert [post["id"] for post in server.posts] == [provider_idempotency_id(_KEY, "google")] * 2
    assert len(server.events) == 1
    assert created["id"] == provider_idempotency_id(_KEY, "google")


async def test_a_google_create_the_provider_never_kept_stays_a_failure() -> None:
    """Every answer lost and nothing ever readable: nothing proves the act, the failure
    stands — after the request loop's attempts and the bounded reads, never more."""
    server = _GoogleCalendar()
    server.events = _Forgetful()

    with pytest.raises(ExternalServiceError) as raised:
        await _create_on_google(server, idempotency_key=_KEY)

    assert isinstance(raised.value.__cause__, httpx.ReadTimeout)
    assert [post["id"] for post in server.posts] == [
        provider_idempotency_id(_KEY, "google")
    ] * retry_policy.CONNECTOR_REQUEST_ATTEMPTS


async def test_a_google_create_read_back_is_bounded() -> None:
    """An event never readable is read CREATE_SETTLE_READS times, then the failure stands."""
    server = _GoogleInFlight(visible_after_reads=10**6)

    with pytest.raises(ConnectorAPIError) as raised:
        await _create_on_google(server, idempotency_key=_KEY)

    assert raised.value.status_code == 409
    assert server.reads == retry_policy.CREATE_SETTLE_READS


async def test_a_deleted_act_sent_again_fails_on_its_first_read() -> None:
    """Measured live: Google refuses a deleted event's id too, and reads it back
    « cancelled » — a final answer: the act failed, nothing is read again."""
    server = _GoogleInFlight()
    event_id = provider_idempotency_id(_KEY, "google")
    server.events[event_id] = {"id": event_id, "status": "cancelled"}
    server.visible_after_reads = 0

    with pytest.raises(ConnectorAPIError) as raised:
        await _create_on_google(server, idempotency_key=_KEY)

    assert raised.value.status_code == 409
    assert server.reads == 1


class _GoogleCreatesThenFails(_GoogleCalendar):
    """Creates the event, answers 503; the resent create meets the id it already used."""

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method != "POST":
            return super().__call__(request)
        body = httpx.Response(200, content=request.content).json()
        self.posts.append(body)
        if body["id"] in self.events:
            return httpx.Response(409, json={"error": {"code": 409, "reason": "duplicate"}})
        self.events[body["id"]] = {**body, "status": "confirmed"}
        return httpx.Response(503, json={"error": {"code": 503}})


async def test_a_google_create_meeting_its_own_id_is_the_same_act() -> None:
    """A 5xx is resent as it always was; Google may have created the event first, and
    the resend then meets the id this very create chose — the act exists: a success."""
    server = _GoogleCreatesThenFails()

    created = await _create_on_google(server, idempotency_key=_KEY)

    assert len(server.posts) == 2
    assert len(server.events) == 1
    assert created["id"] == provider_idempotency_id(_KEY, "google")


async def test_google_create_sends_the_id_derived_from_the_key() -> None:
    server = _GoogleCalendar(lose_creation=False)

    await _create_on_google(server, idempotency_key=_KEY)
    await _create_on_google(server)

    keyed, unkeyed = server.posts
    assert keyed["id"] == provider_idempotency_id(_KEY, "google")
    assert unkeyed["id"] != keyed["id"]


async def test_graph_create_carries_transaction_id() -> None:
    server = _Graph()

    created = await _create_on_microsoft(server, idempotency_key=_KEY)

    assert [post["transactionId"] for post in server.posts] == [
        provider_idempotency_id(_KEY, "microsoft")
    ] * 2
    assert len(server.events) == 1
    assert created["id"] == "graph-1"


async def test_apple_create_resend_keeps_uid() -> None:
    server = _CalDav()

    created = await _create_on_apple(server, idempotency_key=_KEY)

    uids = [save["uid"] for save in server.saves]
    assert uids == [provider_idempotency_id(_KEY, "apple")] * 2
    assert len(server.objects) == 1
    assert created["id"] == uids[0]


async def test_an_apple_create_without_a_key_still_keeps_one_uid_across_its_resends() -> None:
    server = _CalDav()

    await _create_on_apple(server)

    first, second = (save["uid"] for save in server.saves)
    assert first == second
    assert len(server.objects) == 1


@pytest.mark.parametrize("provider", ["google", "microsoft", "apple"])
async def test_one_lost_answer_is_one_event_and_a_success_on_every_provider(provider) -> None:
    if provider == "google":
        server: Any = _GoogleCalendar()
        created = await _create_on_google(server, idempotency_key=_KEY)
        stored = server.events
    elif provider == "microsoft":
        server = _Graph()
        created = await _create_on_microsoft(server, idempotency_key=_KEY)
        stored = server.events
    else:
        server = _CalDav()
        created = await _create_on_apple(server, idempotency_key=_KEY)
        stored = server.objects

    assert len(stored) == 1
    assert created.get("id")


async def test_a_create_the_provider_refused_is_never_reconciled() -> None:
    """A 400 is an answer: nothing was created, nothing is looked up."""
    requests: list[httpx.Request] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(400, json={"error": {"code": 400}})

    with pytest.raises(ConnectorAPIError) as raised:
        await _create_on_google(refuse, idempotency_key=_KEY)  # type: ignore[arg-type]

    assert raised.value.status_code == 400
    assert [request.method for request in requests] == ["POST"]


class _KeptThenUnavailable(_GoogleInFlight):
    """The first create is kept and its answer lost; every resend meets a status."""

    def __init__(self, status: int) -> None:
        super().__init__(visible_after_reads=0)
        self.status = status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and self.posts:
            self.posts.append({})
            return httpx.Response(self.status, json={"error": {"code": self.status}})
        return super().__call__(request)


@pytest.mark.parametrize("status", [503, 429])
async def test_a_kept_create_whose_resends_ran_out_is_read_back(status: int) -> None:
    """Third fresh review: the first answer lost, the resends spent on a 5xx or a 429 —
    the loop raised « max retries » with no cause, nothing was read back, the act was
    reported failed while Google kept the event, and the next attempt made a second."""
    server = _KeptThenUnavailable(status)

    created = await _create_on_google(server, idempotency_key=_KEY)

    assert created["id"] == provider_idempotency_id(_KEY, "google")
    assert len(server.events) == 1
    assert len(server.posts) == retry_policy.CONNECTOR_REQUEST_ATTEMPTS


class _ReadBackFails(_GoogleCalendar):
    """The create is kept and its answer lost; the read back is refused or unanswered."""

    def __init__(self, read_status: int | None) -> None:
        super().__init__()
        self.read_status = read_status
        self.reads = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return super().__call__(request)
        self.reads += 1
        if self.read_status is None:
            raise httpx.ReadTimeout("read back lost", request=request)
        return httpx.Response(self.read_status, json={"error": {"code": self.read_status}})


@pytest.mark.parametrize(
    ("read_status", "cause"),
    [(403, ConnectorAPIError), (None, ExternalServiceError)],
    ids=["refused", "unanswered"],
)
async def test_a_read_back_that_fails_leaves_the_creates_failure_standing(
    read_status: int | None, cause: type[Exception]
) -> None:
    """Only a found event proves the act and only « not found » is read again: a read
    back refused or unanswered leaves the create's own failure, the read as its cause."""
    server = _ReadBackFails(read_status)

    with pytest.raises(ExternalServiceError) as raised:
        await _create_on_google(server, idempotency_key=_KEY)

    assert isinstance(raised.value.__cause__, cause)
    assert len(server.events) == 1  # kept by Google, unproven here: never created twice


async def test_a_create_refused_with_a_4xx_is_never_read_back() -> None:
    """A 4xx other than 409 is an answer: nothing was kept, nothing is read."""
    reads: list[str] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            reads.append(request.url.path)
        return httpx.Response(403, json={"error": {"code": 403}})

    with pytest.raises(ConnectorAPIError):
        await _create_on_google(refuse, idempotency_key=_KEY)  # type: ignore[arg-type]

    assert reads == []
