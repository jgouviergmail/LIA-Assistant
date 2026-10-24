"""Who may receive a password-reset link (ADR-363).

Measured on production 2026-10-23: a link went to every account an address
named — the administrator's included, the 199 Google accounts whose link would
CREATE a password, and the deleted accounts, whose address is kept for billing.
"""

import ast
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.domains.auth.password_reset_policy import (
    SIGN_IN_PROVIDER_LABELS,
    PasswordRecovery,
    ResetDecision,
    acquire_reset_send,
    decide_reset,
    recovery_without_password,
    sign_in_provider_label,
)
from src.domains.users.models import User
from src.infrastructure.cache.key_families import is_reset_purgeable
from src.infrastructure.database.registry import import_all_models
from tests.fixtures.factories import UserFactory
from tests.unit.domains.auth.reset_budget_fakes import (
    SlidingWindowLimiter,
    install_reset_budget,
)

import_all_models()

pytestmark = pytest.mark.unit

_SRC = Path(__file__).parents[4] / "src"


def _account(
    *,
    password: bool = True,
    provider: str | None = None,
    superuser: bool = False,
    deleted: bool = False,
) -> User:
    user = UserFactory.create(is_superuser=superuser, oauth_provider=provider)
    if not password:
        user.hashed_password = None
    if deleted:
        user.deleted_at = datetime.now(UTC)
    return user


@pytest.mark.parametrize(
    ("account", "decision"),
    [
        (_account(), ResetDecision.LINK),
        # A8: password disabled for passkeys — the link is the documented way back.
        (_account(password=False), ResetDecision.LINK),
        (_account(password=False, provider="google"), ResetDecision.NOTICE),
        (_account(provider="google"), ResetDecision.LINK),
        (_account(superuser=True), ResetDecision.REFUSE_SUPERUSER),
        (
            _account(password=False, provider="google", superuser=True),
            ResetDecision.REFUSE_SUPERUSER,
        ),
        (_account(password=False, deleted=True), ResetDecision.REFUSE_DELETED),
        (_account(password=False, deleted=True, superuser=True), ResetDecision.REFUSE_DELETED),
    ],
    ids=[
        "password",
        "passkeys-only",
        "google-without-password",
        "google-with-password",
        "superuser",
        "google-superuser",
        "deleted",
        "deleted-superuser",
    ],
)
def test_the_decision_for_each_kind_of_account(account: User, decision: ResetDecision) -> None:
    assert decide_reset(account) is decision


@pytest.mark.parametrize(
    ("account", "recovery"),
    [
        (_account(), PasswordRecovery.EMAIL_LINK),
        (_account(password=False), PasswordRecovery.EMAIL_LINK),
        (_account(provider="google"), PasswordRecovery.PROVIDER),
        (_account(password=False, provider="google"), PasswordRecovery.PROVIDER),
        (_account(superuser=True), PasswordRecovery.NONE),
        (_account(password=False, provider="google", superuser=True), PasswordRecovery.NONE),
        (_account(password=False, deleted=True), PasswordRecovery.NONE),
    ],
    ids=[
        "password",
        "passkeys-only",
        "google-with-password",
        "google-without-password",
        "superuser",
        "google-superuser",
        "deleted",
    ],
)
def test_what_remains_once_the_account_holds_no_password(
    account: User, recovery: PasswordRecovery
) -> None:
    """The Security settings promise this way back — beside a password already
    off, and in the dialog that turns one off (ADR-143, A8)."""
    assert recovery_without_password(account) is recovery


@pytest.mark.parametrize(
    "account",
    [
        _account(password=False),
        _account(password=False, provider="google"),
        _account(password=False, provider="google", superuser=True),
        _account(password=False, superuser=True),
        _account(password=False, deleted=True),
    ],
    ids=["passkeys-only", "google", "google-superuser", "passkeys-superuser", "deleted"],
)
def test_the_published_way_back_is_what_a_request_would_do(account: User) -> None:
    """For an account without a password, the settings and the route never disagree."""
    sent = {
        ResetDecision.LINK: PasswordRecovery.EMAIL_LINK,
        ResetDecision.NOTICE: PasswordRecovery.PROVIDER,
    }

    assert recovery_without_password(account) is sent.get(
        decide_reset(account), PasswordRecovery.NONE
    )


def test_google_is_named_as_people_know_it() -> None:
    assert sign_in_provider_label("google") == "Google"


def _written_providers() -> set[str]:
    """Every literal the code writes into ``oauth_provider``."""
    found: set[str] = set()
    for path in _SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Dict):
                pairs = zip(node.keys, node.values, strict=True)
                for key, value in pairs:
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "oauth_provider"
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                    ):
                        found.add(value.value)
            elif isinstance(node, ast.keyword) and node.arg == "oauth_provider":
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    found.add(node.value.value)
    return found


def test_every_provider_the_code_writes_has_a_label() -> None:
    written = _written_providers()

    assert "google" in written, "the scan no longer sees the Google sign-in writer"
    assert written <= set(SIGN_IN_PROVIDER_LABELS)


# ---------------------------------------------------------------------------
# A — the account's budget, whatever IP asks (ADR-363)
# ---------------------------------------------------------------------------


@pytest.fixture
def limiter(monkeypatch: pytest.MonkeyPatch) -> SlidingWindowLimiter:
    return install_reset_budget(monkeypatch)


async def test_one_e_mail_per_interval(limiter: SlidingWindowLimiter) -> None:
    account_id = uuid4()

    assert await acquire_reset_send(account_id)
    assert not await acquire_reset_send(account_id)
    limiter.now += 901
    assert await acquire_reset_send(account_id)


async def test_a_few_e_mails_per_rolling_day(limiter: SlidingWindowLimiter) -> None:
    account_id = uuid4()
    sent = []
    for _ in range(4):
        sent.append(await acquire_reset_send(account_id))
        limiter.now += 3_600

    assert sent == [True, True, True, False]
    limiter.now += 86_400
    assert await acquire_reset_send(account_id)


async def test_a_refused_attempt_spends_none_of_the_day(limiter: SlidingWindowLimiter) -> None:
    account_id = uuid4()
    await acquire_reset_send(account_id)
    for _ in range(10):
        assert not await acquire_reset_send(account_id)

    day_keys = [key for key in limiter.entries if key.endswith(":day")]
    assert [len(limiter.entries[key]) for key in day_keys] == [1]


async def test_each_account_has_its_own_budget(limiter: SlidingWindowLimiter) -> None:
    first, second = uuid4(), uuid4()

    assert await acquire_reset_send(first)
    assert await acquire_reset_send(second)


async def test_a_conversation_reset_never_deletes_the_budget(
    limiter: SlidingWindowLimiter,
) -> None:
    await acquire_reset_send(uuid4())

    assert limiter.entries
    assert not any(is_reset_purgeable(key) for key in limiter.entries)


async def test_the_budget_names_the_account_by_its_id(limiter: SlidingWindowLimiter) -> None:
    account_id = uuid4()

    await acquire_reset_send(account_id)

    assert all(str(account_id) in key for key in limiter.entries)


async def test_an_unreachable_store_lets_the_e_mail_leave(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _unreachable() -> None:
        raise RedisConnectionError("cache redis is down")

    monkeypatch.setattr("src.domains.auth.password_reset_policy.get_rate_limiter", _unreachable)

    assert await acquire_reset_send(uuid4())
