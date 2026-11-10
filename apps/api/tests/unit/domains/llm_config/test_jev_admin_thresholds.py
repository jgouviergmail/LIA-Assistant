"""An administrator moves a JEV threshold within its bounds, audited (ADR-374)."""

from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from pydantic import ValidationError

from src.domains.llm_config import jev_admin as module
from src.domains.llm_config.jev_admin import JevThresholdUpdate
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import JevRouting
from src.domains.system_settings.models import SystemSettingKey

pytestmark = pytest.mark.unit

EMAIL = JevUsage.EMAIL_CLASSIFICATION


def _routing(stored: dict[str, str] | None = None) -> JevRouting:
    return JevRouting(
        flags={"global": True, **{usage.value: False for usage in JevUsage}},
        thresholds=stored or {},
    )


async def _patch(body: JevThresholdUpdate, routing: JevRouting) -> AsyncMock:
    with (
        patch.object(module, "read_routing", AsyncMock(return_value=routing)),
        patch.object(module, "write_setting", AsyncMock()) as write,
        patch.object(module, "get_jev_settings", AsyncMock()),
    ):
        await module.update_jev_thresholds(
            AsyncMock(),
            body,
            admin_user_id=uuid4(),
            request=Request({"type": "http", "headers": []}),
        )
    return write


async def test_patch_writes_bounded_value_and_audits() -> None:
    write = await _patch(
        JevThresholdUpdate(usage=EMAIL, values={"priority": Decimal("0.50")}), _routing()
    )
    write.assert_awaited_once()
    args, kwargs = write.await_args
    assert args[1] is SystemSettingKey.JEV_EMAIL_CLASSIFICATION_THRESHOLDS
    assert args[2] == '{"priority":"0.50"}'
    assert kwargs["action"] == "jev_thresholds_updated"


async def test_trailing_zeros_are_still_at_the_hundredth() -> None:
    write = await _patch(
        JevThresholdUpdate(usage=EMAIL, values={"priority": Decimal("0.6000")}), _routing()
    )
    assert write.await_args.args[2] == '{"priority":"0.60"}'


async def test_a_key_left_out_keeps_its_stored_value() -> None:
    routing = _routing({EMAIL.value: '{"category":"0.75"}'})
    write = await _patch(
        JevThresholdUpdate(usage=EMAIL, values={"priority": Decimal("0.60")}), routing
    )
    assert write.await_args.args[2] == '{"category":"0.75","priority":"0.60"}'


async def test_a_value_set_back_to_its_default_is_no_longer_stored() -> None:
    routing = _routing({EMAIL.value: '{"priority":"0.50"}'})
    write = await _patch(
        JevThresholdUpdate(usage=EMAIL, values={"priority": Decimal("0.80")}), routing
    )
    assert write.await_args.args[2] == "{}"


@pytest.mark.parametrize(
    ("usage", "values"),
    [
        (EMAIL, {"nope": Decimal("0.80")}),
        (EMAIL, {"priority": Decimal("0.20")}),
        (EMAIL, {"priority": Decimal("1.01")}),
        (EMAIL, {"priority": Decimal("0.805")}),
        (JevUsage.RADIO_VERIFICATION, {"line_margin": Decimal("0.45")}),
        (JevUsage.OBSERVE_MEMORY, {"empty": Decimal("0.90")}),
    ],
    ids=["unknown-key", "below", "above", "past-the-hundredth", "margin-above", "no-gate"],
)
async def test_an_unusable_value_is_422_and_writes_nothing(
    usage: JevUsage, values: dict[str, Decimal]
) -> None:
    with pytest.raises(HTTPException) as refused:
        await _patch(JevThresholdUpdate(usage=usage, values=values), _routing())
    assert refused.value.status_code == 422


def test_an_empty_or_non_numeric_body_is_refused_by_the_schema() -> None:
    with pytest.raises(ValidationError):
        JevThresholdUpdate(usage=EMAIL, values={})
    with pytest.raises(ValidationError):
        JevThresholdUpdate.model_validate({"usage": EMAIL.value, "values": {"priority": "abc"}})
    assert JevThresholdUpdate.model_validate(
        {"usage": EMAIL.value, "values": {"priority": 0.85}}
    ).values == {"priority": Decimal("0.85")}


async def test_get_reports_each_gate_and_whether_it_stays_qualified() -> None:
    routing = _routing({EMAIL.value: '{"priority":"0.5"}'})
    with (
        patch.object(module, "read_routing", AsyncMock(return_value=routing)),
        patch.object(module, "read_configuration", AsyncMock(return_value=("ready", None))),
    ):
        settings = await module.get_jev_settings(AsyncMock())
    by_usage = {status.usage: status for status in settings.usages}
    email = by_usage[EMAIL]
    assert not email.qualified
    assert {gate.key: gate.value for gate in email.gates} == {
        "category": 0.8,
        "priority": 0.5,
        "alert": 0.8,
        "reply_expected": 0.3,
    }
    priority = next(gate for gate in email.gates if gate.key == "priority")
    assert (priority.default, priority.minimum, priority.maximum) == (0.8, 0.5, 1.0)
    assert by_usage[JevUsage.MEETING_TEMPLATE].qualified
    assert (
        by_usage[JevUsage.OBSERVE_MEMORY].gates == []
        and by_usage[JevUsage.OBSERVE_MEMORY].qualified
    )
