"""Named, local detail panels for complete known venue information."""

from collections.abc import Callable, Mapping

from src.core.constants import PLACES_FEATURE_FIELD_TO_I18N_KEY
from src.core.i18n_cards import card_label
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    RenderContext,
    render_collapsible,
    render_d_item,
)
from src.domains.agents.display.components.card_content import render_availability_rows
from src.domains.agents.display.components.environment_row import air_quality_text
from src.domains.agents.display.components.place_hours import hours_content
from src.domains.agents.display.components.place_reviews import render_place_reviews
from src.domains.agents.display.values import list_values

_ACCESS = {
    "wheelchairAccessibleEntrance": "wheelchair_entrance",
    "wheelchairAccessibleParking": "wheelchair_parking",
    "wheelchairAccessibleSeating": "wheelchair_seating",
    "wheelchairAccessibleRestroom": "wheelchair_restroom",
}
_PAYMENT = {
    "acceptsCreditCards": "credit_cards",
    "acceptsCashOnly": "cash_only",
    "acceptsNfc": "contactless",
}
_PARKING = (
    "freeParkingLot",
    "paidParkingLot",
    "freeStreetParking",
    "paidStreetParking",
    "valetParking",
    "freeGarageParking",
    "paidGarageParking",
)


def _options(
    value: object, labels: Callable[[str], str], keys: Mapping[str, str], language: str
) -> str:
    if not isinstance(value, dict):
        return ""
    rows = [
        (labels(label), value[key])
        for key, label in keys.items()
        if isinstance(value.get(key), bool)
    ]
    return render_availability_rows([(label, state) for label, state in rows if label], language)


def _features(data: Mapping[str, object], language: str) -> str:
    states = data.get("feature_states")
    if isinstance(states, dict):
        keys = {key: key for key in PLACES_FEATURE_FIELD_TO_I18N_KEY.values()}
        return _options(
            states, lambda key: V3Messages.get_place_feature(language, key), keys, language
        )
    labels = [
        V3Messages.get_place_feature(language, key)
        for key in list_values(data.get("features"))
        if isinstance(key, str)
    ]
    return render_availability_rows([(label, True) for label in labels if label], language)


def _payment(value: object, language: str) -> str:
    keys = {**_PAYMENT, "acceptsDebitCards": "debit_cards"}
    return _options(
        value,
        lambda key: (
            card_label("debit_cards", language)
            if key == "debit_cards"
            else V3Messages.get_payment(language, key)
        ),
        keys,
        language,
    )


def render_place_details(data: Mapping[str, object], ctx: RenderContext) -> str:
    language = ctx.language
    sections = [
        (V3Messages.get_opening_hours(language), hours_content(data, ctx)),
        (V3Messages.get_services_amenities(language), _features(data, language)),
        (
            V3Messages.get_reviews(language).capitalize(),
            "".join(render_place_reviews(data.get("reviews"), ctx)),
        ),
        (
            V3Messages.get_accessibility_title(language),
            _options(
                data.get("accessibilityOptions"),
                lambda key: V3Messages.get_accessibility(language, key),
                _ACCESS,
                language,
            ),
        ),
        (
            V3Messages.get_parking_title(language),
            _options(
                data.get("parkingOptions"),
                lambda key: V3Messages.get_parking_option(language, key),
                {key: key for key in _PARKING},
                language,
            ),
        ),
        (V3Messages.get_air_quality(language), _air_quality(data, language)),
        (V3Messages.get_payment_title(language), _payment(data.get("paymentOptions"), language)),
    ]
    return "".join(
        render_collapsible(label, content, with_separator=False)
        for label, content in sections
        if content
    )


def _air_quality(data: Mapping[str, object], language: str) -> str:
    text = air_quality_text(dict(data), language)
    return render_d_item("air", text) if text else ""
