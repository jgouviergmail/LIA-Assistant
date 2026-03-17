"""SKILL.md file loader.

Parses YAML frontmatter + markdown body from SKILL.md files.
Standard: agentskills.io specification.

Validation is lenient per client implementation guide:
- Name mismatch with directory → warn, load anyway
- Name exceeds 64 chars → warn, load anyway
- Missing description → skip (essential for catalogue)
- Unparseable YAML → try fallback, then skip
"""

import json
import re
from pathlib import Path
from typing import Any

import yaml

from src.core.constants import (
    SKILLS_DESCRIPTION_MAX_LENGTH,
    SKILLS_NAME_MAX_LENGTH,
    SKILLS_RESOURCE_SKIP_DIRS,
    SKILLS_RESOURCE_SKIP_FILES,
    SKILLS_SCRIPT_ALLOWED_EXTENSIONS,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

REQUIRED_FIELDS = {"name", "description"}
# Per agentskills.io spec: [a-z0-9], max 64 chars, no consecutive hyphens, no start/end hyphen
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
SKILL_NAME_NO_CONSECUTIVE_HYPHENS = re.compile(r"--")

# LIA extension fields (ignored by other parsers)
EXTENSION_FIELDS: dict[str, Any] = {
    "category": None,
    "priority": 50,
    "always_loaded": False,
    "plan_template": None,
    # F6 Sub-Agents: declarative skill visibility
    # agent_visibility: null (all) | list of agent types (e.g., ["research_assistant"])
    # visibility_mode: "include" (whitelist) | "exclude" (blacklist)
    "agent_visibility": None,
    "visibility_mode": "include",
}


def _fallback_yaml_parse(yaml_str: str) -> dict[str, Any] | None:
    """Fallback YAML parsing for common cross-client issues.

    Per client implementation guide: "Consider a fallback that wraps
    such values in quotes or converts them to YAML block scalars."
    Common issue: unquoted values containing colons.
    """
    fixed = re.sub(
        r"^(\w[\w-]*?):\s+(.+:.+)$",
        r'\1: "\2"',
        yaml_str,
        flags=re.MULTILINE,
    )
    try:
        result = yaml.safe_load(fixed)
        if isinstance(result, dict):
            return result
    except yaml.YAMLError:
        pass
    return None


def _list_dir(dir_path: Path, allowed_ext: frozenset[str] | None = None) -> list[str]:
    """List files in a directory, optionally filtering by extension."""
    if not dir_path.exists() or not dir_path.is_dir():
        return []
    return [
        f.name
        for f in sorted(dir_path.iterdir())
        if f.is_file() and (allowed_ext is None or f.suffix in allowed_ext)
    ]


def _discover_all_resources(skill_dir: Path) -> list[str]:
    """Discover all bundled resources in a skill directory (recursive).

    Per agentskills.io standard, a skill package can contain arbitrary files
    beyond the standard directories (scripts/, references/, assets/).
    Examples: template.md, examples/sample.md, config.yaml, etc.

    Returns paths relative to skill_dir, excluding SKILL.md itself.
    """
    resources: list[str] = []
    for item in sorted(skill_dir.rglob("*")):
        if not item.is_file():
            continue
        if item.name in SKILLS_RESOURCE_SKIP_FILES:
            continue
        # Skip files inside excluded directories
        rel = item.relative_to(skill_dir)
        if any(part in SKILLS_RESOURCE_SKIP_DIRS for part in rel.parts):
            continue
        resources.append(rel.as_posix())
    return resources


def parse_skill_file(path: Path) -> dict[str, Any] | None:
    """Parse a SKILL.md file into a skill dict.

    Lenient validation per agentskills.io client implementation guide:
    - Name mismatch with directory → warn, load anyway
    - Name exceeds 64 chars → warn, load anyway
    - Missing description → skip (essential for catalogue)
    - Unparseable YAML → skip
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("skill_file_read_error", path=str(path))
        return None

    # Split YAML frontmatter from markdown body
    if not content.startswith("---"):
        logger.warning("skill_file_no_frontmatter", path=str(path))
        return None

    parts = content.split("---", 2)
    if len(parts) < 3:
        logger.warning("skill_file_bad_frontmatter", path=str(path))
        return None

    try:
        meta = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        # Fallback: handle common YAML issues (unquoted colons per client impl guide)
        meta = _fallback_yaml_parse(parts[1])
        if meta is None:
            logger.warning("skill_file_yaml_error", path=str(path))
            return None

    if not isinstance(meta, dict):
        logger.warning("skill_file_invalid_meta", path=str(path))
        return None

    # Description is essential (agentskills.io: "skip the skill if missing")
    if not meta.get("description"):
        logger.warning("skill_file_missing_description", path=str(path))
        return None

    # Security: no XML tags in frontmatter (per Anthropic spec)
    for field in ("name", "description"):
        val = meta.get(field, "")
        if isinstance(val, str) and ("<" in val or ">" in val):
            logger.warning("skill_xml_in_frontmatter", path=str(path), field=field)
            return None

    # Name validation (lenient: warn but load)
    name = meta.get("name", path.parent.name)  # Fallback to directory name
    if len(name) > SKILLS_NAME_MAX_LENGTH:
        logger.warning("skill_name_too_long", path=str(path), name=name)
    if not SKILL_NAME_PATTERN.match(name):
        logger.warning("skill_name_invalid_chars", path=str(path), name=name)
    if SKILL_NAME_NO_CONSECUTIVE_HYPHENS.search(name):
        logger.warning("skill_name_consecutive_hyphens", path=str(path), name=name)

    # Reserved names: "claude" and "anthropic" prefixes (per Anthropic spec)
    if name.startswith("claude") or name.startswith("anthropic"):
        logger.warning("skill_name_reserved", path=str(path), name=name)
        return None

    # Description length check (per Anthropic spec: max 1024 chars)
    desc = meta["description"].strip()
    if len(desc) > SKILLS_DESCRIPTION_MAX_LENGTH:
        logger.warning("skill_description_too_long", path=str(path), length=len(desc))

    # Warn if name doesn't match directory (agentskills.io spec)
    if name != path.parent.name:
        logger.warning("skill_name_dir_mismatch", name=name, dir=path.parent.name)

    instructions = parts[2].strip()

    # Discover standard directories (agentskills.io: scripts/, references/, assets/)
    scripts = _list_dir(path.parent / "scripts", SKILLS_SCRIPT_ALLOWED_EXTENSIONS)
    references = _list_dir(path.parent / "references")
    assets = _list_dir(path.parent / "assets")

    # Discover ALL bundled resources (standard + non-standard files)
    all_resources = _discover_all_resources(path.parent)

    # Load translations.json if present (generated by admin translate action)
    translations: dict[str, str] | None = None
    translations_file = path.parent / "translations.json"
    if translations_file.exists():
        try:
            raw = json.loads(translations_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and all(
                isinstance(k, str) and isinstance(v, str) for k, v in raw.items()
            ):
                translations = raw
        except (OSError, ValueError):
            logger.warning("skill_translations_load_error", path=str(translations_file))

    skill: dict[str, Any] = {
        "name": name,
        "description": desc,
        "descriptions": translations,
        "instructions": instructions,
        "source_path": str(path),
        "scripts": scripts,
        "references": references,
        "assets": assets,
        "all_resources": all_resources,
        # Standard optional fields (agentskills.io)
        "license": meta.get("license"),
        "compatibility": meta.get("compatibility"),
        "allowed_tools": meta.get("allowed-tools") or meta.get("allowed_tools"),
        "skill_metadata": meta.get("metadata"),
        # Claude Code extensions (parsed leniently)
        "disable_model_invocation": meta.get("disable-model-invocation", False),
        # LIA extensions
        **{k: meta.get(k, default) for k, default in EXTENSION_FIELDS.items()},
    }
    return skill


def scan_skills_directory(
    base_path: Path,
    scope: str,
    owner_id: str | None = None,
) -> list[dict[str, Any]]:
    """Scan a directory for SKILL.md files.

    Per agentskills.io: look for subdirectories containing SKILL.md.
    Skip .git, node_modules, __pycache__.
    """
    skills: list[dict[str, Any]] = []
    if not base_path.exists():
        return skills

    skip_dirs = {".git", "node_modules", "__pycache__", ".venv"}

    for skill_dir in sorted(base_path.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name in skip_dirs:
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        skill = parse_skill_file(skill_file)
        if skill:
            skill["scope"] = scope
            skill["owner_id"] = owner_id
            skill["id"] = f"{scope}:{skill['name']}"
            skills.append(skill)

    return skills
