"""Skill validation script — validates generated SKILL.md content.

Runs in a sandboxed subprocess via SkillScriptExecutor.
Cannot import application modules — all constants are self-contained.

Input: JSON on stdin with {"parameters": {"content": "---\\nname: ...\\n---\\n..."}, ...}
Output: JSON on stdout with {"valid": bool, "errors": [...], "warnings": [...]}
"""

from __future__ import annotations

import json
import re
import sys

import yaml

# ============================================================================
# Constants (mirrored from src/core/constants.py and src/domains/skills/loader.py)
# ============================================================================

NAME_MAX_LENGTH: int = 64
DESCRIPTION_MAX_LENGTH: int = 1024
NAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
CONSECUTIVE_HYPHENS: re.Pattern[str] = re.compile(r"--")
RESERVED_PREFIXES: tuple[str, ...] = ("claude", "anthropic")

VALID_AGENTS: frozenset[str] = frozenset({
    "contact_agent",
    "context_agent",
    "email_agent",
    "event_agent",
    "file_agent",
    "task_agent",
    "weather_agent",
    "query_agent",
    "reminder_agent",
    "place_agent",
    "route_agent",
    "wikipedia_agent",
    "perplexity_agent",
    "brave_agent",
    "web_search_agent",
    "web_fetch_agent",
    "mcp_agent",
    "browser_agent",
    "hue_agent",
    "image_generation_agent",
})

VALID_STEP_TYPES: frozenset[str] = frozenset({
    "TOOL",
    "CONDITIONAL",
    "PARALLEL",
    "RESPONSE",
})

VALID_OUTPUTS: frozenset[str] = frozenset({"text", "frame", "image"})


# ============================================================================
# Validation
# ============================================================================


def validate_skill(content: str) -> dict[str, object]:
    """Validate a SKILL.md file content.

    Args:
        content: Raw SKILL.md file content (frontmatter + body).

    Returns:
        Dict with "valid" (bool), "errors" (list[str]), "warnings" (list[str]).
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- Parse frontmatter ---
    if not content.startswith("---"):
        errors.append("File must start with '---' (YAML frontmatter delimiter)")
        return {"valid": False, "errors": errors, "warnings": warnings}

    parts = content.split("---", 2)
    if len(parts) < 3:
        errors.append("Missing closing '---' delimiter for YAML frontmatter")
        return {"valid": False, "errors": errors, "warnings": warnings}

    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        errors.append(f"YAML parsing failed: {exc}")
        return {"valid": False, "errors": errors, "warnings": warnings}

    if not isinstance(meta, dict):
        errors.append("Frontmatter must be a YAML mapping (key: value pairs)")
        return {"valid": False, "errors": errors, "warnings": warnings}

    # --- Required fields ---
    if not meta.get("name"):
        errors.append("Missing required field: 'name'")
    if not meta.get("description"):
        errors.append("Missing required field: 'description'")

    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings}

    name: str = str(meta["name"])
    description: str = str(meta["description"]).strip()

    # --- Name validation ---
    if len(name) > NAME_MAX_LENGTH:
        errors.append(f"Name exceeds {NAME_MAX_LENGTH} characters (got {len(name)})")

    if len(name) < 2:
        errors.append("Name must be at least 2 characters")

    if not NAME_PATTERN.match(name):
        errors.append(
            f"Name '{name}' does not match pattern [a-z0-9][a-z0-9-]*[a-z0-9]"
        )

    if CONSECUTIVE_HYPHENS.search(name):
        errors.append(f"Name '{name}' contains consecutive hyphens ('--')")

    for prefix in RESERVED_PREFIXES:
        if name.startswith(prefix):
            errors.append(
                f"Name '{name}' uses reserved prefix '{prefix}'"
            )
            break

    # --- Description validation ---
    if len(description) > DESCRIPTION_MAX_LENGTH:
        errors.append(
            f"Description exceeds {DESCRIPTION_MAX_LENGTH} characters "
            f"(got {len(description)})"
        )

    # --- XML tags check (security) ---
    for field_name, value in [("name", name), ("description", description)]:
        if "<" in value or ">" in value:
            errors.append(f"XML tags (<, >) are forbidden in '{field_name}'")

    # --- Description style check ---
    first_word = description.split()[0] if description.split() else ""
    if first_word and not first_word[0].isupper():
        warnings.append(
            "Description should start with an uppercase verb "
            "(e.g., 'Generates...', 'Provides...')"
        )

    # --- Plan template validation ---
    template = meta.get("plan_template")
    if template and isinstance(template, dict):
        steps = template.get("steps", [])
        if not isinstance(steps, list):
            errors.append("plan_template.steps must be a list")
        else:
            step_ids: set[str] = set()
            for i, step in enumerate(steps):
                if not isinstance(step, dict):
                    errors.append(f"Step {i} must be a mapping")
                    continue

                # step_id
                step_id = step.get("step_id")
                if not step_id:
                    errors.append(f"Step {i}: missing 'step_id'")
                elif step_id in step_ids:
                    errors.append(f"Step {i}: duplicate step_id '{step_id}'")
                else:
                    step_ids.add(step_id)

                # step_type
                step_type = step.get("step_type", "TOOL")
                if step_type not in VALID_STEP_TYPES:
                    errors.append(
                        f"Step '{step_id}': invalid step_type '{step_type}' "
                        f"(valid: {', '.join(sorted(VALID_STEP_TYPES))})"
                    )

                # agent_name
                agent_name = step.get("agent_name")
                if not agent_name:
                    errors.append(f"Step '{step_id}': missing 'agent_name'")
                elif agent_name not in VALID_AGENTS:
                    errors.append(
                        f"Step '{step_id}': unknown agent_name '{agent_name}' "
                        f"(valid: {', '.join(sorted(VALID_AGENTS))})"
                    )

                # tool_name (required for TOOL steps)
                tool_name = step.get("tool_name")
                if step_type == "TOOL" and not tool_name:
                    errors.append(f"Step '{step_id}': TOOL step requires 'tool_name'")

                # depends_on
                depends_on = step.get("depends_on", [])
                if not isinstance(depends_on, list):
                    errors.append(f"Step '{step_id}': depends_on must be a list")
                else:
                    for dep in depends_on:
                        if dep not in step_ids:
                            warnings.append(
                                f"Step '{step_id}': depends_on references "
                                f"'{dep}' which appears later or doesn't exist"
                            )

    # --- outputs field validation (rich outputs contract) ---
    outputs = meta.get("outputs")
    if outputs is not None:
        if not isinstance(outputs, list):
            errors.append("'outputs' must be a list (e.g., [text, frame, image])")
        else:
            for out in outputs:
                if not isinstance(out, str):
                    errors.append(f"'outputs' entry must be a string, got {type(out).__name__}")
                elif out not in VALID_OUTPUTS:
                    errors.append(
                        f"Invalid output type '{out}' "
                        f"(valid: {', '.join(sorted(VALID_OUTPUTS))})"
                    )
            # 'text' should always be present (required by SkillScriptOutput contract)
            if outputs and "text" not in outputs:
                warnings.append(
                    "'outputs' should include 'text' — the SkillScriptOutput contract "
                    "always requires a text field for voice/accessibility"
                )
            # If frame or image is declared, the skill must have a scripts/ folder
            # (cannot verify directly here but the LLM reformulator should mention it
            # — emit a warning as a reminder).
            if ("frame" in outputs or "image" in outputs) and not outputs == ["text"]:
                warnings.append(
                    "Skills declaring 'frame' or 'image' outputs must ship a Python "
                    "script in scripts/ that emits the SkillScriptOutput JSON contract "
                    "(see references/format-specification.md § Rich Outputs Contract)"
                )

    # --- Body check ---
    body = parts[2].strip() if len(parts) > 2 else ""
    if not body:
        warnings.append("SKILL.md body is empty (no instructions)")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


# ============================================================================
# Main entry point
# ============================================================================


def main() -> None:
    """Read SKILL.md content from stdin JSON and validate it."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            result = {"valid": False, "errors": ["Empty stdin"], "warnings": []}
            print(json.dumps(result, ensure_ascii=False))
            return

        payload = json.loads(raw)
        content = payload.get("parameters", {}).get("content", "")

        if not content:
            result = {
                "valid": False,
                "errors": ["Missing 'content' in parameters"],
                "warnings": [],
            }
            print(json.dumps(result, ensure_ascii=False))
            return

        result = validate_skill(content)
        print(json.dumps(result, ensure_ascii=False))

    except json.JSONDecodeError as exc:
        result = {
            "valid": False,
            "errors": [f"Invalid JSON input: {exc}"],
            "warnings": [],
        }
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        result = {
            "valid": False,
            "errors": [f"Unexpected error: {exc}"],
            "warnings": [],
        }
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
