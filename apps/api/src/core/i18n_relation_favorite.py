"""Favorite approval names the displayed identity and the effect on merged spellings."""

from src.core.i18n_types import Language

RELATION_FAVORITE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Favori de la relation",
        "Le favori change pour cette carte. Son retrait enlève aussi les favoris des noms regroupés ; les données et les regroupements restent conservés. Aucun débrief ni partage n’est lancé.",
    ),
    "en": (
        "Relationship favorite",
        "The favorite changes for this card. Removing it also removes stars on merged spellings; data and groupings are retained. No debrief or sharing is started.",
    ),
    "de": (
        "Beziehungsfavorit",
        "Der Favorit dieser Karte ändert sich. Beim Entfernen werden auch Sterne zusammengeführter Namen entfernt; Daten und Gruppierungen bleiben erhalten. Kein Debriefing und keine Freigabe werden gestartet.",
    ),
    "es": (
        "Favorito de la relación",
        "Cambia el favorito de esta tarjeta. Al retirarlo también se quitan las estrellas de los nombres agrupados; se conservan los datos y las agrupaciones. No se inicia ningún resumen ni uso compartido.",
    ),
    "it": (
        "Preferito della relazione",
        "Cambia il preferito di questa scheda. Rimuoverlo elimina anche le stelle dei nomi raggruppati; dati e raggruppamenti restano conservati. Non viene avviato alcun riepilogo né condivisione.",
    ),
    "zh-CN": (
        "关系收藏",
        "更改此卡片的收藏状态。取消收藏也会移除已合并名称的收藏；数据和合并关系保持不变。不启动简报或共享。",
    ),
}
