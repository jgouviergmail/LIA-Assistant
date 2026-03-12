"""
Internationalized regex patterns for reference resolution.

Provides language-specific patterns for:
- Ordinal numbers (premier, first, primero, erster, primo, 第一)
- Keywords (dernier, last, último, letzter, ultimo, 最后)
- Ordinal suffixes for number parsing (ème, th, º, ter, esimo, 第)

Supported languages: fr, en, es, de, it, zh-CN
"""

from src.core.config import settings
from src.core.i18n_types import Language

# =============================================================================
# ORDINAL WORD MAPPINGS
# =============================================================================

# Each language maps ordinal words to their numeric value (1-indexed)
ORDINAL_MAPS: dict[Language, dict[str, int]] = {
    "fr": {
        "premier": 1,
        "première": 1,
        "premiere": 1,
        "deuxième": 2,
        "deuxieme": 2,
        "second": 2,
        "seconde": 2,
        "troisième": 3,
        "troisieme": 3,
        "quatrième": 4,
        "quatrieme": 4,
        "cinquième": 5,
        "cinquieme": 5,
        "sixième": 6,
        "sixieme": 6,
        "septième": 7,
        "septieme": 7,
        "huitième": 8,
        "huitieme": 8,
        "neuvième": 9,
        "neuvieme": 9,
        "dixième": 10,
        "dixieme": 10,
    },
    "en": {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    },
    "es": {
        "primero": 1,
        "primera": 1,
        "segundo": 2,
        "segunda": 2,
        "tercero": 3,
        "tercera": 3,
        "cuarto": 4,
        "cuarta": 4,
        "quinto": 5,
        "quinta": 5,
        "sexto": 6,
        "sexta": 6,
        "séptimo": 7,
        "septimo": 7,
        "octavo": 8,
        "octava": 8,
        "noveno": 9,
        "novena": 9,
        "décimo": 10,
        "decimo": 10,
    },
    "de": {
        "erste": 1,
        "erster": 1,
        "erstes": 1,
        "zweite": 2,
        "zweiter": 2,
        "zweites": 2,
        "dritte": 3,
        "dritter": 3,
        "drittes": 3,
        "vierte": 4,
        "vierter": 4,
        "fünfte": 5,
        "funfte": 5,
        "sechste": 6,
        "siebte": 7,
        "achte": 8,
        "neunte": 9,
        "zehnte": 10,
    },
    "it": {
        "primo": 1,
        "prima": 1,
        "secondo": 2,
        "seconda": 2,
        "terzo": 3,
        "terza": 3,
        "quarto": 4,
        "quarta": 4,
        "quinto": 5,
        "quinta": 5,
        "sesto": 6,
        "sesta": 6,
        "settimo": 7,
        "settima": 7,
        "ottavo": 8,
        "ottava": 8,
        "nono": 9,
        "nona": 9,
        "decimo": 10,
        "decima": 10,
    },
    "zh-CN": {
        "第一": 1,
        "第二": 2,
        "第三": 3,
        "第四": 4,
        "第五": 5,
        "第六": 6,
        "第七": 7,
        "第八": 8,
        "第九": 9,
        "第十": 10,
    },
}


# =============================================================================
# KEYWORD MAPPINGS
# =============================================================================

# Maps keywords like "last", "dernier" to special indices
# -1 = last item, 1 = first item
# Demonstrative pronouns ("cet", "this", "ce") also resolve to -1 (most recent/current)
KEYWORD_MAPS: dict[Language, dict[str, int]] = {
    "fr": {
        "dernier": -1,
        "dernière": -1,
        "derniere": -1,
        "premier": 1,
        "première": 1,
        "premiere": 1,
        # Demonstrative pronouns - resolve to last/current item
        "cet": -1,
        "cette": -1,
        "ce": -1,
        "celui-ci": -1,
        "celle-ci": -1,
    },
    "en": {
        "last": -1,
        "first": 1,
        # Demonstrative pronouns
        "this": -1,
        "that": -1,
        "it": -1,
    },
    "es": {
        "último": -1,
        "ultimo": -1,
        "última": -1,
        "ultima": -1,
        "primero": 1,
        "primera": 1,
        # Demonstrative pronouns
        "este": -1,
        "esta": -1,
        "ese": -1,
        "esa": -1,
    },
    "de": {
        "letzter": -1,
        "letzte": -1,
        "letztes": -1,
        "erste": 1,
        "erster": 1,
        "erstes": 1,
        # Demonstrative pronouns
        "dieser": -1,
        "diese": -1,
        "dieses": -1,
    },
    "it": {
        "ultimo": -1,
        "ultima": -1,
        "primo": 1,
        "prima": 1,
        # Demonstrative pronouns
        "questo": -1,
        "questa": -1,
        "quello": -1,
        "quella": -1,
    },
    "zh-CN": {
        "最后": -1,
        "最後": -1,
        "第一": 1,
        # Demonstrative pronouns
        "这个": -1,
        "那个": -1,
    },
}


# =============================================================================
# ORDINAL SUFFIX PATTERNS (for regex matching)
# =============================================================================

# Patterns to match ordinal suffixes in each language
# Used to extract numeric index from strings like "2ème", "3rd", "4º"
ORDINAL_SUFFIX_PATTERNS: dict[Language, list[str]] = {
    "fr": [
        r"^(\d+)$",  # Plain number
        r"^(\d+)(ème|eme|er|ère|ere|e)$",  # French ordinals
    ],
    "en": [
        r"^(\d+)$",  # Plain number
        r"^(\d+)(st|nd|rd|th)$",  # English ordinals
    ],
    "es": [
        r"^(\d+)$",  # Plain number
        r"^(\d+)(º|ª|o|a)$",  # Spanish ordinals
    ],
    "de": [
        r"^(\d+)$",  # Plain number
        r"^(\d+)(\.|\-?ter?|\-?tes?|\-?te)$",  # German ordinals
    ],
    "it": [
        r"^(\d+)$",  # Plain number
        r"^(\d+)(º|ª|°|esimo|esima)$",  # Italian ordinals
    ],
    "zh-CN": [
        r"^(\d+)$",  # Plain number
        r"^第?(\d+)$",  # Chinese with optional 第 prefix
    ],
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_ordinal_map(language: Language | None = None) -> dict[str, int]:
    """
    Get ordinal word mappings for a language.

    Returns combined mappings for all supported languages if language is None.
    This allows recognition of ordinals in any supported language.

    Args:
        language: Target language or None for all languages combined.

    Returns:
        Dictionary mapping ordinal words to their numeric values.
    """
    if language:
        default_lang: Language = settings.default_language  # type: ignore[assignment]
        return ORDINAL_MAPS.get(language, ORDINAL_MAPS[default_lang])

    # Combine all languages for universal recognition
    combined: dict[str, int] = {}
    for lang_map in ORDINAL_MAPS.values():
        combined.update(lang_map)
    return combined


def get_keyword_map(language: Language | None = None) -> dict[str, int]:
    """
    Get keyword mappings for a language.

    Returns combined mappings for all supported languages if language is None.

    Args:
        language: Target language or None for all languages combined.

    Returns:
        Dictionary mapping keywords to their special index values.
    """
    if language:
        default_lang: Language = settings.default_language  # type: ignore[assignment]
        return KEYWORD_MAPS.get(language, KEYWORD_MAPS[default_lang])

    # Combine all languages for universal recognition
    combined: dict[str, int] = {}
    for lang_map in KEYWORD_MAPS.values():
        combined.update(lang_map)
    return combined


def get_ordinal_suffix_patterns(language: Language | None = None) -> list[str]:
    """
    Get ordinal suffix regex patterns for a language.

    Returns combined patterns for all supported languages if language is None.

    Args:
        language: Target language or None for all languages combined.

    Returns:
        List of regex patterns for matching ordinal suffixes.
    """
    if language:
        default_lang: Language = settings.default_language  # type: ignore[assignment]
        return ORDINAL_SUFFIX_PATTERNS.get(language, ORDINAL_SUFFIX_PATTERNS[default_lang])

    # Combine all languages for universal recognition
    combined: list[str] = []
    seen: set[str] = set()
    for patterns in ORDINAL_SUFFIX_PATTERNS.values():
        for pattern in patterns:
            if pattern not in seen:
                combined.append(pattern)
                seen.add(pattern)
    return combined


def get_all_ordinal_words() -> set[str]:
    """
    Get all ordinal words from all supported languages.

    Returns:
        Set of all ordinal words (lowercase).
    """
    words: set[str] = set()
    for lang_map in ORDINAL_MAPS.values():
        words.update(word.lower() for word in lang_map.keys())
    return words


def get_all_keywords() -> set[str]:
    """
    Get all keywords from all supported languages.

    Returns:
        Set of all keywords (lowercase).
    """
    words: set[str] = set()
    for lang_map in KEYWORD_MAPS.values():
        words.update(word.lower() for word in lang_map.keys())
    return words


# =============================================================================
# INDEX TO ORDINAL LABELS (for output generation)
# =============================================================================

# Maps 1-based index to ordinal labels for each language
# Used when generating prompts/outputs with ordinal references
# Includes abbreviated forms commonly used in user interfaces
INDEX_TO_ORDINAL_LABELS: dict[Language, dict[int, str]] = {
    "fr": {
        1: "premier/1er",
        2: "deuxième/2ème",
        3: "troisième/3ème",
        4: "quatrième/4ème",
        5: "cinquième/5ème",
        6: "sixième/6ème",
        7: "septième/7ème",
        8: "huitième/8ème",
        9: "neuvième/9ème",
        10: "dixième/10ème",
        -1: "dernier",
    },
    "en": {
        1: "first/1st",
        2: "second/2nd",
        3: "third/3rd",
        4: "fourth/4th",
        5: "fifth/5th",
        6: "sixth/6th",
        7: "seventh/7th",
        8: "eighth/8th",
        9: "ninth/9th",
        10: "tenth/10th",
        -1: "last",
    },
    "es": {
        1: "primero/1º",
        2: "segundo/2º",
        3: "tercero/3º",
        4: "cuarto/4º",
        5: "quinto/5º",
        6: "sexto/6º",
        7: "séptimo/7º",
        8: "octavo/8º",
        9: "noveno/9º",
        10: "décimo/10º",
        -1: "último",
    },
    "de": {
        1: "erste/1.",
        2: "zweite/2.",
        3: "dritte/3.",
        4: "vierte/4.",
        5: "fünfte/5.",
        6: "sechste/6.",
        7: "siebte/7.",
        8: "achte/8.",
        9: "neunte/9.",
        10: "zehnte/10.",
        -1: "letzte",
    },
    "it": {
        1: "primo/1º",
        2: "secondo/2º",
        3: "terzo/3º",
        4: "quarto/4º",
        5: "quinto/5º",
        6: "sesto/6º",
        7: "settimo/7º",
        8: "ottavo/8º",
        9: "nono/9º",
        10: "decimo/10º",
        -1: "ultimo",
    },
    "zh-CN": {
        1: "第一/1",
        2: "第二/2",
        3: "第三/3",
        4: "第四/4",
        5: "第五/5",
        6: "第六/6",
        7: "第七/7",
        8: "第八/8",
        9: "第九/9",
        10: "第十/10",
        -1: "最后",
    },
}


def get_ordinal_label_for_index(index: int, language: Language | None = None) -> str:
    """
    Get ordinal label for a 1-based index in the specified language.

    Used when generating prompts/outputs that need to reference items by ordinal.

    Args:
        index: 1-based index (1 = first, 2 = second, etc.) or -1 for last
        language: Target language or None for default (fr)

    Returns:
        Ordinal label string (e.g., "deuxième/2ème" for index=2, language="fr")

    Example:
        >>> get_ordinal_label_for_index(2, "fr")
        'deuxième/2ème'
        >>> get_ordinal_label_for_index(1, "en")
        'first/1st'
        >>> get_ordinal_label_for_index(15, "fr")
        '15ème'
    """
    lang: Language = language or settings.default_language  # type: ignore[assignment]

    # Handle unsupported language with fallback
    if lang not in INDEX_TO_ORDINAL_LABELS:
        lang = "fr"  # Default fallback

    label_map = INDEX_TO_ORDINAL_LABELS[lang]

    # Direct lookup for known ordinals
    if index in label_map:
        return label_map[index]

    # Dynamic generation for larger numbers
    if lang == "fr":
        return f"{index}ème"
    elif lang == "en":
        # English ordinal suffix rules
        if 11 <= index <= 13:
            return f"{index}th"
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(index % 10, "th")
        return f"{index}{suffix}"
    elif lang == "es":
        return f"{index}º"
    elif lang == "de":
        return f"{index}."
    elif lang == "it":
        return f"{index}º"
    elif lang == "zh-CN":
        return f"第{index}"
    else:
        return f"{index}ème"  # Fallback to French style
