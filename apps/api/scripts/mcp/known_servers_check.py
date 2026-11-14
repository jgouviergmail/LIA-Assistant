"""Re-measure that LIA reaches every known MCP server as it is (network, read-only).

The known catalogue (``src/infrastructure/mcp/known_servers.py``) offers servers a person
adds without typing an address. An address a vendor moved, or an authorization server
that stopped registering clients, is a dead card nobody sees until a person clicks it.
This script asks each entry the fact it was admitted on:

- a server that needs no account answers ``tools/list`` through LIA's own ephemeral
  connection;
- a server the person signs in to is found by LIA's own OAuth discovery, and its
  authorization server publishes a registration endpoint (RFC 7591) and PKCE ``S256``;
  where the person brings their own OAuth application (``own_oauth_client``), the
  discovery finds its authorization and token endpoints;
- a server read with the person's key or token refuses a session opened with an
  invalid one placed where the catalogue says (``401`` or ``403``), and either refuses
  a session without one too or opens it (the key then adds the person's account): the
  address is alive, and it reads the secret where the catalogue puts it.

Nothing is registered, nobody signs in, no request carries anything of a person. A
discovery proves the documents are there, not that a sign-in completes, and a refusal
proves the address asks for a secret, not that the person's will be accepted: those
last steps need an account at the vendor.

Usage:
    task mcp:known-servers:check

Exit status: 0 when every entry holds, 1 otherwise.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Awaitable, Callable

import httpx2

from src.core.constants import MCP_HTTP_TIMEOUT_SECONDS
from src.infrastructure.mcp.known_servers import KNOWN_MCP_SERVERS, KnownMCPServer
from src.infrastructure.mcp.oauth_flow import MCPOAuthFlowHandler

# The pool's own connection is the fact being measured: its client, its timeouts, its
# redirect policy. It has no public name because nothing else may open one.
from src.infrastructure.mcp.user_pool import _ephemeral_client

#: Longest one entry may take before it is reported as unreachable.
_ENTRY_TIMEOUT_SECONDS = 40
#: Entries asked at once: enough to finish in seconds, few enough to stay polite.
_CONCURRENCY = 6
#: What a server answers a session opened without the secret it reads, or with a wrong one.
_ASKS_FOR_A_SECRET = frozenset({401, 403})
#: A secret no vendor issued: proves where a server reads one, and carries nothing of a person.
_INVALID_SECRET = "lia-known-servers-check-invalid"
#: The opening of a session (MCP ``initialize``), sent with no credential at all.
_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "lia-known-servers-check", "version": "1"},
    },
}


async def _open_server(server: KnownMCPServer) -> str:
    """List the tools of a server that needs no account."""
    async with _ephemeral_client(server.url, None) as client:
        listed = await client.list_tools()
    if not listed.tools:
        raise ValueError("the server lists no tool")
    return f"{len(listed.tools)} tools listed"


async def _signed_in_server(server: KnownMCPServer) -> str:
    """Discover the authorization server of a server the person signs in to."""
    async with MCPOAuthFlowHandler() as flow:
        metadata = await flow.discover_auth_server(server.url)
    if server.own_oauth_client:
        # The person registers the application: the vendor need not register one.
        if not (metadata.authorization_endpoint and metadata.token_endpoint):
            raise ValueError("no authorization or token endpoint discovered")
        return "discovered, authorization and token endpoints (the person's own client)"
    if not metadata.registration_endpoint:
        raise ValueError("no registration endpoint: a client would have to be pre-registered")
    if not metadata.supports_pkce_s256:
        raise ValueError("PKCE S256 is not published")
    return "discovered, registration endpoint and PKCE S256 published"


def _invalid_secret(server: KnownMCPServer) -> dict[str, str]:
    """A secret no vendor issued, placed where the catalogue says the server reads it."""
    if server.auth_type == "api_key" and server.header_name:
        return {server.header_name: _INVALID_SECRET}
    return {"Authorization": f"Bearer {_INVALID_SECRET}"}


async def _secret_server(server: KnownMCPServer) -> str:
    """Open a session with no secret, then with an invalid one where the catalogue puts it.

    A server that refuses both asks for the secret. A server that opens without one but
    refuses an invalid one reads it where the catalogue says (the person's adds their
    account). A server that accepts an invalid secret does not read it there.
    """
    accept = {"Accept": "application/json, text/event-stream"}
    async with httpx2.AsyncClient(
        follow_redirects=False, timeout=MCP_HTTP_TIMEOUT_SECONDS
    ) as client:
        bare = await client.post(server.url, json=_INITIALIZE, headers=accept)
        invalid = await client.post(
            server.url, json=_INITIALIZE, headers={**accept, **_invalid_secret(server)}
        )
    scheme = server.auth_type
    if invalid.status_code not in _ASKS_FOR_A_SECRET:
        raise ValueError(
            f"answered {invalid.status_code} to an invalid {scheme}: the address does not "
            "read it where the catalogue puts it"
        )
    if bare.status_code in _ASKS_FOR_A_SECRET:
        return f"refuses a session without its {scheme} ({bare.status_code}) or a wrong one"
    if bare.is_success:
        return f"opens without a {scheme}, refuses a wrong one ({invalid.status_code})"
    raise ValueError(f"answered {bare.status_code} to a session opened without a {scheme}")


#: How each scheme is measured.
_PROBES: dict[str, Callable[[KnownMCPServer], Awaitable[str]]] = {
    "none": _open_server,
    "oauth2": _signed_in_server,
    "api_key": _secret_server,
    "bearer": _secret_server,
}


def _root_cause(error: BaseException) -> BaseException:
    """The first error under the task groups the MCP client raises through."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return error


async def check(server: KnownMCPServer) -> tuple[KnownMCPServer, str | None, str]:
    """Measure one entry.

    Args:
        server: The catalogue entry.

    Returns:
        The entry, the failure (``None`` when it holds) and what was measured.
    """
    probe = _PROBES[server.auth_type]
    try:
        async with asyncio.timeout(_ENTRY_TIMEOUT_SECONDS):
            return server, None, await probe(server)
    except Exception as error:
        cause = _root_cause(error)
        return server, f"{type(cause).__name__}: {str(cause)[:160]}", ""
    except BaseExceptionGroup as group:
        cause = _root_cause(group)
        return server, f"{type(cause).__name__}: {str(cause)[:160]}", ""


async def main() -> int:
    """Measure every entry and print one line each.

    Returns:
        The process exit status.
    """
    slots = asyncio.Semaphore(_CONCURRENCY)

    async def bounded(server: KnownMCPServer) -> tuple[KnownMCPServer, str | None, str]:
        async with slots:
            return await check(server)

    results = await asyncio.gather(*(bounded(server) for server in KNOWN_MCP_SERVERS))
    failures = 0
    for server, failure, measured in results:
        verdict = f"FAILED  {failure}" if failure else f"ok      {measured}"
        failures += failure is not None
        sys.stdout.write(f"{server.key:16} {server.auth_type:7} {verdict}\n")
    sys.stdout.write(
        f"\n{len(results) - failures}/{len(results)} known servers reachable as LIA is.\n"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
