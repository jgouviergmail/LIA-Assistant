"""Consent discloses complete answer copying and eventual paid indexing."""

from src.core.i18n_types import Language

BOOKMARK_KEEP_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Réponse à enregistrer",
        "La réponse et sa demande sont copiées intégralement, même si l’aperçu n’en affiche qu’un extrait. Le message, sa date et les quotas sont recontrôlés. La copie survit à la suppression de la conversation. Après validation SQL certaine, l’indexation automatique habituelle peut consommer des tokens et les quotas de la plateforme ou du compte. Une indexation en attente n’est pas terminée. Une copie déjà enregistrée reste inchangée ; un résultat incertain ne sera pas relancé automatiquement.",
    ),
    "en": (
        "Answer to save",
        "The answer and its request are copied in full, even when the preview shows only excerpts. Message identity, date and quotas are checked again. The copy survives conversation deletion. After known SQL commit, normal automatic indexing may consume tokens and platform or account quota. Pending indexing is not finished. An existing saved copy remains unchanged; uncertain results are never automatically replayed.",
    ),
    "de": (
        "Zu speichernde Antwort",
        "Antwort und Anfrage werden vollständig kopiert, auch wenn die Vorschau nur Auszüge zeigt. Nachricht, Datum und Kontingente werden erneut geprüft. Die Kopie bleibt nach Löschung des Gesprächs erhalten. Nach bestätigtem SQL-Commit kann die übliche automatische Indexierung Tokens und Plattform- oder Kontokontingente verbrauchen. Ausstehende Indexierung ist nicht abgeschlossen. Bereits gespeicherte Kopien bleiben unverändert; ungewisse Ergebnisse werden nicht automatisch wiederholt.",
    ),
    "es": (
        "Respuesta para guardar",
        "La respuesta y su solicitud se copian completas, aunque la vista previa solo muestre extractos. Se verifican de nuevo el mensaje, la fecha y las cuotas. La copia sobrevive a la eliminación de la conversación. Tras confirmar el commit SQL, la indexación automática habitual puede consumir tokens y cuotas de la plataforma o cuenta. Una indexación pendiente no está terminada. Las copias existentes no cambian; los resultados inciertos no se repiten automáticamente.",
    ),
    "it": (
        "Risposta da salvare",
        "La risposta e la richiesta vengono copiate integralmente, anche quando l’anteprima mostra solo estratti. Messaggio, data e quote vengono ricontrollati. La copia resta dopo l’eliminazione della conversazione. Dopo un commit SQL certo, la normale indicizzazione automatica può consumare token e quote della piattaforma o dell’account. Un’indicizzazione in attesa non è conclusa. Le copie esistenti restano invariate; risultati incerti non vengono ripetuti automaticamente.",
    ),
    "zh-CN": (
        "待保存的回答",
        "回答和原始请求会被完整复制，即使预览只显示摘要。系统将重新检查消息、日期和配额。删除对话后副本仍然保留。确认 SQL 提交后，常规自动索引可能消耗令牌以及平台或账户配额。待索引不表示已经完成。已有副本保持不变；不确定的结果不会自动重试。",
    ),
}
