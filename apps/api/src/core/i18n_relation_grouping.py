"""Grouping approval explains display identity and the removal of stale stored debriefs."""

from src.core.i18n_types import Language

RELATION_GROUPING_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Regroupement de la relation",
        "Le regroupement change pour les noms affichés. Si le nom source est déjà regroupé, seuls ce nom et les noms qui pointent vers lui sont réaffectés. Les débriefs enregistrés concernés sont supprimés ; les données, favoris et permissions de partage restent conservés. Une génération déjà commencée peut terminer son travail sans rétablir le débrief supprimé. Aucun nouveau débrief n’est lancé.",
    ),
    "en": (
        "Relationship grouping",
        "Grouping changes for the displayed names. If the source name is already merged, only that spelling and names pointing to it are reassigned. Affected stored debriefs are removed; data, favorites and sharing permissions are retained. An already-started build may finish its work without restoring the deleted debrief. No new debrief is started.",
    ),
    "de": (
        "Beziehungsgruppierung",
        "Die Gruppierung der angezeigten Namen ändert sich. Ist der Quellname bereits zusammengeführt, werden nur diese Schreibweise und darauf verweisende Namen neu zugeordnet. Betroffene gespeicherte Debriefings werden entfernt; Daten, Favoriten und Freigaben bleiben erhalten. Eine begonnene Erstellung kann ihre Arbeit beenden, ohne das gelöschte Debriefing wiederherzustellen. Kein neues Debriefing wird gestartet.",
    ),
    "es": (
        "Agrupación de la relación",
        "Cambia la agrupación de los nombres mostrados. Si el nombre de origen ya está agrupado, solo se reasignan ese nombre y los que apuntan a él. Se eliminan los resúmenes guardados afectados; se conservan datos, favoritos y permisos compartidos. Una generación iniciada puede terminar sin restaurar el resumen eliminado. No se inicia un nuevo resumen.",
    ),
    "it": (
        "Raggruppamento della relazione",
        "Cambia il raggruppamento dei nomi mostrati. Se il nome sorgente è già raggruppato, vengono riassegnati solo quel nome e quelli che vi puntano. I riepiloghi salvati interessati vengono rimossi; dati, preferiti e permessi di condivisione restano conservati. Una generazione iniziata può terminare senza ripristinare il riepilogo eliminato. Non viene avviato un nuovo riepilogo.",
    ),
    "zh-CN": (
        "关系分组",
        "更改显示名称的分组。如果来源名称已合并，仅重新分配该名称和指向它的名称。删除受影响的已保存简报；数据、收藏和共享权限保持不变。已开始的生成可能完成工作，但不会恢复已删除的简报。不启动新简报。",
    ),
}
