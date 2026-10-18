"""Existing multilingual result indicators for rejected-plan history filtering."""

_RESULT_INDICATORS_BY_LANG: dict[str, set[str]] = {
    "fr": {
        "trouvé",
        "voici",
        "résultat",
        "résultats",
        "contact",
        "événement",
        "email",
        "lieu",
        "fichier",
    },
    "en": {
        "found",
        "result",
        "results",
        "here is",
        "here are",
        "contact",
        "event",
        "email",
        "place",
        "file",
    },
    "es": {
        "encontrado",
        "aquí",
        "resultado",
        "resultados",
        "contacto",
        "evento",
        "correo",
        "lugar",
        "archivo",
    },
    "de": {
        "gefunden",
        "hier ist",
        "hier sind",
        "ergebnis",
        "ergebnisse",
        "kontakt",
        "termin",
        "e-mail",
        "ort",
        "datei",
    },
    "it": {
        "trovato",
        "ecco",
        "risultato",
        "risultati",
        "contatto",
        "evento",
        "email",
        "luogo",
        "file",
    },
    "zh-CN": {"找到", "结果", "这里是", "联系人", "事件", "邮件", "地点", "文件"},
}

# Build combined frozenset for all languages + JSON indicators
RESULT_CONTENT_INDICATORS: frozenset[str] = frozenset(
    indicator for indicators in _RESULT_INDICATORS_BY_LANG.values() for indicator in indicators
) | frozenset(
    {
        # JSON/data indicators (language-agnostic)
        "```json",
        "```",
        '"id":',
        '"name":',
    }
)
