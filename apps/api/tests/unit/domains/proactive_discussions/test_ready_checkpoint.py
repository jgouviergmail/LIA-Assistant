"""Warm understanding remains conditional on the exact prior ready evidence."""

import pytest

from src.domains.proactive_discussions.context_store.checkpoints import (
    ReadyCheckpoint,
    verified_ready,
)
from tests.unit.domains.proactive_discussions.test_context_loop import FACT

pytestmark = pytest.mark.unit


def test_changed_or_missing_fact_and_changed_rules_never_reuse_ready_understanding():
    checkpoint = ReadyCheckpoint(signature="control-v1", references={FACT.reference: FACT.version})
    assert verified_ready(checkpoint, "control-v1", (FACT,)) == {FACT.reference}
    assert verified_ready(checkpoint, "control-v2", (FACT,)) == set()
    assert verified_ready(checkpoint, "control-v1", ()) == set()
    assert (
        verified_ready(checkpoint, "control-v1", (FACT.model_copy(update={"version": "changed"}),))
        == set()
    )
