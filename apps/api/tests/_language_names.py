"""One reading of « this identifier names a language », shared by the i18n guards (ADR-323).

Three guards read language names — the language-default guard, the locale
normalization guard and the language-name-to-model guard — and each carried its
own regex: one read camel case and not plurals, another plurals and not camel
case, the third ``_hint`` and ``_codes`` and not ``accept-language``. A name one
guard recognised slipped past the next.
"""

from __future__ import annotations

import re

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_LANGUAGE_NAME = re.compile(r"(^|_)(lang|language|locale)s?(_code|_codes|_hint|_tag|_tags)?$")


def snake(identifier: str) -> str:
    """``languageCode`` → ``language_code``, ``accept-language`` → ``accept_language``."""
    return _CAMEL_BOUNDARY.sub("_", identifier).replace("-", "_").lower()


def is_language_name(identifier: str) -> bool:
    """Whether an identifier names a language or locale code.

    ``lang``, ``language`` or ``locale``, alone or ending a compound, singular or
    plural, with an optional ``code``/``codes``/``hint``/``tag``/``tags`` suffix
    (a BCP 47 language TAG is a locale), in snake, camel or kebab case:
    ``user_language``, ``languageCode``, ``language_hint``, ``language_tag``,
    ``languages``, ``accept-language``. Not ``slang``, not ``language_model``.

    Args:
        identifier: A variable, attribute, keyword or key name.

    Returns:
        True when it names a language.
    """
    return bool(_LANGUAGE_NAME.search(snake(identifier)))
