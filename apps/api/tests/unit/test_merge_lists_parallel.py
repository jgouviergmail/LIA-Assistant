"""
Regression tests for merge_lists parallel tool calls fix.

Bug (langchain-core < 1.2.14): merge_lists incorrectly merged parallel tool
calls sharing the same index but with different IDs, concatenating string
fields instead of appending as separate entries.

Fix (langchain-core >= 1.2.14): Tool calls with different IDs are appended,
not merged, even when sharing the same index.
"""

import pytest


@pytest.mark.unit
class TestMergeListsParallelToolCalls:

    def test_parallel_tool_calls_not_merged(self):
        """
        Regression test for langchain-core 1.2.14 fix.

        Bug: merge_lists incorrectly merged parallel tool calls sharing
        the same index but with different IDs, concatenating string fields.
        Fix: Tool calls with different IDs are appended, not merged.
        """
        from langchain_core.utils._merge import merge_lists

        # Two parallel tool call chunks with same index=0 but different IDs
        left = [{"index": 0, "type": "tool_use", "id": "call_abc", "name": "search"}]
        right = [{"index": 0, "type": "tool_use", "id": "call_xyz", "name": "fetch"}]

        result = merge_lists(left, right)

        # After fix: should be 2 separate entries
        assert len(result) == 2
        ids = {item["id"] for item in result}
        assert ids == {"call_abc", "call_xyz"}

    def test_same_tool_call_chunks_still_merge(self):
        """Streaming chunks of the SAME tool call should still merge correctly."""
        from langchain_core.utils._merge import merge_lists

        # Two chunks of the same tool call (same ID)
        left = [
            {
                "index": 0,
                "type": "tool_use",
                "id": "call_abc",
                "name": "search",
                "input": '{"q',
            }
        ]
        right = [{"index": 0, "type": "tool_use", "id": "call_abc", "input": 'uery":"test"}'}]

        result = merge_lists(left, right)

        # Should merge into single entry
        assert len(result) == 1
        assert result[0]["id"] == "call_abc"
        assert result[0]["input"] == '{"query":"test"}'
