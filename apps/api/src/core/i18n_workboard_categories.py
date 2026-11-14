"""Where a person administers their workboard categories, as their screen names it (ADR-276).

``list_ticket_categories_tool`` tells the model WHERE categories are created,
renamed, reordered and deleted: a page of the application's menu and a button
of that page. The sentence around the two names is technical English, read by
a model alone; the NAMES are the person's, because the answer quotes them and
the person then looks for those exact words on their screen.

The web draws both from its locale files (``navigation.workboard`` and
``workboard.categories.manage``). They are restated here under the
backend-canonical codes (``zh-CN``) because a tool cannot read a frontend file
at run time; ``tests/unit/core/test_i18n_workboard_categories.py`` holds the
two tables equal, so a label renamed on one side alone reds the build.

Data module (like the other ``core/i18n_*``): no domain imports.
"""

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, NamedTuple

from src.core.i18n import normalize_language
from src.core.i18n_types import Language


class WorkboardCategoryPlace(NamedTuple):
    """The two labels a person follows to their categories.

    Attributes:
        page: The workboard's name in the application's menu.
        button: The label of the board's button that opens the categories.
    """

    page: str
    button: str


#: The place, as each language's screen shows it.
WORKBOARD_CATEGORY_PLACES: Final[Mapping[Language, WorkboardCategoryPlace]] = MappingProxyType(
    {
        "fr": WorkboardCategoryPlace(page="Workboard", button="Catégories"),
        "en": WorkboardCategoryPlace(page="Workboard", button="Categories"),
        "de": WorkboardCategoryPlace(page="Workboard", button="Kategorien"),
        "es": WorkboardCategoryPlace(page="Workboard", button="Categorías"),
        "it": WorkboardCategoryPlace(page="Workboard", button="Categorie"),
        "zh-CN": WorkboardCategoryPlace(page="工作看板", button="分类"),
    }
)


def workboard_category_place(language: str | None) -> WorkboardCategoryPlace:
    """The page and the button a person administers their categories from.

    Args:
        language: The person's language (any spelling of a code); an absent or
            unsupported one reads as the instance's default.

    Returns:
        The two labels their screen shows.
    """
    return WORKBOARD_CATEGORY_PLACES[normalize_language(language)]


__all__ = ["WORKBOARD_CATEGORY_PLACES", "WorkboardCategoryPlace", "workboard_category_place"]
