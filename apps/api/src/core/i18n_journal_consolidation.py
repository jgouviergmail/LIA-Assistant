"""Human approval explains source maintenance scope, costs and uncertain generated effects."""

from src.core.i18n_types import Language

JOURNAL_CONSOLIDATION_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Consolidation du journal",
        "Lancer la maintenance des entrées actives et du portrait avec les réglages affichés. Les compteurs incluent toutes les entrées conservées pour vérifier le périmètre. Le modèle peut créer, modifier, fusionner ou supprimer des entrées ; son résultat n’est pas connu avant l’exécution. Le réglage d’historique détermine l’usage des conversations. Modèle, revue du portrait et embeddings peuvent consommer des tokens et le budget plateforme sous quotas. Un échec peut avoir consommé des tokens sans publier un portrait. Accord expiré, données modifiées ou droits retirés : nouvel accord nécessaire. Ne pas relancer automatiquement un résultat incertain.",
    ),
    "en": (
        "Journal consolidation",
        "Run active-entry and portrait maintenance with the displayed settings. Counts cover all retained entries to verify scope. The model may create, edit, merge or remove entries; its result is unknown before execution. The history setting governs conversation use. Model, portrait review and embeddings may consume tokens and platform budget under quotas. A failure may spend tokens without publishing a portrait. Expiry, changed data or withdrawn authority require fresh approval. Never automatically retry an uncertain outcome.",
    ),
    "de": (
        "Journalkonsolidierung",
        "Aktive Einträge und Porträt mit den angezeigten Einstellungen warten. Die Zähler umfassen alle gespeicherten Einträge zur Bereichsprüfung. Das Modell kann Einträge erstellen, ändern, zusammenführen oder löschen; sein Ergebnis ist vorab unbekannt. Die Verlaufseinstellung regelt die Nutzung von Gesprächen. Modell, Porträtprüfung und Embeddings können Token und Plattformbudget unter Quoten verbrauchen. Fehler können Kosten ohne neues Porträt verursachen. Ablauf, Datenänderungen oder entzogene Rechte erfordern neue Zustimmung. Ein unsicheres Ergebnis nie automatisch wiederholen.",
    ),
    "es": (
        "Consolidación del diario",
        "Mantener las entradas activas y el retrato con los ajustes indicados. Los contadores incluyen todas las entradas guardadas para verificar el alcance. El modelo puede crear, editar, fusionar o eliminar entradas; su resultado no se conoce antes de ejecutar. El ajuste de historial determina el uso de conversaciones. Modelo, revisión del retrato y embeddings pueden consumir tokens y presupuesto de plataforma con cuotas. Un fallo puede generar costes sin publicar un retrato. Caducidad, cambios o permisos retirados requieren nueva aprobación. No repetir automáticamente un resultado incierto.",
    ),
    "it": (
        "Consolidamento del diario",
        "Eseguire la manutenzione delle voci attive e del ritratto con le impostazioni mostrate. I contatori includono tutte le voci conservate per verificare l’ambito. Il modello può creare, modificare, unire o eliminare voci; il risultato non è noto prima dell’esecuzione. L’impostazione della cronologia regola l’uso delle conversazioni. Modello, revisione del ritratto ed embedding possono consumare token e budget della piattaforma con quote. Un errore può comportare costi senza pubblicare un ritratto. Scadenza, modifiche o permessi revocati richiedono un nuovo consenso. Non ripetere automaticamente un risultato incerto.",
    ),
    "zh-CN": (
        "日志整合",
        "按显示的设置维护当前条目与画像。计数包含全部已保存条目，用于核对范围。模型可能创建、修改、合并或删除条目；执行前无法预知结果。历史设置决定是否使用对话。模型、画像复核和嵌入可能在配额限制下消耗令牌及平台预算。失败也可能产生费用而未发布画像。批准过期、数据变化或权限撤销时需重新批准。不得自动重试结果不确定的操作。",
    ),
}
