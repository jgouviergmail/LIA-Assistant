"""Consent names literal envelope, complete attachment and acknowledged versus delivered outcome."""

from src.core.i18n_types import Language

EMAIL_SHARE_SEND_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "E-mail à envoyer",
        "Vérifiez les destinataires, le canal d’envoi, l’objet, le message et le fichier complet. Les réponses sont exportées intégralement avec leur demande en Markdown ; les extraits ne limitent pas la pièce jointe. Un changement impose une nouvelle confirmation. L’accusé du fournisseur confirme l’envoi, pas la réception par le destinataire. Un résultat incertain ne sera pas relancé automatiquement.",
    ),
    "en": (
        "Email to send",
        "Check recipients, sending route, subject, message and complete attachment. Answers export their complete request and answer as Markdown; excerpts never truncate the attachment. Changes require new confirmation. Provider acknowledgement confirms sending, not recipient delivery. Uncertain results are never automatically replayed.",
    ),
    "de": (
        "Zu sendende E-Mail",
        "Prüfen Sie Empfänger, Versandweg, Betreff, Nachricht und vollständigen Anhang. Antworten werden mit ihrer vollständigen Anfrage als Markdown exportiert; Auszüge kürzen den Anhang nicht. Änderungen erfordern eine neue Bestätigung. Die Bestätigung des Anbieters bestätigt den Versand, nicht die Zustellung. Ungewisse Ergebnisse werden nicht automatisch wiederholt.",
    ),
    "es": (
        "Correo para enviar",
        "Compruebe destinatarios, canal, asunto, mensaje y archivo completo. Las respuestas y sus solicitudes se exportan completas en Markdown; los extractos no recortan el adjunto. Los cambios requieren nueva confirmación. La confirmación del proveedor acredita el envío, no la entrega al destinatario. Los resultados inciertos no se repiten automáticamente.",
    ),
    "it": (
        "E-mail da inviare",
        "Verifica destinatari, canale, oggetto, messaggio e allegato completo. Le risposte e le relative richieste vengono esportate integralmente in Markdown; gli estratti non limitano l’allegato. Le modifiche richiedono una nuova conferma. La conferma del fornitore attesta l’invio, non la consegna. I risultati incerti non vengono ripetuti automaticamente.",
    ),
    "zh-CN": (
        "待发送的电子邮件",
        "请检查收件人、发送渠道、主题、正文和完整附件。回答及其原始请求将完整导出为 Markdown，摘录不会截断附件。任何变化都需要重新确认。服务商确认仅表示已发送，不证明收件人已收到。不确定的结果不会自动重试。",
    ),
}
