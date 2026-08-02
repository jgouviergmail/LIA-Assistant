"""The safety net asks a question; it never shows its diagnosis.

When a MUTATION plan exhausts its auto-replans, ``semantic_validator_node``
routes to a HITL clarification rather than executing a still-invalid mutation.
The question it asks used to be the issue's own ``description`` — English
technical literals meant for the trace. Production 2026-08-02 delivered
"for_each pattern issue detected" and a fabricated e-mail address to a French
account, 4 times in 30 days.

These tests pin the assembly: one localized question per issue TYPE, in the
user's language, deduplicated and capped.
"""

from __future__ import annotations

import pytest

from src.core.i18n_hitl import HitlMessages
from src.domains.agents.nodes.semantic_validator_node import _questions_for_issues
from src.domains.agents.orchestration.validation_models import (
    SemanticIssue,
    SemanticIssueType,
)

pytestmark = pytest.mark.unit


def _issue(
    issue_type: SemanticIssueType, description: str = "internal english text"
) -> SemanticIssue:
    """An issue as the DETERMINISTIC rules build it: technical, not showable.

    ``user_facing=False`` is what those five sites now declare — see
    ``TestALocalizedDescriptionIsPreferred`` for the LLM path, whose
    descriptions are localized and specific and must survive untouched.
    """
    return SemanticIssue(
        issue_type=issue_type, description=description, severity="high", user_facing=False
    )


class TestQuestionsForIssues:
    def test_asks_the_localized_question_not_the_description(self) -> None:
        """The regression itself: the description must never reach the user."""
        issues = [
            _issue(
                SemanticIssueType.FOR_EACH_MISSING_CARDINALITY, "for_each pattern issue detected"
            )
        ]

        questions = _questions_for_issues(issues, "fr")

        assert questions == [
            HitlMessages.get_semantic_issue_question("for_each_missing_cardinality", "fr")
        ]
        assert "for_each pattern issue detected" not in questions

    def test_uses_the_user_language(self) -> None:
        issues = [_issue(SemanticIssueType.CARDINALITY_MISMATCH)]

        assert _questions_for_issues(issues, "de") == [
            HitlMessages.get_semantic_issue_question("cardinality_mismatch", "de")
        ]

    def test_two_issues_of_the_same_type_ask_once(self) -> None:
        """Repeating the same question reads like a bug to the user."""
        issues = [
            _issue(SemanticIssueType.CARDINALITY_MISMATCH),
            _issue(SemanticIssueType.CARDINALITY_MISMATCH, "another wording"),
        ]

        assert len(_questions_for_issues(issues, "fr")) == 1

    def test_distinct_types_ask_distinct_questions_in_order(self) -> None:
        issues = [
            _issue(SemanticIssueType.WRONG_PARAMETERS),
            _issue(SemanticIssueType.MISSING_STEP),
        ]

        questions = _questions_for_issues(issues, "fr")

        assert questions == [
            HitlMessages.get_semantic_issue_question("wrong_parameters", "fr"),
            HitlMessages.get_semantic_issue_question("missing_step", "fr"),
        ]

    def test_capped_at_three_distinct_questions(self) -> None:
        """A wall of questions is not a clarification."""
        issues = [
            _issue(SemanticIssueType.WRONG_PARAMETERS),
            _issue(SemanticIssueType.MISSING_STEP),
            _issue(SemanticIssueType.SCOPE_OVERFLOW),
            _issue(SemanticIssueType.LOGICAL_CYCLE),
        ]

        assert len(_questions_for_issues(issues, "fr")) == 3

    def test_no_issue_yields_no_question(self) -> None:
        assert _questions_for_issues([], "fr") == []

    def test_tolerates_a_mapping_shaped_issue(self) -> None:
        """State that crossed a checkpoint can hand back plain mappings."""
        assert _questions_for_issues([{"issue_type": "cardinality_mismatch"}], "fr") == [
            HitlMessages.get_semantic_issue_question("cardinality_mismatch", "fr")
        ]

    def test_unknown_type_still_asks_something(self) -> None:
        """Never an empty prompt, even for a type nobody mapped."""
        questions = _questions_for_issues([{"issue_type": "brand_new_type"}], "fr")

        assert len(questions) == 1
        assert questions[0].strip().endswith("?")


class TestALocalizedDescriptionIsPreferred:
    """The LLM path writes a SPECIFIC description in the user's language.

    ``SemanticIssue.description`` is contractually "in user's language", and the
    LLM honours it: "La date de début est incorrecte (samedi 18 à 9h30
    demandé)" tells the user far more than any generic question could. Only the
    five PROGRAMMATIC rejections break that contract — English technical
    literals — and they now say so with ``user_facing=False``.
    """

    def test_a_user_facing_description_is_used_as_is(self) -> None:
        issue = SemanticIssue(
            issue_type=SemanticIssueType.WRONG_PARAMETERS,
            description="La date de début est incorrecte (samedi 18 à 9h30 demandé).",
            severity="high",
        )

        assert _questions_for_issues([issue], "fr") == [
            "La date de début est incorrecte (samedi 18 à 9h30 demandé)."
        ]

    def test_a_technical_description_is_replaced_by_the_localized_question(self) -> None:
        issue = SemanticIssue(
            issue_type=SemanticIssueType.WRONG_PARAMETERS,
            description="Fabricated placeholder contact detail: step_2.to='x@example.com'",
            severity="high",
            user_facing=False,
        )

        questions = _questions_for_issues([issue], "fr")

        assert questions == [HitlMessages.get_semantic_issue_question("wrong_parameters", "fr")]
        assert "example.com" not in questions[0]

    def test_an_empty_description_falls_back_to_the_question(self) -> None:
        issue = SemanticIssue(
            issue_type=SemanticIssueType.MISSING_STEP, description="   ", severity="high"
        )

        assert _questions_for_issues([issue], "fr") == [
            HitlMessages.get_semantic_issue_question("missing_step", "fr")
        ]

    def test_default_is_user_facing_so_the_llm_path_is_unchanged(self) -> None:
        """No opt-in required: only the programmatic sites declare otherwise."""
        assert (
            SemanticIssue(issue_type=SemanticIssueType.MISSING_STEP, description="d").user_facing
            is True
        )


class TestExhaustedMutationAsksInTheUserLanguage:
    """End-to-end reproduction of the reported defect, through the real node.

    A mutation plan carrying a fabricated address exhausts its auto-replans:
    the safety net reroutes to a clarification rather than executing it. What
    the user must receive is a question in their language — NOT
    ``Fabricated placeholder contact detail: step_2.to='jerome@example.com'``,
    which is what production delivered on 2026-08-02.
    """

    async def test_the_user_gets_a_question_not_the_diagnosis(self) -> None:
        from src.core.config import settings
        from src.domains.agents.nodes.semantic_validator_node import semantic_validator_node
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )

        plan = ExecutionPlan(
            plan_id="p1",
            user_id="u1",
            session_id="s1",
            steps=[
                ExecutionStep(
                    step_id="step_1",
                    step_type=StepType.TOOL,
                    agent_name="contacts_agent",
                    tool_name="get_contacts_tool",
                    parameters={"query": "Jerome"},
                ),
                ExecutionStep(
                    step_id="step_2",
                    step_type=StepType.TOOL,
                    agent_name="emails_agent",
                    tool_name="send_email_tool",
                    parameters={"to": "jerome@example.com", "subject": "s", "body": "b"},
                ),
            ],
        )
        state = {
            "execution_plan": plan,
            "user_language": "fr",
            # One below the bypass threshold: the next increment exhausts it.
            "planner_iteration": settings.planner_max_replans,
            "messages": [],
            "original_query": "envoie un email à Jérôme",
        }

        result = await semantic_validator_node(state, None)
        verdict = result["semantic_validation"]

        assert verdict.requires_clarification, "an invalid mutation must ask, never execute"
        questions = verdict.clarification_questions
        assert questions, "the user must be given something to answer"

        joined = " ".join(questions)
        # The exact strings production leaked.
        assert "example.com" not in joined, "a fabricated address must never be shown"
        assert "step_2" not in joined, "no implementation path in a user-facing question"
        assert "Fabricated" not in joined and "placeholder" not in joined
        # And it must be French, the account's language.
        assert joined == " ".join(
            HitlMessages.get_semantic_issue_question(
                (
                    issue.issue_type.value
                    if hasattr(issue.issue_type, "value")
                    else str(issue.issue_type)
                ),
                "fr",
            )
            for issue in verdict.issues[:3]
        )


class TestTheUserIsNeverAskedTheSameThingTwice:
    """Distinct diagnoses can map to one question — that is the whole point.

    ``cardinality_mismatch`` and ``for_each_missing_cardinality`` are two ways of
    detecting "did you mean one or all of them?". Deduplicating per issue TYPE
    let both through and the user read the identical sentence twice, which reads
    as a bug in the assistant.
    """

    def test_two_types_sharing_a_question_are_asked_once(self) -> None:
        questions = _questions_for_issues(
            [
                _issue(SemanticIssueType.CARDINALITY_MISMATCH, "Plan processes only one"),
                _issue(
                    SemanticIssueType.FOR_EACH_MISSING_CARDINALITY,
                    "for_each pattern issue detected",
                ),
            ],
            "fr",
        )

        assert len(questions) == 1, f"the same sentence was asked twice: {questions}"

    def test_two_distinct_llm_descriptions_of_one_type_both_survive(self) -> None:
        """They carry different information; collapsing them would lose one."""
        questions = _questions_for_issues(
            [
                SemanticIssue(
                    issue_type=SemanticIssueType.WRONG_PARAMETERS,
                    description="La date de début est incorrecte (samedi 18 à 9h30 demandé)",
                    severity="high",
                ),
                SemanticIssue(
                    issue_type=SemanticIssueType.WRONG_PARAMETERS,
                    description="Le lieu ne correspond pas à celui demandé",
                    severity="high",
                ),
            ],
            "fr",
        )

        assert len(questions) == 2
