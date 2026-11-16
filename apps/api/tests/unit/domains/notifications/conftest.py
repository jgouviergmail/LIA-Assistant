"""Shared setup of the notifications unit tests.

The push door publishes to ntfy after Firebase (ADR-391), and the ntfy door reads its targets
from the database. The tests of the Firebase road are not about ntfy and have no database: they
get an ntfy door with nothing to publish to. A test about ntfy installs its own door on top.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.domains.notifications import service as push_service
from src.domains.notifications.ntfy_delivery import NtfyBatch


@pytest.fixture(autouse=True)
def _no_ntfy_subscription(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(push_service, "push_to_ntfy", AsyncMock(return_value=NtfyBatch()))
