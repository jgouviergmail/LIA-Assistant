"""The sharing policy: a published share is final for that recipient — for now (2026-10-24).

The owner kept the door open: the rule is ONE function, so a « newer version »
rule changes it alone. This pins today's answer, including for a newer version.
"""

import pytest

from src.domains.shared.capability_shares import reshare_allowed

pytestmark = pytest.mark.unit


def test_a_recipient_nothing_was_published_to_may_receive() -> None:
    assert reshare_allowed([], None) is True
    assert reshare_allowed([], "2" * 64) is True


def test_a_published_share_is_final_even_for_a_newer_version() -> None:
    assert reshare_allowed(["1" * 64], None) is False
    assert reshare_allowed(["1" * 64], "2" * 64) is False
