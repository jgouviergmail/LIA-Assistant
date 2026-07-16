"""Contract: the test process never inherits the DEVELOPER environment.

The task runner exports the ENTIRE repo-root ``.env`` (the developer
environment) into every task's process environment (``Taskfile.yml`` →
``dotenv: [.env]``) — including the test tasks. ``.env.test`` only overrides
the keys it defines, so every other developer value leaked into ``Settings``:
``SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED=true`` silently flipped the
semantic-expansion code path (7 order-independent failures) and
``DEFAULT_CURRENCY=EUR`` + a real ``CURRENCY_API_URL`` made cost tests convert
at the LIVE exchange rate (5 failures) — green under direct pytest, red under
``task test:backend:integration``: launcher-dependent results misread as
test-order pollution.

``tests/conftest.py`` now scrubs every key declared in the repo-root ``.env``
from ``os.environ`` before loading ``.env.test``. These assertions pin the
test-canonical values that the leak flipped; they fail loudly if any launcher
reinjects the developer environment.
"""

from __future__ import annotations

import pytest

from src.core.config import settings

pytestmark = pytest.mark.integration


def test_semantic_expansion_flag_is_test_canonical() -> None:
    """Ships-dark flag must be OFF in tests (constants default, ADR-120)."""
    assert settings.semantic_expansion_evidence_driven_enabled is False, (
        "SEMANTIC_EXPANSION_EVIDENCE_DRIVEN_ENABLED leaked from the developer "
        "environment into the test process (launcher-injected .env?) — the "
        "semantic-expansion tests would exercise the wrong code path"
    )


def test_default_currency_is_test_canonical() -> None:
    """Cost tests assert raw USD figures — EUR conversion must stay off."""
    assert settings.default_currency == "USD", (
        f"default_currency={settings.default_currency!r} leaked from the "
        "developer environment — cost assertions would depend on a LIVE "
        "exchange-rate API call"
    )
