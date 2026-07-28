"""The no-progress guard: same call, same arguments, no progress.

The ReAct loop already caps iterations and compute time. Neither notices
*stagnation*: an agent repeating ``get_emails_tool(query="unread")`` fifteen
times burns the whole budget, the user's tokens and the provider quota, then
ends on a timeout instead of an answer.

Two properties carry the design and are pinned here:

- **the digest is stable and shared** — it is keyed with the server secret, not
  a per-process key. A HITL resume routinely lands on another worker; a
  process-local key would silently reset the guard on every resume, which is
  precisely when a stalled loop resumes stalling;
- **nothing but the digest is stored** — the table lives in the LangGraph
  checkpoint, i.e. in PostgreSQL, and tool arguments carry the user's own data.
"""

from __future__ import annotations

import pytest

from src.domains.agents.utils.loop_guard import (
    MAX_TRACKED_DIGESTS,
    compute_call_digest,
    register_call,
    repeated_call_message,
)

pytestmark = [pytest.mark.unit]

SECRET = "a" * 64
BLOCK, TERMINAL = 4, 5


def _digest(name: str, args: dict | None = None, secret: str = SECRET) -> str:
    return compute_call_digest(name, args, secret)


class TestDigest:
    def test_identical_calls_share_a_digest(self) -> None:
        assert _digest("t", {"q": "unread"}) == _digest("t", {"q": "unread"})

    def test_argument_order_does_not_change_the_digest(self) -> None:
        """Without sorted keys, two identical calls would hash differently and
        the guard would simply never fire."""
        assert _digest("t", {"a": 1, "b": 2}) == _digest("t", {"b": 2, "a": 1})

    def test_different_arguments_give_different_digests(self) -> None:
        assert _digest("t", {"q": "unread"}) != _digest("t", {"q": "starred"})

    def test_different_tools_give_different_digests(self) -> None:
        assert _digest("a", {"q": 1}) != _digest("b", {"q": 1})

    def test_none_and_empty_arguments_agree(self) -> None:
        assert _digest("t", None) == _digest("t", {})

    def test_non_serialisable_arguments_do_not_raise(self) -> None:
        assert _digest("t", {"when": object()})

    def test_digest_does_not_leak_the_arguments(self) -> None:
        digest = _digest("send_email_tool", {"to": "victim@example.test"})
        assert "victim@example.test" not in digest
        assert "send_email_tool" not in digest

    def test_same_secret_reproduces_the_digest_across_processes(self) -> None:
        """What makes the guard survive a resume on another worker."""
        assert _digest("t", {"q": 1}, secret=SECRET) == _digest("t", {"q": 1}, secret=SECRET)

    def test_a_different_secret_changes_the_digest(self) -> None:
        assert _digest("t", {"q": 1}, secret="b" * 64) != _digest("t", {"q": 1})


class TestRegisterCall:
    def test_first_calls_are_allowed(self) -> None:
        table: dict[str, int] = {}
        digest = _digest("t")
        for _ in range(BLOCK - 1):
            table, verdict = register_call(
                table, digest, block_threshold=BLOCK, terminal_threshold=TERMINAL
            )
            assert verdict == "allow"

    def test_the_verdict_sequence_leaves_room_to_adapt(self) -> None:
        """Block first, end only after: the model gets one chance to change
        method before the turn is cut."""
        table: dict[str, int] = {}
        digest = _digest("t")
        outcomes = []
        for _ in range(TERMINAL):
            table, verdict = register_call(
                table, digest, block_threshold=BLOCK, terminal_threshold=TERMINAL
            )
            outcomes.append(verdict)
        assert outcomes == ["allow", "allow", "allow", "block", "terminal"]

    def test_a_different_call_is_not_penalised(self) -> None:
        """A busy turn must not be punished for being busy."""
        table: dict[str, int] = {}
        for index in range(10):
            table, verdict = register_call(
                table,
                _digest("t", {"q": index}),
                block_threshold=BLOCK,
                terminal_threshold=TERMINAL,
            )
            assert verdict == "allow"

    def test_alternating_calls_are_still_caught(self) -> None:
        """A,B,A,B,… is stagnation too; a single-slot counter would miss it."""
        table: dict[str, int] = {}
        digests = [_digest("a"), _digest("b")]
        verdicts = []
        for round_index in range(TERMINAL):
            for digest in digests:
                table, verdict = register_call(
                    table, digest, block_threshold=BLOCK, terminal_threshold=TERMINAL
                )
                verdicts.append(verdict)
            del round_index
        assert "terminal" in verdicts

    def test_the_table_is_copied_not_mutated(self) -> None:
        """LangGraph state values are replaced, never edited in place."""
        original: dict[str, int] = {}
        updated, _ = register_call(
            original, _digest("t"), block_threshold=BLOCK, terminal_threshold=TERMINAL
        )
        assert original == {}
        assert updated != original

    def test_tracking_is_capped(self) -> None:
        table = {f"digest-{i}": 1 for i in range(MAX_TRACKED_DIGESTS)}
        updated, verdict = register_call(
            table, _digest("brand-new"), block_threshold=BLOCK, terminal_threshold=TERMINAL
        )
        assert verdict == "allow"
        assert len(updated) == MAX_TRACKED_DIGESTS

    def test_existing_counters_keep_working_past_the_cap(self) -> None:
        """The degenerate case this guard targets repeats ONE signature."""
        digest = _digest("t")
        table = {f"digest-{i}": 1 for i in range(MAX_TRACKED_DIGESTS - 1)}
        table[digest] = TERMINAL - 1
        _, verdict = register_call(
            table, digest, block_threshold=BLOCK, terminal_threshold=TERMINAL
        )
        assert verdict == "terminal"


class TestHitlResumeSafety:
    """An interrupted node never returns, so its increments are discarded."""

    def test_a_discarded_execution_does_not_double_count(self) -> None:
        digest = _digest("search_emails")
        persisted: dict[str, int] = {}

        # Execution 1: two calls counted, then the node is interrupted before
        # returning — the updated table is thrown away with the partial work.
        discarded, _ = register_call(
            persisted, digest, block_threshold=BLOCK, terminal_threshold=TERMINAL
        )
        discarded, _ = register_call(
            discarded, digest, block_threshold=BLOCK, terminal_threshold=TERMINAL
        )
        assert persisted == {}, "the caller must not have mutated the state table"

        # Execution 2 (resume): the same two calls are replayed and counted once.
        resumed, verdict_a = register_call(
            persisted, digest, block_threshold=BLOCK, terminal_threshold=TERMINAL
        )
        resumed, verdict_b = register_call(
            resumed, digest, block_threshold=BLOCK, terminal_threshold=TERMINAL
        )
        assert (verdict_a, verdict_b) == ("allow", "allow")
        assert resumed[digest] == 2


class TestMessage:
    def test_block_message_tells_the_model_what_to_do(self) -> None:
        """A bare refusal is what a stalled model retries verbatim."""
        message = repeated_call_message("block")
        assert message.startswith("ERROR:")
        assert "change the approach" in message

    def test_terminal_message_asks_for_an_honest_answer(self) -> None:
        message = repeated_call_message("terminal")
        assert "Answer the user now" in message
        assert "could not obtain" in message
