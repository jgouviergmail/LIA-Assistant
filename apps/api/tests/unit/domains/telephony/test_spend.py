"""One run id per owner call (lot 8): every euro of a call lands under it.

The live lookups during the call, the synthesis after it and the relayed turn
each used to spend under a run id of their own, so the call's total existed
nowhere. They now share ONE deterministic id derived from the call, and the
per-run summary the chat meter already reads (``message_token_summary``,
unique on ``run_id``, accumulated by column arithmetic) becomes the call's
cumulated bill — shown on the relayed answer's bubble and on the calls list.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from src.domains.telephony.spend import PHONE_CALL_RUN_PREFIX, phone_call_run_id


@pytest.mark.unit
def test_the_run_id_is_deterministic_and_names_the_call() -> None:
    call_id = uuid4()
    run_id = phone_call_run_id(call_id)
    assert run_id == phone_call_run_id(call_id)
    assert run_id.startswith(PHONE_CALL_RUN_PREFIX)
    assert run_id != phone_call_run_id(uuid4())
    assert len(run_id) <= 255  # the column's width


@pytest.mark.unit
def test_the_run_id_is_the_relay_session_prefix_the_chat_already_groups_on() -> None:
    """The relay's session id was already ``phone_call_<call id>``: the run id
    keeps that prefix so a reader of the logs sees one family."""
    assert PHONE_CALL_RUN_PREFIX == "phone_call_"
    assert phone_call_run_id(UUID(int=1)) == f"phone_call_{UUID(int=1).hex}"
