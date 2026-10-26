"""The native decision provider's keep-alive client: one owner, one loop, closed at shutdown."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest

from src.infrastructure.llm import jev_http

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
async def _no_shared_client_left_behind():
    await jev_http.close_jev_http_client()
    yield
    await jev_http.close_jev_http_client()


async def test_the_serving_loop_reuses_one_client_across_decisions() -> None:
    jev_http.open_jev_http_client()
    async with jev_http.jev_http_client() as first:
        pass
    async with jev_http.jev_http_client() as second:
        pass
    assert first is second
    assert not first.is_closed


async def test_opening_twice_keeps_the_client_already_bound() -> None:
    jev_http.open_jev_http_client()
    async with jev_http.jev_http_client() as before:
        pass
    jev_http.open_jev_http_client()
    async with jev_http.jev_http_client() as after:
        pass
    assert before is after


async def test_without_a_shared_client_each_call_owns_and_closes_its_own() -> None:
    async with jev_http.jev_http_client() as client:
        assert isinstance(client, httpx.AsyncClient)
        assert not client.is_closed
    assert client.is_closed


async def test_another_loop_never_borrows_the_serving_loops_client() -> None:
    jev_http.open_jev_http_client()
    async with jev_http.jev_http_client() as serving:
        pass

    def elsewhere() -> bool:
        async def probe() -> bool:
            async with jev_http.jev_http_client() as client:
                return client is serving

        return asyncio.run(probe())

    assert await asyncio.to_thread(elsewhere) is False


async def test_shutdown_closes_the_shared_client_and_later_calls_get_their_own() -> None:
    jev_http.open_jev_http_client()
    async with jev_http.jev_http_client() as shared:
        pass
    await jev_http.close_jev_http_client()
    assert shared.is_closed
    async with jev_http.jev_http_client() as later:
        assert later is not shared
    assert later.is_closed


async def test_closing_without_a_client_is_a_no_op() -> None:
    await jev_http.close_jev_http_client()
    await jev_http.close_jev_http_client()


class _BurstServer:
    """A keep-alive HTTP/1.1 server that answers a burst only once all of it arrived.

    Holding every answer until the whole burst is in proves the burst was served
    concurrently; counting accepted connections proves what the pool reused.
    """

    def __init__(self, burst: int) -> None:
        self.burst = burst
        self.connections = 0
        self._arrived = 0
        self._waiting = 0
        self.peak_waiting = 0
        self._arrival_changed = asyncio.Condition()
        self._everyone_in = asyncio.Event()
        self._server: asyncio.Server | None = None

    async def __aenter__(self) -> str:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return f"http://127.0.0.1:{self._server.sockets[0].getsockname()[1]}/"

    async def __aexit__(self, *exc: object) -> None:
        self._everyone_in.set()  # Pass or fail, no handler is left waiting for a burst.
        assert self._server is not None
        self._server.close()
        self._server.close_clients()
        await self._server.wait_closed()

    def next_burst(self) -> None:
        self._arrived = 0
        self.peak_waiting = 0
        self._everyone_in = asyncio.Event()

    async def wait_arrivals(self, count: int) -> None:
        async with self._arrival_changed:
            await self._arrival_changed.wait_for(lambda: self._arrived >= count)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        try:
            while True:
                await reader.readuntil(b"\r\n\r\n")
                async with self._arrival_changed:
                    self._arrived += 1
                    self._waiting += 1
                    self.peak_waiting = max(self.peak_waiting, self._waiting)
                    self._arrival_changed.notify_all()
                    if self._arrived == self.burst:
                        self._everyone_in.set()
                try:
                    await self._everyone_in.wait()
                finally:
                    self._waiting -= 1
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
        except asyncio.IncompleteReadError, ConnectionError:
            writer.close()


async def _burst(url: str, size: int, server: _BurstServer | None = None) -> list[int]:
    async def decide() -> int:
        async with jev_http.jev_http_client() as http:
            return (await http.get(url)).status_code

    tasks: list[asyncio.Task[int]] = []
    try:
        async with asyncio.timeout(10):
            for index in range(size):
                tasks.append(asyncio.create_task(decide()))
                if server is not None:
                    # Admit the next request only after this one reached the
                    # server. Every response stays blocked until ALL arrived,
                    # so the full burst is still concurrently in flight. This
                    # avoids HTTPcore's idle-connection reassignment cascade
                    # becoming an accidental scheduling benchmark under coverage.
                    await server.wait_arrivals(index + 1)
            return await asyncio.gather(*tasks)
    finally:
        # gather propagates the first error without stopping its other children.
        # Await cancellation before closing the pool/server or the owning loop.
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_a_failed_burst_cancels_and_awaits_every_other_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()
    requests: set[asyncio.Task[object]] = set()

    async def answer(request: httpx.Request) -> httpx.Response:
        task = asyncio.current_task()
        assert task is not None
        requests.add(task)
        if len(requests) == 1:
            await started.wait()
            raise httpx.ReadTimeout("inert burst failure", request=request)
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:

        @asynccontextmanager
        async def borrowed() -> AsyncIterator[httpx.AsyncClient]:
            yield client

        monkeypatch.setattr(jev_http, "jev_http_client", borrowed)
        try:
            with pytest.raises(httpx.ReadTimeout, match="inert burst failure"):
                await _burst("http://fixture.invalid/", 2)
            assert cancelled.is_set(), "a failed burst must finish its siblings before returning"
            assert all(task.done() for task in requests)
        finally:
            # The red regression must not itself strand the legacy gather's work.
            for task in requests:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*requests, return_exceptions=True)


async def test_a_burst_up_to_the_documented_limit_never_waits_for_a_connection() -> None:
    # A decision's deadline includes waiting for a pooled connection, so the pool
    # must admit every concurrent decision a worker can plausibly fire (two
    # classifications of four batches, the previews, the observers). The limit is
    # the vendor SDK's own default (docs.typesafe.ai/sdk/python/usage/advanced).
    size = jev_http.JEV_HTTP_MAX_CONNECTIONS
    jev_http.open_jev_http_client()
    server = _BurstServer(size)
    async with server as url:
        assert await _burst(url, size, server) == [200] * size
        assert server.peak_waiting == size


async def test_a_second_burst_reuses_every_connection_of_the_first() -> None:
    # The vendor keeps ALL connections open while idle "so bursts reuse connections
    # instead of opening new ones": a fresh one costs DNS, TCP and TLS, which on the
    # production host includes a measured ~4 s resolver failover.
    size = jev_http.JEV_HTTP_MAX_CONNECTIONS
    jev_http.open_jev_http_client()
    server = _BurstServer(size)
    async with server as url:
        assert await _burst(url, size, server) == [200] * size
        assert server.peak_waiting == size
        server.next_burst()
        assert await _burst(url, size, server) == [200] * size
        assert server.peak_waiting == size
    assert server.connections == size
