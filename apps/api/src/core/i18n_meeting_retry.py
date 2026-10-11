"""Consent states original paid workflow effects and later configuration resolution."""

MEETING_RETRY_COPY: dict[str, tuple[str, str]] = {
    "fr": (
        "Traitement de réunion à relancer",
        "Remet cette réunion arrêtée ou en échec en file d’attente et réinitialise son budget de tentatives. Le traitement peut réutiliser ses étapes sauvegardées, transcrire l’audio, choisir un modèle de compte rendu, remplacer les minutes, enrichir le lieu/calendrier, notifier, envoyer un courriel si auto_email est activé, indexer et supprimer l’audio non conservé. Les coûts habituels de transcription, synthèse et indexation ainsi que les quotas s’appliquent, y compris sans clé personnelle. Les préférences affichées sont celles de la confirmation ; le traitement ultérieur relit sa configuration et les modèles de compte rendu, donc des modifications ultérieures peuvent l’affecter. Aucun prix final ni succès immédiat n’est garanti. Le contenu n’est pas affiché ici. Un traitement remis en attente n’est pas un traitement terminé.",
    ),
    "en": (
        "Meeting processing to retry",
        "Requeue this stopped or failed meeting and reset its attempt budget. The workflow can reuse saved stages, transcribe audio, select a minutes template, replace minutes, enrich location/calendar, notify, email when auto_email is enabled, index and purge unkept audio. Existing transcription, synthesis and indexing costs and quotas apply, including platform-funded use without a personal key. Displayed preferences belong to this confirmation; the later job rereads runtime configuration and templates, so later edits can affect it. No final price or immediate success is guaranteed. Content is not displayed here. Requeued processing is not completed processing.",
    ),
    "de": (
        "Besprechungsverarbeitung erneut starten",
        "Stellt diese gestoppte oder fehlgeschlagene Besprechung erneut in die Warteschlange und setzt die Versuchsanzahl zurück. Gespeicherte Schritte können wiederverwendet werden; Audio wird transkribiert, eine Vorlage gewählt, das Protokoll ersetzt, Ort/Kalender ergänzt, benachrichtigt, bei auto_email per E-Mail gesendet, indexiert und nicht aufbewahrtes Audio gelöscht. Übliche Kosten und Kontingente gelten, auch ohne eigenen Schlüssel. Die angezeigten Einstellungen gelten bei Bestätigung; der spätere Auftrag liest Konfiguration und Vorlagen erneut, sodass spätere Änderungen wirken können. Endpreis und sofortiger Erfolg sind nicht garantiert. Inhalte werden hier nicht angezeigt. Ein erneut eingereihter Auftrag ist noch nicht abgeschlossen.",
    ),
    "es": (
        "Procesamiento de reunión para reintentar",
        "Vuelve a poner esta reunión detenida o fallida en cola y reinicia sus intentos. Puede reutilizar etapas guardadas, transcribir audio, elegir una plantilla, sustituir actas, completar lugar/calendario, notificar, enviar correo si auto_email está activo, indexar y eliminar audio no conservado. Se aplican los costes y cuotas habituales, incluso sin clave personal. Las preferencias mostradas son las de esta confirmación; el trabajo posterior relee configuración y plantillas, por lo que cambios posteriores pueden afectarlo. No garantiza precio final ni éxito inmediato. Aquí no se muestra el contenido. Un trabajo en cola todavía no ha terminado.",
    ),
    "it": (
        "Elaborazione della riunione da riprovare",
        "Rimette in coda questa riunione interrotta o non riuscita e azzera i tentativi. Può riutilizzare fasi salvate, trascrivere audio, scegliere un modello, sostituire il verbale, completare luogo/calendario, notificare, inviare email se auto_email è attivo, indicizzare ed eliminare audio non conservato. Si applicano costi e quote abituali, anche senza chiave personale. Le preferenze mostrate sono quelle della conferma; il lavoro successivo rilegge configurazione e modelli, quindi modifiche successive possono influire. Prezzo finale e successo immediato non sono garantiti. Il contenuto non è mostrato qui. Un’elaborazione in coda non è ancora terminata.",
    ),
    "zh-CN": (
        "待重试的会议处理",
        "将已停止或失败的会议重新排队并重置尝试次数。流程可能复用已保存阶段、转录音频、选择纪要模板、替换纪要、补充地点和日历信息、通知、在 auto_email 开启时发送邮件、建立索引并删除未保留的音频。通常的转录、生成、索引费用和额度限制仍然适用，包括没有个人密钥的平台付费使用。显示的是确认时的偏好；后续任务会重新读取运行配置和模板，因此之后的修改可能影响结果。不保证最终费用或立即成功。此处不显示内容。重新排队并不代表处理已完成。",
    ),
}
