"""A correction saved before generation is distinguished from a regenerated portrait."""

from src.core.i18n_types import Language

JOURNAL_FEEDBACK_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Correction du portrait",
        "Enregistrer la correction complète affichée comme observation L0, sans fabriquer de preuve, puis lancer la consolidation avec les réglages et l’accord d’historique affichés. Embedding, modèle, revue du portrait et maintenance peuvent consommer des tokens plateforme sous quotas. Le commentaire reste enregistré même si la génération échoue, est occupée ou devient incertaine ; un commentaire enregistré ne prouve pas qu’un nouveau portrait a été publié. La consolidation peut créer, modifier, fusionner ou supprimer des entrées actives. Données modifiées, droits retirés ou accord expiré : les étapes restantes sont refusées. Ne pas rejouer automatiquement un résultat partiel ou incertain.",
    ),
    "en": (
        "Portrait correction",
        "Save the complete displayed correction as an L0 observation without fabricating evidence, then consolidate with the displayed settings and history consent. Embedding, model, portrait review and maintenance may consume platform tokens under quotas. Feedback remains saved if generation fails, is busy or becomes uncertain; saved feedback does not prove a new portrait was published. Consolidation may create, edit, merge or remove active entries. Changed data, withdrawn rights or expired approval refuse remaining phases. Never automatically replay a partial or uncertain result.",
    ),
    "de": (
        "Porträtkorrektur",
        "Die vollständige Korrektur als L0-Beobachtung ohne erfundene Belege speichern, danach mit angezeigten Einstellungen und Verlaufseinwilligung konsolidieren. Embedding, Modell, Porträtprüfung und Wartung können Plattform-Token unter Quoten verbrauchen. Feedback bleibt bei Fehler, laufender Wartung oder unsicherem Ergebnis gespeichert; dies beweist kein neues Porträt. Aktive Einträge können erstellt, geändert, zusammengeführt oder gelöscht werden. Geänderte Daten, entzogene Rechte oder abgelaufene Zustimmung stoppen weitere Phasen. Teilweise oder unsichere Ergebnisse nie automatisch wiederholen.",
    ),
    "es": (
        "Corrección del retrato",
        "Guardar la corrección completa como observación L0 sin inventar pruebas y consolidar con los ajustes y consentimiento de historial indicados. Embedding, modelo, revisión del retrato y mantenimiento pueden consumir tokens de plataforma con cuotas. El comentario permanece si la generación falla, está ocupada o es incierta; guardarlo no demuestra que exista un nuevo retrato. Se pueden crear, editar, fusionar o eliminar entradas activas. Cambios, permisos retirados o aprobación caducada impiden las fases pendientes. No repetir automáticamente resultados parciales o inciertos.",
    ),
    "it": (
        "Correzione del ritratto",
        "Salvare l’intera correzione come osservazione L0 senza inventare prove, poi consolidare con le impostazioni e il consenso alla cronologia mostrati. Embedding, modello, revisione del ritratto e manutenzione possono consumare token della piattaforma con quote. Il commento rimane salvato in caso di errore, elaborazione occupata o risultato incerto; non prova che sia stato pubblicato un nuovo ritratto. Le voci attive possono essere create, modificate, unite o eliminate. Modifiche, permessi revocati o consenso scaduto impediscono le fasi restanti. Non ripetere automaticamente risultati parziali o incerti.",
    ),
    "zh-CN": (
        "画像纠正",
        "将显示的完整纠正保存为L0观察，不虚构证据，然后按显示的设置和历史同意范围进行整合。嵌入、模型、画像复核和维护可能在配额限制下消耗平台令牌。生成失败、忙碌或结果不确定时，评论仍保留；保存评论不代表新画像已发布。整合可能创建、修改、合并或删除当前条目。数据变化、权限撤销或批准过期时，后续阶段被拒绝。不得自动重放部分完成或结果不确定的操作。",
    ),
}
