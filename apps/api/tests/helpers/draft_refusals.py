"""Assert the separate machine disposition and human explanation of a draft refusal."""

from src.domains.agents.services.draft_execution_result import DraftExecutionResult


def draft_refusal_code(result: DraftExecutionResult) -> str:
    """Keep refusal assertions on the code without letting the card show that code."""
    assert not result.success
    assert isinstance(result.result_data, dict)
    code = result.result_data.get("error_code")
    assert isinstance(code, str) and code
    assert result.error and result.error != code
    return code
