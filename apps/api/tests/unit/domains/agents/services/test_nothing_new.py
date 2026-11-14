"""« Nothing new »: what a routine's answer declares when its owner asked for silence.

A routine whose owner ticked « only tell me when there is something new » still
runs and still answers in the chat; what it holds back is the NOTIFICATION. The
answering model is the only one that knows whether its answer says anything
new, so it declares it — by a machine tag after the answer, the shape the tone
register already travels in (ADR-253): stripped from what is stored and shown,
handed to the ``done`` chunk for the routine's executor to read.

What must hold:

- the instruction is given ONLY inside such a run — an ordinary chat turn is
  never taught the tag, and its prompt does not grow by a token;
- the tag never reaches the person: stripped wherever it stands, complete or
  cut short, declared or not;
- the declaration counts only inside such a run: a tag written elsewhere is
  removed and declares nothing;
- the hand-off is per run, read once, and one run never reads another's.
"""

from __future__ import annotations

import pytest

from src.domains.agents.prompts.prompt_loader import FINAL_REMINDER_MARKER
from src.domains.agents.services import nothing_new
from src.domains.agents.services.nothing_new import (
    NOTHING_NEW_TAG_MARKER,
    attach_nothing_new_to_done,
    inject_nothing_new_instruction,
    quiet_run_scope,
    take_nothing_new,
)
from src.domains.agents.services.streaming.machine_tags import MachineTagFilter

pytestmark = pytest.mark.unit

_PROMPT = f"You are LIA.\n\n{FINAL_REMINDER_MARKER}\nAnswer in the person's language."


@pytest.fixture(autouse=True)
def _no_declaration_left_behind() -> None:
    nothing_new._declared.clear()


def _done(run_id: str) -> dict[str, object]:
    metadata: dict[str, object] = {"tokens_in": 1}
    attach_nothing_new_to_done(metadata, run_id)
    return metadata


class TestTheInstruction:
    def test_an_ordinary_turn_is_never_taught_the_tag(self) -> None:
        assert inject_nothing_new_instruction(_PROMPT) == _PROMPT

    def test_a_run_that_tells_everything_is_not_taught_it_either(self) -> None:
        with quiet_run_scope(False):
            assert inject_nothing_new_instruction(_PROMPT) == _PROMPT

    def test_a_quiet_run_is_told_how_to_declare_it_before_the_final_reminder(self) -> None:
        with quiet_run_scope(True):
            prompt = inject_nothing_new_instruction(_PROMPT)

        assert NOTHING_NEW_TAG_MARKER in prompt
        assert prompt.index(NOTHING_NEW_TAG_MARKER) < prompt.index(FINAL_REMINDER_MARKER)
        assert prompt.endswith("Answer in the person's language.")

    def test_the_scope_ends_with_the_run(self) -> None:
        with quiet_run_scope(True):
            pass

        assert inject_nothing_new_instruction(_PROMPT) == _PROMPT


class TestTheDeclaration:
    def test_a_quiet_run_s_tag_is_stripped_and_declared(self) -> None:
        with quiet_run_scope(True):
            cleaned = take_nothing_new("Nothing new this morning.\n<lia_nothing_new/>", "run-1")

        assert cleaned == "Nothing new this morning."
        assert _done("run-1") == {"tokens_in": 1, "nothing_new": True}

    def test_an_answer_without_the_tag_declares_nothing(self) -> None:
        with quiet_run_scope(True):
            cleaned = take_nothing_new("Two invoices arrived.", "run-2")

        assert cleaned == "Two invoices arrived."
        assert _done("run-2") == {"tokens_in": 1}

    @pytest.mark.parametrize(
        "written",
        [
            "Nothing new.\n<lia_nothing_new />",
            "Nothing new.\n<LIA_NOTHING_NEW/>",
            '<div class="lia-response"><p>Nothing new.</p></div>\n<lia_nothing_new/>',
            'Nothing new.\n<lia_nothing_new/>\n<lia_tone register="factual"/>',
        ],
    )
    def test_however_it_is_written_the_tag_leaves_the_answer(self, written: str) -> None:
        with quiet_run_scope(True):
            cleaned = take_nothing_new(written, "run-3")

        assert NOTHING_NEW_TAG_MARKER not in cleaned.lower()
        assert "Nothing new." in cleaned
        assert _done("run-3")["nothing_new"] is True

    def test_a_tag_cut_short_is_swept_and_declares_nothing(self) -> None:
        """An answer the provider cut mid-tag: the person never sees the
        fragment, and a declaration nobody finished is not one."""
        with quiet_run_scope(True):
            cleaned = take_nothing_new("Nothing new.\n<lia_nothing_ne", "run-4")
            swept = take_nothing_new("Nothing new.\n<lia_nothing_new", "run-5")

        assert cleaned == "Nothing new.\n<lia_nothing_ne"
        assert swept == "Nothing new."
        assert _done("run-4") == {"tokens_in": 1}
        assert _done("run-5") == {"tokens_in": 1}

    def test_outside_a_quiet_run_the_tag_is_removed_and_declares_nothing(self) -> None:
        cleaned = take_nothing_new("All good.\n<lia_nothing_new/>", "run-6")

        assert cleaned == "All good."
        assert _done("run-6") == {"tokens_in": 1}


class TestTheHandOff:
    def test_it_is_read_once(self) -> None:
        with quiet_run_scope(True):
            take_nothing_new("Nothing.\n<lia_nothing_new/>", "run-7")

        assert _done("run-7")["nothing_new"] is True
        assert _done("run-7") == {"tokens_in": 1}

    def test_one_run_never_reads_another_s(self) -> None:
        with quiet_run_scope(True):
            take_nothing_new("Nothing.\n<lia_nothing_new/>", "run-8")

        assert _done("run-9") == {"tokens_in": 1}

    def test_a_declaration_nobody_collected_is_forgotten(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A run that ends without its ``done`` chunk leaves an entry behind:
        the sweep keeps the registry from growing for the life of the worker."""
        clock = iter([100.0, 100.0 + nothing_new._DECLARATION_TTL_SECONDS + 1])
        monkeypatch.setattr(nothing_new, "_now", lambda: next(clock))
        with quiet_run_scope(True):
            take_nothing_new("Nothing.\n<lia_nothing_new/>", "run-10")

        assert _done("run-11") == {"tokens_in": 1}
        assert nothing_new._declared == {}


class TestTheTokenStream:
    def test_the_tag_never_reaches_whoever_reads_the_stream(self) -> None:
        """Declared with the other machine tags: a reader of the token stream
        (the chat voice) must not hear it typed out."""
        stream = MachineTagFilter()
        heard = "".join(
            stream.feed(token) for token in ["Nothing new.", "\n<lia_", "nothing_new", "/>"]
        )
        heard += stream.flush()

        assert heard.strip() == "Nothing new."
