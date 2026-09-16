"""A tool result reaches the ReAct model item by item, under a token budget.

Measured on Docker dev, 2026-09-15 (thread ``35e9301b…``, « recherche mes 5
derniers emails »): ``extract_data_for_llm`` dumped ``structured_data`` to JSON
and cut the STRING at 8 000 characters. Each Gmail ``format=full`` message
carries its raw provider tree (SMTP headers, MIME parts, base64 body — 85 to
98 % of the item, 12 000 to 130 000 characters), placed BEFORE the readable
fields in key order. So the 8 000 characters were spent on the first item's
``Received`` / ``ARC-Seal`` headers and base64, and the model read **zero**
``subject``, ``message_id`` or ``date_formatted`` of any e-mail — its own
thought said « Payloads systématiquement tronqués après le 1er item ». Eleven
iterations, ~74 k tokens of context, a wrong answer on two entries out of five.

The contract pinned here (ADR-286):

- every item the budget admits is COMPLETE — the block is valid JSON, nothing
  is cut mid-item;
- the budget is TOKENS, the currency the model pays in, derived from the
  ReAct slot's own window (ADR-278) under an absolute ceiling;
- at least one item always reaches the model;
- a cut is STATED — count shown, count total, and what to do next — never
  silent (ADR-184: an enforced bound is a published bound);
- the cut is counted, per tool, so an operator can see a budget that is too
  small for a deployment's data.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest
from langchain_core.tools import BaseTool

from src.core.config import get_settings
from src.domains.agents.tools.mixins import ToolOutputMixin
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.react_tool_wrapper import (
    ReactToolWrapper,
    extract_data_for_llm,
    render_data_block,
)
from src.domains.agents.utils.react_budget import (
    tool_result_budget_note,
    tool_result_token_budget,
)
from src.infrastructure.observability.metrics_react import (
    react_tool_result_truncated_total,
)

pytestmark = [pytest.mark.unit]


class _StubTool(BaseTool):
    name: str = "get_emails_tool"
    description: str = "stub"

    def _run(self, **kwargs: Any) -> str:  # pragma: no cover - never invoked
        return ""


class _Builder(ToolOutputMixin):
    """Expose the mixin's builder without a connector tool around it."""


def _gmail_full_message(index: int, *, body_bytes: int = 8_000) -> dict[str, Any]:
    """One message shaped like ``users.messages.get?format=full`` — the raw tree
    the client returns and ``_enrich_email`` leaves in place."""
    headers = [
        {"name": "Delivered-To", "value": "someone@example.com"},
        *[
            {
                "name": "Received",
                "value": (
                    f"by 2002:a05:7208:300f:b0:10c:d2c0:d0c7 with SMTP id f{hop}csp5184218rba; "
                    "Tue, 15 Sep 2026 10:24:46 -0700 (PDT)"
                ),
            }
            for hop in range(4)
        ],
        {"name": "ARC-Seal", "value": "i=1; a=rsa-sha256; " + "T0Jw5gzr7hie52VfIUA2" * 20},
        {"name": "DKIM-Signature", "value": "v=1; a=rsa-sha256; " + "saCA5KVJOOeIm4Rs53W0" * 20},
        {"name": "From", "value": f"Sender {index} <sender{index}@example.com>"},
        {"name": "To", "value": "someone@example.com"},
        {"name": "Subject", "value": f"Sujet numero {index}"},
        {"name": "Date", "value": "Tue, 15 Sep 2026 10:24:45 -0700"},
    ]
    body = base64.urlsafe_b64encode(("lorem ipsum " * (body_bytes // 12)).encode()).decode()
    return {
        "id": f"1a0a6198{index:08x}",
        "threadId": f"1a0a6198{index:08x}",
        "labelIds": ["UNREAD", "INBOX"],
        "snippet": f"Snippet {index}",
        "payload": {
            "partId": "",
            "mimeType": "text/plain",
            "filename": "",
            "headers": headers,
            "body": {"size": body_bytes, "data": body},
        },
        "sizeEstimate": body_bytes,
        "historyId": "15472503",
        "internalDate": str(1_789_493_085_929 - index * 3_600_000),
        "body": f"Corps lisible {index}",
        "attachments": [],
    }


def _json_block(rendered: str) -> dict[str, Any]:
    """The Data block is one JSON line inside the external-content wrapper; an
    injection notice, when any, follows on the same line — hence ``raw_decode``."""
    line = next(line for line in rendered.splitlines() if line.startswith("{"))
    parsed, _ = json.JSONDecoder().raw_decode(line)
    return parsed


def _items(count: int, *, size: int) -> list[dict[str, Any]]:
    return [{"id": f"item_{i}", "text": f"{i}-" + "x " * size} for i in range(count)]


class TestEveryEmailReachesTheModel:
    def test_every_email_of_a_full_gmail_result_is_readable(self) -> None:
        """The measured defect: five real-shaped messages, all five readable."""
        emails = [_gmail_full_message(i) for i in range(1, 6)]
        output = _Builder().build_emails_output(
            emails=emails, query="in:inbox", user_timezone="Europe/Paris", locale="fr"
        )

        rendered = ReactToolWrapper(_StubTool())._process_result(output)

        block = _json_block(rendered)
        assert block["count"] == 5
        assert [e["subject"] for e in block["emails"]] == [f"Sujet numero {i}" for i in range(1, 6)]
        assert all(e["message_id"] and e["date_formatted"] for e in block["emails"])
        assert all(e["from"].startswith("Sender ") for e in block["emails"])

    def test_the_block_stays_valid_json_whatever_the_budget(self) -> None:
        """Whatever the budget, an admitted item is complete and the block parses."""
        emails = [_gmail_full_message(i) for i in range(1, 11)]
        output = _Builder().build_emails_output(emails=emails, user_timezone="UTC")
        for budget in (50, 300, 3_000, 25_000):
            rendered = ReactToolWrapper(_StubTool())._process_result(output, budget_tokens=budget)
            block = _json_block(rendered)
            assert block["count"] == 10
            assert 1 <= len(block["emails"]) <= 10
            assert all(
                "subject" in e for e in block["emails"]
            ), "an admitted item is complete, never cut mid-way"


class TestItemBoundary:
    def test_items_are_never_cut_mid_way(self) -> None:
        data = {"rows": _items(6, size=200), "count": 6, "query": "q"}
        block = render_data_block(data, budget_tokens=700)

        parsed = json.loads(block.text)
        assert 1 <= len(parsed["rows"]) < 6
        assert all(row["text"].endswith("x ") for row in parsed["rows"])
        assert parsed["rows_shown"] == len(parsed["rows"])
        assert parsed["count"] == 6, "the scalars travel whole — the total is exact"
        assert block.truncated is True
        assert (block.shown, block.total, block.key) == (len(parsed["rows"]), 6, "rows")

    def test_at_least_one_item_is_always_shown_and_whole(self) -> None:
        """A first item that alone exceeds the budget passes COMPLETE: a cut
        item is unusable to the model, an oversized one merely costs. Measured
        on a real mailbox (2026-09-15): a 1 500-character body over a 600-token
        budget, cut mid-JSON, was unparseable."""
        data = {"rows": _items(3, size=2_000), "count": 3}
        block = render_data_block(data, budget_tokens=50)

        parsed = json.loads(block.text)
        assert parsed["rows"] == data["rows"][:1]
        assert parsed["rows_shown"] == 1
        assert (block.shown, block.total, block.truncated) == (1, 3, True)
        assert block.used_tokens > block.budget_tokens

    def test_a_single_oversized_item_is_neither_cut_nor_reported_as_a_cut(self) -> None:
        data = {"rows": _items(1, size=2_000), "count": 1}
        block = render_data_block(data, budget_tokens=50)

        assert json.loads(block.text) == data
        assert block.truncated is False
        assert block.used_tokens > block.budget_tokens

    def test_under_budget_output_is_the_plain_dump(self) -> None:
        data = {"rows": _items(3, size=5), "count": 3, "query": "q"}
        block = render_data_block(data, budget_tokens=25_000)

        assert json.loads(block.text) == data
        assert block.truncated is False
        assert (block.shown, block.total) == (3, 3)

    def test_the_heaviest_list_is_the_one_paged(self) -> None:
        """A small ``errors`` list ahead of the rows must not be the one paged."""
        data = {"errors": [{"id": "e1"}], "rows": _items(6, size=200), "count": 6}
        block = render_data_block(data, budget_tokens=700)

        parsed = json.loads(block.text)
        assert block.key == "rows"
        assert parsed["errors"] == [{"id": "e1"}]
        assert 1 <= len(parsed["rows"]) < 6

    def test_key_order_is_preserved_and_the_count_sits_next_to_its_list(self) -> None:
        data = {"a": 1, "rows": _items(4, size=300), "z": "end"}
        block = render_data_block(data, budget_tokens=400)

        keys = list(json.loads(block.text).keys())
        assert keys == ["a", "rows", "rows_shown", "z"]

    def test_a_shape_without_an_item_list_is_cut_explicitly(self) -> None:
        data = {"content": "word " * 5_000}
        block = render_data_block(data, budget_tokens=200)

        assert block.truncated is True
        assert "[cut:" in block.text
        assert block.text.endswith(" tokens]"), block.text[-80:]

    def test_a_shape_without_an_item_list_under_budget_is_untouched(self) -> None:
        data = {"server_name": "x", "iterations": 2}
        block = render_data_block(data, budget_tokens=25_000)
        assert json.loads(block.text) == data
        assert block.truncated is False


class TestTheCutIsStated:
    def test_the_note_names_shown_total_and_the_way_out(self) -> None:
        note = tool_result_budget_note(shown=2, total=9, key="emails", budget_tokens=1_000)
        assert "2 of 9" in note
        assert "emails" in note
        assert "1000" in note
        assert "narrow" in note.lower()

    def test_the_tool_message_carries_the_note_outside_the_external_block(self) -> None:
        emails = [_gmail_full_message(i) for i in range(1, 11)]
        output = _Builder().build_emails_output(emails=emails, user_timezone="UTC")

        # ~120 tokens per item once the raw tree is gone (A2): 600 admits a few.
        rendered = ReactToolWrapper(_StubTool())._process_result(output, budget_tokens=600)

        assert "</external_content>" in rendered
        head, _, tail = rendered.rpartition("</external_content>")
        assert " of 10 " in tail, "the note is ours, it must not be marked as third-party text"
        assert " of 10 " not in head

    def test_no_note_when_nothing_was_cut(self) -> None:
        output = UnifiedToolOutput.data_success(
            message="ok", structured_data={"rows": _items(2, size=3), "count": 2}
        )
        rendered = ReactToolWrapper(_StubTool())._process_result(output)
        assert "[Budget]" not in rendered

    def test_a_cut_is_counted_per_tool(self) -> None:
        counter = react_tool_result_truncated_total.labels(tool_name="get_emails_tool")
        before = counter._value.get()
        output = UnifiedToolOutput.data_success(
            message="ok", structured_data={"rows": _items(20, size=500), "count": 20}
        )

        ReactToolWrapper(_StubTool())._process_result(output, budget_tokens=300)

        assert counter._value.get() == before + 1


class TestTheBudget:
    def test_defaults_to_the_ceiling_without_a_window(self) -> None:
        assert tool_result_token_budget(None, ceiling=25_000, window_fraction=0.25) == 25_000
        assert tool_result_token_budget(0, ceiling=25_000, window_fraction=0.25) == 25_000

    def test_a_small_window_bounds_the_result_by_its_fraction(self) -> None:
        assert tool_result_token_budget(8_000, ceiling=25_000, window_fraction=0.25) == 2_000

    def test_a_large_window_never_exceeds_the_ceiling(self) -> None:
        assert tool_result_token_budget(2_000_000, ceiling=25_000, window_fraction=0.25) == 25_000

    def test_settings_carry_the_two_knobs(self) -> None:
        settings = get_settings()
        assert settings.react_tool_result_max_tokens >= 1_000
        assert 0.05 <= settings.react_tool_result_window_fraction <= 0.5

    def test_the_string_door_keeps_its_contract(self) -> None:
        """``extract_data_for_llm`` is the door the MCP sub-agent wrapper shares."""
        result = UnifiedToolOutput.data_success(
            message="ok", structured_data={"mcp": _items(2, size=2)}
        )
        assert json.loads(extract_data_for_llm(result))["mcp"][0]["id"] == "item_0"
