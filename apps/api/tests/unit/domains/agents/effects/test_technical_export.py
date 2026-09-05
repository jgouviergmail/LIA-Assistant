"""The technical register names nobody — by construction (ADR-263).

The decisive test in this file is the NEGATIVE one: a column added to the
model tomorrow must be ABSENT from the export until somebody decides
otherwise. A denylist would leak it on the day it lands; an allowlist cannot.

Everything else follows from the same idea: identifiers become keyed handles
(stable inside the deployment, meaningless outside), and the two columns that
carry content — the label and the result — are never exported at all.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from src.domains.agents.effects.models import AgentEffect
from src.domains.agents.effects.technical_export import (
    EXPORTED_COLUMNS,
    FORBIDDEN_COLUMNS,
    export_header,
    pseudonymise,
    render_jsonl,
    technical_row,
)

pytestmark = [pytest.mark.unit]


def _effect(**overrides: Any) -> Any:
    row = {
        "id": uuid.uuid4(),
        "schema_version": 1,
        "user_id": uuid.uuid4(),
        "thread_id": "conversation-42",
        "run_id": "run-42",
        "idempotency_key": "step:s1",
        "tool_name": "control_hue_light_tool",
        "mutation_policy": "reversible",
        "status": SimpleNamespace(value="succeeded"),
        "source": SimpleNamespace(value="user"),
        "execution_mode": "pipeline",
        "approval_kind": None,
        "error_code": None,
        "args_digest": "d" * 64,
        "draft_digest": None,
        "result_truncated": False,
        "claimed_at": datetime(2026, 9, 4, 10, 0, tzinfo=UTC),
        "closed_at": datetime(2026, 9, 4, 10, 0, 1, tzinfo=UTC),
        "label": "ENCRYPTED-LABEL-NAMING-MARIE",
        "result_payload": "ENCRYPTED-RESULT-QUOTING-A-THIRD-PARTY",
        "provider_ref": "gmail-message-id-1234",
        "claim_token": uuid.uuid4(),
    }
    row.update(overrides)
    return SimpleNamespace(**row)


class TestNothingIdentifyingLeaves:
    def test_no_forbidden_column_appears(self) -> None:
        row = technical_row(_effect())

        assert not set(row) & FORBIDDEN_COLUMNS

    def test_the_content_columns_appear_nowhere_in_the_file(self) -> None:
        """Not as a key, not as a value — the strongest form of the check."""
        effect = _effect()
        rendered = render_jsonl(
            [technical_row(effect)],
            export_header(row_count=1, cap=10, filters={}, generated_at=datetime.now(UTC)),
        )

        assert "ENCRYPTED-LABEL-NAMING-MARIE" not in rendered
        assert "ENCRYPTED-RESULT-QUOTING-A-THIRD-PARTY" not in rendered
        assert "gmail-message-id-1234" not in rendered
        assert str(effect.user_id) not in rendered
        assert str(effect.claim_token) not in rendered
        assert "conversation-42" not in rendered

    def test_an_unknown_column_added_tomorrow_does_not_leak(self) -> None:
        """THE guard: the allowlist decides, so a new column is absent."""
        effect = _effect()
        effect.newly_added_column = "a phone number nobody thought about"

        row = technical_row(effect)

        assert "newly_added_column" not in row
        assert "phone number" not in json.dumps(row)

    def test_the_allowlist_and_the_forbidden_list_never_overlap(self) -> None:
        assert not set(EXPORTED_COLUMNS) & FORBIDDEN_COLUMNS

    def test_every_forbidden_column_actually_exists_on_the_model(self) -> None:
        """A stale entry would advertise a protection that protects nothing."""
        columns = set(AgentEffect.__table__.columns.keys())
        stale = sorted(FORBIDDEN_COLUMNS - columns)

        assert not stale, f"{stale} no longer exist on the model — update the list"

    def test_every_exported_column_exists_on_the_model(self) -> None:
        columns = set(AgentEffect.__table__.columns.keys())
        missing = sorted(set(EXPORTED_COLUMNS) - columns)

        assert not missing, f"{missing} are exported but do not exist"

    def test_every_model_column_is_classified(self) -> None:
        """No column may be neither exported nor explicitly excluded.

        This is what makes the allowlist a DECISION rather than an oversight:
        adding a column to the model forces a choice here.
        """
        columns = set(AgentEffect.__table__.columns.keys())
        unclassified = sorted(columns - set(EXPORTED_COLUMNS) - FORBIDDEN_COLUMNS)

        assert not unclassified, (
            f"{unclassified} are neither exported nor forbidden. Decide: add them to "
            "EXPORTED_COLUMNS, or to FORBIDDEN_COLUMNS with the reason."
        )


class TestThePseudonymsAreUsable:
    def test_the_same_identifier_yields_the_same_handle(self) -> None:
        """Grouping one account's rows must stay possible."""
        identifier = uuid.uuid4()

        assert pseudonymise(identifier) == pseudonymise(identifier)

    def test_two_identifiers_do_not_collide(self) -> None:
        assert pseudonymise(uuid.uuid4()) != pseudonymise(uuid.uuid4())

    def test_a_handle_is_not_the_identifier(self) -> None:
        identifier = uuid.uuid4()

        assert str(identifier) not in str(pseudonymise(identifier))

    def test_nothing_to_name_yields_nothing(self) -> None:
        assert pseudonymise(None) is None

    def test_a_row_keeps_its_correlation_handles(self) -> None:
        first = technical_row(_effect(run_id="run-A"))
        second = technical_row(_effect(run_id="run-A"))

        assert first["run_id"] == second["run_id"] is not None


class TestTheFileSaysWhatItIs:
    def test_the_header_states_the_cap_and_the_truncation(self) -> None:
        header = export_header(
            row_count=500, cap=500, filters={"status": "failed"}, generated_at=datetime.now(UTC)
        )

        assert header["truncated"] is True
        assert header["row_cap"] == 500
        assert header["filters"] == {"status": "failed"}

    def test_a_complete_export_says_so(self) -> None:
        header = export_header(row_count=3, cap=500, filters={}, generated_at=datetime.now(UTC))

        assert header["truncated"] is False

    def test_the_header_lists_what_it_excludes(self) -> None:
        header = export_header(row_count=0, cap=1, filters={}, generated_at=datetime.now(UTC))

        assert set(header["excluded_columns"]) == FORBIDDEN_COLUMNS
        assert header["pseudonymised"] is True

    def test_the_file_is_one_json_object_per_line(self) -> None:
        rendered = render_jsonl(
            [technical_row(_effect()), technical_row(_effect())],
            export_header(row_count=2, cap=10, filters={}, generated_at=datetime.now(UTC)),
        )
        lines = rendered.strip().split("\n")

        assert len(lines) == 3  # header + two rows
        for line in lines:
            assert isinstance(json.loads(line), dict)

    def test_an_empty_export_still_carries_its_header(self) -> None:
        rendered = render_jsonl(
            [], export_header(row_count=0, cap=10, filters={}, generated_at=datetime.now(UTC))
        )

        assert len(rendered.strip().split("\n")) == 1


class TestBothRegistersObeyTheSameContract:
    """The guard applies to EVERY spec, not to the one that came first.

    The consultation register was added to the technical export by extending
    the renderer rather than copying it. A guard covering only the original
    would leave the copy's columns unclassified — which is exactly how a
    denylist-shaped hole appears in an allowlist-shaped design.
    """

    @staticmethod
    def _model(spec: object) -> object:
        # The spec says where its class lives; a guard resolving it itself
        # would be a second reader of the same declaration.
        from src.domains.agents.effects.technical_export import spec_model

        return spec_model(spec)  # type: ignore[arg-type]

    def test_every_spec_classifies_every_column_of_its_model(self) -> None:
        from src.domains.agents.effects.technical_export import TECHNICAL_SPECS

        for name, spec in TECHNICAL_SPECS.items():
            columns = set(self._model(spec).__table__.columns.keys())
            unclassified = sorted(columns - set(spec.exported) - spec.forbidden)
            assert not unclassified, (
                f"{name}: {unclassified} are neither exported nor forbidden. Decide: "
                "add them to the spec's allowlist, or to its forbidden set with the reason."
            )

    def test_no_spec_exports_a_column_it_also_forbids(self) -> None:
        from src.domains.agents.effects.technical_export import TECHNICAL_SPECS

        for name, spec in TECHNICAL_SPECS.items():
            assert not set(spec.exported) & spec.forbidden, f"{name} contradicts itself"

    def test_no_spec_exports_a_column_its_model_does_not_have(self) -> None:
        from src.domains.agents.effects.technical_export import TECHNICAL_SPECS

        for name, spec in TECHNICAL_SPECS.items():
            columns = set(self._model(spec).__table__.columns.keys())
            missing = sorted(set(spec.exported) - columns)
            assert not missing, f"{name}: {missing} are exported but do not exist"

    def test_a_consultation_row_names_nobody(self) -> None:
        from datetime import UTC, datetime
        from types import SimpleNamespace

        from src.domains.agents.effects.technical_export import TREATMENTS_SPEC, technical_row

        row = technical_row(
            SimpleNamespace(
                id="11111111-1111-4111-8111-111111111111",
                user_id="22222222-2222-4222-8222-222222222222",
                thread_id="conv-7",
                run_id="run-7",
                source=SimpleNamespace(value="user"),
                execution_mode="react",
                tool_name="get_emails_tool",
                mutation_policy="read",
                outcome=SimpleNamespace(value="ok"),
                duration_ms=142,
                occurred_at=datetime(2026, 9, 4, tzinfo=UTC),
            ),
            TREATMENTS_SPEC,
        )

        assert "user_id" not in row
        assert row["user"] and row["user"] != "22222222-2222-4222-8222-222222222222"
        assert row["thread_id"] != "conv-7", "a conversation id reconstructs someone's day"
        assert row["run_id"] != "run-7"
        assert row["tool_name"] == "get_emails_tool"
        assert row["outcome"] == "ok"
        # A consultation carries no provider reference: inventing the field
        # would advertise a correlation handle that stands for nothing.
        assert "provider_fingerprint" not in row


class TestAHeaderNeverStatesAFilterTheQueryIgnored:
    """A file that says it was filtered, and was not, is worse than an
    unfiltered one: a reader draws conclusions from an absence that is an
    artefact of the request rather than of the data (ADR-184 — whatever a layer
    enforces, its caller must be able to read).
    """

    def test_each_register_declares_what_it_can_be_asked(self) -> None:
        from src.domains.agents.effects.technical_export import TECHNICAL_SPECS

        assert TECHNICAL_SPECS["actions"].filters == {
            "tool_name",
            "mutation_policy",
            "status",
            "source",
            "execution_mode",
        }
        assert TECHNICAL_SPECS["consultations"].filters == {"tool_name"}
        assert TECHNICAL_SPECS["decisions"].filters == frozenset()

    def test_a_filter_a_register_cannot_honour_is_REPORTED(self) -> None:
        from src.domains.agents.effects.admin_router import _stated_query
        from src.domains.agents.effects.technical_reads import TechnicalQuery

        asked = TechnicalQuery(
            register="decisions",
            since=None,
            until=None,
            user_ids=None,
            tool_name="send_email_tool",
            mutation_policy=None,
            status=None,
            source=None,
            execution_mode=None,
        )

        stated = _stated_query(asked)

        assert stated["tool_name"] is None, "the header claimed a filter nobody applied"
        assert stated["ignored_filters"] == ["tool_name"]

    def test_a_filter_the_register_HONOURS_is_stated(self) -> None:
        from src.domains.agents.effects.admin_router import _stated_query
        from src.domains.agents.effects.technical_reads import TechnicalQuery

        asked = TechnicalQuery(
            register="consultations",
            since=None,
            until=None,
            user_ids=None,
            tool_name="get_emails_tool",
            mutation_policy=None,
            status=None,
            source=None,
            execution_mode=None,
        )

        stated = _stated_query(asked)

        assert stated["tool_name"] == "get_emails_tool"
        assert stated["ignored_filters"] == []

    def test_an_unasked_filter_is_never_reported_as_ignored(self) -> None:
        """Listing every inapplicable filter would drown the one that matters."""
        from src.domains.agents.effects.admin_router import _stated_query
        from src.domains.agents.effects.technical_reads import TechnicalQuery

        asked = TechnicalQuery(
            register="decisions",
            since=None,
            until=None,
            user_ids=None,
            tool_name=None,
            mutation_policy=None,
            status=None,
            source=None,
            execution_mode=None,
        )

        assert _stated_query(asked)["ignored_filters"] == []

    def test_every_declared_filter_is_a_real_query_parameter(self) -> None:
        """A spec naming a filter the route never accepts would be a contract
        with nobody on the other side."""
        import inspect

        from src.domains.agents.effects.admin_router import export_technical
        from src.domains.agents.effects.technical_export import TECHNICAL_SPECS

        accepted = set(inspect.signature(export_technical).parameters)
        for name, spec in TECHNICAL_SPECS.items():
            assert (
                spec.filters <= accepted
            ), f"{name} declares a filter the route has no parameter for"


class TestEverySpecIsREACHABLE:
    """A contract the route cannot accept is a capability nobody can use.

    Caught live during the lot-8 review: ``inference`` had a read branch and no
    value in the route's ``Literal`` (every request 422'd), while ``integrity``
    had a contract and no branch at all. Both halves looked done from their own
    side. The guard below reads the route's own signature, so a spec added
    without its two other halves fails the build rather than the user.
    """

    @staticmethod
    def _accepted_registers() -> set[str]:
        from src.domains.agents.effects.admin_router import export_technical
        from tests.unit.domains.agents.effects.route_vocabulary import literal_values

        return literal_values(export_technical, "register")

    def test_the_guard_reads_something(self) -> None:
        assert self._accepted_registers(), "the route's register vocabulary is unreadable"

    def test_every_declared_spec_is_accepted_by_the_route(self) -> None:
        from src.domains.agents.effects.technical_export import TECHNICAL_SPECS

        missing = sorted(set(TECHNICAL_SPECS) - self._accepted_registers())

        assert not missing, (
            f"{missing} declare an export contract the route refuses. Add the value to "
            "the Literal AND a read branch, or the capability is unreachable."
        )

    def test_every_accepted_value_has_a_contract(self) -> None:
        from src.domains.agents.effects.technical_export import TECHNICAL_SPECS

        orphans = sorted(self._accepted_registers() - set(TECHNICAL_SPECS))

        assert not orphans, f"{orphans} are accepted by the route and describe nothing"

    def test_every_accepted_value_has_a_READ_branch(self) -> None:
        """The third half. A value the route accepts and the dispatch ignores
        silently falls through to whichever branch is last."""
        import inspect

        from src.domains.agents.effects.technical_reads import read_register

        source = inspect.getsource(read_register)
        for register in self._accepted_registers():
            assert f'"{register}"' in source or register == "consultations", (
                f"{register} is accepted but has no branch — the dispatch would serve "
                "another register's rows under its name"
            )
