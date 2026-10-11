"""Relationship preference approval explains exact scope and absence of provider work."""

from src.core.i18n_types import Language

RELATION_SETTINGS_COPY: dict[Language, tuple[str, str, str]] = {
    "fr": (
        "Débrief relationnel quotidien",
        "Périmètre du point à 360°",
        "Seuls les réglages affichés changent. Les listes vides excluent ces sources ; les champs omis du périmètre prennent les valeurs par défaut. Aucun débrief ni appel fournisseur n’est lancé. Un débrief désactivé sur la plateforme reste indisponible.",
    ),
    "en": (
        "Daily relationship debrief",
        "360-degree overview scope",
        "Only the displayed settings change. Empty lists exclude those sources; omitted scope fields use defaults. No debrief or provider request is started. A platform-disabled debrief remains unavailable.",
    ),
    "de": (
        "Tägliches Beziehungsdebriefing",
        "Umfang der 360-Grad-Übersicht",
        "Nur die angezeigten Einstellungen ändern sich. Leere Listen schließen diese Quellen aus; ausgelassene Umfangsfelder verwenden Standardwerte. Es wird kein Debriefing oder Anbieteraufruf gestartet. Ein plattformweit deaktiviertes Debriefing bleibt nicht verfügbar.",
    ),
    "es": (
        "Resumen diario de relaciones",
        "Alcance de la vista de 360°",
        "Solo cambian los ajustes mostrados. Las listas vacías excluyen esas fuentes; los campos de alcance omitidos usan valores predeterminados. No se inicia ningún resumen ni solicitud al proveedor. Un resumen desactivado en la plataforma sigue sin estar disponible.",
    ),
    "it": (
        "Riepilogo quotidiano delle relazioni",
        "Ambito della panoramica a 360°",
        "Cambiano solo le impostazioni mostrate. Gli elenchi vuoti escludono queste fonti; i campi dell’ambito omessi usano i valori predefiniti. Non viene avviato alcun riepilogo né richiesta al fornitore. Un riepilogo disattivato sulla piattaforma resta indisponibile.",
    ),
    "zh-CN": (
        "每日关系简报",
        "360度概览范围",
        "仅更改显示的设置。空列表排除对应来源；省略的范围字段使用默认值。不启动简报或服务商请求。平台已停用的简报仍不可用。",
    ),
}
