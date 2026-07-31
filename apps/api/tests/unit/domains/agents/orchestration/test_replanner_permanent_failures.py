"""A failure that cannot succeed on a retry must not be called transient.

Production, 2026-07-30: a plan named `search_emails_tool`, a tool with no
catalogue manifest. The validator answered NOT_FOUND, the step failed with
`ToolManifestNotFound`, and the replanner concluded:

    "Steps ['search_emails_tool'] failed; failure looks transient
     (would warrant a retry)."

Replaying that plan byte-for-byte cannot ever succeed: the manifest will still
be missing. The assessment was not merely useless — it was false, and it is
what the operator reads in the logs while hunting the real cause.

The distinction this pins is between failures whose cause is OUTSIDE the plan
(timeout, upstream 5xx, rate limit — a retry is a reasonable bet) and failures
whose cause IS the plan (a tool that does not exist, a capability the account
is not allowed to use). Only the former warrant "retry the same thing".
"""

from unittest.mock import MagicMock

import pytest

from src.domains.agents.orchestration.adaptive_replanner import (
    AdaptiveRePlanner,
    ExecutionAnalysis,
    RePlanContext,
    RePlanDecision,
    StepAnalysis,
)

# Errors whose cause is the plan itself — a rerun reproduces them exactly.
PERMANENT_ERRORS = [
    "Tool manifest not found: search_emails_tool",
    "Tool 'search_emails_tool' not found in catalogue",
    "Missing required scopes: https://www.googleapis.com/auth/calendar",
    "UNAUTHORIZED: the user has not authorized this capability",
]

# Errors whose cause is outside the plan — retrying is a reasonable bet.
TRANSIENT_ERRORS = [
    "Timeout after 30s",
    "Upstream returned 503 Service Unavailable",
    "Rate limit exceeded, retry later",
    "Connection reset by peer",
]


def _context(error: str, attempt: int = 0) -> RePlanContext:
    """One failed step carrying `error`, at the given replan attempt."""
    step = StepAnalysis(
        step_id="step_1",
        tool_name="search_emails_tool",
        success=False,
        has_results=False,
        result_count=0,
        error=error,
        execution_time_ms=12,
    )
    analysis = ExecutionAnalysis(
        total_steps=1,
        completed_steps=1,
        successful_steps=0,
        failed_steps=1,
        empty_steps=0,
        total_results=0,
        execution_time_ms=12,
        step_analyses=[step],
    )
    return RePlanContext(
        user_request="Summarize the email X and propose a reply",
        user_language="fr",
        execution_plan=MagicMock(),
        plan_id="smart_unknown",
        completed_steps={},
        execution_analysis=analysis,
        replan_attempt=attempt,
        max_attempts=2,
    )


@pytest.fixture
def replanner() -> AdaptiveRePlanner:
    return AdaptiveRePlanner()


@pytest.mark.parametrize("error", PERMANENT_ERRORS)
def test_a_permanent_failure_is_never_answered_with_retry_same(replanner, error):
    """The production case: replaying the same plan cannot change the outcome."""
    decision, _, reason, _ = replanner._handle_partial_failure(_context(error))

    assert decision is not RePlanDecision.RETRY_SAME
    assert "transient" not in reason.lower()


@pytest.mark.parametrize("error", TRANSIENT_ERRORS)
def test_a_transient_failure_still_warrants_a_retry(replanner, error):
    """The existing behaviour must survive: this is the case retry was built for."""
    decision, _, reason, _ = replanner._handle_partial_failure(_context(error))

    assert decision is RePlanDecision.RETRY_SAME
    assert "transient" in reason.lower()


def test_the_permanent_reason_names_the_tool_and_the_cause(replanner):
    """The log line is what an operator reads while hunting the cause."""
    _, _, reason, _ = replanner._handle_partial_failure(
        _context("Tool manifest not found: search_emails_tool")
    )

    assert "search_emails_tool" in reason
    assert "retry" not in reason.lower() or "not" in reason.lower()


def test_an_unknown_error_keeps_the_conservative_retry(replanner):
    """Unclassifiable failures keep the historical benefit of the doubt."""
    decision, _, _, _ = replanner._handle_partial_failure(_context("something odd happened"))

    assert decision is RePlanDecision.RETRY_SAME


def test_a_missing_error_string_does_not_crash_the_classification(replanner):
    """A failed step may carry no error text at all."""
    decision, _, _, _ = replanner._handle_partial_failure(_context(""))

    assert decision is RePlanDecision.RETRY_SAME


def test_later_attempts_are_unchanged_for_permanent_failures(replanner):
    """Attempt 1 already declines to retry — the fix must not regress it."""
    decision, _, _, _ = replanner._handle_partial_failure(
        _context("Tool manifest not found: x", attempt=1)
    )

    assert decision is RePlanDecision.REPLAN_MODIFIED
