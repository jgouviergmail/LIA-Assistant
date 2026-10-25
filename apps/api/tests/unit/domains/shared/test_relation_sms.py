"""The relationship SMS seam: a closed archive is told apart from a failing one.

The assistant reads the archive only under the person's consent and only while
the capability is on: those refusals are DECISIONS, not incidents, and logging
them as « unavailable » warnings on every directory read would bury a real
failure in noise. Every outcome still degrades to an empty page.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from structlog.testing import capture_logs

from src.core.exceptions import AuthorizationError
from src.domains.shared import relation_sms
from src.domains.shared.relation_sms import RelationSmsPage, read_relation_sms

pytestmark = pytest.mark.unit


def _reader(error: Exception) -> AbstractContextManager[object]:
    reader = AsyncMock()
    reader.read = AsyncMock(side_effect=error)
    return patch.object(relation_sms, "_factory", lambda: reader)


@pytest.mark.parametrize("code", ["SMS_CONSENT_REQUIRED", "CAPABILITY_DISABLED"])
async def test_an_archive_closed_by_decision_is_no_warning(code: str) -> None:
    with _reader(AuthorizationError(detail={"error_code": code})), capture_logs() as logs:
        page = await read_relation_sms(uuid4(), assistant=True)

    assert page == RelationSmsPage()
    assert [entry["log_level"] for entry in logs] == ["debug"]
    assert logs[0]["error_code"] == code


@pytest.mark.parametrize(
    "error",
    [
        AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"}),
        RuntimeError("database gone"),
    ],
)
async def test_a_failing_archive_is_a_warning(error: Exception) -> None:
    with _reader(error), capture_logs() as logs:
        page = await read_relation_sms(uuid4())

    assert page == RelationSmsPage()
    assert [entry["log_level"] for entry in logs] == ["warning"]
    assert logs[0]["event"] == "relation_sms_unavailable"
