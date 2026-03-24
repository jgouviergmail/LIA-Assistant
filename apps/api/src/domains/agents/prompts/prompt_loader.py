"""
Prompt Loader with Versioning and Integrity Validation.

This module provides utilities for loading versioned prompts with:
- Version management (semantic versioning)
- Hash-based integrity validation
- Fallback mechanisms
- Caching for performance (Phase 3.2.9)

Compliance: LangGraph v1.0 + LangChain v1.0 best practices
"""

import hashlib
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import structlog

logger = structlog.get_logger(__name__)

# Base directory for prompts
PROMPTS_DIR = Path(__file__).parent  # Parent of v1/ since file is in v1/


def _get_available_versions() -> set[str]:
    """
    Dynamically detect available prompt versions from filesystem.

    Returns:
        Set of version strings (e.g., {"v1", "v2", "v3", ...})

    Note:
        - Scans PROMPTS_DIR for subdirectories matching pattern "v[0-9]+"
        - Called once at module import to populate PromptVersion type
        - Prevents critical bug where Literal["v1", "v2", "v3"] blocks v4+
    """
    if not PROMPTS_DIR.exists():
        logger.warning("prompts_directory_not_found", path=str(PROMPTS_DIR))
        return {"v1"}  # Fallback to v1 only

    versions = set()
    version_pattern = re.compile(r"^v\d+$")

    for item in PROMPTS_DIR.iterdir():
        if item.is_dir() and version_pattern.match(item.name):
            versions.add(item.name)

    if not versions:
        logger.warning("no_version_directories_found", fallback="v1")
        return {"v1"}

    logger.debug("detected_prompt_versions", versions=sorted(versions))
    return versions


# Dynamically detect available versions (populated at module import)
_AVAILABLE_VERSIONS = _get_available_versions()

# Version type alias - DYNAMIC to prevent v4+ blocking bug
# Before fix: Literal["v1", "v2", "v3"] blocked v8 from loading
# After fix: Automatically includes all versions found in filesystem
PromptVersion = str  # Accept any version string, validated at runtime

# Prompt name type alias
PromptName = Literal[
    "router_system_prompt",
    "response_system_prompt_base",
    "response_directive_plan_rejection",
    "response_directive_conversational",
    "response_directive_draft_cancelled",
    "contacts_agent_prompt",
    "planner_system_prompt",
    "hitl_classifier_prompt",
    "reminder_prompt",
    # Email content generation
    "email_content_generation_prompt",
    "email_subject_generation_prompt",
    # Fallback and HITL
    "fallback_response_prompt",
    "hitl_draft_critique_fallback_prompt",
    "hitl_draft_critique_prompt",
    "hitl_question_generator_prompt",
    "hitl_plan_approval_question_prompt",
    "draft_modifier_prompt",
    # Context instructions
    "context_reference_instructions_prompt",
    # Default personality
    "default_personality_prompt",
    # Interest learning system
    "interest_extraction_prompt",
    "interest_content_prompt",
    "interest_llm_reflection_prompt",
    # Agent prompts
    "brave_agent_prompt",
    "weather_agent_prompt",
    "perplexity_agent_prompt",
    "wikipedia_agent_prompt",
    "web_search_agent_prompt",
    "hue_agent_prompt",
    # Heartbeat autonome (proactive notifications)
    "heartbeat_decision_prompt",
    "heartbeat_message_prompt",
    # MCP domain description generation
    "mcp_description_prompt",
    # Skills system
    "skill_description_translation_prompt",
    # Context compaction (F4)
    "compaction_prompt",
    # App self-knowledge (System RAG Spaces)
    "app_identity_prompt",
    # Personal Journals (Carnets de Bord)
    "journal_introspection_prompt",
    "journal_introspection_personality_addon",
    "journal_consolidation_prompt",
    # ADR-062: Initiative Phase + MCP ReAct
    "initiative_prompt",
    "mcp_react_agent_prompt",
    # Future prompts:
    # "emails_agent_prompt",
    # "calendar_agent_prompt",
]


class PromptLoadError(Exception):
    """Raised when prompt loading fails."""

    pass


class PromptIntegrityError(Exception):
    """Raised when prompt hash validation fails."""

    pass


def calculate_prompt_hash(content: str) -> str:
    """
    Calculate SHA256 hash of prompt content for integrity validation.

    Args:
        content: Prompt text content

    Returns:
        Hexadecimal SHA256 hash string

    Example:
        >>> content = "Tu es un agent..."
        >>> hash_value = calculate_prompt_hash(content)
        >>> len(hash_value)
        64
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@lru_cache(maxsize=32)
def load_prompt(
    name: PromptName,
    version: PromptVersion = "v1",
    validate_hash: bool = False,
    expected_hash: str | None = None,
) -> str:
    """
    Load a versioned prompt from file with optional hash validation.

    Optimizations (Phase 3.2.9):
    - LRU cache (maxsize=32) for prompt reuse across requests
    - Reduces disk I/O from ~1000s reads/min to ~10 reads at startup
    - Cache key: (name, version, validate_hash, expected_hash)

    Args:
        name: Prompt filename (without .txt extension)
        version: Prompt version (default: "v1")
        validate_hash: Whether to validate prompt integrity with hash (default: False)
        expected_hash: Expected SHA256 hash for validation (required if validate_hash=True)

    Returns:
        Prompt content as string

    Raises:
        PromptLoadError: If prompt file not found or cannot be read
        PromptIntegrityError: If hash validation fails
        ValueError: If version is not available in filesystem

    Example:
        >>> # Basic loading (cached after first call)
        >>> prompt = load_prompt("router_system_prompt")
        >>> print(prompt[:50])
        Tu es un routeur intelligent...

        >>> # With hash validation
        >>> prompt = load_prompt(
        ...     "router_system_prompt",
        ...     validate_hash=True,
        ...     expected_hash="abc123..."
        ... )

    Note:
        - Hash validation is recommended in production to detect unauthorized modifications
        - Cache is in-memory and cleared on process restart (prompts reloaded from disk)
        - maxsize=32 covers all prompts × versions with room for growth
        - Version is validated at runtime against available versions in filesystem
    """
    # Validate version exists (runtime check to prevent silent fallback bugs)
    if version not in _AVAILABLE_VERSIONS:
        available_list = ", ".join(sorted(_AVAILABLE_VERSIONS))
        msg = (
            f"Prompt version '{version}' not found in filesystem. "
            f"Available versions: {available_list}. "
            f"Check PROMPTS_DIR has subdirectory: {PROMPTS_DIR / version}"
        )
        logger.error(msg)
        raise ValueError(msg)

    # Construct file path
    prompt_file = PROMPTS_DIR / version / f"{name}.txt"

    # Check if file exists
    if not prompt_file.exists():
        msg = f"Prompt file not found: {prompt_file}"
        logger.error(msg)
        raise PromptLoadError(msg)

    try:
        # Load prompt content
        content = prompt_file.read_text(encoding="utf-8")
    except Exception as e:
        msg = f"Failed to read prompt file {prompt_file}: {e}"
        logger.error(msg)
        raise PromptLoadError(msg) from e

    # Validate hash if requested
    if validate_hash:
        if expected_hash is None:
            msg = "validate_hash=True requires expected_hash parameter"
            logger.error(msg)
            raise ValueError(msg)

        actual_hash = calculate_prompt_hash(content)
        if actual_hash != expected_hash:
            msg = (
                f"Prompt integrity validation failed for {name} v{version}\n"
                f"Expected: {expected_hash}\n"
                f"Actual:   {actual_hash}\n"
                f"This may indicate unauthorized modification or version mismatch."
            )
            logger.error(msg)
            raise PromptIntegrityError(msg)

        logger.info("prompt_integrity_validated", name=name, version=version, hash=actual_hash[:8])

    logger.debug("loaded_prompt", name=name, version=version, chars=len(content))
    return content


def load_prompt_with_fallback(
    name: PromptName, version: PromptVersion = "v1", fallback_content: str | None = None
) -> str:
    """
    Load prompt with fallback to provided content if file not found.

    Useful for gradual migration from hardcoded prompts to versioned files.

    Args:
        name: Prompt filename (without .txt extension)
        version: Prompt version (default: "v1")
        fallback_content: Fallback prompt content if file not found

    Returns:
        Prompt content (from file or fallback)

    Example:
        >>> # During migration period
        >>> OLD_PROMPT = "Tu es un agent..."
        >>> prompt = load_prompt_with_fallback(
        ...     "router_system_prompt",
        ...     fallback_content=OLD_PROMPT
        ... )

    Note:
        This is a temporary migration helper. Production code should use load_prompt()
        without fallback to ensure versioned prompts are always used.
    """
    try:
        return load_prompt(name, version)
    except PromptLoadError:
        if fallback_content is not None:
            logger.warning(
                f"Prompt file not found for {name} v{version}, using fallback content. "
                f"This should only happen during migration."
            )
            return fallback_content
        raise


def get_available_versions() -> list[str]:
    """
    Get list of all available prompt versions.

    Returns:
        Sorted list of version strings (e.g., ["v1", "v2", "v3", ...])

    Example:
        >>> versions = get_available_versions()
        >>> print(versions)
        ['v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8']

    Note:
        This is useful for debugging and configuration validation.
        Called automatically at module import to populate _AVAILABLE_VERSIONS.
    """
    return sorted(_AVAILABLE_VERSIONS, key=lambda v: int(v[1:]) if v[1:].isdigit() else 0)


def list_available_prompts(version: PromptVersion = "v1") -> list[str]:
    """
    List all available prompts for a given version.

    Args:
        version: Prompt version (default: "v1")

    Returns:
        List of prompt names (without .txt extension)

    Raises:
        ValueError: If version is not available

    Example:
        >>> prompts = list_available_prompts("v1")
        >>> print(prompts)
        ['router_system_prompt', 'response_system_prompt', 'contacts_agent_prompt']
    """
    # Validate version exists
    if version not in _AVAILABLE_VERSIONS:
        available_list = ", ".join(sorted(_AVAILABLE_VERSIONS))
        raise ValueError(f"Version '{version}' not found. Available versions: {available_list}")

    version_dir = PROMPTS_DIR / version

    if not version_dir.exists():
        logger.warning("version_directory_not_found", path=str(version_dir))
        return []

    prompt_files = version_dir.glob("*.txt")
    return sorted([f.stem for f in prompt_files])


def validate_all_prompts(
    version: PromptVersion = "v1", expected_hashes: dict[str, str] | None = None
) -> dict[str, str]:
    """
    Validate integrity of all prompts for a given version.

    Args:
        version: Prompt version (default: "v1")
        expected_hashes: Optional dict mapping prompt names to expected hashes

    Returns:
        Dictionary mapping prompt names to their actual hashes

    Raises:
        PromptIntegrityError: If any hash validation fails

    Example:
        >>> expected = {
        ...     "router_system_prompt": "abc123...",
        ...     "response_system_prompt_base": "def456...",
        ... }
        >>> actual = validate_all_prompts("v1", expected)
        >>> print(actual)
        {'router_system_prompt': 'abc123...', 'response_system_prompt_base': 'def456...'}
    """
    prompts = list_available_prompts(version)
    actual_hashes = {}

    for prompt_name in prompts:
        try:
            # Type assertion: prompt_name comes from list_available_prompts which scans actual files
            content = load_prompt(prompt_name, version)
            actual_hash = calculate_prompt_hash(content)
            actual_hashes[prompt_name] = actual_hash

            # Validate if expected hash provided
            if expected_hashes and prompt_name in expected_hashes:
                expected = expected_hashes[prompt_name]
                if actual_hash != expected:
                    raise PromptIntegrityError(
                        f"Hash mismatch for {prompt_name}: expected {expected}, got {actual_hash}"
                    )
        except PromptLoadError as e:
            logger.error("failed_to_load_prompt", prompt_name=prompt_name, error=str(e))
            raise

    return actual_hashes


def get_prompt_metadata(name: PromptName, version: PromptVersion = "v1") -> dict[str, str | int]:
    """
    Get metadata about a prompt (size, hash, etc.).

    Args:
        name: Prompt filename (without .txt extension)
        version: Prompt version (default: "v1")

    Returns:
        Dictionary with metadata: name, version, size, hash, file_path

    Example:
        >>> metadata = get_prompt_metadata("router_system_prompt")
        >>> print(metadata)
        {
            'name': 'router_system_prompt',
            'version': 'v1',
            'size': 5421,
            'hash': 'abc123...',
            'file_path': '/path/to/prompts/v1/router_system_prompt.txt'
        }
    """
    content = load_prompt(name, version)
    prompt_hash = calculate_prompt_hash(content)
    prompt_file = PROMPTS_DIR / version / f"{name}.txt"

    return {
        "name": name,
        "version": version,
        "size": len(content),
        "hash": prompt_hash,
        "file_path": str(prompt_file),
    }


# Export public API
__all__ = [
    "PromptIntegrityError",
    "PromptLoadError",
    "PromptName",
    "PromptVersion",
    "calculate_prompt_hash",
    "get_available_versions",
    "get_prompt_metadata",
    "list_available_prompts",
    "load_prompt",
    "load_prompt_with_fallback",
    "validate_all_prompts",
]
