"""Source update consequences and future LIA work are explicit in every confirmation."""

from src.core.i18n_types import Language

WORKBOARD_UPDATE_COPY: dict[Language, tuple[str, str]] = {
    "fr": (
        "Modification du ticket",
        "La confirmation applique la modification et ses conséquences affichées. Une réponse à une action en attente peut l’approuver, la refuser ou demander une nouvelle exécution. Affecter le ticket à LIA ou demander son lancement autorise du travail ultérieur soumis aux quotas et coûts habituels ; cela ne prouve pas que l’exécution est terminée. Une affectation à une autre personne est notifiée après sauvegarde.",
    ),
    "en": (
        "Ticket change",
        "Confirmation applies the displayed change and its consequences. Answering a pending action may approve it, refuse it or request a new run. Assigning to LIA or requesting a run allows later work under the usual quotas and costs; it does not prove that execution has finished. Assignment to another person is notified after saving.",
    ),
    "de": (
        "Ticketänderung",
        "Die Bestätigung übernimmt die angezeigte Änderung und ihre Folgen. Eine Antwort auf eine ausstehende Aktion kann sie genehmigen, ablehnen oder einen neuen Lauf anfordern. Zuweisung an LIA oder Startanforderung erlaubt spätere Arbeit unter den üblichen Kontingenten und Kosten; sie bestätigt keinen abgeschlossenen Lauf. Die neue Person wird erst nach dem Speichern benachrichtigt.",
    ),
    "es": (
        "Cambio del ticket",
        "La confirmación aplica el cambio mostrado y sus consecuencias. Responder a una acción pendiente puede aprobarla, rechazarla o solicitar otra ejecución. Asignar a LIA o solicitar una ejecución permite trabajo posterior sujeto a las cuotas y costes habituales; no confirma que haya terminado. La asignación a otra persona se notifica después de guardar.",
    ),
    "it": (
        "Modifica del ticket",
        "La conferma applica la modifica mostrata e le sue conseguenze. Rispondere a un’azione in attesa può approvarla, rifiutarla o richiedere una nuova esecuzione. Assegnare a LIA o richiedere l’avvio autorizza lavoro successivo soggetto alle quote e ai costi abituali; non conferma il completamento. L’assegnazione a un’altra persona viene notificata dopo il salvataggio.",
    ),
    "zh-CN": (
        "工单修改",
        "确认会应用展示的修改及其后果。对待确认操作的回答可能批准、拒绝该操作或要求重新执行。分配给 LIA 或请求启动会允许后续工作，并适用通常的配额和费用；这不表示执行已经完成。分配给其他人的通知将在保存后发送。",
    ),
}
