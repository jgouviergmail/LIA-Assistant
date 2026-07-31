"""The catalogue handed to the planner must allow a valid plan to exist.

Production, 2026-07-30. "Summarize this email and draft a reply" was scored
against an English paraphrase produced by an LLM at temperature 0.2. One run
paraphrased it "Summarize the email titled…" and ``get_emails_tool`` scored
0.010 — below the 0.07 threshold, excluded. Thirty minutes later the same
request came out as "Find the email titled…" and the tool was kept. The first
run handed the planner ``reply_email_tool``, whose ``message_id`` is REQUIRED,
with nothing able to produce a ``message_id``. No valid plan existed, the model
invented ``search_emails_tool``, and the request failed.

These tests pin the structural rule that removes the coin toss, and above all
the two traps that would silently turn it into a no-op:

- a tool must not satisfy its own requirement (``reply_email_tool`` consumes
  AND produces ``message_id``);
- a mutation is not a source (``send_email_tool`` also outputs a
  ``message_id``, and it WAS in the failing catalogue).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.services.catalogue.closure import (
    MAX_CLOSURE_ROUNDS,
    resolve_closure_additions,
)


class _Param:
    def __init__(self, name: str, semantic_type: str | None, required: bool) -> None:
        self.name = name
        self.semantic_type = semantic_type
        self.required = required


class _Output:
    def __init__(self, path: str, semantic_type: str | None) -> None:
        self.path = path
        self.semantic_type = semantic_type


class _Manifest:
    """Minimal stand-in carrying only what the closure reads."""

    def __init__(
        self,
        name: str,
        agent: str,
        tool_category: str,
        params: list[_Param] | None = None,
        outputs: list[_Output] | None = None,
    ) -> None:
        self.name = name
        self.agent = agent
        self.tool_category = tool_category
        self.parameters = params or []
        self.outputs = outputs or []


def _read(name: str, agent: str = "email_agent", **kw: Any) -> _Manifest:
    return _Manifest(name, agent, "search", **kw)


def _mutation(name: str, agent: str = "email_agent", **kw: Any) -> _Manifest:
    return _Manifest(name, agent, "send", **kw)


# The real shapes, reduced to the fields that matter.
GET_EMAILS = _read(
    "get_emails_tool",
    params=[_Param("message_id", "message_id", required=False)],
    outputs=[_Output("emails[].id", "message_id"), _Output("emails[].from", "email_address")],
)
REPLY_EMAIL = _mutation(
    "reply_email_tool",
    params=[_Param("message_id", "message_id", required=True)],
    outputs=[_Output("message_id", "message_id")],
)
SEND_EMAIL = _mutation(
    "send_email_tool",
    params=[_Param("to", "email_address", required=True)],
    outputs=[_Output("message_id", "message_id")],
)
EMAIL_POOL = [GET_EMAILS, REPLY_EMAIL, SEND_EMAIL]


@pytest.mark.unit
class TestTheProductionIncident:
    def test_a_read_tool_is_pulled_in_when_the_catalogue_cannot_source_a_handle(self) -> None:
        """The exact failing catalogue: reply + send, no way to read an email."""
        result = resolve_closure_additions([REPLY_EMAIL, SEND_EMAIL], EMAIL_POOL)

        assert result.additions == ["get_emails_tool"]

    def test_both_stranded_consumers_are_reported(self) -> None:
        """One provider covers several consumers — none may be dropped later.

        get_emails_tool sources the message_id reply needs AND the email_address
        send needs. Deriving the consumer list after the addition would omit the
        second one, leaving it evictable and stranding the provider.
        """
        result = resolve_closure_additions([REPLY_EMAIL, SEND_EMAIL], EMAIL_POOL)

        assert result.consumers == {"reply_email_tool", "send_email_tool"}

    def test_a_tool_never_satisfies_its_own_required_parameter(self) -> None:
        """reply_email_tool outputs a message_id — the one it just sent.

        Counting that as a source is the single mistake that would make this
        whole mechanism a no-op on the incident it was written for.
        """
        result = resolve_closure_additions([REPLY_EMAIL], EMAIL_POOL)

        assert result.additions == ["get_emails_tool"]

    def test_a_mutation_is_never_accepted_as_a_source(self) -> None:
        """send_email_tool outputs a message_id and was in the failing catalogue.

        One does not send an email to obtain an id to reply to.
        """
        result = resolve_closure_additions([REPLY_EMAIL, SEND_EMAIL], EMAIL_POOL)

        assert "send_email_tool" not in result.additions
        assert result.additions == ["get_emails_tool"]


@pytest.mark.unit
class TestClosedCataloguesAreLeftAlone:
    def test_the_run_that_succeeded_is_not_touched(self) -> None:
        """The paraphrase that kept get_emails_tool must behave identically."""
        result = resolve_closure_additions([GET_EMAILS, REPLY_EMAIL, SEND_EMAIL], EMAIL_POOL)

        assert not result.additions
        assert not result

    def test_a_read_only_request_stays_minimal(self) -> None:
        """ "my last 2 emails" requires no handle — no token may be added."""
        result = resolve_closure_additions([GET_EMAILS], EMAIL_POOL)

        assert not result.additions

    def test_an_optional_typed_parameter_never_triggers_an_addition(self) -> None:
        """The planner may simply omit it, so its absence empties nothing."""
        optional_consumer = _mutation(
            "optional_tool",
            params=[_Param("message_id", "message_id", required=False)],
        )

        result = resolve_closure_additions([optional_consumer], EMAIL_POOL)

        assert not result.additions

    def test_an_untyped_required_parameter_is_ignored(self) -> None:
        """Free text from the user's request (a query, a body) is not a handle."""
        free_text = _mutation("body_tool", params=[_Param("body", None, required=True)])

        result = resolve_closure_additions([free_text], EMAIL_POOL)

        assert not result.additions


@pytest.mark.unit
class TestProviderSelection:
    def test_the_same_domain_provider_wins_over_a_better_scored_foreign_one(self) -> None:
        foreign = _read("foreign_tool", agent="contact_agent", outputs=[_Output("x", "message_id")])
        pool = [*EMAIL_POOL, foreign]

        result = resolve_closure_additions(
            [REPLY_EMAIL], pool, {"foreign_tool": 0.99, "get_emails_tool": 0.01}
        )

        assert result.additions == ["get_emails_tool"]

    def test_within_a_domain_the_best_scored_provider_wins(self) -> None:
        rival = _read("rival_tool", outputs=[_Output("x", "message_id")])
        pool = [*EMAIL_POOL, rival]

        result = resolve_closure_additions(
            [REPLY_EMAIL], pool, {"rival_tool": 0.9, "get_emails_tool": 0.1}
        )

        assert result.additions == ["rival_tool"]

    def test_selection_is_deterministic_without_any_score(self) -> None:
        """No score must never mean no provider — ties break on the name."""
        rival = _read("aaa_tool", outputs=[_Output("x", "message_id")])
        pool = [*EMAIL_POOL, rival]

        first = resolve_closure_additions([REPLY_EMAIL], pool)
        second = resolve_closure_additions([REPLY_EMAIL], list(reversed(pool)))

        assert first.additions == second.additions == ["aaa_tool"]

    def test_a_kept_tool_needing_what_it_yields_does_not_count_as_a_source(self) -> None:
        """It cannot run either, so it sources nothing for anyone else.

        ``_discoverable_sources`` and ``_best_provider`` must share one
        definition of "source"; when only the selection applied this rule, a
        stuck read-only tool already in the catalogue silently marked another
        consumer's requirement as satisfied (e.g. a fetch tool needing a URL to
        yield a URL).
        """
        stuck_reader = _read(
            "stuck_reader_tool",
            params=[_Param("dep", "message_id", required=True)],
            outputs=[_Output("out", "message_id")],
        )

        result = resolve_closure_additions([REPLY_EMAIL, stuck_reader], EMAIL_POOL)

        assert result.additions == ["get_emails_tool"]

    def test_a_provider_that_requires_what_it_provides_is_not_eligible(self) -> None:
        """It would be just as stuck as the tool we are trying to unblock."""
        stuck = _read(
            "stuck_tool",
            params=[_Param("message_id", "message_id", required=True)],
            outputs=[_Output("x", "message_id")],
        )

        result = resolve_closure_additions([REPLY_EMAIL], [REPLY_EMAIL, stuck])

        assert not result.additions

    def test_no_provider_in_the_active_domains_is_reported_not_crashed(self) -> None:
        """The manifests simply cannot express this dependency — stay silent."""
        result = resolve_closure_additions([REPLY_EMAIL], [REPLY_EMAIL])

        assert not result.additions
        assert result.consumers == {"reply_email_tool"}


@pytest.mark.unit
class TestBoundsAndDegenerateInputs:
    def test_a_chain_of_dependencies_is_resolved_across_rounds(self) -> None:
        """A pulled provider may itself need a handle."""
        level_two = _read("level_two_tool", outputs=[_Output("x", "level_one")])
        level_one = _read(
            "level_one_tool",
            params=[_Param("dep", "level_one", required=True)],
            outputs=[_Output("y", "message_id")],
        )

        result = resolve_closure_additions([REPLY_EMAIL], [REPLY_EMAIL, level_one, level_two])

        assert result.additions == ["level_one_tool", "level_two_tool"]

    def test_a_mutual_dependency_terminates_without_looping(self) -> None:
        """Two tools each requiring what the other provides.

        The closure guarantees that a declared source is PRESENT, not that an
        execution order exists: it adds the partner (a legitimate source, since
        it does not require the type it yields) and stops. Detecting the
        deadlock would need a topological pass over the catalogue — no manifest
        exhibits one today, and the round bound keeps this terminating.
        """
        left = _read(
            "left_tool",
            params=[_Param("p", "right_type", required=True)],
            outputs=[_Output("o", "left_type")],
        )
        right = _read(
            "right_tool",
            params=[_Param("p", "left_type", required=True)],
            outputs=[_Output("o", "right_type")],
        )

        result = resolve_closure_additions([left], [left, right])

        assert result.additions == ["right_tool"]
        assert result.consumers == {"left_tool"}

    def test_the_round_bound_caps_a_dependency_chain(self) -> None:
        """A chain longer than the bound stops rather than resolving forever."""
        chain = [
            _read(
                f"chain_{index}_tool",
                params=[_Param("p", f"type_{index + 1}", required=True)],
                outputs=[_Output("o", f"type_{index}")],
            )
            for index in range(MAX_CLOSURE_ROUNDS + 3)
        ]
        head = _read(
            "head_tool",
            params=[_Param("p", "type_0", required=True)],
            outputs=[_Output("o", "head_type")],
        )

        result = resolve_closure_additions([head], [head, *chain])

        assert len(result.additions) <= MAX_CLOSURE_ROUNDS

    def test_an_empty_catalogue_is_already_closed(self) -> None:
        assert not resolve_closure_additions([], EMAIL_POOL).additions

    def test_a_manifest_without_parameters_or_outputs_is_harmless(self) -> None:
        bare = _Manifest("bare_tool", "email_agent", "search")

        assert not resolve_closure_additions([bare], [bare]).additions
