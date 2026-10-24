"""The Turnstile bot check at the password doors (ADR-364).

Owner decision 2026-10-24: Cloudflare unreachable, ONLY the sign-in proceeds — a
person must always reach their account; a new account and a reset e-mail can
wait. A token Cloudflare REFUSED is refused everywhere, the sign-in included.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
import structlog
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from src.core.config import settings
from src.core.constants import (
    TURNSTILE_FAILED_ERROR_CODE,
    TURNSTILE_REACHABILITY_TTL_SECONDS,
    TURNSTILE_TOKEN_HEADER,
    TURNSTILE_TOKEN_MAX_LENGTH,
    TURNSTILE_UNAVAILABLE_ERROR_CODE,
)
from src.domains.auth import turnstile_gate
from src.domains.auth.turnstile_gate import (
    PROCEEDS_WHEN_UNAVAILABLE,
    TurnstileAction,
    TurnstileOutcome,
    classify,
    require_turnstile,
)
from src.infrastructure.external.turnstile_client import SiteverifyAnswer
from src.infrastructure.observability.metrics_auth import turnstile_verifications_total

pytestmark = pytest.mark.unit

_HOST = "lia.example.org"
_TOKEN = "XXXX.DUMMY.TOKEN.XXXX"


def _passed(action: TurnstileAction, hostname: str = _HOST) -> SiteverifyAnswer:
    return SiteverifyAnswer(success=True, error_codes=(), hostname=hostname, action=action.value)


def _testing(success: bool) -> SiteverifyAnswer:
    """What siteverify answers under Cloudflare's testing keys (measured 2026-10-24):
    no action, ``example.com`` whatever the page."""
    return SiteverifyAnswer(
        success=success,
        error_codes=() if success else ("invalid-input-response",),
        hostname="example.com",
        action=None,
        testing_key=True,
    )


class _FakeClient:
    """Stands in for Cloudflare: one scripted answer, every call recorded."""

    answer: SiteverifyAnswer | None = None
    calls: list[tuple[str, str | None]] = []

    def __init__(self, *, secret: str, timeout: float) -> None:
        assert secret == "1x0000000000000000000000000000000AA"

    hold: asyncio.Event | None = None

    async def verify(self, token: str, *, remote_ip: str | None) -> SiteverifyAnswer | None:
        type(self).calls.append((token, remote_ip))
        hold = type(self).hold
        if hold is not None:
            await hold.wait()
        return type(self).answer


class _Clock:
    """The gate's monotonic clock, moved by hand."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def cloudflare(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_FakeClient]]:
    monkeypatch.setattr(settings, "turnstile_enabled", True)
    monkeypatch.setattr(settings, "turnstile_site_key", "1x00000000000000000000AA")
    monkeypatch.setattr(settings, "turnstile_secret_key", "1x0000000000000000000000000000000AA")
    monkeypatch.setattr(settings, "frontend_url", f"https://{_HOST.upper()}")
    _FakeClient.answer = None
    _FakeClient.calls = []
    _FakeClient.hold = None
    monkeypatch.setattr(turnstile_gate, "TurnstileClient", _FakeClient)
    monkeypatch.setattr(turnstile_gate, "_reachability", turnstile_gate.Reachability())
    yield _FakeClient


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    ticking = _Clock()
    monkeypatch.setattr(turnstile_gate, "monotonic", ticking)
    return ticking


_CLOUDFLARE_IS_UP = SiteverifyAnswer(False, ("missing-input-response",), None, None)


def _request(token: str | None = _TOKEN, peer: str = "198.51.100.24") -> Request:
    headers = [] if token is None else [(TURNSTILE_TOKEN_HEADER.lower().encode(), token.encode())]
    return Request({"type": "http", "headers": headers, "client": (peer, 40000)})


def _detail(refused: pytest.ExceptionInfo[HTTPException]) -> object:
    """The refusal's body (FastAPI types it ``str``; the gate sends a dict)."""
    detail: object = refused.value.detail
    return detail


def _count(action: TurnstileAction, outcome: TurnstileOutcome) -> float:
    child = turnstile_verifications_total.labels(action=action.value, outcome=outcome.value)
    return float(child._value.get())


# --------------------------------------------------------------------------- policy


def test_only_the_sign_in_proceeds_when_cloudflare_is_unreachable() -> None:
    assert PROCEEDS_WHEN_UNAVAILABLE == frozenset({TurnstileAction.LOGIN})


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        (None, TurnstileOutcome.UNAVAILABLE),
        (
            SiteverifyAnswer(False, ("invalid-input-response",), None, None),
            TurnstileOutcome.REJECTED,
        ),
        (_passed(TurnstileAction.REGISTER), TurnstileOutcome.REJECTED),
        (_passed(TurnstileAction.LOGIN, hostname="elsewhere.example"), TurnstileOutcome.REJECTED),
        (_passed(TurnstileAction.LOGIN, hostname=_HOST.upper()), TurnstileOutcome.PASSED),
    ],
    ids=["no-answer", "refused", "token-of-another-door", "another-site", "passed"],
)
def test_what_an_answer_means_for_the_sign_in(
    answer: SiteverifyAnswer | None, outcome: TurnstileOutcome
) -> None:
    for honour_testing_keys in (True, False):
        assert (
            classify(
                answer,
                action=TurnstileAction.LOGIN,
                expected_hostnames=frozenset({_HOST}),
                honour_testing_keys=honour_testing_keys,
            )
            is outcome
        )


@pytest.mark.parametrize(
    ("success", "outcome"),
    [(True, TurnstileOutcome.PASSED), (False, TurnstileOutcome.REJECTED)],
    ids=["always-passes", "always-fails"],
)
def test_outside_production_a_testing_key_answers_for_itself(
    success: bool, outcome: TurnstileOutcome
) -> None:
    """Cloudflare's testing keys exist to try the chain end to end; they carry
    neither the door nor the page, so their verdict alone is read."""
    assert (
        classify(
            _testing(success),
            action=TurnstileAction.LOGIN,
            expected_hostnames=frozenset({_HOST}),
            honour_testing_keys=True,
        )
        is outcome
    )


@pytest.mark.parametrize("success", [True, False], ids=["always-passes", "always-fails"])
def test_in_production_a_testing_key_is_no_usable_answer(success: bool) -> None:
    """A testing secret in production voids the check — anyone may send the dummy
    token — and it is the operator's mistake, read like a mistyped secret: the
    sign-in proceeds, the rest waits, the alert fires. Never « bad token »."""
    assert (
        classify(
            _testing(success),
            action=TurnstileAction.LOGIN,
            expected_hostnames=frozenset({_HOST}),
            honour_testing_keys=False,
        )
        is TurnstileOutcome.UNAVAILABLE
    )


# --------------------------------------------------------------------------- the door


async def test_a_switched_off_check_asks_nobody(
    cloudflare: type[_FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "turnstile_enabled", False)

    await require_turnstile(TurnstileAction.REGISTER)(_request(token=None))

    assert cloudflare.calls == []


@pytest.mark.parametrize("action", [TurnstileAction.REGISTER, TurnstileAction.PASSWORD_RESET])
async def test_a_sign_up_or_a_reset_without_a_token_is_refused_without_asking_cloudflare(
    cloudflare: type[_FakeClient], action: TurnstileAction
) -> None:
    before = _count(action, TurnstileOutcome.MISSING)

    with pytest.raises(HTTPException) as refused:
        await require_turnstile(action)(_request(token="   "))

    assert refused.value.status_code == 403
    assert _detail(refused) == {"error": TURNSTILE_FAILED_ERROR_CODE}
    assert cloudflare.calls == []
    assert _count(action, TurnstileOutcome.MISSING) == before + 1


async def test_a_sign_in_without_a_token_is_refused_while_cloudflare_answers(
    cloudflare: type[_FakeClient],
) -> None:
    """No token and Cloudflare up: the browser never ran the widget — a script,
    or a blocked challenge the visitor can allow. Cloudflare is asked about an
    EMPTY token (it answers ``missing-input-response`` when it is up)."""
    cloudflare.answer = _CLOUDFLARE_IS_UP
    before = _count(TurnstileAction.LOGIN, TurnstileOutcome.MISSING)

    with pytest.raises(HTTPException) as refused:
        await require_turnstile(TurnstileAction.LOGIN)(_request(token=None))

    assert refused.value.status_code == 403
    assert _detail(refused) == {"error": TURNSTILE_FAILED_ERROR_CODE}
    assert cloudflare.calls == [("", None)]
    assert _count(TurnstileAction.LOGIN, TurnstileOutcome.MISSING) == before + 1


async def test_a_sign_in_without_a_token_proceeds_when_cloudflare_does_not_answer(
    cloudflare: type[_FakeClient],
) -> None:
    """The owner's rule holds where an outage actually shows: Cloudflare down, the
    widget cannot load in the browser either, so the sign-in arrives WITHOUT a
    token — and only the server's own view can tell that from a script."""
    before = _count(TurnstileAction.LOGIN, TurnstileOutcome.UNAVAILABLE)

    await require_turnstile(TurnstileAction.LOGIN)(_request(token=None))

    assert cloudflare.calls == [("", None)]
    assert _count(TurnstileAction.LOGIN, TurnstileOutcome.UNAVAILABLE) == before + 1


async def test_cloudflares_reachability_is_asked_once_per_ttl(
    cloudflare: type[_FakeClient], clock: _Clock
) -> None:
    cloudflare.answer = _CLOUDFLARE_IS_UP
    door = require_turnstile(TurnstileAction.LOGIN)

    for _ in range(3):
        with pytest.raises(HTTPException):
            await door(_request(token=None))
    assert len(cloudflare.calls) == 1

    clock.now += TURNSTILE_REACHABILITY_TTL_SECONDS + 1
    cloudflare.answer = None
    await door(_request(token=None))
    assert len(cloudflare.calls) == 2


async def test_a_real_check_tells_the_tokenless_sign_in_what_cloudflare_did(
    cloudflare: type[_FakeClient], clock: _Clock
) -> None:
    """A check with a token already asked Cloudflare: its verdict stands for the
    next tokenless sign-in, which then asks nothing."""
    await require_turnstile(TurnstileAction.LOGIN)(_request())  # Cloudflare silent
    await require_turnstile(TurnstileAction.LOGIN)(_request(token=None))

    assert cloudflare.calls == [(_TOKEN, "198.51.100.24")]


async def test_concurrent_tokenless_sign_ins_share_one_question(
    cloudflare: type[_FakeClient],
) -> None:
    cloudflare.hold = asyncio.Event()
    cloudflare.answer = None
    door = require_turnstile(TurnstileAction.LOGIN)

    async def _sign_in() -> None:
        await door(_request(token=None))

    waiting = [asyncio.create_task(_sign_in()) for _ in range(5)]
    await asyncio.sleep(0)
    cloudflare.hold.set()
    await asyncio.gather(*waiting)

    assert cloudflare.calls == [("", None)]


async def test_an_oversized_token_is_refused_without_asking_cloudflare(
    cloudflare: type[_FakeClient],
) -> None:
    with pytest.raises(HTTPException) as refused:
        await require_turnstile(TurnstileAction.LOGIN)(
            _request(token="x" * (TURNSTILE_TOKEN_MAX_LENGTH + 1))
        )

    assert refused.value.status_code == 403
    assert cloudflare.calls == []


async def test_a_passed_check_lets_the_request_through(cloudflare: type[_FakeClient]) -> None:
    cloudflare.answer = _passed(TurnstileAction.PASSWORD_RESET)
    before = _count(TurnstileAction.PASSWORD_RESET, TurnstileOutcome.PASSED)

    await require_turnstile(TurnstileAction.PASSWORD_RESET)(_request())

    assert cloudflare.calls == [(_TOKEN, "198.51.100.24")]
    assert _count(TurnstileAction.PASSWORD_RESET, TurnstileOutcome.PASSED) == before + 1


@pytest.mark.parametrize("action", list(TurnstileAction))
async def test_a_token_cloudflare_refused_is_refused_at_every_door(
    cloudflare: type[_FakeClient], action: TurnstileAction
) -> None:
    cloudflare.answer = SiteverifyAnswer(False, ("timeout-or-duplicate",), None, None)

    with pytest.raises(HTTPException) as refused:
        await require_turnstile(action)(_request())

    assert refused.value.status_code == 403
    assert _detail(refused) == {"error": TURNSTILE_FAILED_ERROR_CODE}


async def test_the_sign_in_proceeds_when_cloudflare_does_not_answer(
    cloudflare: type[_FakeClient],
) -> None:
    before = _count(TurnstileAction.LOGIN, TurnstileOutcome.UNAVAILABLE)

    await require_turnstile(TurnstileAction.LOGIN)(_request())

    assert _count(TurnstileAction.LOGIN, TurnstileOutcome.UNAVAILABLE) == before + 1


@pytest.mark.parametrize("action", [TurnstileAction.REGISTER, TurnstileAction.PASSWORD_RESET])
async def test_a_sign_up_or_a_reset_waits_for_cloudflare(
    cloudflare: type[_FakeClient], action: TurnstileAction
) -> None:
    with pytest.raises(HTTPException) as refused:
        await require_turnstile(action)(_request())

    assert refused.value.status_code == 503
    assert _detail(refused) == {"error": TURNSTILE_UNAVAILABLE_ERROR_CODE}


async def test_a_testing_key_in_production_never_locks_the_sign_in(
    cloudflare: type[_FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "environment", "production")
    cloudflare.answer = _testing(True)
    before = _count(TurnstileAction.LOGIN, TurnstileOutcome.UNAVAILABLE)

    with structlog.testing.capture_logs() as captured:
        await require_turnstile(TurnstileAction.LOGIN)(_request())
        with pytest.raises(HTTPException) as refused:
            await require_turnstile(TurnstileAction.REGISTER)(_request())

    assert _count(TurnstileAction.LOGIN, TurnstileOutcome.UNAVAILABLE) == before + 1
    assert refused.value.status_code == 503
    named = [e for e in captured if e["event"] == "turnstile_testing_key_in_production"]
    assert [e["log_level"] for e in named] == ["error", "error"]


async def test_outside_production_the_testing_keys_open_every_door(
    cloudflare: type[_FakeClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "environment", "development")
    cloudflare.answer = _testing(True)

    for action in TurnstileAction:
        await require_turnstile(action)(_request())

    assert len(cloudflare.calls) == len(TurnstileAction)


@pytest.mark.parametrize(
    ("page_host", "passes"),
    [("second.example.org", True), ("LIA.example.org", True), ("elsewhere.example", False)],
    ids=["a-second-origin", "the-frontend", "another-site"],
)
async def test_a_token_counts_when_made_on_any_page_of_this_instance(
    cloudflare: type[_FakeClient],
    monkeypatch: pytest.MonkeyPatch,
    page_host: str,
    passes: bool,
) -> None:
    """The instance's pages are every browser origin allowed to call the API with
    its cookie: a second origin an operator added to ``CORS_ORIGINS`` is one of
    them, a site sharing the widget is not — and an origin nobody can parse names
    no page, without failing the door."""
    monkeypatch.setattr(
        settings,
        "cors_origins",
        [f"https://{_HOST}", "https://second.example.org:8443", "*", "http://[::1"],
    )
    cloudflare.answer = _passed(TurnstileAction.LOGIN, hostname=page_host)

    if passes:
        await require_turnstile(TurnstileAction.LOGIN)(_request())
    else:
        with pytest.raises(HTTPException) as refused:
            await require_turnstile(TurnstileAction.LOGIN)(_request())
        assert refused.value.status_code == 403


async def test_an_unknown_peer_sends_no_address(cloudflare: type[_FakeClient]) -> None:
    cloudflare.answer = _passed(TurnstileAction.LOGIN)
    request = Request(
        {"type": "http", "headers": [(TURNSTILE_TOKEN_HEADER.lower().encode(), b"t")]}
    )

    await require_turnstile(TurnstileAction.LOGIN)(request)

    assert cloudflare.calls == [("t", None)]


# --------------------------------------------------------------------------- the site key


def test_the_sign_in_pages_receive_the_site_key_only_when_the_check_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.domains.auth.security_queries import public_auth_features

    monkeypatch.setattr(settings, "turnstile_site_key", "1x00000000000000000000AA")
    monkeypatch.setattr(settings, "turnstile_enabled", False)
    assert public_auth_features().turnstile_site_key is None

    monkeypatch.setattr(settings, "turnstile_enabled", True)
    assert public_auth_features().turnstile_site_key == "1x00000000000000000000AA"


def test_the_site_key_never_reaches_the_chats_security_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The chat's security read projects ``effective_auth_features`` — reviewed
    fields only; a key for the sign-in pages is noise to a model."""
    from src.domains.auth.security_queries import effective_auth_features

    monkeypatch.setattr(settings, "turnstile_enabled", True)
    monkeypatch.setattr(settings, "turnstile_site_key", "1x00000000000000000000AA")

    assert "turnstile_site_key" not in effective_auth_features().model_dump()


def test_the_browser_may_send_the_token_across_origins() -> None:
    """The web app and the API are two origins (lia / lia-back): a header the CORS
    preflight does not allow never leaves the browser, and every check would read
    as « missing »."""
    from unittest.mock import patch

    from src.core.middleware import setup_middleware

    app = FastAPI()
    with (
        patch("src.core.middleware.settings.cors_origins", ["https://web.test"]),
        patch("src.core.middleware.settings.rate_limit_enabled", False),
    ):
        setup_middleware(app)
        response = TestClient(app).options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://web.test",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": TURNSTILE_TOKEN_HEADER,
            },
        )

    assert response.status_code == 200
    assert (
        TURNSTILE_TOKEN_HEADER.lower() in response.headers["access-control-allow-headers"].lower()
    )


# --------------------------------------------------------------------------- the guards


@pytest.mark.parametrize(
    ("path", "bot_check"),
    [
        ("/register", "turnstile_register"),
        ("/login", "turnstile_login"),
        ("/request-password-reset", "turnstile_password_reset"),
    ],
)
def test_every_password_door_of_the_router_runs_its_bot_check(path: str, bot_check: str) -> None:
    """The real routes, not a test app: a door whose guard was dropped would pass
    every other test here."""
    from fastapi.dependencies.models import Dependant

    from src.domains.auth import dependencies
    from src.domains.auth.router import router
    from tests._routes import served_routes

    def calls(dependant: Dependant) -> Iterator[object]:
        for sub in dependant.dependencies:
            yield sub.call
            yield from calls(sub)

    route = next(
        r
        for r in served_routes(router)
        if r.path == router.prefix + path and "POST" in (r.methods or set())
    )
    assert getattr(dependencies, bot_check) in set(calls(route.dependant))


def test_the_per_ip_limiter_runs_before_the_bot_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """A flood is refused by the cheap local limiter before it costs a call to Cloudflare."""
    from src.domains.auth import dependencies

    order: list[str] = []

    async def _limiter() -> None:
        order.append("limiter")

    async def _bot_check() -> None:
        order.append("bot_check")

    app = FastAPI()

    @app.post("/door")
    async def _door(_guard: None = Depends(dependencies.login_guard)) -> dict[str, bool]:
        return {"ok": True}

    app.dependency_overrides[dependencies.rate_limit_login] = _limiter
    app.dependency_overrides[dependencies.turnstile_login] = _bot_check

    assert TestClient(app).post("/door").status_code == 200
    assert order == ["limiter", "bot_check"]
