"""A currency quote carries the day its rate belongs to, and says when a pair is not published.

The responses below are the ones the reference-rate API returned on 2026-09-24
from the dev stack (measured, not assumed): a quote carries ``date``; an
unknown code answers 404 « not found »; the same code twice answers 422
« bad currency pair ». A pair nobody publishes is a fact about the question —
never retried, never mistaken for an outage — while a network failure still
degrades to ``None`` for the billing callers, which fall back to the database.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date
from decimal import Decimal

import httpx
import pytest

from src.infrastructure.external.currency_api import (
    CurrencyQuote,
    CurrencyRateService,
    UnsupportedCurrencyError,
)

pytestmark = pytest.mark.unit

_Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def _empty_caches() -> Iterator[None]:
    CurrencyRateService.reset_caches()
    yield
    CurrencyRateService.reset_caches()


class _Api:
    """A fake of the rate API that counts what it was asked."""

    def __init__(self, handler: _Handler) -> None:
        self.handler = handler
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.handler(request)


def _serve(monkeypatch: pytest.MonkeyPatch, handler: _Handler) -> _Api:
    api = _Api(handler)
    real_client = httpx.AsyncClient

    def client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        return real_client(transport=httpx.MockTransport(api), timeout=5.0)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return api


def _quote(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"amount": 1.0, "base": "USD", "date": "2026-09-24", "rates": {"EUR": 0.87974}},
    )


class TestAQuote:
    async def test_carries_the_rate_and_its_day(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _serve(monkeypatch, _quote)

        quote = await CurrencyRateService().get_quote("USD", "EUR")

        assert quote == CurrencyQuote(rate=Decimal("0.87974"), rate_date=date(2026, 9, 24))

    async def test_is_served_from_the_cache_the_second_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _serve(monkeypatch, _quote)

        await CurrencyRateService().get_quote("USD", "EUR")
        await CurrencyRateService().get_quote("USD", "EUR")

        assert len(api.requests) == 1

    async def test_the_billing_reader_still_gets_the_bare_rate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(monkeypatch, _quote)

        assert await CurrencyRateService().get_rate("USD", "EUR") == Decimal("0.87974")

    async def test_a_payload_without_a_day_keeps_the_rate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(monkeypatch, lambda request: httpx.Response(200, json={"rates": {"EUR": 0.9}}))

        quote = await CurrencyRateService().get_quote("USD", "EUR")

        assert quote == CurrencyQuote(rate=Decimal("0.9"), rate_date=None)


class TestAPairNobodyPublishes:
    @pytest.mark.parametrize(
        ("status", "body"),
        [(404, {"message": "not found"}), (422, {"message": "bad currency pair"})],
    )
    async def test_is_said_and_not_retried(
        self, monkeypatch: pytest.MonkeyPatch, status: int, body: dict[str, str]
    ) -> None:
        api = _serve(monkeypatch, lambda request: httpx.Response(status, json=body))

        with pytest.raises(UnsupportedCurrencyError):
            await CurrencyRateService().get_quote("USD", "XYZ")

        assert len(api.requests) == 1

    async def test_reads_as_no_rate_for_the_billing_reader(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(monkeypatch, lambda request: httpx.Response(404, json={"message": "not found"}))

        assert await CurrencyRateService().get_rate("USD", "XYZ") is None


class TestAnOutage:
    async def test_degrades_to_none_and_stops_asking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("unreachable", request=request)

        api = _serve(monkeypatch, refuse)

        assert await CurrencyRateService().get_quote("USD", "EUR") is None
        asked = len(api.requests)
        assert await CurrencyRateService().get_quote("USD", "EUR") is None
        assert len(api.requests) == asked, "the negative cache must spare the second call"

    async def test_a_server_error_is_retried(self, monkeypatch: pytest.MonkeyPatch) -> None:
        answers = iter([httpx.Response(503), _quote(httpx.Request("GET", "https://x"))])
        _serve(monkeypatch, lambda request: next(answers))

        quote = await CurrencyRateService().get_quote("USD", "EUR")

        assert quote is not None and quote.rate == Decimal("0.87974")


class TestTheSupportedCurrencies:
    async def test_are_read_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = _serve(
            monkeypatch,
            lambda request: httpx.Response(200, json={"USD": "US Dollar", "EUR": "Euro"}),
        )

        first = await CurrencyRateService().supported_currencies()
        second = await CurrencyRateService().supported_currencies()

        assert first == second == ("EUR", "USD")
        assert len(api.requests) == 1

    async def test_are_unknown_when_the_api_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _serve(monkeypatch, lambda request: httpx.Response(500))

        assert await CurrencyRateService().supported_currencies() is None
