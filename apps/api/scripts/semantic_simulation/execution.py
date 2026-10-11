"""Mechanical execution of generated plans up to a simulated action boundary."""

from pydantic import BaseModel, TypeAdapter

from scripts.semantic_simulation.corpus import Scenario, assess, read_result
from scripts.semantic_simulation.prompts import TOOLS
from src.domains.agents.orchestration.condition_evaluator import ReferenceResolver
from src.domains.agents.orchestration.jinja_evaluator import JinjaTemplateEvaluator
from src.domains.agents.orchestration.parallel_executor import _coerce_args_to_schema
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.orchestration.validator import PlanValidator, ValidationContext
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.utils.json_parser import extract_json_from_llm_response

_OBJECT = TypeAdapter(dict[str, object])


def _pydantic_schema(candidate: object) -> type[BaseModel] | None:
    """Narrow the public schema by runtime checks, without a typing cast."""
    if isinstance(candidate, type) and issubclass(candidate, BaseModel):
        return candidate
    return None


def parse_plan(text: str, registry: AgentRegistry) -> ExecutionPlan:
    parsed = extract_json_from_llm_response(
        response_text=text, expected_type=dict, required_fields=["steps"]
    )
    if not parsed.success:
        raise ValueError("Planner output did not contain a valid plan")
    data = _OBJECT.validate_python(parsed.data)
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("Planner steps are not an array")
    steps = [_parse_step(_OBJECT.validate_python(item), registry) for item in raw_steps]
    return ExecutionPlan(steps=steps, user_id="semantic-simulation", execution_mode="sequential")


def _parse_step(item: dict[str, object], registry: AgentRegistry) -> ExecutionStep:
    name = TypeAdapter(str).validate_python(item.get("tool_name"))
    manifest = registry.get_tool_manifest(name)
    raw_dependencies = item.get("depends_on", [])
    dependencies = TypeAdapter(list[str]).validate_python(raw_dependencies)
    return ExecutionStep(
        step_id=TypeAdapter(str).validate_python(item.get("id")),
        step_type=StepType.TOOL,
        agent_name=manifest.agent,
        tool_name=name,
        parameters=_OBJECT.validate_python(item.get("parameters", {})),
        depends_on=dependencies,
        for_each=TypeAdapter(str | None).validate_python(item.get("for_each")),
    )


def validate_plan(plan: ExecutionPlan, registry: AgentRegistry) -> list[str]:
    scopes = [
        scope
        for manifest in registry.list_tool_manifests()
        for scope in manifest.permissions.required_scopes
    ]
    result = PlanValidator(registry).validate_execution_plan(
        plan,
        ValidationContext(
            user_id="semantic-simulation", session_id="offline-boundary", available_scopes=scopes
        ),
    )
    return [f"{issue.code}: {issue.message}" for issue in result.errors]


def check_arguments(name: str, arguments: dict[str, object]) -> None:
    tool = next(tool for tool in TOOLS if tool.name == name)
    schema = _pydantic_schema(tool.tool_call_schema)
    if schema is not None:
        arguments.update(_coerce_args_to_schema(arguments, schema))
        schema.model_validate(arguments)


def simulate_plan(scenario: Scenario, text: str, registry: AgentRegistry) -> dict[str, object]:
    plan = parse_plan(text, registry)
    errors = validate_plan(plan, registry)
    if errors:
        return {"calls": [], "failures": errors, "validation": errors}
    completed: dict[str, dict[str, object]] = {}
    calls: list[dict[str, object]] = []
    for step in plan.steps:
        arguments = ReferenceResolver().resolve_args(step.parameters, completed)
        arguments = JinjaTemplateEvaluator().evaluate_parameters(arguments, completed, step.step_id)
        name = step.tool_name or ""
        check_arguments(name, arguments)
        calls.append({"name": name, "arguments": arguments})
        if name == scenario.action:
            # No native tool execution: no draft, account or provider mutation.
            continue
        completed[step.step_id] = read_result(name, scenario)
    return {"calls": calls, "failures": errors + assess(scenario, calls), "validation": errors}
