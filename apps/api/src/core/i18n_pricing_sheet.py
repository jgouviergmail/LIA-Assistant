"""Translations for the LLM pricing workbook (ADR-228).

The workbook is a working surface, not a report: an administrator reads its
column headings, follows its notice and acts on its diagnostics. Every one of
those strings therefore belongs here, in the six supported languages, rather
than inline in the code that builds the file.

Chinese is keyed on the backend canonical ``zh-CN``; every lookup goes through
``normalize_language`` so a frontend ``zh`` or a regional ``fr-FR`` resolves
correctly instead of falling back to English in silence.

Supported languages: fr, en, es, de, it, zh-CN
"""

from __future__ import annotations

from src.core.i18n import DEFAULT_LANGUAGE, normalize_language
from src.core.i18n_types import Language

_COLUMN_PREFIX = "settings.admin.llm.sheet.column."

# ---------------------------------------------------------------------------
# Column headings — the second row of every data sheet
# ---------------------------------------------------------------------------

_COLUMNS: dict[Language, dict[str, str]] = {
    "fr": {
        "model_name": "Nom du modèle",
        "provider": "Fournisseur",
        "kind": "Nature",
        "is_active": "Actif",
        "max_input_tokens": "Entrée max (jetons)",
        "max_output_tokens": "Sortie max (jetons)",
        "supports_tools": "Outils",
        "supports_structured_output": "Sortie structurée",
        "supports_strict_mode": "Mode strict",
        "supports_streaming": "Streaming",
        "supports_vision": "Vision",
        "supports_temperature": "Température",
        "supports_top_p": "Top-p",
        "supports_frequency_penalty": "Pénalité fréquence",
        "supports_presence_penalty": "Pénalité présence",
        "reasoning_template": "Gabarit de raisonnement",
        "reasoning_shape": "Forme du raisonnement (lecture seule)",
        "reasoning_doc_i18n_key": "Clé d'aide",
        "effort_values": "Valeurs d'effort (lecture seule)",
        "pricing_unit": "Unité de tarif",
        "input_unit_price": "Prix entrée (USD)",
        "cached_input_unit_price": "Prix entrée en cache (USD)",
        "output_unit_price": "Prix sortie (USD)",
        "effective_from": "En vigueur depuis (lecture seule)",
        "time_slots_mode": "Plages horaires",
        "time_slots_summary": "Fenêtres actives (lecture seule)",
        "statut": "Statut (lecture seule)",
        "row_fingerprint": "Empreinte",
        "start_utc": "Début UTC",
        "end_utc": "Fin UTC",
    },
    "en": {
        "model_name": "Model name",
        "provider": "Provider",
        "kind": "Kind",
        "is_active": "Active",
        "max_input_tokens": "Max input (tokens)",
        "max_output_tokens": "Max output (tokens)",
        "supports_tools": "Tools",
        "supports_structured_output": "Structured output",
        "supports_strict_mode": "Strict mode",
        "supports_streaming": "Streaming",
        "supports_vision": "Vision",
        "supports_temperature": "Temperature",
        "supports_top_p": "Top-p",
        "supports_frequency_penalty": "Frequency penalty",
        "supports_presence_penalty": "Presence penalty",
        "reasoning_template": "Reasoning template",
        "reasoning_shape": "Reasoning shape (read-only)",
        "reasoning_doc_i18n_key": "Help key",
        "effort_values": "Effort values (read-only)",
        "pricing_unit": "Pricing unit",
        "input_unit_price": "Input price (USD)",
        "cached_input_unit_price": "Cached input price (USD)",
        "output_unit_price": "Output price (USD)",
        "effective_from": "Effective from (read-only)",
        "time_slots_mode": "Time slots",
        "time_slots_summary": "Active windows (read-only)",
        "statut": "Status (read-only)",
        "row_fingerprint": "Fingerprint",
        "start_utc": "Start UTC",
        "end_utc": "End UTC",
    },
    "es": {
        "model_name": "Nombre del modelo",
        "provider": "Proveedor",
        "kind": "Tipo",
        "is_active": "Activo",
        "max_input_tokens": "Entrada máx. (tokens)",
        "max_output_tokens": "Salida máx. (tokens)",
        "supports_tools": "Herramientas",
        "supports_structured_output": "Salida estructurada",
        "supports_strict_mode": "Modo estricto",
        "supports_streaming": "Streaming",
        "supports_vision": "Visión",
        "supports_temperature": "Temperatura",
        "supports_top_p": "Top-p",
        "supports_frequency_penalty": "Penalización de frecuencia",
        "supports_presence_penalty": "Penalización de presencia",
        "reasoning_template": "Plantilla de razonamiento",
        "reasoning_shape": "Forma del razonamiento (solo lectura)",
        "reasoning_doc_i18n_key": "Clave de ayuda",
        "effort_values": "Valores de esfuerzo (solo lectura)",
        "pricing_unit": "Unidad de tarifa",
        "input_unit_price": "Precio de entrada (USD)",
        "cached_input_unit_price": "Precio de entrada en caché (USD)",
        "output_unit_price": "Precio de salida (USD)",
        "effective_from": "Vigente desde (solo lectura)",
        "time_slots_mode": "Franjas horarias",
        "time_slots_summary": "Ventanas activas (solo lectura)",
        "statut": "Estado (solo lectura)",
        "row_fingerprint": "Huella",
        "start_utc": "Inicio UTC",
        "end_utc": "Fin UTC",
    },
    "de": {
        "model_name": "Modellname",
        "provider": "Anbieter",
        "kind": "Art",
        "is_active": "Aktiv",
        "max_input_tokens": "Max. Eingabe (Tokens)",
        "max_output_tokens": "Max. Ausgabe (Tokens)",
        "supports_tools": "Werkzeuge",
        "supports_structured_output": "Strukturierte Ausgabe",
        "supports_strict_mode": "Strikter Modus",
        "supports_streaming": "Streaming",
        "supports_vision": "Bildverarbeitung",
        "supports_temperature": "Temperatur",
        "supports_top_p": "Top-p",
        "supports_frequency_penalty": "Häufigkeitsstrafe",
        "supports_presence_penalty": "Präsenzstrafe",
        "reasoning_template": "Reasoning-Vorlage",
        "reasoning_shape": "Reasoning-Form (schreibgeschützt)",
        "reasoning_doc_i18n_key": "Hilfeschlüssel",
        "effort_values": "Effort-Werte (schreibgeschützt)",
        "pricing_unit": "Tarifeinheit",
        "input_unit_price": "Eingabepreis (USD)",
        "cached_input_unit_price": "Preis für zwischengespeicherte Eingabe (USD)",
        "output_unit_price": "Ausgabepreis (USD)",
        "effective_from": "Gültig ab (schreibgeschützt)",
        "time_slots_mode": "Zeitfenster",
        "time_slots_summary": "Aktive Fenster (schreibgeschützt)",
        "statut": "Status (schreibgeschützt)",
        "row_fingerprint": "Prüfsumme",
        "start_utc": "Beginn UTC",
        "end_utc": "Ende UTC",
    },
    "it": {
        "model_name": "Nome del modello",
        "provider": "Fornitore",
        "kind": "Tipo",
        "is_active": "Attivo",
        "max_input_tokens": "Input max (token)",
        "max_output_tokens": "Output max (token)",
        "supports_tools": "Strumenti",
        "supports_structured_output": "Output strutturato",
        "supports_strict_mode": "Modalità rigorosa",
        "supports_streaming": "Streaming",
        "supports_vision": "Visione",
        "supports_temperature": "Temperatura",
        "supports_top_p": "Top-p",
        "supports_frequency_penalty": "Penalità di frequenza",
        "supports_presence_penalty": "Penalità di presenza",
        "reasoning_template": "Modello di ragionamento",
        "reasoning_shape": "Forma del ragionamento (sola lettura)",
        "reasoning_doc_i18n_key": "Chiave di aiuto",
        "effort_values": "Valori di sforzo (sola lettura)",
        "pricing_unit": "Unità di tariffa",
        "input_unit_price": "Prezzo input (USD)",
        "cached_input_unit_price": "Prezzo input in cache (USD)",
        "output_unit_price": "Prezzo output (USD)",
        "effective_from": "In vigore dal (sola lettura)",
        "time_slots_mode": "Fasce orarie",
        "time_slots_summary": "Finestre attive (sola lettura)",
        "statut": "Stato (sola lettura)",
        "row_fingerprint": "Impronta",
        "start_utc": "Inizio UTC",
        "end_utc": "Fine UTC",
    },
    "zh-CN": {
        "model_name": "模型名称",
        "provider": "供应商",
        "kind": "类型",
        "is_active": "启用",
        "max_input_tokens": "最大输入（词元）",
        "max_output_tokens": "最大输出（词元）",
        "supports_tools": "工具",
        "supports_structured_output": "结构化输出",
        "supports_strict_mode": "严格模式",
        "supports_streaming": "流式传输",
        "supports_vision": "视觉",
        "supports_temperature": "温度",
        "supports_top_p": "Top-p",
        "supports_frequency_penalty": "频率惩罚",
        "supports_presence_penalty": "存在惩罚",
        "reasoning_template": "推理模板",
        "reasoning_shape": "推理形态（只读）",
        "reasoning_doc_i18n_key": "帮助键",
        "effort_values": "投入档位（只读）",
        "pricing_unit": "计价单位",
        "input_unit_price": "输入价格（美元）",
        "cached_input_unit_price": "缓存输入价格（美元）",
        "output_unit_price": "输出价格（美元）",
        "effective_from": "生效时间（只读）",
        "time_slots_mode": "时段",
        "time_slots_summary": "生效窗口（只读）",
        "statut": "状态（只读）",
        "row_fingerprint": "指纹",
        "start_utc": "开始（UTC）",
        "end_utc": "结束（UTC）",
    },
}

# ---------------------------------------------------------------------------
# Structural strings, diagnostics and the yes/no words
# ---------------------------------------------------------------------------

_STRINGS: dict[Language, dict[str, str]] = {
    "fr": {
        "sheet.notice": "Notice",
        "sheet.referentials": "Référentiels",
        "sheet.metadata": "Métadonnées",
        "settings.admin.llm.sheet.models": "Modèles",
        "settings.admin.llm.sheet.slots": "Plages horaires",
        "settings.admin.llm.sheet.status.ok": "ok",
        "settings.admin.llm.sheet.status.no_pricing": "aucun tarif actif",
        "settings.admin.llm.sheet.status.multiple": "{count} tarifs actifs",
        "settings.admin.llm.sheet.status.shadowed": "facturé sous {name}",
        "settings.admin.llm.sheet.slots_summary": "{count} fenêtres : {windows}",
        "settings.admin.llm.sheet.reasoning_prefix": "raisonnement",
        "boolean.true": "VRAI",
        "boolean.false": "FAUX",
    },
    "en": {
        "sheet.notice": "Notice",
        "sheet.referentials": "Referentials",
        "sheet.metadata": "Metadata",
        "settings.admin.llm.sheet.models": "Models",
        "settings.admin.llm.sheet.slots": "Time slots",
        "settings.admin.llm.sheet.status.ok": "ok",
        "settings.admin.llm.sheet.status.no_pricing": "no active tariff",
        "settings.admin.llm.sheet.status.multiple": "{count} active tariffs",
        "settings.admin.llm.sheet.status.shadowed": "billed under {name}",
        "settings.admin.llm.sheet.slots_summary": "{count} windows: {windows}",
        "settings.admin.llm.sheet.reasoning_prefix": "reasoning",
        "boolean.true": "TRUE",
        "boolean.false": "FALSE",
    },
    "es": {
        "sheet.notice": "Instrucciones",
        "sheet.referentials": "Referenciales",
        "sheet.metadata": "Metadatos",
        "settings.admin.llm.sheet.models": "Modelos",
        "settings.admin.llm.sheet.slots": "Franjas horarias",
        "settings.admin.llm.sheet.status.ok": "ok",
        "settings.admin.llm.sheet.status.no_pricing": "sin tarifa activa",
        "settings.admin.llm.sheet.status.multiple": "{count} tarifas activas",
        "settings.admin.llm.sheet.status.shadowed": "facturado como {name}",
        "settings.admin.llm.sheet.slots_summary": "{count} ventanas: {windows}",
        "settings.admin.llm.sheet.reasoning_prefix": "razonamiento",
        "boolean.true": "VERDADERO",
        "boolean.false": "FALSO",
    },
    "de": {
        "sheet.notice": "Hinweise",
        "sheet.referentials": "Referenzlisten",
        "sheet.metadata": "Metadaten",
        "settings.admin.llm.sheet.models": "Modelle",
        "settings.admin.llm.sheet.slots": "Zeitfenster",
        "settings.admin.llm.sheet.status.ok": "ok",
        "settings.admin.llm.sheet.status.no_pricing": "kein aktiver Tarif",
        "settings.admin.llm.sheet.status.multiple": "{count} aktive Tarife",
        "settings.admin.llm.sheet.status.shadowed": "abgerechnet als {name}",
        "settings.admin.llm.sheet.slots_summary": "{count} Fenster: {windows}",
        "settings.admin.llm.sheet.reasoning_prefix": "Reasoning",
        "boolean.true": "WAHR",
        "boolean.false": "FALSCH",
    },
    "it": {
        "sheet.notice": "Istruzioni",
        "sheet.referentials": "Referenziali",
        "sheet.metadata": "Metadati",
        "settings.admin.llm.sheet.models": "Modelli",
        "settings.admin.llm.sheet.slots": "Fasce orarie",
        "settings.admin.llm.sheet.status.ok": "ok",
        "settings.admin.llm.sheet.status.no_pricing": "nessuna tariffa attiva",
        "settings.admin.llm.sheet.status.multiple": "{count} tariffe attive",
        "settings.admin.llm.sheet.status.shadowed": "fatturato come {name}",
        "settings.admin.llm.sheet.slots_summary": "{count} finestre: {windows}",
        "settings.admin.llm.sheet.reasoning_prefix": "ragionamento",
        "boolean.true": "VERO",
        "boolean.false": "FALSO",
    },
    "zh-CN": {
        "sheet.notice": "使用说明",
        "sheet.referentials": "参照表",
        "sheet.metadata": "元数据",
        "settings.admin.llm.sheet.models": "模型",
        "settings.admin.llm.sheet.slots": "时段",
        "settings.admin.llm.sheet.status.ok": "正常",
        "settings.admin.llm.sheet.status.no_pricing": "无生效价格",
        "settings.admin.llm.sheet.status.multiple": "{count} 条生效价格",
        "settings.admin.llm.sheet.status.shadowed": "按 {name} 计费",
        "settings.admin.llm.sheet.slots_summary": "{count} 个窗口：{windows}",
        "settings.admin.llm.sheet.reasoning_prefix": "推理",
        "boolean.true": "是",
        "boolean.false": "否",
    },
}

# ---------------------------------------------------------------------------
# The notice — the rules an administrator cannot deduce from the file
# ---------------------------------------------------------------------------

_NOTICE: dict[Language, tuple[str, ...]] = {
    "fr": (
        "LIA — Catalogue des modèles LLM et de leurs tarifs",
        "",
        "Saisissez vos données à partir de la ligne 3. La ligne des libellés ne se modifie pas.",
        "Une ligne absente de ce fichier n'est JAMAIS supprimée : rien ne disparaît par oubli.",
        "Pour retirer un modèle, mettez is_active à FAUX ; le remettre à VRAI le réactive.",
        "Les colonnes grisées sont calculées : elles sont ignorées à l'import.",
        "Les prix sont en USD, avec 6 décimales au maximum ; une valeur plus précise est refusée.",
        "Une formule dans une cellule est refusée : saisissez la valeur, pas le calcul.",
        "Plages horaires : « flat » supprime les fenêtres, « windows » applique l'onglet dédié,",
        "« inherit » les laisse inchangées.",
        "Un import est intégral ou nul : une seule anomalie et rien n'est écrit.",
    ),
    "en": (
        "LIA — LLM model catalogue and pricing",
        "",
        "Enter your data from row 3 onwards. The label row is not meant to be edited.",
        "A row missing from this file is NEVER deleted: nothing disappears by omission.",
        "To retire a model, set is_active to FALSE; setting it back to TRUE reactivates it.",
        "Greyed columns are computed: they are ignored on import.",
        "Prices are in USD with at most 6 decimals; a more precise value is refused.",
        "A formula in a cell is refused: enter the value, not the calculation.",
        "Time slots: 'flat' clears the windows, 'windows' applies the dedicated sheet,",
        "'inherit' leaves them untouched.",
        "An import is all or nothing: a single problem and nothing is written.",
    ),
    "es": (
        "LIA — Catálogo de modelos LLM y sus tarifas",
        "",
        "Introduzca sus datos a partir de la fila 3. La fila de etiquetas no debe modificarse.",
        "Una fila ausente de este archivo NUNCA se elimina: nada desaparece por olvido.",
        "Para retirar un modelo, ponga is_active en FALSO; volver a VERDADERO lo reactiva.",
        "Las columnas grises son calculadas: se ignoran al importar.",
        "Los precios son en USD, con 6 decimales como máximo; un valor más preciso se rechaza.",
        "Una fórmula en una celda se rechaza: introduzca el valor, no el cálculo.",
        "Franjas horarias: «flat» borra las ventanas, «windows» aplica la pestaña dedicada,",
        "«inherit» las deja sin cambios.",
        "Una importación es total o nula: un solo problema y no se escribe nada.",
    ),
    "de": (
        "LIA — Katalog der LLM-Modelle und ihrer Tarife",
        "",
        "Tragen Sie Ihre Daten ab Zeile 3 ein. Die Beschriftungszeile wird nicht bearbeitet.",
        "Eine in dieser Datei fehlende Zeile wird NIE gelöscht: nichts verschwindet aus Versehen.",
        "Zum Stilllegen eines Modells is_active auf FALSCH setzen; WAHR aktiviert es wieder.",
        "Graue Spalten sind berechnet: beim Import werden sie ignoriert.",
        "Preise in USD mit höchstens 6 Nachkommastellen; ein genauerer Wert wird abgelehnt.",
        "Eine Formel in einer Zelle wird abgelehnt: tragen Sie den Wert ein, nicht die Rechnung.",
        "Zeitfenster: „flat“ löscht die Fenster, „windows“ wendet das eigene Blatt an,",
        "„inherit“ lässt sie unverändert.",
        "Ein Import ist ganz oder gar nicht: ein einziges Problem und nichts wird geschrieben.",
    ),
    "it": (
        "LIA — Catalogo dei modelli LLM e delle loro tariffe",
        "",
        "Inserisca i dati a partire dalla riga 3. La riga delle etichette non va modificata.",
        "Una riga assente da questo file non viene MAI eliminata: nulla sparisce per dimenticanza.",
        "Per ritirare un modello, imposti is_active su FALSO; riportarlo a VERO lo riattiva.",
        "Le colonne grigie sono calcolate: all'importazione vengono ignorate.",
        "I prezzi sono in USD, con 6 decimali al massimo; un valore più preciso viene rifiutato.",
        "Una formula in una cella viene rifiutata: inserisca il valore, non il calcolo.",
        "Fasce orarie: «flat» cancella le finestre, «windows» applica il foglio dedicato,",
        "«inherit» le lascia invariate.",
        "Un'importazione è totale o nulla: un solo problema e non viene scritto nulla.",
    ),
    "zh-CN": (
        "LIA — LLM 模型目录与价格",
        "",
        "请从第 3 行开始填写数据。标签行请勿修改。",
        "本文件中缺失的行**绝不会**被删除：不会因遗漏而丢失任何内容。",
        "如需停用某个模型，请将 is_active 设为「否」；改回「是」即可重新启用。",
        "灰色列为计算列：导入时会被忽略。",
        "价格以美元计，最多 6 位小数；精度更高的数值会被拒绝。",
        "单元格中的公式会被拒绝：请填写数值，而不是算式。",
        "时段：「flat」清除窗口，「windows」应用专用工作表，「inherit」保持不变。",
        "导入要么全部生效，要么完全不生效：只要有一处问题，就不会写入任何内容。",
    ),
}

#: Every key :func:`build_sheet_labels` produces. Published so a caller can
#: check coverage rather than discover a gap in a generated file.
SHEET_LABEL_KEYS: tuple[str, ...] = tuple(
    [_COLUMN_PREFIX + key for key in _COLUMNS["en"]] + list(_STRINGS["en"])
)


def build_sheet_labels(language: str) -> dict[str, str]:
    """Return every workbook string in ``language``.

    Args:
        language: Raw locale, in any spelling the frontend or a user profile
            may carry (``zh``, ``zh_CN``, ``fr-FR``…).

    Returns:
        Mapping of label key to translated string, ready for the writer and
        the export row builder.
    """
    resolved = normalize_language(language)
    columns = _COLUMNS.get(resolved) or _COLUMNS[DEFAULT_LANGUAGE]
    strings = _STRINGS.get(resolved) or _STRINGS[DEFAULT_LANGUAGE]
    labels = {_COLUMN_PREFIX + key: value for key, value in columns.items()}
    labels.update(strings)
    return labels


def build_sheet_notice(language: str) -> tuple[str, ...]:
    """Return the notice lines in ``language``.

    Args:
        language: Raw locale, normalized like every other lookup here.

    Returns:
        The lines of the notice sheet, in reading order.
    """
    resolved = normalize_language(language)
    return _NOTICE.get(resolved) or _NOTICE[DEFAULT_LANGUAGE]
