"""Whole minutes email consent; SMTP success is never receipt by the recipient."""

MEETING_EMAIL_COPY: dict[str, tuple[str, str]] = {
    "fr": (
        "Compte rendu à envoyer par courriel",
        "Envoie le compte rendu actuel complet, avec son en-tête daté, à l’adresse de votre compte depuis l’expéditeur de la plateforme. Le texte complet n’est pas affiché dans cette confirmation. Vérifiez le destinataire, l’expéditeur, l’objet et la langue. Tout changement nécessite une nouvelle confirmation. Une demande distincte peut renvoyer le document. L’acceptation par le serveur mail ne prouve ni la réception ni la lecture. Si l’enregistrement de la date échoue après l’envoi, ne renvoyez pas automatiquement le courriel. Aucune nouvelle synthèse ni indexation n’est lancée.",
    ),
    "en": (
        "Meeting minutes to email",
        "Send the entire current minutes with their dated header to your account address from the platform sender. This confirmation does not show the complete body. Check recipient, sender, subject and language. Any change requires fresh confirmation. A separate request can resend the document. Mail-server acknowledgment proves neither recipient delivery nor reading. If saving the send date fails after sending, never resend automatically. No new synthesis or indexing is launched.",
    ),
    "de": (
        "Protokoll per E-Mail senden",
        "Sendet das gesamte aktuelle Protokoll mit datiertem Kopf an deine Kontoadresse vom Plattformabsender. Diese Bestätigung zeigt nicht den vollständigen Text. Prüfe Empfänger, Absender, Betreff und Sprache. Änderungen erfordern neue Zustimmung. Ein neuer Auftrag kann das Dokument erneut senden. Die Bestätigung des Mailservers beweist weder Zustellung noch Lesen. Scheitert danach das Speichern des Versanddatums, niemals automatisch erneut senden. Keine neue Zusammenfassung oder Indexierung startet.",
    ),
    "es": (
        "Actas para enviar por correo",
        "Envía todas las actas actuales con su encabezado fechado a la dirección de tu cuenta desde el remitente de la plataforma. Esta confirmación no muestra el texto completo. Revisa destinatario, remitente, asunto e idioma. Los cambios requieren nueva confirmación. Una solicitud distinta puede reenviar el documento. La aceptación del servidor no demuestra recepción ni lectura. Si después falla el registro de la fecha, nunca reenvíes automáticamente. No inicia nueva síntesis ni indexación.",
    ),
    "it": (
        "Verbale da inviare per email",
        "Invia l’intero verbale attuale con intestazione datata all’indirizzo del tuo account dal mittente della piattaforma. La conferma non mostra il testo completo. Verifica destinatario, mittente, oggetto e lingua. Ogni modifica richiede una nuova conferma. Una richiesta distinta può reinviare il documento. L’accettazione del server non prova ricezione né lettura. Se poi non viene salvata la data di invio, non reinviare automaticamente. Nessuna nuova sintesi o indicizzazione viene avviata.",
    ),
    "zh-CN": (
        "待发送的会议纪要",
        "使用平台发件人向你的账户邮箱发送当前完整会议纪要及日期页眉。本次确认不显示全文。请核对收件人、发件人、主题和语言。任何变更都需要重新确认。新的独立请求可以再次发送。邮件服务器接受邮件并不证明收件人已收到或阅读。发送后若保存发送日期失败，切勿自动重发。不会启动新的纪要生成或索引。",
    ),
}
