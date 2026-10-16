"""What a ReAct sub-loop's recursion limit buys, in model calls and tool rounds (ADR-083).

LangGraph's ``recursion_limit`` counts graph STEPS, not model calls: one round is a
model call then a tool call, two steps. Measured on 2026-10-13 against the installed
``create_react_agent`` (langgraph-prebuilt 1.1.0) with a model that always asks for
a tool:

- an EVEN limit R makes R/2 model calls, and the prebuilt guard REPLACES the last
  one's answer with its own sentence (« Sorry, need more steps to process this
  request. ») — every result the loop gathered is lost;
- an ODD limit raises ``GraphRecursionError`` after (R+1)/2 calls.

``ReactSubAgentRunner`` therefore hands the model no tool once fewer than
``CLOSING_BELOW_REMAINING_STEPS`` steps remain: every limit of 2 or more then ends
on a closing call, after ``model_calls_for(R)`` calls of which
``tool_rounds_for(R)`` ran tools. A limit of 1 cannot end at all — its first call
lands on the last step.

The runner now uses native ``create_agent`` with model middleware. Its managed
step counter adds no node, so the same arithmetic holds. A closing reply that
still proposes a call is EMPTY, never a successful promise or another tool run.

Pure arithmetic, importing nothing: the planner prompt and the delegation tool
publish these numbers, so they read them here rather than from the runner.
"""

#: The managed ``remaining_steps`` value below which a call is the closing pass.
#: The prebuilt guard fires below 2, which an even limit reaches on a model call;
#: on an odd limit the call at 2 would be followed by a tool step and a model call
#: on the very last step, which raises. Closing below 3 covers both parities.
CLOSING_BELOW_REMAINING_STEPS = 3


def model_calls_for(recursion_limit: int) -> int:
    """The most model calls a sub-loop of this recursion limit makes.

    Args:
        recursion_limit: The loop's LangGraph recursion limit, in steps.

    Returns:
        The model calls, its closing pass included (0 when no call can end).
    """
    return max(recursion_limit // 2, 0)


def tool_rounds_for(recursion_limit: int) -> int:
    """The most rounds of tool calls before the closing pass.

    Args:
        recursion_limit: The loop's LangGraph recursion limit, in steps.

    Returns:
        The tool rounds (0 when the first call is already the closing pass).
    """
    return max(recursion_limit // 2 - 1, 0)
