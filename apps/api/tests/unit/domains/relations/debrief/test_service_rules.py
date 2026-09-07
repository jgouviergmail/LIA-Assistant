"""The debrief's judgement calls, isolated from any database.

Four decisions this service makes on its own, each with a defect behind it:

- what counts as EVIDENCE (a payload of identity and caveats is not a
  relationship worth a paragraph);
- what the digest is computed over (unstable input = a "nothing changed"
  shortcut that fires at random);
- whether a stored body can still be read (a shape from another version is
  rebuilt, never half-rendered);
- whether the rebuild control should even be offered (a button that would be
  refused is a promise the system cannot keep).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.core.constants import RELATION_DEBRIEF_BODY_VERSION
from src.domains.relations.debrief.models import DebriefState
from src.domains.relations.debrief.schemas import DebriefStatus
from src.domains.relations.debrief.service import (
    _body_of,
    _can_rebuild,
    _digest,
    _has_evidence,
    _sections_of,
    read_of,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
BODY = {
    "version": RELATION_DEBRIEF_BODY_VERSION,
    "headline": "Vous lui devez une réponse.",
    "where_we_stand": "Deux échanges cette semaine.",
    "open_points": ["Répondre au devis"],
    "suggested_next_step": None,
    "notable_facts": [],
}


def _row(**over: object) -> SimpleNamespace:
    base = {
        "display_name": "Gérard Dupont",
        "state": DebriefState.READY,
        "body": dict(BODY),
        "generated_at": NOW,
        "generated_for": date(2026, 9, 7),
        "sections_used": ["open_commitments"],
        "unavailable": ["emails"],
        "held_until": None,
        # Present because the real row has it: a stub that omits a column the
        # reader reads is a harness that passes where production would break.
        "usage": {"tokens_in": 900, "tokens_out": 120, "tokens_cache": 0, "cost_eur": 0.004},
    }
    return SimpleNamespace(**{**base, **over})


class TestWhatCountsAsEvidence:
    """A paragraph written from nothing is the one thing worse than no paragraph."""

    def test_identity_alone_is_not_evidence(self) -> None:
        assert not _has_evidence(
            {
                "person": "Gérard Dupont",
                "identity_confidence": "exact",
                "is_peer": False,
                "unavailable": [],
            }
        )

    def test_empty_blocks_are_not_evidence(self) -> None:
        """ "No open commitments" is a fact; a debrief of only such facts is not."""
        assert not _has_evidence(
            {
                "person": "X",
                "open_commitments": [],
                "open_commitments_total": 0,
                "recent_calls": [],
                "recent_calls_total": 0,
                "unavailable": [],
            }
        )

    def test_a_single_item_is_evidence(self) -> None:
        assert _has_evidence({"person": "X", "open_commitments": [{"subject": "devis"}]})

    def test_a_window_without_items_is_not_evidence(self) -> None:
        """A scope is a caveat about a lookup, not something that happened."""
        assert not _has_evidence({"person": "X", "emails": [], "emails_window_days": 365})

    def test_a_connection_is_evidence(self) -> None:
        """Being connected through LIA is a fact about the relationship."""
        assert _has_evidence({"person": "X", "peer_connection": {"shared_by_me": []}})


class TestTheDigestIsStable:
    """An unstable digest makes the "nothing changed" shortcut fire at random."""

    def test_key_order_does_not_change_it(self) -> None:
        assert _digest({"a": 1, "b": [2, 3]}) == _digest({"b": [2, 3], "a": 1})

    def test_a_changed_value_changes_it(self) -> None:
        assert _digest({"a": 1}) != _digest({"a": 2})

    def test_a_changed_list_order_does_change_it(self) -> None:
        """Order inside a list is meaning — most recent first is not the same set."""
        assert _digest({"a": [1, 2]}) != _digest({"a": [2, 1]})


class TestWhichSectionsAreReported:
    """The honesty footer names what was read, never the plumbing."""

    def test_totals_windows_and_flags_are_not_sections(self) -> None:
        assert _sections_of(
            {
                "person": "X",
                "open_commitments": [{"subject": "s"}],
                "open_commitments_total": 3,
                "emails": [{"subject": "e"}],
                "emails_window_days": 365,
                "emails_matched_by_name": True,
                "unavailable": ["events"],
            }
        ) == ["emails", "open_commitments"]

    def test_an_empty_block_is_not_reported_as_read(self) -> None:
        assert _sections_of({"person": "X", "emails": []}) == []


class TestAStoredBodyThisVersionCannotRead:
    """Rebuilding is the repair; rendering half of it is not."""

    def test_a_foreign_version_reads_as_absent(self) -> None:
        assert _body_of(_row(body={**BODY, "version": RELATION_DEBRIEF_BODY_VERSION + 1})) is None

    def test_a_malformed_body_reads_as_absent(self) -> None:
        assert _body_of(_row(body={"version": RELATION_DEBRIEF_BODY_VERSION})) is None

    def test_a_null_body_reads_as_absent(self) -> None:
        assert _body_of(_row(body=None)) is None

    def test_a_ready_row_whose_body_is_unreadable_is_reported_ABSENT(self) -> None:
        """Otherwise the panel renders "ready" over an empty debrief."""
        read = read_of(_row(body={"version": 99}))  # type: ignore[arg-type]
        assert read.status is DebriefStatus.ABSENT
        assert read.body is None


class TestAFailedRebriefStillShowsWhatStands:
    """ "I could not refresh this" and "there is nothing" are different answers."""

    def test_a_failed_row_keeps_its_body_and_its_date(self) -> None:
        read = read_of(_row(state=DebriefState.FAILED))  # type: ignore[arg-type]
        assert read.status is DebriefStatus.FAILED
        assert read.body is not None
        assert read.body.headline == BODY["headline"]
        assert read.generated_at == NOW

    def test_the_gaps_travel_with_the_answer(self) -> None:
        read = read_of(_row())  # type: ignore[arg-type]
        assert read.unavailable == ["emails"]
        assert read.sections_used == ["open_commitments"]


class TestTheRebuildControlIsOnlyOfferedWhenItWouldWork:
    """A button that would be refused is a promise the system cannot keep."""

    def test_not_while_a_build_holds_the_row(self) -> None:
        row = _row(state=DebriefState.BUILDING, held_until=datetime.now(UTC) + timedelta(minutes=2))
        assert _can_rebuild(row) is False  # type: ignore[arg-type]

    def test_yes_once_a_dead_builders_lease_expired(self) -> None:
        row = _row(state=DebriefState.BUILDING, held_until=datetime.now(UTC) - timedelta(minutes=2))
        assert _can_rebuild(row) is True  # type: ignore[arg-type]

    def test_not_while_a_failure_is_cooling_down(self) -> None:
        row = _row(state=DebriefState.FAILED, held_until=datetime.now(UTC) + timedelta(minutes=5))
        assert _can_rebuild(row) is False  # type: ignore[arg-type]

    def test_yes_once_the_cooldown_elapsed(self) -> None:
        row = _row(state=DebriefState.FAILED, held_until=datetime.now(UTC) - timedelta(minutes=1))
        assert _can_rebuild(row) is True  # type: ignore[arg-type]

    def test_yes_on_a_settled_answer(self) -> None:
        assert _can_rebuild(_row()) is True  # type: ignore[arg-type]
        assert (
            _can_rebuild(_row(state=DebriefState.EMPTY, body=None))  # type: ignore[arg-type]
            is True
        )


class TestThePromptsActuallyRender:
    """A placeholder the caller never fills is a KeyError on every build.

    Both files carry named placeholders and both are rendered with
    ``str.format``. A prompt edit that adds one — or a brace typed in prose —
    fails at RUNTIME, on the first debrief, with a message that names a key
    rather than a cause. That defect class has bitten this codebase before
    (a fallback prompt interpolating the user's own text).
    """

    def test_the_writing_prompt_renders_with_exactly_what_the_builder_passes(self) -> None:
        from src.core.constants import (
            RELATION_DEBRIEF_MAX_NOTABLE_FACTS_DEFAULT,
            RELATION_DEBRIEF_MAX_OPEN_POINTS_DEFAULT,
            RELATION_DEBRIEF_PROMPT_NAME,
        )
        from src.domains.relations.debrief.prompts import load_debrief_prompt

        rendered = load_debrief_prompt(RELATION_DEBRIEF_PROMPT_NAME).format(
            user_name="Jean",
            language="fr",
            personality_brief="",
            user_model_block="",
            person_name="Gérard Dupont",
            today_iso="2026-09-07",
            evidence='{"person":"Gérard Dupont"}',
            max_open_points=RELATION_DEBRIEF_MAX_OPEN_POINTS_DEFAULT,
            max_notable_facts=RELATION_DEBRIEF_MAX_NOTABLE_FACTS_DEFAULT,
        )
        assert "Gérard Dupont" in rendered
        # The bounds are PUBLISHED to the writer, never written in prose
        # (ADR-184): what the schema will trim is what it could read.
        assert str(RELATION_DEBRIEF_MAX_OPEN_POINTS_DEFAULT) in rendered

    def test_evidence_braces_never_reach_the_template(self) -> None:
        """A subject line full of braces is an ARGUMENT, not a template."""
        from src.core.constants import RELATION_DEBRIEF_PROMPT_NAME
        from src.domains.relations.debrief.prompts import load_debrief_prompt

        hostile = '{"subject":"{not_a_placeholder} {{also}} {0}"}'
        rendered = load_debrief_prompt(RELATION_DEBRIEF_PROMPT_NAME).format(
            user_name="Jean",
            language="fr",
            personality_brief="",
            user_model_block="",
            person_name="X",
            today_iso="2026-09-07",
            evidence=hostile,
            max_open_points=5,
            max_notable_facts=5,
        )
        assert hostile in rendered

    def test_the_injection_template_renders_with_exactly_what_it_is_given(self) -> None:
        from src.domains.relations.debrief.prompts import load_debrief_prompt

        rendered = load_debrief_prompt("relation_debrief_context_template").format(
            person_name="Gérard Dupont",
            generated_on="2026-09-07",
            age_days=3,
            sections="WHERE IT STANDS\nok",
        )
        assert "2026-09-07" in rendered
        # The AGE, not only the date: the block's whole safety property is that
        # the model treats it as dated, and asking it to do the arithmetic
        # against "today" is a weaker guarantee than telling it outright.
        assert "3 day" in rendered

    @staticmethod
    def _placeholders(template: str) -> set[str]:
        """The named fields a ``str.format`` template expects."""
        import string

        return {field for _text, field, _spec, _conv in string.Formatter().parse(template) if field}

    def test_the_templates_expect_exactly_the_fields_their_callers_pass(self) -> None:
        """A placeholder added on one side only is a KeyError on every build.

        Frozen as a SET rather than only checked by a successful render: a
        render test proves the caller covers the template; this proves the
        template did not quietly lose a field the caller still computes — and it
        forces the caller to be looked at whenever the file gains one.

        Measured on 2026-09-07: adding ``age_days`` to the injection template
        turned every injection into a swallowed ``KeyError`` — silent, because
        an injection never raises into the turn. This test and the render test
        both fired within seconds.
        """
        from src.core.constants import RELATION_DEBRIEF_PROMPT_NAME
        from src.domains.relations.debrief.prompts import load_debrief_prompt

        assert self._placeholders(load_debrief_prompt(RELATION_DEBRIEF_PROMPT_NAME)) == {
            "user_name",
            "language",
            "personality_brief",
            "user_model_block",
            "person_name",
            "today_iso",
            "evidence",
            "max_open_points",
            "max_notable_facts",
        }
        assert self._placeholders(load_debrief_prompt("relation_debrief_context_template")) == {
            "person_name",
            "generated_on",
            "age_days",
            "sections",
        }

    def test_the_section_file_declares_a_real_field_for_every_line(self) -> None:
        """A header pointing at a field the body has not would render nothing."""
        from src.domains.relations.debrief.injection import _section_formats
        from src.domains.relations.debrief.schemas import DebriefBody

        fields = set(DebriefBody.model_fields)
        declared = [field for field, _header, _template in _section_formats()]
        assert declared, "the section file must declare at least one block"
        assert set(declared) <= fields, set(declared) - fields
        # Every field of the body is rendered somewhere: one added to the schema
        # and not to the file would be written by the model and never shown.
        assert set(declared) == fields


class TestTheModelsAnswerIsREPAIRED:
    """A bound in a schema refuses; the doctrine says repair (ADR-184).

    A model one item over the published maximum must not cost the reader their
    debrief — and a schema keyword a provider refuses must not cost every
    reader theirs.
    """

    @staticmethod
    def _draft(**over: object):
        from src.domains.relations.debrief.schemas import DebriefDraft

        base = {
            "headline": "Vous lui devez une réponse.",
            "where_we_stand": "Deux échanges cette semaine.",
            "open_points": [],
            "suggested_next_step": None,
            "notable_facts": [],
        }
        return DebriefDraft(**{**base, **over})  # type: ignore[arg-type]

    @staticmethod
    def _constraint_keys(fragment: object) -> set[str]:
        """Every JSON-schema keyword the fragment declares, at any depth."""
        found: set[str] = set()
        if isinstance(fragment, dict):
            found |= set(fragment)
            for value in fragment.values():
                found |= TestTheModelsAnswerIsREPAIRED._constraint_keys(value)
        elif isinstance(fragment, list):
            for item in fragment:
                found |= TestTheModelsAnswerIsREPAIRED._constraint_keys(item)
        return found

    def test_the_schema_the_model_sees_carries_no_bound(self) -> None:
        """Length and item-count keywords are not universally accepted in strict mode.

        Asserted on the schema's KEYS, never on its serialised text: the class
        docstring reaches the model as a description, so a prose match here
        would fire on the very comment explaining the rule.
        """
        from src.domains.relations.debrief.schemas import DebriefDraft

        declared = self._constraint_keys(DebriefDraft.model_json_schema())
        assert not declared & {
            "maxLength",
            "minLength",
            "maxItems",
            "minItems",
            "pattern",
            "format",
            "minimum",
            "maximum",
        }

    def test_the_schema_description_is_not_an_essay(self) -> None:
        """Pydantic sends the docstring to the model — it is prompt material."""
        from src.domains.relations.debrief.schemas import DebriefDraft

        description = DebriefDraft.model_json_schema().get("description", "")
        assert len(description) < 120, description

    def test_it_stays_compatible_with_strict_structured_output(self) -> None:
        from src.domains.relations.debrief.schemas import DebriefDraft
        from src.infrastructure.llm.strict_schema import (
            _analyze_schema_strict_compatibility,
        )

        compatible, reason = _analyze_schema_strict_compatibility(DebriefDraft)
        assert compatible, reason

    def test_an_over_long_list_is_TRIMMED_not_refused(self) -> None:
        from src.core.constants import RELATION_DEBRIEF_MAX_OPEN_POINTS_DEFAULT

        over = [f"point {index}" for index in range(RELATION_DEBRIEF_MAX_OPEN_POINTS_DEFAULT + 3)]
        body = self._draft(open_points=over).to_body()

        assert len(body.open_points) == RELATION_DEBRIEF_MAX_OPEN_POINTS_DEFAULT
        assert body.open_points[0] == "point 0"

    def test_an_over_long_sentence_is_CUT_within_its_bound(self) -> None:
        from src.domains.relations.debrief.schemas import _HEADLINE_MAX

        body = self._draft(headline="mot " * 400).to_body()

        assert len(body.headline) <= _HEADLINE_MAX
        assert body.headline.endswith("…")

    def test_blank_items_are_dropped_rather_than_rendered_as_bullets(self) -> None:
        body = self._draft(open_points=["  ", "vrai point", ""]).to_body()
        assert body.open_points == ["vrai point"]

    def test_an_empty_next_step_becomes_null_not_an_empty_line(self) -> None:
        assert self._draft(suggested_next_step="   ").to_body().suggested_next_step is None

    def test_a_draft_within_its_bounds_travels_unchanged(self) -> None:
        draft = self._draft(open_points=["a", "b"], notable_facts=["c"])
        body = draft.to_body()
        assert body.headline == draft.headline
        assert body.open_points == ["a", "b"]
        assert body.notable_facts == ["c"]


class TestWhatTheWritingPromptDemands:
    """Three instructions whose absence is invisible until a reader sees it.

    Each is pinned because the surface CANNOT repair it: the card renders these
    fields as React children, so any marker the model types is shown verbatim,
    and nothing downstream re-reads them for style.
    """

    @staticmethod
    def _prompt() -> str:
        from src.core.constants import RELATION_DEBRIEF_PROMPT_NAME
        from src.domains.relations.debrief.prompts import load_debrief_prompt

        return load_debrief_prompt(RELATION_DEBRIEF_PROMPT_NAME)

    def test_it_forbids_markdown(self) -> None:
        """The card escapes what it is given: `**bold**` reaches the reader as is."""
        prompt = self._prompt().lower()
        assert "plain text" in prompt
        assert "no markdown" in prompt

    def test_it_forbids_bullet_characters_inside_a_field(self) -> None:
        """The list fields ARE the lists; a typed bullet doubles the semantics."""
        assert "no bullet characters" in self._prompt().lower()

    def test_it_names_the_person_it_writes_about(self) -> None:
        """ "FOR the user, ABOUT them" left "them" pointing at either of two people."""
        prompt = self._prompt()
        assert "ABOUT {person_name}" in prompt
        assert "never to {person_name}" in prompt

    def test_it_publishes_the_bounds_it_will_be_trimmed_to(self) -> None:
        """ADR-184: whatever the schema clips, the writer could read."""
        prompt = self._prompt()
        assert "{max_open_points}" in prompt
        assert "{max_notable_facts}" in prompt

    def test_it_states_the_totals_rule(self) -> None:
        """ADR-185 reaching the writer: a page is not a count."""
        assert "never the length of the list" in self._prompt()

    def test_it_distinguishes_an_absent_key_from_an_empty_one(self) -> None:
        """The whole honesty contract of the payload, restated for the writer."""
        prompt = self._prompt()
        assert "ABSENT was never read" in prompt
        assert "EMPTY list means the question WAS asked" in prompt


class TestWhatTheUsageLogRecords:
    """A cost an operator cannot attribute is a cost nobody can act on.

    Measured on the dev database 2026-09-07: all 3 632 proactive rows carried a
    NULL ``llm_type``, so ``token_usage_logs`` could say WHICH TASK spent, never
    which configured SLOT — and the Article-12 export reads that column
    (ADR-263 lot 7). The debrief passes it; the six other proactive callers are
    unchanged and still do not.
    """

    async def test_the_slot_travels_with_the_spend(self) -> None:
        from unittest.mock import AsyncMock, patch
        from uuid import uuid4

        from src.core.constants import (
            RELATION_DEBRIEF_LLM_TYPE,
            RELATION_DEBRIEF_PROACTIVE_TASK_TYPE,
        )
        from src.domains.relations.debrief.service import RelationDebriefService

        tracker = AsyncMock()
        usage = SimpleNamespace(
            tokens_in=10, tokens_out=20, tokens_cache=0, model_name="gpt-4.1-mini"
        )
        with patch("src.infrastructure.proactive.tracking.track_proactive_tokens", tracker):
            await RelationDebriefService(uuid4())._track(usage, "gerard dupont", "run-probe")

        kwargs = tracker.await_args.kwargs
        assert kwargs["llm_type"] == RELATION_DEBRIEF_LLM_TYPE
        assert kwargs["task_type"] == RELATION_DEBRIEF_PROACTIVE_TASK_TYPE
        assert (kwargs["tokens_in"], kwargs["tokens_out"]) == (10, 20)

    async def test_a_call_that_cost_nothing_writes_nothing(self) -> None:
        """A zero-token result is not a spend to record."""
        from unittest.mock import AsyncMock, patch
        from uuid import uuid4

        from src.domains.relations.debrief.service import RelationDebriefService

        tracker = AsyncMock()
        usage = SimpleNamespace(tokens_in=0, tokens_out=0, tokens_cache=0, model_name="m")
        with patch("src.infrastructure.proactive.tracking.track_proactive_tokens", tracker):
            await RelationDebriefService(uuid4())._track(usage, "gerard dupont", "run-probe")

        tracker.assert_not_awaited()

    async def test_the_target_is_a_digest_never_the_person(self) -> None:
        """A target id lands in the usage log; a person's name does not belong there."""
        from unittest.mock import AsyncMock, patch
        from uuid import uuid4

        from src.domains.relations.debrief.service import RelationDebriefService

        tracker = AsyncMock()
        usage = SimpleNamespace(tokens_in=1, tokens_out=1, tokens_cache=0, model_name="m")
        with patch("src.infrastructure.proactive.tracking.track_proactive_tokens", tracker):
            await RelationDebriefService(uuid4())._track(usage, "gérard dupont", "run-probe")

        target = tracker.await_args.kwargs["target_id"]
        assert "dupont" not in target.lower()
        assert len(target) == 16
