"""Labels a document renderer writes on its own (ADR-274).

The model writes the document in the reader's language; the renderer adds a
handful of words of its own — the table of contents heading, the page footer, a
table label, a generated column name — and those must exist in the six
languages too, or a French report grows an English footer.

Data module (ratchet-exempt like ``i18n_effects``): one table per language, the
SAME key set under each, checked by ``tests/unit/core/test_i18n_documents.py``.
Keys live under ``documents.*`` and are BACKEND-only — nothing here reaches the
frontend, which never renders a generated document.
"""

from __future__ import annotations

from src.core.i18n import normalize_language

#: Backend-canonical codes every label exists in (``zh-CN``, not ``zh``).
SUPPORTED_DOCUMENT_LABEL_LANGUAGES: tuple[str, ...] = ("fr", "en", "de", "es", "it", "zh-CN")

#: language -> {label key -> template}. Placeholders are the renderer's values.
DOCUMENT_LABELS: dict[str, dict[str, str]] = {
    "fr": {
        "documents.toc_heading": "Sommaire",
        "documents.page_of": "Page {page} / {total}",
        "documents.table_label": "Tableau {n}",
        "documents.column_label": "Colonne {n}",
    },
    "en": {
        "documents.toc_heading": "Contents",
        "documents.page_of": "Page {page} of {total}",
        "documents.table_label": "Table {n}",
        "documents.column_label": "Column {n}",
    },
    "de": {
        "documents.toc_heading": "Inhalt",
        "documents.page_of": "Seite {page} von {total}",
        "documents.table_label": "Tabelle {n}",
        "documents.column_label": "Spalte {n}",
    },
    "es": {
        "documents.toc_heading": "Índice",
        "documents.page_of": "Página {page} de {total}",
        "documents.table_label": "Tabla {n}",
        "documents.column_label": "Columna {n}",
    },
    "it": {
        "documents.toc_heading": "Indice",
        "documents.page_of": "Pagina {page} di {total}",
        "documents.table_label": "Tabella {n}",
        "documents.column_label": "Colonna {n}",
    },
    "zh-CN": {
        "documents.toc_heading": "目录",
        "documents.page_of": "第 {page} 页，共 {total} 页",
        "documents.table_label": "表 {n}",
        "documents.column_label": "列 {n}",
    },
}


def document_label(language: str, key: str, **values: object) -> str:
    """A renderer label in the reader's language.

    Args:
        language: Any locale spelling; normalised to the backend canon.
        key: One of the ``documents.*`` keys.
        **values: Placeholder values.

    Returns:
        The rendered label; the English wording when the language is unknown.
    """
    table = DOCUMENT_LABELS.get(normalize_language(language), DOCUMENT_LABELS["en"])
    template = table.get(key) or DOCUMENT_LABELS["en"][key]
    return template.format(**values)
