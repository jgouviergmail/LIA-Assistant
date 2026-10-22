"""Read restrictions are resolved before opening any personal source."""

from uuid import uuid4

import pytest

from src.domains.proactive_discussions.rule_controls import (
    ControlSupport,
    RuleCompilation,
    restricted_sources,
)
from src.domains.shared.discussion_sources import SourceKey

pytestmark = pytest.mark.unit


def test_owned_exact_rule_can_only_remove_an_authorized_source():
    support = ControlSupport(id=f"memory:{uuid4()}", text="Do not consult my calendar anymore.")
    result = RuleCompilation.model_validate(
        {
            "abstain": False,
            "denied": [
                {
                    "source": "calendar",
                    "support_id": support.id,
                    "quote": "Do not consult my calendar",
                }
            ],
        }
    )
    assert restricted_sources(result, (support,), (SourceKey.CALENDAR, SourceKey.SMS)) == (
        SourceKey.SMS,
    )


@pytest.mark.parametrize(
    "change", [{"support_id": "foreign"}, {"quote": "an invented restriction"}]
)
def test_invented_rule_proof_refuses_the_whole_run(change):
    support = ControlSupport(id=f"reply:{uuid4()}", text="Never read my SMS.")
    result = RuleCompilation.model_validate(
        {
            "abstain": False,
            "denied": [
                {"source": "sms", "support_id": support.id, "quote": support.text, **change}
            ],
        }
    )
    with pytest.raises(ValueError, match="owned exact"):
        restricted_sources(result, (support,), (SourceKey.SMS,))


def test_uncertain_rule_abstains_before_private_read():
    result = RuleCompilation(abstain=True, denied=())
    assert restricted_sources(result, (), (SourceKey.CALENDAR,)) == ()
