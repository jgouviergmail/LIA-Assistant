"""Production launcher: uvicorn's supervisor without the application inside it.

``uvicorn.main.run`` (0.48) imports the ASGI application in the SUPERVISOR
before it spawns the workers — ``config.load_app()`` exists for an early
"Error loading ASGI app" message and its result is discarded. The supervisor
then keeps every module of the application resident for the life of the
container while serving no request. Measured on the production Raspberry Pi on
2026-09-12: 437 MB (389 MB anonymous, grpc / PyMuPDF / numpy mapped) for the
supervisor of ``lia-api-prod``, 407 MB for the demonstrator's.

This module drives the very chain the CLI drives — ``Config`` → ``Server`` →
``Multiprocess`` with the listening socket bound once in the parent — and
never calls ``load_app``. What it gives up is the early import error: a worker
that cannot import the application dies at startup, the supervisor restarts
it, and the container's health check turns red, which is the verdict the
deploy reads (ADR-250). Flags are the CLI's, one to one, so the image's
``CMD`` keeps reading like a uvicorn command line and the graceful-shutdown
guard keeps finding ``--timeout-graceful-shutdown`` where it looks for it.

The module imports NOTHING from ``src`` at module level, by construction and
under an AST guard (``tests/unit/test_serve_launcher.py``): the whole point is
that the supervisor never pays the application's import.

Usage (the production image's ``CMD``)::

    python -m src.serve src.main:app --host 0.0.0.0 --port 8000 \\
        --limit-max-requests 10000 --limit-max-requests-jitter 1000 \\
        --proxy-headers --forwarded-allow-ips '*' --timeout-graceful-shutdown 20

The worker count follows ``WEB_CONCURRENCY`` exactly as uvicorn's ``Config``
reads it; ``--workers`` overrides it. Reload is deliberately not offered:
development runs the uvicorn CLI (``Dockerfile.dev``), where the supervisor's
import is the reloader's job.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from uvicorn import Config, Server
from uvicorn.main import STARTUP_FAILURE
from uvicorn.supervisors import Multiprocess

__all__ = ["STARTUP_FAILURE", "build_config", "main"]

DEFAULT_APP = "src.main:app"


def _parser() -> argparse.ArgumentParser:
    """The subset of uvicorn's command line the production image uses."""
    parser = argparse.ArgumentParser(
        prog="python -m src.serve",
        description="Serve the LIA API under uvicorn's multiprocess supervisor "
        "without importing the application in the supervisor.",
    )
    parser.add_argument("app", nargs="?", default=DEFAULT_APP, help="ASGI import string")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Worker processes; defaults to WEB_CONCURRENCY, then 1 (uvicorn's rule).",
    )
    parser.add_argument("--limit-max-requests", type=int, default=None)
    parser.add_argument("--limit-max-requests-jitter", type=int, default=0)
    parser.add_argument(
        "--proxy-headers",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Trust X-Forwarded-* headers (uvicorn's default: on).",
    )
    parser.add_argument("--forwarded-allow-ips", default=None)
    parser.add_argument("--timeout-graceful-shutdown", type=int, default=None)
    return parser


def build_config(argv: Sequence[str] | None = None) -> Config:
    """Translate the command line into a uvicorn ``Config``, flag for flag.

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        The configuration uvicorn's CLI would have built for the same flags.
    """
    args = _parser().parse_args(argv)
    return Config(
        args.app,
        host=args.host,
        port=args.port,
        workers=args.workers,
        limit_max_requests=args.limit_max_requests,
        limit_max_requests_jitter=args.limit_max_requests_jitter,
        proxy_headers=args.proxy_headers,
        forwarded_allow_ips=args.forwarded_allow_ips,
        timeout_graceful_shutdown=args.timeout_graceful_shutdown,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the server; the supervisor binds the socket and never imports the app.

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        The process exit code: ``0``, or uvicorn's ``STARTUP_FAILURE`` when a
        single in-process server never reached the started state.
    """
    config = build_config(argv)
    server = Server(config=config)
    try:
        if config.workers > 1:
            sock = config.bind_socket()
            Multiprocess(config, target=server.run, sockets=[sock]).run()
            return 0
        server.run()
    except KeyboardInterrupt:  # pragma: no cover - operator interrupt
        return 0
    return 0 if server.started else STARTUP_FAILURE


if __name__ == "__main__":  # pragma: no cover - process entry point
    sys.exit(main())
