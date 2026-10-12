"""One bounded call through the DB-configured analyzer and its production schema."""

from langchain_core.utils.function_calling import convert_to_openai_tool

from scripts.semantic_simulation.corpus import Scenario
from scripts.semantic_simulation.runtime import ProbeRuntime, invoke
from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.prompt_layout import single_call_messages
from src.core.time_utils import get_current_datetime_context, now_in_timezone
from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.analysis.requested_outcomes import anchored_requirements
from src.domains.agents.analysis.resolved_references import merge_resolved_references
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.analysis.domain_availability import build_available_domains
from src.domains.agents.services.analysis.query_analysis_schemas import QueryAnalysisOutput
from src.domains.agents.utils.json_parser import extract_json_from_llm_response


async def analyze_case(
    runtime: ProbeRuntime, scenario: Scenario
) -> tuple[QueryIntelligence, dict[str, object]]:
    """No retry, hidden parser repair, historical memory or external account access."""
    descriptions = build_available_domains()
    request_date = now_in_timezone(DEFAULT_USER_DISPLAY_TIMEZONE).date()
    domains = "\n".join(
        f"- **{item['name']}**: {item['description']}"
        for item in descriptions
        if item["name"] in scenario.domains
    )
    prompt = str(load_prompt("query_analyzer_prompt", version="v1")).format(
        current_datetime=get_current_datetime_context(DEFAULT_USER_DISPLAY_TIMEZONE, "fr"),
        available_domains=domains,
        available_skills="None",
        connected_peers="None",
        memory_facts="None",
        conversation_history="None",
        user_location="Not available",
        window_size=5,
        user_query=scenario.query,
    )
    schema: dict[str, object] = convert_to_openai_tool(QueryAnalysisOutput, strict=False)
    response = await invoke(
        runtime,
        "query_analyzer",
        single_call_messages(prompt),
        case=scenario.name,
        tools=[schema],
        tool_choice="QueryAnalysisOutput",
    )
    if response.tool_calls:
        raw = response.tool_calls[0]["args"]
    else:
        parsed = extract_json_from_llm_response(response_text=response.text, expected_type=dict)
        if not parsed.success:
            raise ValueError("Analyzer did not return a schema-conforming result")
        raw = parsed.data
    analysis = QueryAnalysisOutput.model_validate(raw)
    requirements = anchored_requirements(
        analysis.requested_outcomes,
        scenario.query,
        scenario.domains,
        reference_date=request_date,
        reference_timezone=DEFAULT_USER_DISPLAY_TIMEZONE,
    )
    intelligence = QueryIntelligence(
        original_query=scenario.query,
        english_query=analysis.english_query,
        immediate_intent="create" if analysis.is_mutation_intent else "search",
        immediate_confidence=analysis.confidence,
        user_goal=(
            UserGoal.TAKE_ACTION if analysis.is_mutation_intent else UserGoal.FIND_INFORMATION
        ),
        goal_reasoning=analysis.reasoning,
        domains=list(scenario.domains),
        primary_domain=analysis.primary_domain or scenario.domains[-1],
        resolved_references=merge_resolved_references(
            None, None, [item.model_dump(mode="json") for item in analysis.resolved_references]
        ),
        is_mutation_intent=analysis.is_mutation_intent,
        requested_outcomes=requirements,
        user_language="fr",
    )
    evidence: dict[str, object] = analysis.model_dump(mode="json")
    return intelligence, evidence
