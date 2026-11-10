"""Attribution of a memory proposed from selected, untrusted words."""

from src.core.i18n import resolve_language

_PREFIXES = {
    "en": "Selected passage: “{text}”",
    "fr": "Passage sélectionné : « {text} »",
    "de": "Ausgewählte Passage: „{text}“",
    "es": "Pasaje seleccionado: «{text}»",
    "it": "Passaggio selezionato: «{text}»",
    "zh-CN": "所选段落：“{text}”",
}


def quoted_selection(text: str, language: str | None) -> str:
    """A quotation cannot silently become the person's own biography or instruction."""
    return _PREFIXES[resolve_language(language)].format(text=text)
