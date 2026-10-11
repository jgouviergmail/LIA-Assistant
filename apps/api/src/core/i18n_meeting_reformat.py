"""Consent distinguishes full in-place replacement from separate new minutes."""

MEETING_REFORMAT_COPY: dict[str, tuple[str, str]] = {
    "fr": (
        "Format du compte rendu à changer",
        "Utilise la transcription conservée avec le modèle sélectionné. Le mode replace remplace tout le compte rendu actuel, y compris les modifications manuelles, si la synthèse réussit. Le mode new crée un nouveau compte rendu distinct et conserve celui de la réunion source ; il ne recopie pas l’audio ni le coût de transcription. La destination et les instructions affichées sont celles de cette confirmation ; le traitement ultérieur relit le modèle et sa configuration, donc des changements ultérieurs peuvent l’affecter. Les coûts et quotas de synthèse/indexation s’appliquent, y compris sans clé personnelle. Aucun prix final garanti. Les textes complets du compte rendu et de la transcription ne sont pas affichés ici. Mise en attente ne signifie pas traitement ou indexation terminé. Aucun enregistrement, nouvelle transcription, courriel ou notification automatique.",
    ),
    "en": (
        "Meeting minutes format to change",
        "Use the retained transcript with the selected template. replace overwrites the entire current report, including manual edits, on successful synthesis. new creates separate new minutes and preserves the source report; it copies no audio or transcription charge. The displayed destination/instructions belong to this confirmation; the later job rereads the template/runtime configuration, so later changes may affect it. Synthesis/indexing costs and quotas apply, including platform-funded use without a personal key. No final price promised. Full report/transcript bodies are not displayed here. Queue acceptance is not processing or indexing completion. No recording, new transcription, automatic email or notification.",
    ),
    "de": (
        "Format des Besprechungsprotokolls ändern",
        "Verwendet das aufbewahrte Transkript mit der gewählten Vorlage. replace ersetzt bei erfolgreicher Synthese das gesamte aktuelle Protokoll einschließlich manueller Änderungen. new erstellt ein separates neues Protokoll und bewahrt das ursprüngliche; Audio und Transkriptionskosten werden nicht kopiert. Ziel und Anweisungen gelten bei Bestätigung; der spätere Auftrag liest Vorlage und Konfiguration erneut, sodass spätere Änderungen wirken können. Synthese-/Indexierungskosten und Kontingente gelten, auch ohne eigenen Schlüssel. Kein garantierter Endpreis. Vollständige Texte werden hier nicht angezeigt. Eingereiht bedeutet noch nicht fertig verarbeitet oder indexiert. Keine Aufnahme, neue Transkription, automatische E-Mail oder Benachrichtigung.",
    ),
    "es": (
        "Cambiar formato de las actas",
        "Usa la transcripción conservada con la plantilla elegida. replace sustituye todo el informe actual, incluidos cambios manuales, al completar la síntesis. new crea actas nuevas independientes y conserva el informe original; no copia audio ni costes de transcripción. Destino e instrucciones corresponden a esta confirmación; el trabajo posterior relee plantilla y configuración, por lo que cambios posteriores pueden afectarlo. Se aplican costes y cuotas de síntesis/indexación, incluso sin clave personal. No garantiza precio final. Aquí no se muestran los textos completos. En cola no significa procesamiento o indexación terminados. Sin grabación, nueva transcripción, correo ni notificación automática.",
    ),
    "it": (
        "Cambiare formato del verbale",
        "Usa la trascrizione conservata con il modello scelto. replace sostituisce l’intero verbale attuale, incluse modifiche manuali, se la sintesi riesce. new crea un verbale nuovo distinto e conserva quello originale; non copia audio o costi di trascrizione. Destinazione e istruzioni sono quelle della conferma; il lavoro successivo rilegge modello e configurazione, quindi modifiche successive possono influire. Si applicano costi e quote di sintesi/indicizzazione, anche senza chiave personale. Nessun prezzo finale garantito. I testi completi non sono mostrati qui. In coda non significa elaborazione o indicizzazione completata. Nessuna registrazione, nuova trascrizione, email o notifica automatica.",
    ),
    "zh-CN": (
        "更改会议纪要格式",
        "使用保留的转录文本和所选模板。replace 在生成成功后替换整个当前纪要，包括人工编辑。new 创建独立的新纪要并保留原纪要；不复制音频或转录费用。显示的是确认时的目标和指令；后续任务重新读取模板及运行配置，因此之后的修改可能影响结果。生成、索引费用和额度仍适用，包括没有个人密钥的平台付费使用。不保证最终费用。此处不显示纪要及转录全文。排队不代表处理或索引完成。不启动录音、新转录、自动邮件或通知。",
    ),
}
