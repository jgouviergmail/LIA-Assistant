"""
i18n location phrase detection for dual-location feature.

Detects location-related phrases in 6 languages to determine
whether to use home_location (static) or browser geolocation (dynamic).

Location Types:
- QUERY: User asks about their location ("où suis-je", "where am I")
- HOME: References to user's configured home address ("chez moi", "at home")
- CURRENT: References to current position ("nearby", "around me")
- NONE: No location reference detected (implicit, use defaults)

Note (2026-01): Explicit location detection (cities, postal codes, addresses)
is now handled by the planner via the 'location' parameter in tool manifests.
This separation of concerns improves maintainability and i18n compliance.
"""

from enum import Enum
from typing import cast

from src.core.i18n import Language


class LocationType(str, Enum):
    """Type of location reference detected in user message.

    Note: EXPLICIT type was removed in 2026-01 cleanup.
    Explicit location extraction is now handled by the planner via the
    'location' parameter in tool manifests (weather, places, routes).
    This follows the separation of concerns principle: planner extracts
    parameters, tools execute with those parameters.
    """

    HOME = "home"  # User references home ("chez moi", "at home")
    CURRENT = "current"  # User references current position ("nearby", "around me")
    QUERY = "query"  # User asks about current location ("where am I")
    NONE = "none"  # No location reference detected (planner handles explicit locations)


# Phrases indicating HOME location (static, from database)
# User wants info related to their configured home address
HOME_PHRASES: dict[Language, list[str]] = {
    "fr": [
        "chez moi",
        "près de chez moi",
        "à la maison",
        "dans mon quartier",
        "mon domicile",
        "autour de chez moi",
        "proche de chez moi",
        "vers chez moi",
        "à côté de chez moi",
        "mon adresse",
    ],
    "en": [
        "at home",
        "near home",
        "close to home",
        "in my neighborhood",
        "my place",
        "around my house",
        "my home",
        "near my place",
        "close to my place",
        "my address",
    ],
    "es": [
        "en mi casa",
        "cerca de casa",
        "en mi barrio",
        "mi domicilio",
        "alrededor de mi casa",
        "cerca de mi casa",
        "mi hogar",
        "en mi vecindario",
    ],
    "de": [
        "bei mir zuhause",
        "in meiner nähe von zuhause",
        "in meinem viertel",
        "mein zuhause",
        "um mein haus",
        "nahe meines hauses",
        "bei mir",
        "zu hause",
    ],
    "it": [
        "a casa mia",
        "vicino a casa",
        "nel mio quartiere",
        "il mio domicilio",
        "intorno a casa mia",
        "casa mia",
        "dalle mie parti",
        "nel mio vicinato",
    ],
    "zh-CN": [
        "在我家",
        "我家附近",
        "我家周围",
        "我的住处",
        "家附近",
        "靠近我家",
        "我住的地方",
        "我的地址",
    ],
}

# Phrases indicating CURRENT position (dynamic, from browser geolocation)
# User wants info related to their current GPS position
CURRENT_PHRASES: dict[Language, list[str]] = {
    "fr": [
        "à proximité",
        "autour de moi",
        "dans le coin",
        "par ici",
        "près d'ici",
        "à côté",
        "dans les environs",
        "tout près",
        "ici",
        "dans ma zone",
    ],
    "en": [
        "nearby",
        "around me",
        "around here",
        "close by",
        "near me",
        "in the area",
        "close to me",
        "in my vicinity",
        "right here",
        "near here",
    ],
    "es": [
        "cerca de aquí",
        "a mi alrededor",
        "por aquí",
        "en los alrededores",
        "cerca de mí",
        "en esta zona",
        "aquí cerca",
        "por esta zona",
    ],
    "de": [
        "in der nähe",
        "um mich herum",
        "hier in der gegend",
        "in meiner umgebung",
        "nah bei mir",
        "hier",
        "in dieser gegend",
        "ganz in der nähe",
    ],
    "it": [
        "nelle vicinanze",
        "intorno a me",
        "qui vicino",
        "nei dintorni",
        "vicino a me",
        "in questa zona",
        "qui intorno",
        "da queste parti",
    ],
    "zh-CN": [
        "附近",
        "我周围",
        "这附近",
        "在我附近",
        "这里",
        "周边",
        "这一带",
        "我这里",
    ],
}

# Phrases indicating QUERY about current location (user wants to know where they are)
# These trigger the get_current_location_tool for reverse geocoding
QUERY_PHRASES: dict[Language, list[str]] = {
    "fr": [
        "où suis-je",
        "où suis je",
        "je suis où",
        "quelle est ma position",
        "ma position actuelle",
        "à quelle adresse je suis",
        "à quelle adresse suis-je",
        "quelle adresse",
        "c'est où ici",
        "on est où",
        "où on est",
        "où est-ce que je suis",
        "où est-ce qu'on est",
        "ma localisation",
        "quelle est mon adresse",
        "dis-moi où je suis",
        "indique-moi ma position",
    ],
    "en": [
        "where am i",
        "where am I",
        "what is my location",
        "my current location",
        "what address am i at",
        "what's my address",
        "where are we",
        "current position",
        "my position",
        "tell me my location",
        "show my location",
        "what's my current address",
        "where is this place",
    ],
    "es": [
        "dónde estoy",
        "donde estoy",
        "cuál es mi ubicación",
        "mi ubicación actual",
        "en qué dirección estoy",
        "cuál es mi dirección",
        "dónde estamos",
        "mi posición",
        "dime dónde estoy",
        "muestra mi ubicación",
    ],
    "de": [
        "wo bin ich",
        "wo befinde ich mich",
        "mein standort",
        "meine position",
        "welche adresse bin ich",
        "wo sind wir",
        "mein aktueller standort",
        "zeig mir meinen standort",
        "wo ist hier",
    ],
    "it": [
        "dove sono",
        "dove mi trovo",
        "qual è la mia posizione",
        "la mia posizione attuale",
        "a che indirizzo sono",
        "dove siamo",
        "il mio indirizzo",
        "dimmi dove sono",
        "mostra la mia posizione",
    ],
    "zh-CN": [
        "我在哪里",
        "我在哪",
        "我的位置",
        "我现在在哪",
        "这是哪里",
        "这里是哪",
        "我的地址",
        "告诉我我在哪",
        "我们在哪",
        "当前位置",
    ],
}

# Fallback messages when no location is available
# Shown when user explicitly needs location but none is configured/available
FALLBACK_MESSAGES: dict[Language, str] = {
    "fr": (
        "Je n'ai pas accès à ta position. "
        "Peux-tu préciser un lieu, ou activer la géolocalisation dans les paramètres ?"
    ),
    "en": (
        "I don't have access to your location. "
        "Could you specify a place, or enable geolocation in settings?"
    ),
    "es": (
        "No tengo acceso a su ubicación. "
        "¿Podría especificar un lugar o activar la geolocalización en la configuración?"
    ),
    "de": (
        "Ich habe keinen Zugriff auf Ihren Standort. "
        "Könnten Sie einen Ort angeben oder die Geolokalisierung in den Einstellungen aktivieren?"
    ),
    "it": (
        "Non ho accesso alla tua posizione. "
        "Potresti specificare un luogo o attivare la geolocalizzazione nelle impostazioni?"
    ),
    "zh-CN": "我无法访问您的位置。您能否指定一个地点，或在设置中启用地理定位？",
}

# Messages suggesting home location configuration
HOME_CONFIG_SUGGESTION: dict[Language, str] = {
    "fr": "Vous pouvez configurer votre adresse de domicile dans Paramètres > Localisation.",
    "en": "You can configure your home address in Settings > Location.",
    "es": "Puede configurar su dirección de domicilio en Configuración > Ubicación.",
    "de": "Sie können Ihre Heimatadresse unter Einstellungen > Standort konfigurieren.",
    "it": "Puoi configurare il tuo indirizzo di casa in Impostazioni > Posizione.",
    "zh-CN": "您可以在 设置 > 位置 中配置您的家庭地址。",
}


# =============================================================================
# DISTANCE REFERENCE TRANSLATIONS
# =============================================================================
# Used to indicate the origin point when displaying distances
# e.g., "350 m depuis votre position" / "780 m depuis votre domicile"


class DistanceSource:
    """Constants for distance source types."""

    BROWSER = "browser"  # Real-time GPS from browser
    HOME = "home"  # User's configured home address
    SEARCH_LOCATION = "search_location"  # Geocoded location from search query (e.g., "Paris")


DISTANCE_REFERENCE: dict[Language, dict[str, str]] = {
    "fr": {
        DistanceSource.BROWSER: "depuis votre position",
        DistanceSource.HOME: "depuis votre domicile",
        DistanceSource.SEARCH_LOCATION: "depuis le lieu recherché",
    },
    "en": {
        DistanceSource.BROWSER: "from your location",
        DistanceSource.HOME: "from your home",
        DistanceSource.SEARCH_LOCATION: "from the searched location",
    },
    "es": {
        DistanceSource.BROWSER: "desde su ubicación",
        DistanceSource.HOME: "desde su domicilio",
        DistanceSource.SEARCH_LOCATION: "desde la ubicación buscada",
    },
    "de": {
        DistanceSource.BROWSER: "von Ihrem Standort",
        DistanceSource.HOME: "von Ihrem Zuhause",
        DistanceSource.SEARCH_LOCATION: "vom gesuchten Ort",
    },
    "it": {
        DistanceSource.BROWSER: "dalla tua posizione",
        DistanceSource.HOME: "da casa tua",
        DistanceSource.SEARCH_LOCATION: "dalla posizione cercata",
    },
    "zh-CN": {
        DistanceSource.BROWSER: "从您的位置",
        DistanceSource.HOME: "从您的住所",
        DistanceSource.SEARCH_LOCATION: "从搜索位置",
    },
}


# =============================================================================
# PRICE LEVEL TRANSLATIONS
# =============================================================================
# Google Places API price levels translated for display

PRICE_LEVEL: dict[Language, dict[str, str]] = {
    "fr": {
        "PRICE_LEVEL_FREE": "Gratuit",
        "PRICE_LEVEL_INEXPENSIVE": "Bon marché",
        "PRICE_LEVEL_MODERATE": "Modéré",
        "PRICE_LEVEL_EXPENSIVE": "Cher",
        "PRICE_LEVEL_VERY_EXPENSIVE": "Très cher",
    },
    "en": {
        "PRICE_LEVEL_FREE": "Free",
        "PRICE_LEVEL_INEXPENSIVE": "Inexpensive",
        "PRICE_LEVEL_MODERATE": "Moderate",
        "PRICE_LEVEL_EXPENSIVE": "Expensive",
        "PRICE_LEVEL_VERY_EXPENSIVE": "Very expensive",
    },
    "es": {
        "PRICE_LEVEL_FREE": "Gratis",
        "PRICE_LEVEL_INEXPENSIVE": "Económico",
        "PRICE_LEVEL_MODERATE": "Moderado",
        "PRICE_LEVEL_EXPENSIVE": "Caro",
        "PRICE_LEVEL_VERY_EXPENSIVE": "Muy caro",
    },
    "de": {
        "PRICE_LEVEL_FREE": "Kostenlos",
        "PRICE_LEVEL_INEXPENSIVE": "Günstig",
        "PRICE_LEVEL_MODERATE": "Moderat",
        "PRICE_LEVEL_EXPENSIVE": "Teuer",
        "PRICE_LEVEL_VERY_EXPENSIVE": "Sehr teuer",
    },
    "it": {
        "PRICE_LEVEL_FREE": "Gratuito",
        "PRICE_LEVEL_INEXPENSIVE": "Economico",
        "PRICE_LEVEL_MODERATE": "Moderato",
        "PRICE_LEVEL_EXPENSIVE": "Costoso",
        "PRICE_LEVEL_VERY_EXPENSIVE": "Molto costoso",
    },
    "zh-CN": {
        "PRICE_LEVEL_FREE": "免费",
        "PRICE_LEVEL_INEXPENSIVE": "便宜",
        "PRICE_LEVEL_MODERATE": "适中",
        "PRICE_LEVEL_EXPENSIVE": "昂贵",
        "PRICE_LEVEL_VERY_EXPENSIVE": "非常昂贵",
    },
}


def detect_location_type(message: str, language: str = "fr") -> LocationType:
    """
    Detect location type from user message.

    Detects HOME, CURRENT, or QUERY references in user messages.
    Used to determine whether to use home_location or browser geolocation.

    Note: Explicit location detection (cities, postal codes, addresses) is now
    handled by the planner via the 'location' parameter in tool manifests.
    This function only handles implicit location references (home, nearby, etc.).

    Args:
        message: User message to analyze
        language: Language code (fr, en, es, de, it, zh-CN)

    Returns:
        LocationType indicating what kind of location reference was detected:
        - QUERY: User asks about their location ("où suis-je", "where am I")
        - HOME: User references home ("chez moi", "at home")
        - CURRENT: User references current position ("nearby", "around me")
        - NONE: No location reference detected
    """
    message_lower = message.lower()

    # Normalize language code
    lang = _normalize_language(language)

    # Check query phrases first (highest priority - user wants to know location)
    query_phrases = QUERY_PHRASES.get(lang, QUERY_PHRASES["fr"])
    for phrase in query_phrases:
        if phrase in message_lower:
            return LocationType.QUERY

    # Check home phrases (more specific than current)
    home_phrases = HOME_PHRASES.get(lang, HOME_PHRASES["fr"])
    for phrase in home_phrases:
        if phrase in message_lower:
            return LocationType.HOME

    # Check current position phrases
    current_phrases = CURRENT_PHRASES.get(lang, CURRENT_PHRASES["fr"])
    for phrase in current_phrases:
        if phrase in message_lower:
            return LocationType.CURRENT

    return LocationType.NONE


def get_fallback_message(language: str = "fr") -> str:
    """Get localized fallback message when no location is available."""
    lang = _normalize_language(language)
    return FALLBACK_MESSAGES.get(lang, FALLBACK_MESSAGES["fr"])


def get_home_config_suggestion(language: str = "fr") -> str:
    """Get localized suggestion to configure home location."""
    lang = _normalize_language(language)
    return HOME_CONFIG_SUGGESTION.get(lang, HOME_CONFIG_SUGGESTION["fr"])


def contains_home_reference(text: str, language: str = "fr") -> bool:
    """Check if text contains a home location reference."""
    return detect_location_type(text, language) == LocationType.HOME


def contains_current_reference(text: str, language: str = "fr") -> bool:
    """Check if text contains a current position reference."""
    return detect_location_type(text, language) == LocationType.CURRENT


def contains_query_reference(text: str, language: str = "fr") -> bool:
    """Check if text contains a location query (user wants to know where they are)."""
    return detect_location_type(text, language) == LocationType.QUERY


def _normalize_language(language: str) -> Language:
    """Normalize language code to supported format."""
    lang_lower = language.lower().replace("_", "-")

    # Handle Chinese variants
    if lang_lower.startswith("zh"):
        return "zh-CN"

    # Extract base language code
    base_lang = lang_lower.split("-")[0]

    # Return if supported, otherwise default to French
    if base_lang in ("fr", "en", "es", "de", "it"):
        return cast(Language, base_lang)

    return "fr"


# =============================================================================
# DISTANCE & PRICE HELPER FUNCTIONS
# =============================================================================


def get_distance_reference(source: str | None, language: str = "fr") -> str | None:
    """
    Get localized distance reference text based on location source.

    Args:
        source: Location source (DistanceSource.BROWSER, DistanceSource.HOME, or None)
        language: Language code (fr, en, es, de, it, zh-CN)

    Returns:
        Localized reference text or None if source is None

    Example:
        >>> get_distance_reference("browser", "fr")
        "depuis votre position"
        >>> get_distance_reference("home", "en")
        "from your home"
    """
    if source is None:
        return None

    lang = _normalize_language(language)
    lang_refs = DISTANCE_REFERENCE.get(lang, DISTANCE_REFERENCE["fr"])
    return lang_refs.get(source)


def get_price_level(price_code: str | None, language: str = "fr") -> str | None:
    """
    Get localized price level text from Google Places API code.

    Args:
        price_code: Google Places price level code (e.g., "PRICE_LEVEL_MODERATE")
        language: Language code (fr, en, es, de, it, zh-CN)

    Returns:
        Localized price level text or original code if not found

    Example:
        >>> get_price_level("PRICE_LEVEL_MODERATE", "fr")
        "Modéré"
        >>> get_price_level("PRICE_LEVEL_EXPENSIVE", "en")
        "Expensive"
    """
    if price_code is None:
        return None

    lang = _normalize_language(language)
    lang_prices = PRICE_LEVEL.get(lang, PRICE_LEVEL["fr"])
    return lang_prices.get(price_code, price_code)


# =============================================================================
# ROUTES / DIRECTIONS TRANSLATIONS (LOT 12)
# =============================================================================
# Translations for Google Routes API integration

# Phrases indicating ROUTE/DIRECTIONS request
# User wants to get directions or travel information
ROUTE_PHRASES: dict[Language, list[str]] = {
    "fr": [
        "itinéraire pour",
        "itinéraire vers",
        "comment aller",
        "temps de trajet",
        "route vers",
        "direction vers",
        "aller à",
        "aller vers",
        "trajet vers",
        "trajet pour",
        "chemin vers",
        "chemin pour",
        "combien de temps pour aller",
        "distance jusqu'à",
        "distance pour aller",
    ],
    "en": [
        "directions to",
        "how to get to",
        "route to",
        "travel time to",
        "way to",
        "how do I get to",
        "distance to",
        "navigate to",
        "drive to",
        "walk to",
        "get directions",
    ],
    "es": [
        "cómo llegar a",
        "ruta hacia",
        "tiempo de viaje a",
        "direcciones a",
        "camino a",
        "distancia a",
        "ir a",
        "llegar a",
    ],
    "de": [
        "wie komme ich nach",
        "route nach",
        "weg nach",
        "wegbeschreibung nach",
        "fahrzeit nach",
        "entfernung nach",
        "fahrt nach",
    ],
    "it": [
        "come arrivare a",
        "percorso verso",
        "indicazioni per",
        "tempo di percorrenza",
        "distanza da",
        "strada per",
        "direzioni per",
    ],
    "zh-CN": [
        "怎么去",
        "到...的路线",
        "行程时间",
        "导航到",
        "去往",
        "路线到",
        "距离到",
    ],
}

# Transport mode translations
# Maps TravelMode enum values to localized display strings
TRANSPORT_MODES: dict[Language, dict[str, str]] = {
    "fr": {
        "DRIVE": "en voiture",
        "WALK": "à pied",
        "BICYCLE": "à vélo",
        "TRANSIT": "en transports en commun",
        "TWO_WHEELER": "en deux-roues",
    },
    "en": {
        "DRIVE": "by car",
        "WALK": "on foot",
        "BICYCLE": "by bike",
        "TRANSIT": "by public transit",
        "TWO_WHEELER": "by motorcycle",
    },
    "es": {
        "DRIVE": "en coche",
        "WALK": "a pie",
        "BICYCLE": "en bicicleta",
        "TRANSIT": "en transporte público",
        "TWO_WHEELER": "en moto",
    },
    "de": {
        "DRIVE": "mit dem Auto",
        "WALK": "zu Fuß",
        "BICYCLE": "mit dem Fahrrad",
        "TRANSIT": "mit öffentlichen Verkehrsmitteln",
        "TWO_WHEELER": "mit dem Motorrad",
    },
    "it": {
        "DRIVE": "in auto",
        "WALK": "a piedi",
        "BICYCLE": "in bici",
        "TRANSIT": "con i mezzi pubblici",
        "TWO_WHEELER": "in moto",
    },
    "zh-CN": {
        "DRIVE": "驾车",
        "WALK": "步行",
        "BICYCLE": "骑行",
        "TRANSIT": "公共交通",
        "TWO_WHEELER": "摩托车",
    },
}

# Route avoidance options translations
# Maps route modifier options to localized display strings
ROUTE_AVOIDANCES: dict[Language, dict[str, str]] = {
    "fr": {
        "tolls": "péages",
        "highways": "autoroutes",
        "ferries": "ferries",
    },
    "en": {
        "tolls": "tolls",
        "highways": "highways",
        "ferries": "ferries",
    },
    "es": {
        "tolls": "peajes",
        "highways": "autopistas",
        "ferries": "ferris",
    },
    "de": {
        "tolls": "Mautstraßen",
        "highways": "Autobahnen",
        "ferries": "Fähren",
    },
    "it": {
        "tolls": "pedaggi",
        "highways": "autostrade",
        "ferries": "traghetti",
    },
    "zh-CN": {
        "tolls": "收费站",
        "highways": "高速公路",
        "ferries": "渡轮",
    },
}

# Traffic condition translations
# Maps Google Routes API traffic conditions to localized display strings
TRAFFIC_CONDITIONS: dict[Language, dict[str, str]] = {
    "fr": {
        "NORMAL": "fluide",
        "LIGHT": "léger",
        "MODERATE": "modéré",
        "HEAVY": "dense",
    },
    "en": {
        "NORMAL": "normal",
        "LIGHT": "light",
        "MODERATE": "moderate",
        "HEAVY": "heavy",
    },
    "es": {
        "NORMAL": "normal",
        "LIGHT": "leve",
        "MODERATE": "moderado",
        "HEAVY": "denso",
    },
    "de": {
        "NORMAL": "fließend",
        "LIGHT": "leicht",
        "MODERATE": "mäßig",
        "HEAVY": "stockend",
    },
    "it": {
        "NORMAL": "scorrevole",
        "LIGHT": "leggero",
        "MODERATE": "moderato",
        "HEAVY": "intenso",
    },
    "zh-CN": {
        "NORMAL": "畅通",
        "LIGHT": "轻微拥堵",
        "MODERATE": "中度拥堵",
        "HEAVY": "严重拥堵",
    },
}


def get_transport_mode(mode: str, language: str = "fr") -> str:
    """
    Get localized transport mode display string.

    Args:
        mode: TravelMode value (DRIVE, WALK, BICYCLE, TRANSIT, TWO_WHEELER)
        language: Language code (fr, en, es, de, it, zh-CN)

    Returns:
        Localized transport mode string

    Example:
        >>> get_transport_mode("DRIVE", "fr")
        "en voiture"
        >>> get_transport_mode("TRANSIT", "en")
        "by public transit"
    """
    lang = _normalize_language(language)
    lang_modes = TRANSPORT_MODES.get(lang, TRANSPORT_MODES["fr"])
    return lang_modes.get(mode, mode.lower())


def get_traffic_condition(condition: str | None, language: str = "fr") -> str | None:
    """
    Get localized traffic condition display string.

    Args:
        condition: Traffic condition code (NORMAL, LIGHT, MODERATE, HEAVY)
        language: Language code (fr, en, es, de, it, zh-CN)

    Returns:
        Localized traffic condition string or None

    Example:
        >>> get_traffic_condition("MODERATE", "fr")
        "modéré"
        >>> get_traffic_condition("HEAVY", "de")
        "stockend"
    """
    if condition is None:
        return None

    lang = _normalize_language(language)
    lang_conditions = TRAFFIC_CONDITIONS.get(lang, TRAFFIC_CONDITIONS["fr"])
    return lang_conditions.get(condition, condition.lower())


def get_route_avoidance(avoidance: str, language: str = "fr") -> str:
    """
    Get localized route avoidance display string.

    Args:
        avoidance: Avoidance type (tolls, highways, ferries)
        language: Language code (fr, en, es, de, it, zh-CN)

    Returns:
        Localized avoidance string

    Example:
        >>> get_route_avoidance("tolls", "fr")
        "péages"
        >>> get_route_avoidance("highways", "de")
        "Autobahnen"
    """
    lang = _normalize_language(language)
    lang_avoidances = ROUTE_AVOIDANCES.get(lang, ROUTE_AVOIDANCES["fr"])
    return lang_avoidances.get(avoidance, avoidance)


def contains_route_reference(text: str, language: str = "fr") -> bool:
    """
    Check if text contains a route/directions reference.

    Args:
        text: Text to check
        language: Language code

    Returns:
        True if route/directions reference detected

    Example:
        >>> contains_route_reference("Comment aller à Lyon?", "fr")
        True
        >>> contains_route_reference("La météo à Paris", "fr")
        False
    """
    text_lower = text.lower()
    lang = _normalize_language(language)
    route_phrases = ROUTE_PHRASES.get(lang, ROUTE_PHRASES["fr"])

    for phrase in route_phrases:
        if phrase in text_lower:
            return True

    return False
