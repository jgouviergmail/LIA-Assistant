"""
Internationalized regex patterns for reference resolution.

Provides language-specific patterns for:
- Ordinal numbers (premier, first, primero, erster, primo, 第一)
- Keywords (dernier, last, último, letzter, ultimo, 最后)
- Ordinal suffixes for number parsing (ème, th, º, ter, esimo, 第)

Supported languages: fr, en, es, de, it, zh-CN
"""

from src.core.i18n import resolve_language
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
# FUNCTION WORDS (descriptive references, ADR-367)
# =============================================================================

# Articles, prepositions and conjunctions that name nothing: a description such
# as « the email of Marc » designates its item by « Marc » alone. Chinese has
# none to separate — a run of characters is matched as a substring.
FUNCTION_WORDS: dict[Language, frozenset[str]] = {
    "fr": frozenset("le la les de du des un une au aux et ou en sur pour par avec chez".split()),
    "en": frozenset("the an of to from by on in at and or for with".split()),
    "es": frozenset("el la los las de del un una unos unas al en con por para".split()),
    "de": frozenset(
        "der die das den dem des ein eine einen einem einer von vom zu zum zur und "
        "oder im am an auf mit aus bei".split()
    ),
    "it": frozenset(
        "il lo la gli le di del dello della dei degli delle un una uno al alla in "
        "con da su per".split()
    ),
    "zh-CN": frozenset(),
}


# =============================================================================
# CHOICE ANSWERS (« which one? », ADR-367)
# =============================================================================
# Read in the person's own language only: « due » is two in Italian and a date
# in English, « prima » first in Italian and « before » in a sentence. Written
# accent-free and lower-cased, the folded form an answer is read in.

# Cardinal numbers naming an option by its number. One is left out on purpose:
# « un », « one », « uno », « ein » are also articles and pronouns (« the
# garage one »), and « 一 » opens « 一个 » (« a »).
CHOICE_NUMBER_WORDS: dict[Language, dict[str, int]] = {
    "fr": {
        "deux": 2,
        "trois": 3,
        "quatre": 4,
        "cinq": 5,
        "six": 6,
        "sept": 7,
        "huit": 8,
        "neuf": 9,
        "dix": 10,
    },
    "en": {
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    },
    "es": {
        "dos": 2,
        "tres": 3,
        "cuatro": 4,
        "cinco": 5,
        "seis": 6,
        "siete": 7,
        "ocho": 8,
        "nueve": 9,
        "diez": 10,
    },
    "de": {
        "zwei": 2,
        "drei": 3,
        "vier": 4,
        "funf": 5,
        "sechs": 6,
        "sieben": 7,
        "acht": 8,
        "neun": 9,
        "zehn": 10,
    },
    "it": {
        "due": 2,
        "tre": 3,
        "quattro": 4,
        "cinque": 5,
        "sei": 6,
        "sette": 7,
        "otto": 8,
        "nove": 9,
        "dieci": 10,
    },
    "zh-CN": {
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    },
}

# The words a REQUEST gives an item's position among the results with (« le
# dernier mail de Marc », « Marc's latest email »): the act takes that one and
# nothing is asked (ADR-367 amendment, ``nodes/plan_choice.py``). Folded as
# ``fold_name`` folds; a Chinese word is looked for inside the request.
REQUEST_POSITION_WORDS: dict[Language, frozenset[str]] = {
    "fr": frozenset(
        {"dernier", "derniere", "recent", "recente", "ancien", "ancienne", "premier", "premiere"}
    ),
    "en": frozenset({"last", "latest", "newest", "recent", "oldest", "earliest", "first"}),
    "es": frozenset({"ultimo", "ultima", "reciente", "antiguo", "antigua", "primero", "primera"}),
    "de": frozenset(
        {
            "letzte",
            "letzter",
            "letztes",
            "letzten",
            "neueste",
            "neuester",
            "neuesten",
            "aktuellste",
            "aktuellsten",
            "alteste",
            "altesten",
            "erste",
            "ersten",
        }
    ),
    "it": frozenset({"ultimo", "ultima", "recente", "vecchio", "vecchia", "primo"}),
    "zh-CN": frozenset({"最后", "最新", "最近", "最早", "第一"}),
}

# The words naming the LAST option (« le dernier », « the last one »).
CHOICE_LAST_WORDS: dict[Language, frozenset[str]] = {
    "fr": frozenset({"dernier", "derniere"}),
    "en": frozenset({"last"}),
    "es": frozenset({"ultimo", "ultima"}),
    "de": frozenset({"letzte", "letzter", "letztes", "letzten"}),
    "it": frozenset({"ultimo", "ultima"}),
    "zh-CN": frozenset({"最后"}),
}

# Words an answer leans on to name an option without describing it
# (« numéro 2 », « the second one », « quello »).
CHOICE_FILLER_WORDS: dict[Language, frozenset[str]] = {
    "fr": frozenset({"celui", "celle", "lequel", "laquelle", "ci", "numero", "choix", "option"}),
    "en": frozenset({"one", "number", "no", "nr", "option", "choice"}),
    "es": frozenset({"ese", "esa", "este", "esta", "numero", "opcion", "eleccion"}),
    "de": frozenset({"nummer", "nr", "option", "wahl"}),
    "it": frozenset({"quello", "quella", "questo", "questa", "numero", "opzione", "scelta"}),
    "zh-CN": frozenset({"个", "号", "选项"}),
}

# Answers saying the item is none of the options: the request is then looked
# up anew. Matched on the WHOLE answer (politeness aside), never inside one.
CHOICE_NONE_PHRASES: dict[Language, frozenset[str]] = {
    "fr": frozenset(
        {
            "aucun",
            "aucune",
            "aucun des deux",
            "aucun d'eux",
            "aucun de ceux-là",
            "ni l'un ni l'autre",
            "un autre",
        }
    ),
    "en": frozenset(
        {"none", "neither", "none of them", "none of these", "neither of them", "another one"}
    ),
    "es": frozenset(
        {"ninguno", "ninguna", "ninguno de ellos", "ninguno de estos", "ninguno de los dos", "otro"}
    ),
    "de": frozenset(
        {"keiner", "keine", "keines", "keiner davon", "keines davon", "keins", "ein anderer"}
    ),
    "it": frozenset({"nessuno", "nessuna", "nessuno dei due", "nessuno di questi", "un altro"}),
    "zh-CN": frozenset({"都不是", "一个都不是", "都不对", "另一个", "别的"}),
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
        return ORDINAL_MAPS[resolve_language(language)]

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
        return KEYWORD_MAPS[resolve_language(language)]

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
        return ORDINAL_SUFFIX_PATTERNS[resolve_language(language)]

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


def get_all_function_words() -> frozenset[str]:
    """
    Get the function words of every supported language.

    A description is matched in whatever language it was written, so the
    words carrying no identity are those of all six languages at once. They
    are written accent-free and lower-cased, the folded form a matcher reads.

    Returns:
        Frozen set of function words.
    """
    return frozenset(word for words in FUNCTION_WORDS.values() for word in words)
