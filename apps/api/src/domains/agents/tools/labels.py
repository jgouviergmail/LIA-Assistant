"""
Centralized labels, emojis, and translations for all domains.

Provides:
- TYPE_EMOJIS: Field type to emoji mapping
- FIELD_TYPE_TRANSLATIONS: Contact field types (home, work, mobile...)
- RELATION_TYPE_TRANSLATIONS: Relation types (spouse, child, parent...)

Used by formatters to create consistent, localized labels with emojis.

Supported languages: fr, en, es, de, it, zh-CN
"""

from typing import Literal

from src.core.config import settings

Language = Literal["fr", "en", "es", "de", "it", "zh-CN"]

# =============================================================================
# EMOJIS BY FIELD TYPE
# =============================================================================

TYPE_EMOJIS: dict[str, str] = {
    # Contact info types (for labels)
    "home": "🏠",
    "work": "💼",
    "mobile": "📱",
    "main": "📞",
    "other": "📧",
    "default": "ℹ️",
    # Phone-specific
    "homefax": "📠",
    "workfax": "📠",
    "otherfax": "📠",
    "pager": "📟",
    # Field categories (for headers)
    "name": "👤",
    "email": "📧",
    "phone": "📞",
    "address": "📍",
    "birthday": "🎂",
    "relation": "👥",
    "organization": "🏢",
    "notes": "📝",
    "event": "📅",
    "url": "🌐",
    "im": "💬",
    "skill": "🛠️",
    "occupation": "💼",
    "photo": "📷",
    "interest": "⭐",
    # Calendar/Tasks
    "calendar": "📅",
    "task": "✅",
    "location": "📍",
    "participant": "👤",
    "reminder": "⏰",
    # Emails
    "inbox": "📥",
    "sent": "📤",
    "from": "👤",
    "to": "📬",
    "subject": "📋",
    "attachment": "📎",
    # Places
    "place": "📍",
    "rating": "⭐",
    "hours": "🕐",
    # Weather
    "weather": "🌤️",
    "temperature": "🌡️",
}

# =============================================================================
# FIELD TYPE TRANSLATIONS
# =============================================================================

FIELD_TYPE_TRANSLATIONS: dict[str, dict[Language, str]] = {
    # Email/Phone/Address common types
    "home": {
        "fr": "Domicile",
        "en": "Home",
        "es": "Casa",
        "de": "Privat",
        "it": "Casa",
        "zh-CN": "住宅",
    },
    "work": {
        "fr": "Travail",
        "en": "Work",
        "es": "Trabajo",
        "de": "Arbeit",
        "it": "Lavoro",
        "zh-CN": "工作",
    },
    "other": {
        "fr": "Autre",
        "en": "Other",
        "es": "Otro",
        "de": "Andere",
        "it": "Altro",
        "zh-CN": "其他",
    },
    # Phone-specific types
    "mobile": {
        "fr": "Mobile",
        "en": "Mobile",
        "es": "Móvil",
        "de": "Mobil",
        "it": "Cellulare",
        "zh-CN": "手机",
    },
    "main": {
        "fr": "Principal",
        "en": "Main",
        "es": "Principal",
        "de": "Haupt",
        "it": "Principale",
        "zh-CN": "主要",
    },
    "homefax": {
        "fr": "Fax domicile",
        "en": "Home Fax",
        "es": "Fax casa",
        "de": "Fax privat",
        "it": "Fax casa",
        "zh-CN": "住宅传真",
    },
    "workfax": {
        "fr": "Fax travail",
        "en": "Work Fax",
        "es": "Fax trabajo",
        "de": "Fax Arbeit",
        "it": "Fax lavoro",
        "zh-CN": "工作传真",
    },
    "otherfax": {
        "fr": "Autre fax",
        "en": "Other Fax",
        "es": "Otro fax",
        "de": "Anderes Fax",
        "it": "Altro fax",
        "zh-CN": "其他传真",
    },
    "pager": {
        "fr": "Pager",
        "en": "Pager",
        "es": "Buscapersonas",
        "de": "Pager",
        "it": "Cercapersone",
        "zh-CN": "寻呼机",
    },
    # Default fallback
    "default": {
        "fr": "Défaut",
        "en": "Default",
        "es": "Predeterminado",
        "de": "Standard",
        "it": "Predefinito",
        "zh-CN": "默认",
    },
}

# =============================================================================
# RELATION TYPE TRANSLATIONS
# =============================================================================

RELATION_TYPE_TRANSLATIONS: dict[str, dict[Language, str]] = {
    "spouse": {
        "fr": "Conjoint(e)",
        "en": "Spouse",
        "es": "Cónyuge",
        "de": "Ehepartner(in)",
        "it": "Coniuge",
        "zh-CN": "配偶",
    },
    "child": {
        "fr": "Enfant",
        "en": "Child",
        "es": "Hijo/a",
        "de": "Kind",
        "it": "Figlio/a",
        "zh-CN": "子女",
    },
    "mother": {
        "fr": "Mère",
        "en": "Mother",
        "es": "Madre",
        "de": "Mutter",
        "it": "Madre",
        "zh-CN": "母亲",
    },
    "father": {
        "fr": "Père",
        "en": "Father",
        "es": "Padre",
        "de": "Vater",
        "it": "Padre",
        "zh-CN": "父亲",
    },
    "parent": {
        "fr": "Parent",
        "en": "Parent",
        "es": "Padre/Madre",
        "de": "Elternteil",
        "it": "Genitore",
        "zh-CN": "父母",
    },
    "brother": {
        "fr": "Frère",
        "en": "Brother",
        "es": "Hermano",
        "de": "Bruder",
        "it": "Fratello",
        "zh-CN": "兄弟",
    },
    "sister": {
        "fr": "Sœur",
        "en": "Sister",
        "es": "Hermana",
        "de": "Schwester",
        "it": "Sorella",
        "zh-CN": "姐妹",
    },
    "friend": {
        "fr": "Ami(e)",
        "en": "Friend",
        "es": "Amigo/a",
        "de": "Freund(in)",
        "it": "Amico/a",
        "zh-CN": "朋友",
    },
    "relative": {
        "fr": "Parent(e)",
        "en": "Relative",
        "es": "Familiar",
        "de": "Verwandte(r)",
        "it": "Parente",
        "zh-CN": "亲属",
    },
    "domesticPartner": {
        "fr": "Partenaire",
        "en": "Domestic Partner",
        "es": "Pareja",
        "de": "Lebenspartner(in)",
        "it": "Convivente",
        "zh-CN": "伴侣",
    },
    "manager": {
        "fr": "Manager",
        "en": "Manager",
        "es": "Gerente",
        "de": "Vorgesetzte(r)",
        "it": "Responsabile",
        "zh-CN": "经理",
    },
    "assistant": {
        "fr": "Assistant(e)",
        "en": "Assistant",
        "es": "Asistente",
        "de": "Assistent(in)",
        "it": "Assistente",
        "zh-CN": "助理",
    },
    "referredBy": {
        "fr": "Recommandé par",
        "en": "Referred By",
        "es": "Referido por",
        "de": "Empfohlen von",
        "it": "Segnalato da",
        "zh-CN": "推荐人",
    },
    "partner": {
        "fr": "Partenaire",
        "en": "Partner",
        "es": "Socio/a",
        "de": "Partner(in)",
        "it": "Partner",
        "zh-CN": "合作伙伴",
    },
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _extract_language(locale: str | None) -> Language:
    """Extract language code from locale string."""
    if not locale:
        return settings.default_language

    if locale.lower() == "zh-cn":
        return "zh-CN"

    lang = locale.split("-")[0].lower() if "-" in locale else locale.lower()
    if lang in ("fr", "en", "es", "de", "it", "zh-CN"):
        return lang  # type: ignore[return-value]

    return settings.default_language


def get_emoji(field_type: str) -> str:
    """
    Get emoji for a field type.

    Args:
        field_type: Type key (e.g., "home", "work", "email", "birthday")

    Returns:
        Emoji string

    Example:
        >>> get_emoji("home")
        "🏠"
        >>> get_emoji("birthday")
        "🎂"
    """
    return TYPE_EMOJIS.get(field_type.lower(), "ℹ️")


def translate_field_type(
    field_type: str | None, locale: str = "fr", use_default: bool = True
) -> str:
    """
    Translate field type to localized label.

    Args:
        field_type: Field type from API (e.g., "home", "work", "mobile")
        locale: Target locale (e.g., "fr", "en")
        use_default: If True, return "Défaut" when no type; if False, return ""

    Returns:
        Translated field type label

    Example:
        >>> translate_field_type("home", "fr")
        "Domicile"
        >>> translate_field_type("work", "en")
        "Work"
    """
    lang = _extract_language(locale)

    if not field_type:
        if use_default:
            default_translations = FIELD_TYPE_TRANSLATIONS.get("default", {})
            return default_translations.get(lang, default_translations.get("en", "Default"))
        return ""

    normalized = field_type.lower().strip()

    if normalized in FIELD_TYPE_TRANSLATIONS:
        translations = FIELD_TYPE_TRANSLATIONS[normalized]
        return translations.get(lang, translations.get("en", field_type))

    # Fallback: capitalize the original
    return field_type.capitalize()


def translate_relation_type(relation_type: str | None, locale: str = "fr") -> str:
    """
    Translate relation type to localized label.

    Args:
        relation_type: Relation type from API (e.g., "spouse", "child")
        locale: Target locale

    Returns:
        Translated relation type label

    Example:
        >>> translate_relation_type("spouse", "fr")
        "Conjoint(e)"
        >>> translate_relation_type("child", "en")
        "Child"
    """
    lang = _extract_language(locale)

    if not relation_type:
        return ""

    normalized = relation_type.strip()

    if normalized in RELATION_TYPE_TRANSLATIONS:
        translations = RELATION_TYPE_TRANSLATIONS[normalized]
        return translations.get(lang, translations.get("en", relation_type))

    # Fallback: capitalize the original
    return relation_type.capitalize()


def get_emoji_label(field_type: str, locale: str = "fr") -> str:
    """
    Get emoji + translated label for a field type.

    Args:
        field_type: Type key (e.g., "home", "work", "mobile")
        locale: Target locale

    Returns:
        Combined emoji and label string

    Example:
        >>> get_emoji_label("home", "fr")
        "🏠 Domicile"
        >>> get_emoji_label("mobile", "en")
        "📱 Mobile"
    """
    emoji = get_emoji(field_type)
    label = translate_field_type(field_type, locale, use_default=False)
    if label:
        return f"{emoji} {label}"
    return emoji


def get_relation_emoji_label(relation_type: str, locale: str = "fr") -> str:
    """
    Get emoji + translated label for a relation type.

    Args:
        relation_type: Relation type (e.g., "spouse", "child")
        locale: Target locale

    Returns:
        Combined emoji and label string

    Example:
        >>> get_relation_emoji_label("spouse", "fr")
        "👥 Conjoint(e)"
    """
    emoji = get_emoji("relation")
    label = translate_relation_type(relation_type, locale)
    if label:
        return f"{emoji} {label}"
    return emoji
