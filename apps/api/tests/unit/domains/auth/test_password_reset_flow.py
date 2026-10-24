"""The password-reset flow at the service boundary, with real signed tokens (ADR-363).

The repository and the session store are the doubles; the token is minted and
verified by the real code, because the binding is what these tests are about.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security.utils import (
    create_password_reset_token,
    get_password_hash,
    reset_token_matches_account,
    verify_token,
)
from src.domains.auth.service import AuthService
from src.domains.users.models import User
from src.infrastructure.database.registry import import_all_models
from tests.fixtures.factories import UserFactory
from tests.unit.domains.auth.reset_budget_fakes import (
    SlidingWindowLimiter,
    install_reset_budget,
)

import_all_models()

pytestmark = pytest.mark.unit

_NEW_PASSWORD = "NewSecurePass123!!"


@pytest.fixture(autouse=True)
def _instance_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "secret_key", "test-secret-test-secret-test-secret-test-secret")
    monkeypatch.setattr(settings, "algorithm", "HS256")


@pytest.fixture(autouse=True)
def _session_store() -> Iterator[AsyncMock]:
    store = AsyncMock()
    with (
        patch("src.domains.auth.service.get_redis_session", AsyncMock()),
        patch("src.domains.auth.service.SessionStore", return_value=store),
    ):
        yield store


@pytest.fixture(autouse=True)
def budget(monkeypatch: pytest.MonkeyPatch) -> SlidingWindowLimiter:
    return install_reset_budget(monkeypatch)


@pytest.fixture
def repository() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(repository: AsyncMock) -> AuthService:
    auth = AuthService(AsyncMock(spec=AsyncSession))
    auth.repository = repository
    return auth


@pytest.fixture
def account() -> User:
    user = UserFactory.create(email="person@example.com", password="TestPass123!!")
    user.id = uuid4()
    user.created_at = user.updated_at = datetime.now(UTC)
    user.is_superuser = False
    return user


def _link_for(user: User) -> str:
    return create_password_reset_token(
        user.email, user_id=user.id, hashed_password=user.hashed_password
    )


async def test_a_link_issued_for_the_account_resets_its_password(
    service: AuthService, repository: AsyncMock, account: User
) -> None:
    repository.get_by_email.return_value = account
    repository.update_password.return_value = account

    await service.reset_password(_link_for(account), _NEW_PASSWORD)

    repository.update_password.assert_awaited_once()


async def test_a_link_is_refused_once_the_password_changed(
    service: AuthService, repository: AsyncMock, account: User
) -> None:
    link = _link_for(account)
    account.hashed_password = get_password_hash("AnotherPass123!!")
    repository.get_by_email.return_value = account

    with pytest.raises(HTTPException) as refused:
        await service.reset_password(link, _NEW_PASSWORD)

    assert refused.value.status_code == 401
    repository.update_password.assert_not_awaited()


async def test_a_link_of_an_account_recreated_at_the_same_address_is_refused(
    service: AuthService, repository: AsyncMock, account: User
) -> None:
    link_of_the_account_that_left = create_password_reset_token(
        account.email, user_id=uuid4(), hashed_password=account.hashed_password
    )
    repository.get_by_email.return_value = account

    with pytest.raises(HTTPException) as refused:
        await service.reset_password(link_of_the_account_that_left, _NEW_PASSWORD)

    assert refused.value.status_code == 401
    repository.update_password.assert_not_awaited()


async def test_a_link_minted_before_the_binding_is_refused(
    service: AuthService, repository: AsyncMock, account: User
) -> None:
    now = datetime.now(UTC)
    minted_before = jwt.encode(
        {
            "sub": account.email,
            "type": "password_reset",
            "exp": now + timedelta(hours=1),
            "iat": now,
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    repository.get_by_email.return_value = account

    with pytest.raises(HTTPException) as refused:
        await service.reset_password(minted_before, _NEW_PASSWORD)

    assert refused.value.status_code == 401
    repository.update_password.assert_not_awaited()


async def test_the_link_a_request_sends_is_bound_to_the_account(
    service: AuthService, repository: AsyncMock, account: User
) -> None:
    repository.get_by_email.return_value = account

    with patch.object(service, "_send_password_reset_email", AsyncMock(return_value=True)) as send:
        await service.request_password_reset(account.email)

    assert send.await_args is not None
    payload = verify_token(send.await_args.kwargs["token"])
    assert payload is not None
    assert reset_token_matches_account(
        payload, user_id=account.id, email=account.email, hashed_password=account.hashed_password
    )


# ---------------------------------------------------------------------------
# B — which e-mail leaves, and which link may still be used (ADR-363)
# ---------------------------------------------------------------------------


@pytest.fixture
def mail(service: AuthService) -> Iterator[tuple[AsyncMock, AsyncMock]]:
    """The two e-mails a request can send: (the link, the notice)."""
    with (
        patch.object(service, "_send_password_reset_email", AsyncMock(return_value=True)) as link,
        patch.object(
            service, "_send_password_reset_notice", AsyncMock(return_value=True)
        ) as notice,
    ):
        yield link, notice


def _passwordless(user: User, *, provider: str | None) -> User:
    user.hashed_password = None
    user.oauth_provider = provider
    return user


async def test_a_google_account_without_password_is_sent_the_notice_not_a_link(
    service: AuthService,
    repository: AsyncMock,
    account: User,
    mail: tuple[AsyncMock, AsyncMock],
) -> None:
    link, notice = mail
    repository.get_by_email.return_value = _passwordless(account, provider="google")

    await service.request_password_reset(account.email)

    link.assert_not_awaited()
    notice.assert_awaited_once_with(account)


async def test_a_passkeys_only_account_keeps_its_link(
    service: AuthService,
    repository: AsyncMock,
    account: User,
    mail: tuple[AsyncMock, AsyncMock],
) -> None:
    link, notice = mail
    repository.get_by_email.return_value = _passwordless(account, provider=None)

    await service.request_password_reset(account.email)

    link.assert_awaited_once()
    notice.assert_not_awaited()


@pytest.mark.parametrize("state", ["superuser", "deleted"])
async def test_no_e_mail_leaves_for_an_administrator_or_a_deleted_account(
    service: AuthService,
    repository: AsyncMock,
    account: User,
    mail: tuple[AsyncMock, AsyncMock],
    state: str,
) -> None:
    link, notice = mail
    if state == "superuser":
        account.is_superuser = True
    else:
        account.deleted_at = datetime.now(UTC)
    repository.get_by_email.return_value = account

    await service.request_password_reset(account.email)

    link.assert_not_awaited()
    notice.assert_not_awaited()


@pytest.mark.parametrize("state", ["superuser", "deleted", "google-without-password"])
async def test_a_link_of_an_account_no_longer_eligible_is_refused(
    service: AuthService, repository: AsyncMock, account: User, state: str
) -> None:
    if state == "google-without-password":
        _passwordless(account, provider="google")
    link = _link_for(account)
    if state == "superuser":
        account.is_superuser = True
    elif state == "deleted":
        account.deleted_at = datetime.now(UTC)
    repository.get_by_email.return_value = account

    with pytest.raises(HTTPException) as refused:
        await service.reset_password(link, _NEW_PASSWORD)

    assert refused.value.status_code == 401
    repository.update_password.assert_not_awaited()


# ---------------------------------------------------------------------------
# A — the account's budget at the service (ADR-363)
# ---------------------------------------------------------------------------


async def test_a_request_past_the_budget_sends_nothing(
    service: AuthService,
    repository: AsyncMock,
    account: User,
    mail: tuple[AsyncMock, AsyncMock],
) -> None:
    link, _notice = mail
    repository.get_by_email.return_value = account

    await service.request_password_reset(account.email)
    await service.request_password_reset(account.email)

    assert link.await_count == 1


async def test_the_notice_spends_the_same_budget(
    service: AuthService,
    repository: AsyncMock,
    account: User,
    mail: tuple[AsyncMock, AsyncMock],
) -> None:
    _link, notice = mail
    repository.get_by_email.return_value = _passwordless(account, provider="google")

    await service.request_password_reset(account.email)
    await service.request_password_reset(account.email)

    assert notice.await_count == 1


async def test_a_refused_or_unknown_account_spends_no_budget(
    service: AuthService,
    repository: AsyncMock,
    account: User,
    mail: tuple[AsyncMock, AsyncMock],
    budget: SlidingWindowLimiter,
) -> None:
    account.is_superuser = True
    repository.get_by_email.return_value = account
    await service.request_password_reset(account.email)
    repository.get_by_email.return_value = None
    await service.request_password_reset("nobody@example.com")

    assert budget.entries == {}


# ---------------------------------------------------------------------------
# D — what each request did and what each link gave, counted (ADR-363)
# ---------------------------------------------------------------------------


def _requests(outcome: str) -> float:
    value = REGISTRY.get_sample_value("password_reset_requests_total", {"outcome": outcome})
    return value or 0.0


def _uses(outcome: str) -> float:
    value = REGISTRY.get_sample_value("password_reset_confirmations_total", {"outcome": outcome})
    return value or 0.0


def test_every_outcome_exposes_a_series_before_its_first_event() -> None:
    request_outcomes = [
        "link_sent",
        "notice_sent",
        "send_failed",
        "throttled",
        "unknown_account",
        "refused_deleted",
        "refused_superuser",
    ]
    use_outcomes = ["completed", "rejected_token", "stale_token", "unknown_account", "ineligible"]

    assert all(
        REGISTRY.get_sample_value("password_reset_requests_total", {"outcome": o}) is not None
        for o in request_outcomes
    )
    assert all(
        REGISTRY.get_sample_value("password_reset_confirmations_total", {"outcome": o}) is not None
        for o in use_outcomes
    )


@pytest.mark.parametrize(
    "state", ["password", "google", "superuser", "deleted", "unknown"], ids=str
)
async def test_each_request_is_counted_by_what_it_did(
    service: AuthService,
    repository: AsyncMock,
    account: User,
    mail: tuple[AsyncMock, AsyncMock],
    state: str,
) -> None:
    expected = {
        "password": "link_sent",
        "google": "notice_sent",
        "superuser": "refused_superuser",
        "deleted": "refused_deleted",
        "unknown": "unknown_account",
    }[state]
    if state == "google":
        _passwordless(account, provider="google")
    elif state == "superuser":
        account.is_superuser = True
    elif state == "deleted":
        account.deleted_at = datetime.now(UTC)
    repository.get_by_email.return_value = None if state == "unknown" else account
    before = _requests(expected)

    await service.request_password_reset(account.email)

    assert _requests(expected) == before + 1


async def test_a_request_past_the_budget_is_counted_throttled(
    service: AuthService,
    repository: AsyncMock,
    account: User,
    mail: tuple[AsyncMock, AsyncMock],
) -> None:
    repository.get_by_email.return_value = account
    await service.request_password_reset(account.email)
    before = _requests("throttled")

    await service.request_password_reset(account.email)

    assert _requests("throttled") == before + 1


async def test_an_e_mail_that_did_not_leave_is_counted_as_such(
    service: AuthService,
    repository: AsyncMock,
    account: User,
    mail: tuple[AsyncMock, AsyncMock],
) -> None:
    link, _notice = mail
    link.return_value = False
    repository.get_by_email.return_value = account
    before = _requests("send_failed")

    await service.request_password_reset(account.email)

    assert _requests("send_failed") == before + 1


async def test_a_completed_reset_is_counted(
    service: AuthService, repository: AsyncMock, account: User
) -> None:
    repository.get_by_email.return_value = account
    repository.update_password.return_value = account
    before = _uses("completed")

    await service.reset_password(_link_for(account), _NEW_PASSWORD)

    assert _uses("completed") == before + 1


@pytest.mark.parametrize("case", ["forged", "stale", "ineligible", "unknown"], ids=str)
async def test_each_refused_use_is_counted_by_its_reason(
    service: AuthService, repository: AsyncMock, account: User, case: str
) -> None:
    expected = {
        "forged": "rejected_token",
        "stale": "stale_token",
        "ineligible": "ineligible",
        "unknown": "unknown_account",
    }[case]
    link = "not.a.jwt" if case == "forged" else _link_for(account)
    if case == "stale":
        account.hashed_password = get_password_hash("AnotherPass123!!")
    elif case == "ineligible":
        account.is_superuser = True
    repository.get_by_email.return_value = None if case == "unknown" else account
    before = _uses(expected)

    with pytest.raises(HTTPException):
        await service.reset_password(link, _NEW_PASSWORD)

    assert _uses(expected) == before + 1
