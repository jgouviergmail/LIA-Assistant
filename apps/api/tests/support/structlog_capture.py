"""Making ``structlog.testing.capture_logs`` reliable under xdist.

The app configures structlog with ``cache_logger_on_first_use=True``
(``infrastructure/observability/logging.py``). That freezes a module-level
``logger = structlog.get_logger(__name__)`` proxy onto whatever processor chain
was in force at its FIRST call.

`capture_logs` works by swapping that chain. A proxy frozen earlier keeps
writing to the old one, so the capture comes back **empty** — and the assertion
fails as "nothing was logged", which reads like a production defect and is not
one. Whether it happens depends purely on whether some earlier test in the same
worker process already made that module log, which under ``pytest-xdist``
depends on how the suite happened to be partitioned. Adding tests anywhere can
therefore red a test that never changed.

Measured twice on 2026-08-04: `core/oauth/test_flow_handler_state_logging.py`
(3 failures) and `infrastructure/mcp/test_oauth_flow.py` (1), both intermittent,
both green in isolation.

Usage — one autouse fixture per module that captures logs::

    @pytest.fixture(autouse=True)
    def _fresh_logger():
        from src.core.oauth import flow_handler

        yield from fresh_module_logger(flow_handler)
"""

from __future__ import annotations

from collections.abc import Iterator
from types import ModuleType

import structlog


def fresh_module_logger(module: ModuleType, attribute: str = "logger") -> Iterator[None]:
    """Give ``module`` an unfrozen logger for the duration of one test.

    The replacement proxy has never been called, so it freezes onto the chain
    installed by ``capture_logs`` rather than onto the application's. The
    original is restored afterwards, so no other test inherits this one's
    logger.

    Args:
        module: The module under test, whose logger the assertions read.
        attribute: Name of the module-level logger attribute.

    Yields:
        Nothing — this is a fixture body.
    """
    original = getattr(module, attribute)
    setattr(module, attribute, structlog.get_logger(f"test.{module.__name__}"))
    try:
        yield
    finally:
        setattr(module, attribute, original)
