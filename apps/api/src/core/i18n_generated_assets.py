"""Central i18n of the generated-files gallery (ADR-319).

The sentence a person reads when keeping one more file would pass the account's
ceiling. The ceilings travel in it as figures the caller supplies — they are
settings (``GENERATED_ASSETS_KEEP_MAX_*``), never written in the text.

Six supported languages, keyed by the backend-canonical code (``zh-CN``);
``normalize_language`` from ``core.i18n`` is the only entry point for raw
locale strings. Data module (like the other ``core/i18n_*``): no domain
imports, exempt from the size ratchet.
"""

from __future__ import annotations

from src.core.i18n import normalize_language
from src.core.i18n_types import Language

#: ``{max_files}`` and ``{max_mb}`` are the account's two keeping ceilings. Keyed
#: by EVERY canonical code (a test holds the keys equal to ``Language``), so the
#: lookup needs no fallback: ``normalize_language`` always answers one of them.
KEEP_LIMIT_REACHED: dict[Language, str] = {
    "en": (
        "Keeping these files would pass your limit: at most {max_files} kept files "
        "and {max_mb} MB. Release or delete some kept files first."
    ),
    "fr": (
        "Conserver ces fichiers dépasserait ta limite : {max_files} fichiers conservés "
        "et {max_mb} Mo au plus. Libère ou supprime d'abord des fichiers conservés."
    ),
    "de": (
        "Diese Dateien aufzubewahren würde dein Limit überschreiten: höchstens "
        "{max_files} aufbewahrte Dateien und {max_mb} MB. Gib zuerst aufbewahrte "
        "Dateien frei oder lösche welche."
    ),
    "es": (
        "Conservar estos archivos superaría tu límite: como máximo {max_files} "
        "archivos conservados y {max_mb} MB. Libera o elimina antes algunos "
        "archivos conservados."
    ),
    "it": (
        "Conservare questi file supererebbe il tuo limite: al massimo {max_files} "
        "file conservati e {max_mb} MB. Libera o elimina prima alcuni file conservati."
    ),
    "zh-CN": (
        "保留这些文件将超出你的上限：最多保留 {max_files} 个文件、{max_mb} MB。"
        "请先取消保留或删除一些已保留的文件。"
    ),
}


def keep_limit_reached(language: str, *, max_files: int, max_mb: int) -> str:
    """The sentence refusing a keep that would pass the account's ceilings.

    Args:
        language: The reader's language, raw (normalised here).
        max_files: The ceiling on kept files.
        max_mb: The ceiling on kept megabytes.

    Returns:
        The translated sentence, the two ceilings in it.
    """
    return KEEP_LIMIT_REACHED[normalize_language(language)].format(
        max_files=max_files, max_mb=max_mb
    )
