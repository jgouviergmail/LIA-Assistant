"""Configure logging as a side effect of being imported — FIRST, by ``main.py``.

Importing the application runs code that logs: tool modules build their
singleton instances, registries announce what they register, the prompt loader
reports the versions it found. Whatever logs before ``configure_logging()``
has run does so under structlog's DEFAULTS — console rendering Promtail cannot
parse, no level filter, no PII filter (measured 2026-09-23: DEBUG lines at
``LOG_LEVEL=INFO`` in the production logs, tool parameters included).

A call placed after the imports cannot come first, and a call placed before
them makes every import below it an E402. Importing this module first does
both: ``main.py`` imports it ahead of any application module, and the guard
``tests/unit/test_logging_configured_first_guard.py`` holds that order.
"""

from src.infrastructure.observability.logging import configure_logging

configure_logging()
