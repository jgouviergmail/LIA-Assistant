"""Deletion effects are explicit without promising permanently suppressed learning."""

from src.core.i18n_types import Language

JOURNAL_REMOVAL_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Entrées du journal à supprimer",
        "Les entrées affichées, ou toutes les entrées si le périmètre est global, seront définitivement supprimées avec leurs événements de preuve. Le portrait sera invalidé. Les réglages et les conversations restent conservés. Les observations pourront être réapprises ; aucun nouveau portrait n’est généré ici.",
    ),
    "en": (
        "Journal entries to remove",
        "The displayed entry, or all entries for complete scope, will be permanently removed with attached evidence events. The portrait will be invalidated. Settings and conversations remain. Observations may be learned again; no new portrait is generated here.",
    ),
    "de": (
        "Zu löschende Journaleinträge",
        "Der angezeigte Eintrag oder alle Einträge bei vollständigem Umfang werden samt Belegen dauerhaft gelöscht. Das Porträt wird ungültig. Einstellungen und Gespräche bleiben. Beobachtungen können neu gelernt werden; hier entsteht kein neues Porträt.",
    ),
    "es": (
        "Entradas del diario que se eliminarán",
        "Se eliminará definitivamente la entrada mostrada o todas las entradas del alcance completo, junto con sus pruebas. El retrato quedará invalidado. Se conservan los ajustes y conversaciones. Las observaciones pueden aprenderse de nuevo; aquí no se genera otro retrato.",
    ),
    "it": (
        "Voci del diario da eliminare",
        "La voce mostrata o tutte le voci nell’ambito completo saranno eliminate definitivamente con i relativi eventi di prova. Il ritratto sarà invalidato. Impostazioni e conversazioni restano. Le osservazioni possono essere riapprese; qui non viene generato un nuovo ritratto.",
    ),
    "zh-CN": (
        "待删除的日志条目",
        "将永久删除显示的条目或全量范围内的全部条目及其关联证据事件，使画像失效。保留设置和对话。观察内容可能再次被学习，此操作不生成新画像。",
    ),
}
