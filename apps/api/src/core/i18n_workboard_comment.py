"""Source pending-answer consequences belong in the exact comment confirmation."""

from src.core.i18n_types import Language

WORKBOARD_COMMENT_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Commentaire du ticket",
        "La confirmation publie exactement ce commentaire. Si le ticket attend une réponse, la conséquence affichée et l’aperçu de l’action en attente font partie de la confirmation : approbation = autorisation de l’action stockée et reprise par LIA ; refus = clôture ; modification = suppression de l’ancienne action et nouvelle exécution. Les exécutions ultérieures conservent les quotas et coûts habituels.",
    ),
    "en": (
        "Ticket comment",
        "Confirmation posts exactly this comment. If the ticket awaits an answer, the displayed consequence and pending-action preview are part of confirmation: approval authorizes the stored action and hands back to LIA; refusal closes it; amendment discards the old action and starts a fresh run. Later runs retain normal quotas and costs.",
    ),
    "de": (
        "Ticket-Kommentar",
        "Die Bestätigung veröffentlicht genau diesen Kommentar. Wartet das Ticket auf eine Antwort, gehören die angezeigte Folge und die Vorschau der ausstehenden Aktion zur Bestätigung: Zustimmung erlaubt die gespeicherte Aktion und übergibt an LIA; Ablehnung schließt das Ticket; Änderung verwirft die alte Aktion und erlaubt einen neuen Lauf. Spätere Läufe unterliegen den üblichen Kontingenten und Kosten.",
    ),
    "es": (
        "Comentario del ticket",
        "La confirmación publica exactamente este comentario. Si el ticket espera una respuesta, la consecuencia mostrada y la vista previa de la acción pendiente forman parte de la confirmación: aprobar autoriza la acción guardada y devuelve el ticket a LIA; rechazar lo cierra; modificar descarta la acción anterior y permite una nueva ejecución. Las ejecuciones posteriores mantienen las cuotas y costes habituales.",
    ),
    "it": (
        "Commento del ticket",
        "La conferma pubblica esattamente questo commento. Se il ticket attende una risposta, la conseguenza mostrata e l’anteprima dell’azione in sospeso fanno parte della conferma: approvare autorizza l’azione salvata e restituisce il ticket a LIA; rifiutare lo chiude; modificare elimina la vecchia azione e permette una nuova esecuzione. Le esecuzioni successive mantengono quote e costi abituali.",
    ),
    "zh-CN": (
        "工单评论",
        "确认会发布这条完整评论。若工单正在等待答复，显示的后果和待处理操作预览也属于确认内容：同意会授权已保存的操作并交回 LIA；拒绝会关闭工单；修改会放弃旧操作并允许重新执行。之后的执行仍受通常的配额和费用约束。",
    ),
}
