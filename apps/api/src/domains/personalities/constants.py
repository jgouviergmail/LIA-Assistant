"""
Constants for the personalities domain.
"""

from functools import lru_cache

from src.core.prompt_store import read_prompt_file

# Default personality code (used when user has no preference)
DEFAULT_PERSONALITY_CODE = "normal"


@lru_cache(maxsize=1)
def default_personality_prompt() -> str:
    """The personality instruction used when none is configured.

    The versioned prompt itself, never a copy — an inline copy had drifted from
    the file (ADR-284). Read on first use: importing a constants module must not
    read a file.

    Returns:
        The instruction text.
    """
    return read_prompt_file("default_personality_prompt").strip()


# Personality code validation pattern
PERSONALITY_CODE_PATTERN = r"^[a-z][a-z0-9_]*$"

# Maximum lengths
MAX_CODE_LENGTH = 50
MAX_EMOJI_LENGTH = 10
MAX_TITLE_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 500
MAX_PROMPT_LENGTH = 2000
