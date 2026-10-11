"""Exact full-replacement consent and honest asynchronous rebuild consequences."""

MEETING_REGENERATION_COPY: dict[str, tuple[str, str]] = {
    "fr": (
        "Compte rendu à régénérer",
        "Relance la synthèse à partir de la transcription conservée. Si elle réussit, elle remplace tout le compte rendu actuel, y compris les modifications manuelles, et sa version générée, puis lance l’indexation. Le compte rendu actuel reste lisible pendant la synthèse. Le modèle de compte rendu affiché est celui de cette confirmation ; le traitement ultérieur relit les références et la configuration, donc des changements ultérieurs peuvent l’affecter. Les coûts habituels de synthèse/indexation et les quotas s’appliquent, y compris sans clé personnelle. Aucun prix final n’est garanti. Les contenus du compte rendu et de la transcription ne sont pas affichés ici. Mise en attente ne signifie pas synthèse ou indexation terminée. Aucun enregistrement, nouvelle transcription, courriel ou notification automatique.",
    ),
    "en": (
        "Meeting minutes to regenerate",
        "Queue synthesis from the retained transcript. On success it replaces the entire current report, including manual edits, and its generated revision, then schedules indexing. Current minutes remain readable during synthesis. The displayed template belongs to this confirmation; the later job rereads references and runtime configuration, so later changes can affect it. Existing synthesis/indexing costs and quotas apply, including platform-funded use without a personal key. No final price is promised. Report and transcript bodies are not displayed here. Queue acceptance is not synthesis or indexing completion. No recording, new transcription, automatic email or notification.",
    ),
    "de": (
        "Besprechungsprotokoll neu erstellen",
        "Stellt die Synthese aus dem aufbewahrten Transkript in die Warteschlange. Bei Erfolg ersetzt sie das gesamte aktuelle Protokoll einschließlich manueller Änderungen und die generierte Fassung; danach wird die Indexierung geplant. Das aktuelle Protokoll bleibt währenddessen lesbar. Die angezeigte Vorlage gilt bei Bestätigung; der spätere Auftrag liest Referenzen und Konfiguration erneut, sodass spätere Änderungen wirken können. Übliche Synthese-/Indexierungskosten und Kontingente gelten, auch ohne eigenen Schlüssel. Kein garantierter Endpreis. Protokoll und Transkript werden hier nicht vollständig angezeigt. Eingereiht bedeutet noch nicht fertig synthetisiert oder indexiert. Keine Aufnahme, neue Transkription, automatische E-Mail oder Benachrichtigung.",
    ),
    "es": (
        "Actas de reunión para regenerar",
        "Pone en cola la síntesis desde la transcripción conservada. Si tiene éxito, sustituye todo el informe actual, incluidos cambios manuales, y su versión generada; después programa la indexación. Las actas actuales siguen disponibles durante la síntesis. La plantilla mostrada corresponde a esta confirmación; el trabajo posterior relee referencias y configuración, por lo que cambios posteriores pueden afectarlo. Se aplican los costes y cuotas habituales, incluso sin clave personal. No garantiza precio final. Aquí no se muestran los textos completos. En cola no significa síntesis o indexación terminada. Sin grabación, nueva transcripción, correo ni notificación automática.",
    ),
    "it": (
        "Verbale della riunione da rigenerare",
        "Mette in coda la sintesi dalla trascrizione conservata. Se riesce, sostituisce l’intero verbale attuale, incluse modifiche manuali, e la versione generata; poi pianifica l’indicizzazione. Il verbale attuale resta leggibile durante la sintesi. Il modello mostrato è quello della conferma; il lavoro successivo rilegge riferimenti e configurazione, quindi modifiche successive possono influire. Si applicano costi e quote abituali, anche senza chiave personale. Nessun prezzo finale garantito. I testi completi non sono mostrati qui. In coda non significa sintesi o indicizzazione completata. Nessuna registrazione, nuova trascrizione, email o notifica automatica.",
    ),
    "zh-CN": (
        "待重新生成的会议纪要",
        "从保留的转录文本重新排队生成。成功后将替换整个当前纪要（包括人工编辑）和生成版本，随后安排索引。生成期间仍可阅读当前纪要。显示的是确认时的模板；后续任务会重新读取模板引用及运行配置，因此之后的修改可能影响结果。通常的生成、索引费用和额度限制仍然适用，包括没有个人密钥的平台付费使用。不保证最终费用。此处不显示纪要及转录全文。排队不代表生成或索引已完成。不启动录音、新转录、自动邮件或通知。",
    ),
}
