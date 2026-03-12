"""
Constants for the personalities domain.
"""

from src.core.constants import (  # noqa: F401 - re-exported for domain use
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
)

# Fallback languages for translation resolution (in priority order)
# Used when user's language translation is not available
FALLBACK_LANGUAGES: tuple[str, ...] = (DEFAULT_LANGUAGE, "en")

# Default personality code (used when user has no preference)
DEFAULT_PERSONALITY_CODE = "normal"

# Default personality prompt (fallback if no personality found)
DEFAULT_PERSONALITY_PROMPT = """Tu es un assistant equilibre et professionnel.
- Reponds de maniere claire et concise.
- Adapte ton ton au contexte de la conversation.
- Sois utile sans etre excessif.
- Tutoie l'utilisateur."""

# Personality code validation pattern
PERSONALITY_CODE_PATTERN = r"^[a-z][a-z0-9_]*$"

# Maximum lengths
MAX_CODE_LENGTH = 50
MAX_EMOJI_LENGTH = 10
MAX_TITLE_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 500
MAX_PROMPT_LENGTH = 2000
