"""The actual Tools read stays bound to the card's source after navigation admission."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from src.core.content_source import content_source_binding
from src.core.exceptions import BaseAPIException
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.email_attachments import EmailAttachmentContent
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.preferences.owner_defaults import OwnerContainer
from src.domains.users.models import User
from src.domains.workbench import clients
from src.domains.workbench.card_source import card_source_scope, expected_card_source
from src.domains.workbench.card_targets import (
    CARD_TOKEN_MAX_CHARS,
    CardTargetKind,
    CardToolTarget,
    SignedCardTarget,
    sign_card_target,
)
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.rate_limits import rate_limit_download, rate_limit_read, rate_limit_write
from src.domains.workbench.router import router
from src.domains.workbench.schemas.card_queries import FileDownloadQuery, MailAttachmentQuery
from tests.unit.domains.workbench.fakes import FakeRedis

pytestmark = pytest.mark.unit


@dataclass
class _Credentials:
    account_binding: str


@dataclass
class _State:
    binding: str = "original-source"
    provider: ConnectorType = ConnectorType.GOOGLE_CALENDAR
    reads: list[str] = field(default_factory=list)
    writes: list[str] = field(default_factory=list)
    opened: int = 0
    closed: int = 0
    fresh: list[bool] = field(default_factory=list)


@dataclass
class _Calendar:
    credentials: _Credentials
    state: _State

    async def get_event(self, event_id: str, calendar_id: str) -> dict[str, object]:
        self.state.reads.append(self.credentials.account_binding)
        return {
            "id": event_id,
            "summary": "Actual source event",
            "start": {"dateTime": "2027-11-08T09:00:00Z"},
            "end": {"dateTime": "2027-11-08T10:00:00Z"},
        }

    async def get_file_metadata(self, file_id: str, fields: list[str]) -> dict[str, object]:
        self.state.reads.append(self.credentials.account_binding)
        return {"id": file_id, "name": "source.txt", "mimeType": "text/plain", "size": "4"}

    async def get_file_content(
        self, file_id: str, *, max_size_bytes: int, known_size: int | None
    ) -> bytes:
        return b"safe"

    async def download_attachment(
        self, message_id: str, *, attachment_id: str | None, filename: str | None, max_bytes: int
    ) -> EmailAttachmentContent:
        self.state.reads.append(self.credentials.account_binding)
        return EmailAttachmentContent(data=b"safe", filename="source.txt", mime_type="text/plain")

    async def get_person(self, contact_id: str, *, use_cache: bool) -> dict[str, object]:
        self.state.reads.append(self.credentials.account_binding)
        return {"resourceName": contact_id, "names": [{"displayName": "Source Contact"}]}

    async def upload_file(
        self, name: str, data: bytes, mime_type: str, folder_id: str
    ) -> dict[str, object]:
        self.state.writes.append(self.credentials.account_binding)
        return {"id": "uploaded-a", "name": name, "mimeType": mime_type, "size": str(len(data))}


async def _handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, BaseAPIException)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@pytest.fixture
async def http(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, _State, str, UUID]]:
    state = _State()
    owner = uuid4()

    async def enabled(*args: object, **kwargs: object) -> bool:
        return True

    @asynccontextmanager
    async def provider(
        category: str,
        user_id: UUID,
        *,
        container: OwnerContainer | None = None,
        fresh: bool = False,
    ) -> AsyncIterator[ActiveClient]:
        assert category in {"calendar", "files", "email", "contacts"} and user_id == owner
        state.opened += 1
        state.fresh.append(fresh)
        try:
            yield ActiveClient(_Calendar(_Credentials(state.binding), state), state.provider, None)
        finally:
            state.closed += 1

    monkeypatch.setattr("src.domains.feature_switches.guard.is_capability_enabled", enabled)
    monkeypatch.setattr(clients, "open_active_client", provider)

    async def no_cache() -> None:
        return None

    monkeypatch.setattr("src.domains.workbench.downloads._cache", no_cache)
    cache = FakeRedis()

    async def redis() -> FakeRedis:
        return cache

    monkeypatch.setattr("src.domains.workbench.idempotency.get_redis_cache", redis)
    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(BaseAPIException, _handler)
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: User(id=owner)
    app.dependency_overrides[rate_limit_read] = lambda: None
    app.dependency_overrides[rate_limit_download] = lambda: None
    app.dependency_overrides[rate_limit_write] = lambda: None
    proof = SignedCardTarget(
        target=CardToolTarget(
            kind=CardTargetKind.EVENT, item_id="event-a", container_id="calendar-a"
        ),
        provider=state.provider,
        source_binding=content_source_binding(_Calendar(_Credentials(state.binding), state)),
    )
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        yield client, state, sign_card_target(proof, owner), owner


@pytest.mark.parametrize("change", ["account", "provider"])
async def test_changed_source_between_admission_and_real_get_is_refused_before_read(
    http: tuple[AsyncClient, _State, str, UUID], change: str
) -> None:
    client, state, token, _ = http
    admission = await client.post("/workbench/card-target", json={"token": token})
    assert admission.status_code == 200 and admission.json()["available"]
    if change == "account":
        state.binding = "replacement-source"
    else:
        state.provider = ConnectorType.MICROSOFT_CALENDAR
    response = await client.get(
        "/workbench/calendar/event",
        params={"calendar_id": "calendar-a", "event_id": "event-a"},
        headers={"X-LIA-Card-Source": token},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "card_source_changed"
    assert state.reads == []
    assert state.opened == state.closed == 2


async def test_same_source_reads_with_the_acquired_client_and_headerless_navigation_is_unconstrained(
    http: tuple[AsyncClient, _State, str, UUID],
) -> None:
    client, state, token, _ = http
    params = {"calendar_id": "calendar-a", "event_id": "event-a"}
    first = await client.get(
        "/workbench/calendar/event", params=params, headers={"X-LIA-Card-Source": token}
    )
    assert first.status_code == 200
    assert state.fresh == [True]
    state.binding = "replacement-source"
    manual = await client.get("/workbench/calendar/event", params=params)
    assert manual.status_code == 200
    assert state.reads == ["original-source", "replacement-source"]
    assert state.opened == state.closed == 2


@pytest.mark.parametrize("other_owner", [False, True])
async def test_invalid_or_other_owner_proof_never_opens_a_client(
    http: tuple[AsyncClient, _State, str, UUID], other_owner: bool
) -> None:
    client, state, token, _ = http
    if other_owner:
        proof = SignedCardTarget(
            target=CardToolTarget(
                kind=CardTargetKind.EVENT, item_id="event-a", container_id="calendar-a"
            ),
            provider=state.provider,
            source_binding=content_source_binding(_Calendar(_Credentials(state.binding), state)),
        )
        token = sign_card_target(proof, uuid4())
    else:
        token = "invalid"
    response = await client.get(
        "/workbench/calendar/event",
        params={"calendar_id": "calendar-a", "event_id": "event-a"},
        headers={"X-LIA-Card-Source": token},
    )
    assert response.status_code == 409 and state.opened == 0 and state.reads == []


async def test_source_expectation_is_local_to_each_concurrent_request(
    http: tuple[AsyncClient, _State, str, UUID],
) -> None:
    client, state, original_token, owner = http
    replacement = SignedCardTarget(
        target=CardToolTarget(
            kind=CardTargetKind.EVENT, item_id="event-a", container_id="calendar-a"
        ),
        provider=state.provider,
        source_binding=content_source_binding(_Calendar(_Credentials("replacement-source"), state)),
    )
    params = {"calendar_id": "calendar-a", "event_id": "event-a"}
    accepted, refused = await asyncio.gather(
        client.get(
            "/workbench/calendar/event",
            params=params,
            headers={"X-LIA-Card-Source": original_token},
        ),
        client.get(
            "/workbench/calendar/event",
            params=params,
            headers={"X-LIA-Card-Source": sign_card_target(replacement, owner)},
        ),
    )
    assert accepted.status_code == 200 and refused.status_code == 409
    assert state.reads == ["original-source"] and state.closed == 2
    manual = await client.get("/workbench/calendar/event", params=params)
    assert manual.status_code == 200 and state.fresh[-1] is False


async def test_a_different_family_does_not_reinterpret_the_source_expectation(
    http: tuple[AsyncClient, _State, str, UUID],
) -> None:
    client, state, _, owner = http
    mail = SignedCardTarget(
        target=CardToolTarget(kind=CardTargetKind.EMAIL, item_id="mail-id"),
        provider=ConnectorType.GOOGLE_GMAIL,
        source_binding=content_source_binding(_Calendar(_Credentials("mail-source"), state)),
    )
    response = await client.get(
        "/workbench/calendar/event",
        params={"calendar_id": "calendar-a", "event_id": "event-a"},
        headers={"X-LIA-Card-Source": sign_card_target(mail, owner)},
    )
    assert response.status_code == 200
    assert state.fresh == [False] and state.reads == ["original-source"]


async def test_oversized_source_header_is_bounded_before_client_acquisition(
    http: tuple[AsyncClient, _State, str, UUID],
) -> None:
    client, state, _, _ = http
    response = await client.get(
        "/workbench/calendar/event",
        params={"calendar_id": "calendar-a", "event_id": "event-a"},
        headers={"X-LIA-Card-Source": "x" * (CARD_TOKEN_MAX_CHARS + 1)},
    )
    assert response.status_code == 422 and state.opened == 0


async def test_cancelled_dependency_resets_its_source_context(
    http: tuple[AsyncClient, _State, str, UUID],
) -> None:
    _, _, token, owner = http
    dependency = card_source_scope(User(id=owner), source=token)
    await anext(dependency)
    assert expected_card_source(WorkbenchTool.CALENDAR, owner) is not None
    with pytest.raises(asyncio.CancelledError):
        await dependency.athrow(asyncio.CancelledError())
    assert expected_card_source(WorkbenchTool.CALENDAR, owner) is None


@pytest.mark.parametrize(
    ("kind", "provider", "path", "params"),
    [
        (
            CardTargetKind.FILE,
            ConnectorType.GOOGLE_DRIVE,
            "/workbench/files/download",
            {"id": "file-a"},
        ),
        (
            CardTargetKind.EMAIL,
            ConnectorType.GOOGLE_GMAIL,
            "/workbench/mail/attachment",
            {"message_id": "mail-a", "filename": "source.txt"},
        ),
        (
            CardTargetKind.CONTACT,
            ConnectorType.GOOGLE_CONTACTS,
            "/workbench/contacts/export",
            {"id": "people/contact-a"},
        ),
    ],
)
@pytest.mark.parametrize("changed", [False, True])
@pytest.mark.parametrize("also_header", [False, True])
async def test_direct_download_checks_query_proof_on_the_acquired_client(
    http: tuple[AsyncClient, _State, str, UUID],
    kind: CardTargetKind,
    provider: ConnectorType,
    path: str,
    params: dict[str, str],
    changed: bool,
    also_header: bool,
) -> None:
    client, state, _, owner = http
    state.provider = provider
    proof = SignedCardTarget(
        target=CardToolTarget(kind=kind, item_id="item-a"),
        provider=provider,
        source_binding=content_source_binding(_Calendar(_Credentials(state.binding), state)),
    )
    token = sign_card_target(proof, owner)
    if changed:
        state.binding = "replacement-source"
    response = await client.get(
        path,
        params={**params, "card_source": token},
        headers={"X-LIA-Card-Source": token} if also_header else {},
    )
    assert response.status_code == (409 if changed else 200), response.text
    assert state.reads == ([] if changed else ["original-source"])
    assert state.opened == state.closed == 1 and state.fresh == [True]
    if not changed:
        assert response.headers["content-disposition"].startswith("attachment;")
        assert token not in response.text


async def test_conflicting_header_and_query_proofs_are_refused_before_any_client(
    http: tuple[AsyncClient, _State, str, UUID],
) -> None:
    client, state, token, owner = http
    other = SignedCardTarget(
        target=CardToolTarget(
            kind=CardTargetKind.EVENT, item_id="event-a", container_id="calendar-a"
        ),
        provider=state.provider,
        source_binding=content_source_binding(_Calendar(_Credentials("replacement-source"), state)),
    )
    response = await client.get(
        "/workbench/calendar/event",
        params={
            "calendar_id": "calendar-a",
            "event_id": "event-a",
            "card_source": sign_card_target(other, owner),
        },
        headers={"X-LIA-Card-Source": token},
    )
    assert response.status_code == 409
    assert state.opened == 0 and state.reads == []


@pytest.mark.parametrize(
    "token",
    ["", "invalid", "x" * (CARD_TOKEN_MAX_CHARS + 1)],
    ids=["empty", "invalid", "oversized"],
)
async def test_invalid_query_proof_is_refused_before_any_client(
    http: tuple[AsyncClient, _State, str, UUID], token: str
) -> None:
    client, state, _, _ = http
    response = await client.get(
        "/workbench/calendar/event",
        params={"calendar_id": "calendar-a", "event_id": "event-a", "card_source": token},
    )
    assert response.status_code == (422 if len(token) > CARD_TOKEN_MAX_CHARS else 409)
    assert state.opened == 0 and state.reads == []


@pytest.mark.parametrize("transport", ["header", "query", "both"])
@pytest.mark.parametrize("changed", [False, True])
async def test_multipart_upload_checks_source_before_any_provider_write(
    http: tuple[AsyncClient, _State, str, UUID], transport: str, changed: bool
) -> None:
    client, state, _, owner = http
    state.provider = ConnectorType.GOOGLE_DRIVE
    proof = SignedCardTarget(
        target=CardToolTarget(kind=CardTargetKind.FILE, item_id="file-a"),
        provider=state.provider,
        source_binding=content_source_binding(_Calendar(_Credentials(state.binding), state)),
    )
    token = sign_card_target(proof, owner)
    if changed:
        state.binding = "replacement-source"
    response = await client.post(
        "/workbench/files/upload",
        params={"card_source": token} if transport in {"query", "both"} else {},
        headers={"X-LIA-Card-Source": token} if transport in {"header", "both"} else {},
        files={"file": ("source.txt", b"safe", "text/plain")},
        data={"name": "source.txt", "idempotency_key": str(uuid4())},
    )
    assert response.status_code == (409 if changed else 201), response.text
    assert state.writes == ([] if changed else ["original-source"])
    assert state.opened == state.closed == 1 and state.fresh == [True]


@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("/workbench/files/download", {"id": "file-a"}),
        ("/workbench/mail/attachment", {"message_id": "mail-a", "filename": "source.txt"}),
    ],
)
async def test_transport_proof_does_not_weaken_strict_download_queries(
    http: tuple[AsyncClient, _State, str, UUID], path: str, params: dict[str, str]
) -> None:
    client, state, token, _ = http
    response = await client.get(
        path, params={**params, "card_source": token, "unexpected": "value"}
    )
    assert response.status_code == 422
    assert state.opened == 0 and state.reads == []


@pytest.mark.parametrize(
    "query",
    [
        FileDownloadQuery(id="file-a", card_source="transport-proof"),
        MailAttachmentQuery(
            message_id="mail-a", filename="source.txt", card_source="transport-proof"
        ),
    ],
)
def test_transport_proof_never_enters_the_provider_query(
    query: FileDownloadQuery | MailAttachmentQuery,
) -> None:
    assert "card_source" not in query.model_dump()
    assert "transport-proof" not in repr(query)
    assert query.provider_query().model_dump() == query.model_dump()
    assert not hasattr(query.provider_query(), "card_source")
