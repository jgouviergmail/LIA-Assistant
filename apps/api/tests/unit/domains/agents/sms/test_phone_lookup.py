"""The phone reads SMS through its native lookup."""

from src.domains.shared.phone_domains import PHONE_DOMAINS


def test_the_phone_reads_sms_through_its_one_native_lookup() -> None:
    from src.domains.agents.telephony.live_specs import NATIVE_LOOKUPS

    assert "sms" in PHONE_DOMAINS
    sms_lookups = [spec for spec in NATIVE_LOOKUPS if spec.domain == "sms"]
    assert len(sms_lookups) == 1
    assert sms_lookups[0].name == "list_sms_tool" and sms_lookups[0].native
