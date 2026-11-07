"""The phone reads SMS through its native lookup, never through the collection decision."""

from uuid import uuid4

from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.display.jev_qualification import compatible_collection_item
from src.domains.shared.phone_domains import PHONE_DOMAINS


def test_explicit_phone_sms_does_not_enable_collection_decision_calls() -> None:
    from src.domains.agents.telephony.live_specs import NATIVE_LOOKUPS

    assert "sms" in PHONE_DOMAINS
    sms_lookups = [spec for spec in NATIVE_LOOKUPS if spec.domain == "sms"]
    assert len(sms_lookups) == 1
    assert sms_lookups[0].name == "list_sms_tool" and sms_lookups[0].native
    item = RegistryItem(
        id="sms_" + uuid4().hex,
        type=RegistryItemType.SMS,
        payload={"body": "Personal SMS"},
        meta=RegistryItemMeta(source="phone_ingestion", domain="sms"),
    )
    assert not compatible_collection_item(item)
