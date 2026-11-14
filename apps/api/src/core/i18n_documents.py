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
        "documents.figure_label": "Figure {n}",
        "documents.column_label": "Colonne {n}",
        "documents.total_label": "Total",
        "documents.summary_title": "Synthèse par {column}",
        "documents.count_label": "Nombre",
        "documents.inputs_sheet": "Hypothèses",
        "documents.input_name": "Hypothèse",
        "documents.input_value": "Valeur",
        "documents.input_note": "Note",
        "documents.figures_sheet": "Chiffres clés",
        "documents.figure_name": "Indicateur",
        "documents.agenda_title": "Sommaire",
        "documents.quote_attribution": "— {author}",
        "documents.figure_bullet": "{value} — {label}",
        "documents.sources_heading": "Sources",
        "documents.source_entry": "{title} — {url}",
        "documents.note_label": "À noter\u00a0:",
    },
    "en": {
        "documents.toc_heading": "Contents",
        "documents.page_of": "Page {page} of {total}",
        "documents.table_label": "Table {n}",
        "documents.figure_label": "Figure {n}",
        "documents.column_label": "Column {n}",
        "documents.total_label": "Total",
        "documents.summary_title": "Summary by {column}",
        "documents.count_label": "Count",
        "documents.inputs_sheet": "Assumptions",
        "documents.input_name": "Assumption",
        "documents.input_value": "Value",
        "documents.input_note": "Note",
        "documents.figures_sheet": "Key figures",
        "documents.figure_name": "Figure",
        "documents.agenda_title": "Agenda",
        "documents.quote_attribution": "— {author}",
        "documents.figure_bullet": "{value} — {label}",
        "documents.sources_heading": "Sources",
        "documents.source_entry": "{title} — {url}",
        "documents.note_label": "Note.",
    },
    "de": {
        "documents.toc_heading": "Inhalt",
        "documents.page_of": "Seite {page} von {total}",
        "documents.table_label": "Tabelle {n}",
        "documents.figure_label": "Abbildung {n}",
        "documents.column_label": "Spalte {n}",
        "documents.total_label": "Summe",
        "documents.summary_title": "Übersicht nach {column}",
        "documents.count_label": "Anzahl",
        "documents.inputs_sheet": "Annahmen",
        "documents.input_name": "Annahme",
        "documents.input_value": "Wert",
        "documents.input_note": "Hinweis",
        "documents.figures_sheet": "Kennzahlen",
        "documents.figure_name": "Kennzahl",
        "documents.agenda_title": "Agenda",
        "documents.quote_attribution": "— {author}",
        "documents.figure_bullet": "{value} — {label}",
        "documents.sources_heading": "Quellen",
        "documents.source_entry": "{title} — {url}",
        "documents.note_label": "Hinweis:",
    },
    "es": {
        "documents.toc_heading": "Índice",
        "documents.page_of": "Página {page} de {total}",
        "documents.table_label": "Tabla {n}",
        "documents.figure_label": "Figura {n}",
        "documents.column_label": "Columna {n}",
        "documents.total_label": "Total",
        "documents.summary_title": "Resumen por {column}",
        "documents.count_label": "Número",
        "documents.inputs_sheet": "Supuestos",
        "documents.input_name": "Supuesto",
        "documents.input_value": "Valor",
        "documents.input_note": "Nota",
        "documents.figures_sheet": "Cifras clave",
        "documents.figure_name": "Indicador",
        "documents.agenda_title": "Índice",
        "documents.quote_attribution": "— {author}",
        "documents.figure_bullet": "{value} — {label}",
        "documents.sources_heading": "Fuentes",
        "documents.source_entry": "{title} — {url}",
        "documents.note_label": "Nota:",
    },
    "it": {
        "documents.toc_heading": "Indice",
        "documents.page_of": "Pagina {page} di {total}",
        "documents.table_label": "Tabella {n}",
        "documents.figure_label": "Figura {n}",
        "documents.column_label": "Colonna {n}",
        "documents.total_label": "Totale",
        "documents.summary_title": "Riepilogo per {column}",
        "documents.count_label": "Numero",
        "documents.inputs_sheet": "Ipotesi",
        "documents.input_name": "Ipotesi",
        "documents.input_value": "Valore",
        "documents.input_note": "Nota",
        "documents.figures_sheet": "Cifre chiave",
        "documents.figure_name": "Indicatore",
        "documents.agenda_title": "Sommario",
        "documents.quote_attribution": "— {author}",
        "documents.figure_bullet": "{value} — {label}",
        "documents.sources_heading": "Fonti",
        "documents.source_entry": "{title} — {url}",
        "documents.note_label": "Nota:",
    },
    "zh-CN": {
        "documents.toc_heading": "目录",
        "documents.page_of": "第 {page} 页，共 {total} 页",
        "documents.table_label": "表 {n}",
        "documents.figure_label": "图 {n}",
        "documents.column_label": "列 {n}",
        "documents.total_label": "合计",
        "documents.summary_title": "按{column}汇总",
        "documents.count_label": "数量",
        "documents.inputs_sheet": "假设",
        "documents.input_name": "假设",
        "documents.input_value": "数值",
        "documents.input_note": "说明",
        "documents.figures_sheet": "关键数据",
        "documents.figure_name": "指标",
        "documents.agenda_title": "目录",
        "documents.quote_attribution": "——{author}",
        "documents.figure_bullet": "{value}：{label}",
        "documents.sources_heading": "参考来源",
        "documents.source_entry": "{title}——{url}",
        "documents.note_label": "提示：",
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
