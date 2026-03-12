"""
Unit tests for i18n location utilities.

Tests for location phrase detection, distance reference translations,
price level translations, and route-related i18n functions.
"""

from src.domains.agents.utils.i18n_location import (
    CURRENT_PHRASES,
    DISTANCE_REFERENCE,
    FALLBACK_MESSAGES,
    HOME_CONFIG_SUGGESTION,
    HOME_PHRASES,
    PRICE_LEVEL,
    QUERY_PHRASES,
    ROUTE_AVOIDANCES,
    ROUTE_PHRASES,
    TRAFFIC_CONDITIONS,
    TRANSPORT_MODES,
    DistanceSource,
    LocationType,
    _normalize_language,
    contains_current_reference,
    contains_home_reference,
    contains_query_reference,
    contains_route_reference,
    detect_location_type,
    get_distance_reference,
    get_fallback_message,
    get_home_config_suggestion,
    get_price_level,
    get_route_avoidance,
    get_traffic_condition,
    get_transport_mode,
)

# ============================================================================
# Tests for LocationType enum
# ============================================================================


class TestLocationType:
    """Tests for LocationType enum."""

    def test_home_type_exists(self):
        """Test that HOME type exists."""
        assert LocationType.HOME.value == "home"

    def test_current_type_exists(self):
        """Test that CURRENT type exists."""
        assert LocationType.CURRENT.value == "current"

    def test_query_type_exists(self):
        """Test that QUERY type exists."""
        assert LocationType.QUERY.value == "query"

    def test_none_type_exists(self):
        """Test that NONE type exists."""
        assert LocationType.NONE.value == "none"

    def test_location_type_is_str_enum(self):
        """Test that LocationType is a string enum."""
        assert isinstance(LocationType.HOME, str)
        assert LocationType.HOME == "home"


# ============================================================================
# Tests for DistanceSource constants
# ============================================================================


class TestDistanceSource:
    """Tests for DistanceSource class constants."""

    def test_browser_source(self):
        """Test BROWSER constant."""
        assert DistanceSource.BROWSER == "browser"

    def test_home_source(self):
        """Test HOME constant."""
        assert DistanceSource.HOME == "home"

    def test_search_location_source(self):
        """Test SEARCH_LOCATION constant."""
        assert DistanceSource.SEARCH_LOCATION == "search_location"


# ============================================================================
# Tests for phrase dictionaries
# ============================================================================


class TestPhraseDictionaries:
    """Tests for phrase dictionaries."""

    def test_home_phrases_has_6_languages(self):
        """Test that HOME_PHRASES has all 6 languages."""
        expected_languages = {"fr", "en", "es", "de", "it", "zh-CN"}
        assert set(HOME_PHRASES.keys()) == expected_languages

    def test_current_phrases_has_6_languages(self):
        """Test that CURRENT_PHRASES has all 6 languages."""
        expected_languages = {"fr", "en", "es", "de", "it", "zh-CN"}
        assert set(CURRENT_PHRASES.keys()) == expected_languages

    def test_query_phrases_has_6_languages(self):
        """Test that QUERY_PHRASES has all 6 languages."""
        expected_languages = {"fr", "en", "es", "de", "it", "zh-CN"}
        assert set(QUERY_PHRASES.keys()) == expected_languages

    def test_home_phrases_not_empty(self):
        """Test that HOME_PHRASES lists are not empty."""
        for lang, phrases in HOME_PHRASES.items():
            assert len(phrases) > 0, f"HOME_PHRASES[{lang}] is empty"

    def test_current_phrases_not_empty(self):
        """Test that CURRENT_PHRASES lists are not empty."""
        for lang, phrases in CURRENT_PHRASES.items():
            assert len(phrases) > 0, f"CURRENT_PHRASES[{lang}] is empty"

    def test_query_phrases_not_empty(self):
        """Test that QUERY_PHRASES lists are not empty."""
        for lang, phrases in QUERY_PHRASES.items():
            assert len(phrases) > 0, f"QUERY_PHRASES[{lang}] is empty"

    def test_french_home_phrases_examples(self):
        """Test that specific French home phrases exist."""
        assert "chez moi" in HOME_PHRASES["fr"]
        assert "à la maison" in HOME_PHRASES["fr"]

    def test_english_home_phrases_examples(self):
        """Test that specific English home phrases exist."""
        assert "at home" in HOME_PHRASES["en"]
        assert "near home" in HOME_PHRASES["en"]

    def test_french_current_phrases_examples(self):
        """Test that specific French current phrases exist."""
        assert "à proximité" in CURRENT_PHRASES["fr"]
        assert "autour de moi" in CURRENT_PHRASES["fr"]

    def test_english_current_phrases_examples(self):
        """Test that specific English current phrases exist."""
        assert "nearby" in CURRENT_PHRASES["en"]
        assert "around me" in CURRENT_PHRASES["en"]

    def test_french_query_phrases_examples(self):
        """Test that specific French query phrases exist."""
        assert "où suis-je" in QUERY_PHRASES["fr"]

    def test_english_query_phrases_examples(self):
        """Test that specific English query phrases exist."""
        assert "where am i" in QUERY_PHRASES["en"]


# ============================================================================
# Tests for detect_location_type function
# ============================================================================


class TestDetectLocationTypeFrench:
    """Tests for detect_location_type with French."""

    def test_detects_home_chez_moi(self):
        """Test detection of 'chez moi'."""
        result = detect_location_type("Quel temps fait-il chez moi ?", "fr")
        assert result == LocationType.HOME

    def test_detects_home_a_la_maison(self):
        """Test detection of 'à la maison'."""
        result = detect_location_type("Restaurants à la maison", "fr")
        assert result == LocationType.HOME

    def test_detects_current_a_proximite(self):
        """Test detection of 'à proximité'."""
        result = detect_location_type("Restaurants à proximité", "fr")
        assert result == LocationType.CURRENT

    def test_detects_current_autour_de_moi(self):
        """Test detection of 'autour de moi'."""
        result = detect_location_type("Qu'y a-t-il autour de moi ?", "fr")
        assert result == LocationType.CURRENT

    def test_detects_query_ou_suis_je(self):
        """Test detection of 'où suis-je'."""
        result = detect_location_type("Où suis-je ?", "fr")
        assert result == LocationType.QUERY

    def test_detects_query_je_suis_ou(self):
        """Test detection of 'je suis où'."""
        result = detect_location_type("Je suis où exactement ?", "fr")
        assert result == LocationType.QUERY

    def test_returns_none_for_no_location(self):
        """Test that NONE is returned when no location reference."""
        result = detect_location_type("Quelle heure est-il ?", "fr")
        assert result == LocationType.NONE

    def test_query_has_priority_over_home(self):
        """Test that QUERY is detected with higher priority."""
        # "où suis-je" should be detected even if other phrases present
        result = detect_location_type("Où suis-je chez moi ?", "fr")
        assert result == LocationType.QUERY


class TestDetectLocationTypeEnglish:
    """Tests for detect_location_type with English."""

    def test_detects_home_at_home(self):
        """Test detection of 'at home'."""
        result = detect_location_type("What's the weather at home?", "en")
        assert result == LocationType.HOME

    def test_detects_home_near_home(self):
        """Test detection of 'near home'."""
        result = detect_location_type("Restaurants near home", "en")
        assert result == LocationType.HOME

    def test_detects_current_nearby(self):
        """Test detection of 'nearby'."""
        result = detect_location_type("Restaurants nearby", "en")
        assert result == LocationType.CURRENT

    def test_detects_current_around_me(self):
        """Test detection of 'around me'."""
        result = detect_location_type("What's around me?", "en")
        assert result == LocationType.CURRENT

    def test_detects_query_where_am_i(self):
        """Test detection of 'where am i'."""
        result = detect_location_type("Where am I?", "en")
        assert result == LocationType.QUERY

    def test_returns_none_for_explicit_location(self):
        """Test that NONE is returned for explicit location."""
        result = detect_location_type("Weather in Paris", "en")
        assert result == LocationType.NONE


class TestDetectLocationTypeOtherLanguages:
    """Tests for detect_location_type with other languages."""

    def test_spanish_home_detection(self):
        """Test Spanish home detection."""
        result = detect_location_type("Restaurantes cerca de casa", "es")
        assert result == LocationType.HOME

    def test_spanish_current_detection(self):
        """Test Spanish current detection."""
        result = detect_location_type("Restaurantes cerca de aquí", "es")
        assert result == LocationType.CURRENT

    def test_german_home_detection(self):
        """Test German home detection."""
        result = detect_location_type("Restaurants bei mir zuhause", "de")
        assert result == LocationType.HOME

    def test_german_current_detection(self):
        """Test German current detection."""
        result = detect_location_type("Was ist in der nähe?", "de")
        assert result == LocationType.CURRENT

    def test_italian_home_detection(self):
        """Test Italian home detection."""
        result = detect_location_type("Ristoranti vicino a casa", "it")
        assert result == LocationType.HOME

    def test_italian_current_detection(self):
        """Test Italian current detection."""
        result = detect_location_type("Cosa c'è nelle vicinanze?", "it")
        assert result == LocationType.CURRENT

    def test_chinese_home_detection(self):
        """Test Chinese home detection."""
        result = detect_location_type("我家附近的餐厅", "zh-CN")
        assert result == LocationType.HOME

    def test_chinese_current_detection(self):
        """Test Chinese current detection."""
        result = detect_location_type("附近的餐厅", "zh-CN")
        assert result == LocationType.CURRENT


class TestDetectLocationTypeCaseInsensitive:
    """Tests for case insensitivity in location detection."""

    def test_uppercase_home(self):
        """Test uppercase HOME phrase detection."""
        result = detect_location_type("CHEZ MOI il fait beau", "fr")
        assert result == LocationType.HOME

    def test_mixed_case_current(self):
        """Test mixed case CURRENT phrase detection."""
        result = detect_location_type("Restaurants À Proximité", "fr")
        assert result == LocationType.CURRENT

    def test_uppercase_query_english(self):
        """Test uppercase QUERY phrase detection."""
        result = detect_location_type("WHERE AM I?", "en")
        assert result == LocationType.QUERY


# ============================================================================
# Tests for _normalize_language function
# ============================================================================


class TestNormalizeLanguage:
    """Tests for _normalize_language function."""

    def test_normalize_french(self):
        """Test normalizing French."""
        assert _normalize_language("fr") == "fr"
        assert _normalize_language("FR") == "fr"
        assert _normalize_language("fr-FR") == "fr"

    def test_normalize_english(self):
        """Test normalizing English."""
        assert _normalize_language("en") == "en"
        assert _normalize_language("EN") == "en"
        assert _normalize_language("en-US") == "en"
        assert _normalize_language("en-GB") == "en"

    def test_normalize_spanish(self):
        """Test normalizing Spanish."""
        assert _normalize_language("es") == "es"
        assert _normalize_language("es-ES") == "es"
        assert _normalize_language("es-MX") == "es"

    def test_normalize_german(self):
        """Test normalizing German."""
        assert _normalize_language("de") == "de"
        assert _normalize_language("de-DE") == "de"

    def test_normalize_italian(self):
        """Test normalizing Italian."""
        assert _normalize_language("it") == "it"
        assert _normalize_language("it-IT") == "it"

    def test_normalize_chinese(self):
        """Test normalizing Chinese."""
        assert _normalize_language("zh-CN") == "zh-CN"
        assert _normalize_language("zh_CN") == "zh-CN"
        assert _normalize_language("zh") == "zh-CN"
        assert _normalize_language("ZH") == "zh-CN"

    def test_normalize_unknown_defaults_to_french(self):
        """Test that unknown language defaults to French."""
        assert _normalize_language("pt") == "fr"
        assert _normalize_language("ja") == "fr"
        assert _normalize_language("unknown") == "fr"


# ============================================================================
# Tests for helper functions
# ============================================================================


class TestContainsHomeReference:
    """Tests for contains_home_reference function."""

    def test_returns_true_for_home_reference(self):
        """Test returns True for home reference."""
        assert contains_home_reference("Météo chez moi", "fr") is True

    def test_returns_false_for_current_reference(self):
        """Test returns False for current reference."""
        assert contains_home_reference("À proximité", "fr") is False

    def test_returns_false_for_no_reference(self):
        """Test returns False for no reference."""
        assert contains_home_reference("Bonjour", "fr") is False


class TestContainsCurrentReference:
    """Tests for contains_current_reference function."""

    def test_returns_true_for_current_reference(self):
        """Test returns True for current reference."""
        assert contains_current_reference("Restaurants à proximité", "fr") is True

    def test_returns_false_for_home_reference(self):
        """Test returns False for home reference."""
        assert contains_current_reference("Chez moi", "fr") is False

    def test_returns_false_for_no_reference(self):
        """Test returns False for no reference."""
        assert contains_current_reference("Bonjour", "fr") is False


class TestContainsQueryReference:
    """Tests for contains_query_reference function."""

    def test_returns_true_for_query_reference(self):
        """Test returns True for query reference."""
        assert contains_query_reference("Où suis-je ?", "fr") is True

    def test_returns_false_for_home_reference(self):
        """Test returns False for home reference."""
        assert contains_query_reference("Chez moi", "fr") is False

    def test_returns_false_for_no_reference(self):
        """Test returns False for no reference."""
        assert contains_query_reference("Bonjour", "fr") is False


# ============================================================================
# Tests for get_fallback_message
# ============================================================================


class TestGetFallbackMessage:
    """Tests for get_fallback_message function."""

    def test_french_message(self):
        """Test French fallback message."""
        message = get_fallback_message("fr")
        assert "position" in message.lower() or "localisation" in message.lower()

    def test_english_message(self):
        """Test English fallback message."""
        message = get_fallback_message("en")
        assert "location" in message.lower()

    def test_spanish_message(self):
        """Test Spanish fallback message."""
        message = get_fallback_message("es")
        assert "ubicación" in message.lower()

    def test_german_message(self):
        """Test German fallback message."""
        message = get_fallback_message("de")
        assert "Standort" in message

    def test_unknown_defaults_to_french(self):
        """Test that unknown language defaults to French."""
        message = get_fallback_message("ja")
        assert message == FALLBACK_MESSAGES["fr"]


# ============================================================================
# Tests for get_home_config_suggestion
# ============================================================================


class TestGetHomeConfigSuggestion:
    """Tests for get_home_config_suggestion function."""

    def test_french_suggestion(self):
        """Test French config suggestion."""
        suggestion = get_home_config_suggestion("fr")
        assert "Paramètres" in suggestion or "configurer" in suggestion.lower()

    def test_english_suggestion(self):
        """Test English config suggestion."""
        suggestion = get_home_config_suggestion("en")
        assert "Settings" in suggestion

    def test_unknown_defaults_to_french(self):
        """Test that unknown language defaults to French."""
        suggestion = get_home_config_suggestion("ja")
        assert suggestion == HOME_CONFIG_SUGGESTION["fr"]


# ============================================================================
# Tests for get_distance_reference
# ============================================================================


class TestGetDistanceReference:
    """Tests for get_distance_reference function."""

    def test_browser_french(self):
        """Test browser reference in French."""
        result = get_distance_reference("browser", "fr")
        assert result == "depuis votre position"

    def test_browser_english(self):
        """Test browser reference in English."""
        result = get_distance_reference("browser", "en")
        assert result == "from your location"

    def test_home_french(self):
        """Test home reference in French."""
        result = get_distance_reference("home", "fr")
        assert result == "depuis votre domicile"

    def test_home_english(self):
        """Test home reference in English."""
        result = get_distance_reference("home", "en")
        assert result == "from your home"

    def test_search_location_french(self):
        """Test search_location reference in French."""
        result = get_distance_reference("search_location", "fr")
        assert result == "depuis le lieu recherché"

    def test_none_source_returns_none(self):
        """Test that None source returns None."""
        result = get_distance_reference(None, "fr")
        assert result is None

    def test_unknown_source_returns_none(self):
        """Test that unknown source returns None."""
        result = get_distance_reference("unknown_source", "fr")
        assert result is None

    def test_all_languages_have_browser(self):
        """Test all languages have browser reference."""
        for lang in ["fr", "en", "es", "de", "it", "zh-CN"]:
            result = get_distance_reference("browser", lang)
            assert result is not None, f"Missing browser reference for {lang}"

    def test_all_languages_have_home(self):
        """Test all languages have home reference."""
        for lang in ["fr", "en", "es", "de", "it", "zh-CN"]:
            result = get_distance_reference("home", lang)
            assert result is not None, f"Missing home reference for {lang}"


# ============================================================================
# Tests for get_price_level
# ============================================================================


class TestGetPriceLevel:
    """Tests for get_price_level function."""

    def test_free_french(self):
        """Test FREE price level in French."""
        result = get_price_level("PRICE_LEVEL_FREE", "fr")
        assert result == "Gratuit"

    def test_free_english(self):
        """Test FREE price level in English."""
        result = get_price_level("PRICE_LEVEL_FREE", "en")
        assert result == "Free"

    def test_inexpensive_french(self):
        """Test INEXPENSIVE price level in French."""
        result = get_price_level("PRICE_LEVEL_INEXPENSIVE", "fr")
        assert result == "Bon marché"

    def test_moderate_french(self):
        """Test MODERATE price level in French."""
        result = get_price_level("PRICE_LEVEL_MODERATE", "fr")
        assert result == "Modéré"

    def test_expensive_french(self):
        """Test EXPENSIVE price level in French."""
        result = get_price_level("PRICE_LEVEL_EXPENSIVE", "fr")
        assert result == "Cher"

    def test_very_expensive_french(self):
        """Test VERY_EXPENSIVE price level in French."""
        result = get_price_level("PRICE_LEVEL_VERY_EXPENSIVE", "fr")
        assert result == "Très cher"

    def test_none_returns_none(self):
        """Test that None returns None."""
        result = get_price_level(None, "fr")
        assert result is None

    def test_unknown_code_returns_original(self):
        """Test that unknown code returns original."""
        result = get_price_level("UNKNOWN_CODE", "fr")
        assert result == "UNKNOWN_CODE"

    def test_all_levels_in_all_languages(self):
        """Test all price levels exist in all languages."""
        levels = [
            "PRICE_LEVEL_FREE",
            "PRICE_LEVEL_INEXPENSIVE",
            "PRICE_LEVEL_MODERATE",
            "PRICE_LEVEL_EXPENSIVE",
            "PRICE_LEVEL_VERY_EXPENSIVE",
        ]
        for lang in ["fr", "en", "es", "de", "it", "zh-CN"]:
            for level in levels:
                result = get_price_level(level, lang)
                assert result != level, f"Missing translation for {level} in {lang}"


# ============================================================================
# Tests for route-related functions
# ============================================================================


class TestRoutePhrases:
    """Tests for ROUTE_PHRASES dictionary."""

    def test_has_6_languages(self):
        """Test that ROUTE_PHRASES has all 6 languages."""
        expected_languages = {"fr", "en", "es", "de", "it", "zh-CN"}
        assert set(ROUTE_PHRASES.keys()) == expected_languages

    def test_french_route_phrases(self):
        """Test French route phrases exist."""
        assert "itinéraire vers" in ROUTE_PHRASES["fr"]
        assert "comment aller" in ROUTE_PHRASES["fr"]

    def test_english_route_phrases(self):
        """Test English route phrases exist."""
        assert "directions to" in ROUTE_PHRASES["en"]
        assert "how to get to" in ROUTE_PHRASES["en"]


class TestContainsRouteReference:
    """Tests for contains_route_reference function."""

    def test_french_itineraire(self):
        """Test French 'itinéraire' detection."""
        assert contains_route_reference("Itinéraire vers Lyon", "fr") is True

    def test_french_comment_aller(self):
        """Test French 'comment aller' detection."""
        assert contains_route_reference("Comment aller à Paris ?", "fr") is True

    def test_english_directions(self):
        """Test English 'directions to' detection."""
        assert contains_route_reference("Directions to the airport", "en") is True

    def test_english_how_to_get(self):
        """Test English 'how to get to' detection."""
        assert contains_route_reference("How to get to the station?", "en") is True

    def test_no_route_reference(self):
        """Test no route reference."""
        assert contains_route_reference("Weather in Paris", "fr") is False
        assert contains_route_reference("Restaurants nearby", "en") is False


class TestGetTransportMode:
    """Tests for get_transport_mode function."""

    def test_drive_french(self):
        """Test DRIVE in French."""
        result = get_transport_mode("DRIVE", "fr")
        assert result == "en voiture"

    def test_drive_english(self):
        """Test DRIVE in English."""
        result = get_transport_mode("DRIVE", "en")
        assert result == "by car"

    def test_walk_french(self):
        """Test WALK in French."""
        result = get_transport_mode("WALK", "fr")
        assert result == "à pied"

    def test_walk_english(self):
        """Test WALK in English."""
        result = get_transport_mode("WALK", "en")
        assert result == "on foot"

    def test_bicycle_french(self):
        """Test BICYCLE in French."""
        result = get_transport_mode("BICYCLE", "fr")
        assert result == "à vélo"

    def test_transit_french(self):
        """Test TRANSIT in French."""
        result = get_transport_mode("TRANSIT", "fr")
        assert result == "en transports en commun"

    def test_two_wheeler_french(self):
        """Test TWO_WHEELER in French."""
        result = get_transport_mode("TWO_WHEELER", "fr")
        assert result == "en deux-roues"

    def test_unknown_mode_returns_lowercase(self):
        """Test that unknown mode returns lowercase."""
        result = get_transport_mode("UNKNOWN", "fr")
        assert result == "unknown"

    def test_all_modes_in_all_languages(self):
        """Test all transport modes exist in all languages."""
        modes = ["DRIVE", "WALK", "BICYCLE", "TRANSIT", "TWO_WHEELER"]
        for lang in ["fr", "en", "es", "de", "it", "zh-CN"]:
            for mode in modes:
                result = get_transport_mode(mode, lang)
                assert result != mode.lower(), f"Missing translation for {mode} in {lang}"


class TestGetTrafficCondition:
    """Tests for get_traffic_condition function."""

    def test_normal_french(self):
        """Test NORMAL in French."""
        result = get_traffic_condition("NORMAL", "fr")
        assert result == "fluide"

    def test_normal_english(self):
        """Test NORMAL in English."""
        result = get_traffic_condition("NORMAL", "en")
        assert result == "normal"

    def test_light_french(self):
        """Test LIGHT in French."""
        result = get_traffic_condition("LIGHT", "fr")
        assert result == "léger"

    def test_moderate_french(self):
        """Test MODERATE in French."""
        result = get_traffic_condition("MODERATE", "fr")
        assert result == "modéré"

    def test_heavy_french(self):
        """Test HEAVY in French."""
        result = get_traffic_condition("HEAVY", "fr")
        assert result == "dense"

    def test_none_returns_none(self):
        """Test that None returns None."""
        result = get_traffic_condition(None, "fr")
        assert result is None

    def test_unknown_returns_lowercase(self):
        """Test that unknown condition returns lowercase."""
        result = get_traffic_condition("UNKNOWN", "fr")
        assert result == "unknown"

    def test_all_conditions_in_all_languages(self):
        """Test all traffic conditions exist in all languages."""
        conditions = ["NORMAL", "LIGHT", "MODERATE", "HEAVY"]
        for lang in ["fr", "en", "es", "de", "it", "zh-CN"]:
            for condition in conditions:
                result = get_traffic_condition(condition, lang)
                # Check that result is not None and is a string
                assert result is not None, f"Missing translation for {condition} in {lang}"
                assert isinstance(
                    result, str
                ), f"Invalid translation type for {condition} in {lang}"


class TestGetRouteAvoidance:
    """Tests for get_route_avoidance function."""

    def test_tolls_french(self):
        """Test tolls in French."""
        result = get_route_avoidance("tolls", "fr")
        assert result == "péages"

    def test_tolls_english(self):
        """Test tolls in English."""
        result = get_route_avoidance("tolls", "en")
        assert result == "tolls"

    def test_highways_french(self):
        """Test highways in French."""
        result = get_route_avoidance("highways", "fr")
        assert result == "autoroutes"

    def test_highways_german(self):
        """Test highways in German."""
        result = get_route_avoidance("highways", "de")
        assert result == "Autobahnen"

    def test_ferries_french(self):
        """Test ferries in French."""
        result = get_route_avoidance("ferries", "fr")
        assert result == "ferries"

    def test_unknown_returns_original(self):
        """Test that unknown avoidance returns original."""
        result = get_route_avoidance("unknown", "fr")
        assert result == "unknown"

    def test_all_avoidances_in_all_languages(self):
        """Test all avoidances exist in all languages."""
        avoidances = ["tolls", "highways", "ferries"]
        for lang in ["fr", "en", "es", "de", "it", "zh-CN"]:
            for avoidance in avoidances:
                result = get_route_avoidance(avoidance, lang)
                assert result is not None, f"Missing translation for {avoidance} in {lang}"


# ============================================================================
# Tests for dictionary completeness
# ============================================================================


class TestDictionaryCompleteness:
    """Tests for completeness of all translation dictionaries."""

    def test_fallback_messages_has_all_languages(self):
        """Test FALLBACK_MESSAGES has all languages."""
        expected = {"fr", "en", "es", "de", "it", "zh-CN"}
        assert set(FALLBACK_MESSAGES.keys()) == expected

    def test_home_config_suggestion_has_all_languages(self):
        """Test HOME_CONFIG_SUGGESTION has all languages."""
        expected = {"fr", "en", "es", "de", "it", "zh-CN"}
        assert set(HOME_CONFIG_SUGGESTION.keys()) == expected

    def test_distance_reference_has_all_languages(self):
        """Test DISTANCE_REFERENCE has all languages."""
        expected = {"fr", "en", "es", "de", "it", "zh-CN"}
        assert set(DISTANCE_REFERENCE.keys()) == expected

    def test_price_level_has_all_languages(self):
        """Test PRICE_LEVEL has all languages."""
        expected = {"fr", "en", "es", "de", "it", "zh-CN"}
        assert set(PRICE_LEVEL.keys()) == expected

    def test_transport_modes_has_all_languages(self):
        """Test TRANSPORT_MODES has all languages."""
        expected = {"fr", "en", "es", "de", "it", "zh-CN"}
        assert set(TRANSPORT_MODES.keys()) == expected

    def test_route_avoidances_has_all_languages(self):
        """Test ROUTE_AVOIDANCES has all languages."""
        expected = {"fr", "en", "es", "de", "it", "zh-CN"}
        assert set(ROUTE_AVOIDANCES.keys()) == expected

    def test_traffic_conditions_has_all_languages(self):
        """Test TRAFFIC_CONDITIONS has all languages."""
        expected = {"fr", "en", "es", "de", "it", "zh-CN"}
        assert set(TRAFFIC_CONDITIONS.keys()) == expected


# ============================================================================
# Tests for edge cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_message_detection(self):
        """Test detection with empty message."""
        result = detect_location_type("", "fr")
        assert result == LocationType.NONE

    def test_whitespace_only_message(self):
        """Test detection with whitespace only."""
        result = detect_location_type("   ", "fr")
        assert result == LocationType.NONE

    def test_partial_phrase_match(self):
        """Test that partial phrase doesn't match (e.g., 'chezMoi' vs 'chez moi')."""
        result = detect_location_type("chezMoi", "fr")
        # Should not match because "chez moi" requires space
        assert result == LocationType.NONE

    def test_phrase_in_middle_of_sentence(self):
        """Test phrase detection in middle of sentence."""
        result = detect_location_type("Je cherche un restaurant chez moi ce soir", "fr")
        assert result == LocationType.HOME

    def test_multiple_phrases_in_message(self):
        """Test with multiple location phrases (first match wins)."""
        # Query has highest priority
        result = detect_location_type("Où suis-je, et qu'y a-t-il à proximité ?", "fr")
        assert result == LocationType.QUERY

    def test_language_with_underscore(self):
        """Test language code with underscore."""
        assert _normalize_language("fr_FR") == "fr"
        assert _normalize_language("zh_CN") == "zh-CN"

    def test_uppercase_language_code(self):
        """Test uppercase language code."""
        result = detect_location_type("What's nearby?", "EN")
        assert result == LocationType.CURRENT
