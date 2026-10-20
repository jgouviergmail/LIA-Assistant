"""The real pipeline/reference/ReAct serializers preserve and mark SMS evidence."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.core.constants import EXTERNAL_CONTENT_OPEN_TAG
from src.domains.agents.formatters.resolved_context import (
    format_resolved_context_for_prompt,
    generate_html_for_resolved_context,
)
from src.domains.agents.formatters.text_summary import (
    generate_data_for_filtering,
    generate_text_summary_for_llm,
)
from src.domains.agents.services.reference_resolver import ResolvedContext
from src.domains.agents.sms.projection import project_page
from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper
from src.domains.agents.tools.sms_tools import list_sms_tool, sms_output
from src.domains.agents.utils.registry_filtering import parse_relevant_ids_from_response
from src.domains.sms.read_schemas import SmsPage, SmsView


@pytest.fixture
def source():
    view = SmsView(
        id=uuid4(),
        sender="Alice",
        display_name="Alice",
        body="Oui.",
        received_at=datetime.now(UTC),
        date_kind="received",
        origin="iphone",
    )
    return project_page(
        SmsPage(items=[view], total=1, as_of=datetime.now(UTC), revision=0), owner=uuid4()
    )


def test_short_sms_body_and_full_identifier_reach_pipeline_and_react(source):
    output = sms_output(source, "list_sms_tool")
    summary = generate_text_summary_for_llm(output.registry_updates, "en")
    assert "Oui." in summary and EXTERNAL_CONTENT_OPEN_TAG in summary
    filtering = generate_data_for_filtering(output.registry_updates)
    key = next(iter(output.registry_updates))
    assert key in filtering and "Oui." in filtering
    assert key in parse_relevant_ids_from_response(f"<relevant_ids>{key}</relevant_ids>")[0]
    rendered = ReactToolWrapper(list_sms_tool)._process_result(output)
    assert EXTERNAL_CONTENT_OPEN_TAG in rendered and rendered.count("Oui.") == 1


def test_ordinal_reference_keeps_the_same_body_card_and_external_boundary(source):
    items = [source.sms_messages[0].model_dump(mode="json")]
    resolved = {"source_domain": "sms_messages", "items": items}
    context = format_resolved_context_for_prompt(resolved, user_language="en")
    assert "Oui." in context and EXTERNAL_CONTENT_OPEN_TAG in context
    plan = ResolvedContext(
        items=items, confidence=1, method="explicit", source_turn_id=1, source_domain="sms_messages"
    ).to_llm_context()
    assert "Oui." in plan and EXTERNAL_CONTENT_OPEN_TAG in plan
    html = generate_html_for_resolved_context(resolved, user_language="en")
    assert html.count("Oui.") == 1 and "/dashboard/sms?message=" in html
