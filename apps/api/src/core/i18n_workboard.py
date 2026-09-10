"""Central i18n for what a workboard run writes on a ticket (ADR-276).

A run that stops leaves a COMMENT, and a comment is read by a person — so it
belongs here rather than in the runner, in all six languages, keyed by the
backend-canonical code (``zh-CN``). Nothing in this module is prose to
personalise: a stopped run is a fact, and asking a model to phrase it would
spend tokens to make it less exact.

What is deliberately NOT here:

- **the answer of a successful run.** That is the model's own text, in the
  person's language already, filed verbatim.
- **the message of a failed run.** ``last_run_error`` stores a typed CODE and a
  bounded technical message; the board resolves the code from the frontend
  locales, the way every other refusal on this surface does — a translated
  sentence in a payload would be right in one language and wrong in five.

Data module (like the other ``core/i18n_*``): no domain imports, exempt from
the size ratchet.
"""

from __future__ import annotations

from src.core.i18n import normalize_language

_DEFAULT = "en"

#: A capability the gate refused because nobody was there to allow it. The
#: sentence names what is pending and says what happens next, because the
#: person reads it on the ticket with no other context.
_WAITING_FOR_CAPABILITY: dict[str, str] = {
    "en": (
        "I stopped here: « {capability} » needs your go-ahead before I act, "
        "and nobody was there to give it. Tell me to carry on and I will finish."
    ),
    "fr": (
        "Je me suis arrêtée ici : « {capability} » demande ton accord avant "
        "d'agir, et personne n'était là pour le donner. Dis-moi de continuer et "
        "je termine."
    ),
    "de": (
        "Ich habe hier angehalten: « {capability} » braucht deine Zustimmung, "
        "bevor ich handle, und niemand war da, um sie zu geben. Sag mir, dass "
        "ich weitermachen soll, und ich bringe es zu Ende."
    ),
    "es": (
        "Me he detenido aquí: « {capability} » necesita tu visto bueno antes de "
        "actuar, y no había nadie para darlo. Dime que siga y lo termino."
    ),
    "it": (
        "Mi sono fermata qui: « {capability} » ha bisogno del tuo consenso "
        "prima di agire, e non c'era nessuno a darlo. Dimmi di continuare e lo "
        "porto a termine."
    ),
    "zh-CN": (
        "我在这里停下了：「{capability}」需要你同意后才能执行，"
        "而当时没有人可以确认。告诉我继续，我就把它做完。"
    ),
}

#: The same stop, with nothing to name: a clarification the turn asked for.
#: The safety net of D5 — the gate refuses first, but a question can still
#: arise, and a comment saying « something » is better than none.
_WAITING_FOR_YOU: dict[str, str] = {
    "en": "I stopped here: I need something from you before I can go on.",
    "fr": "Je me suis arrêtée ici : j'ai besoin de toi pour aller plus loin.",
    "de": "Ich habe hier angehalten: Ich brauche etwas von dir, um weiterzumachen.",
    "es": "Me he detenido aquí: necesito algo de tu parte para poder continuar.",
    "it": "Mi sono fermata qui: ho bisogno di te per andare avanti.",
    "zh-CN": "我在这里停下了：需要你的确认才能继续。",
}

#: What the person's chat turn says when they follow a stopped run's link
#: (ADR-173's ``?intent=``). It is THEIR instruction to their own assistant, in
#: an ATTENDED turn — so the confirmation the sweep could not obtain is asked
#: for properly, as a card. The ticket is named by title AND by id: a board can
#: hold two tickets called « Relancer le fournisseur », and a turn acting on the
#: wrong one is worse than a turn that asks which.
#:
#: The sentence asks for the COMMENT and the MOVE since lot 3 — and not
#: before. Asking for an action LIA could not perform would have produced a
#: promise it could not keep (ADR-182), which is exactly why lot 2 stopped at
#: « dis-moi où ça en est ».
_FINISH_IN_CHAT: dict[str, str] = {
    "en": (
        "Take up the ticket “{title}” (id {ticket_id}) again: do the action that "
        "was waiting for my agreement, then comment the result on the ticket and "
        "move it to the right column."
    ),
    "fr": (
        "Reprends le ticket « {title} » (id {ticket_id}) : fais l'action qui "
        "attendait mon accord, puis commente le résultat sur le ticket et "
        "déplace-le dans la bonne colonne."
    ),
    "de": (
        "Nimm das Ticket „{title}“ (id {ticket_id}) wieder auf: führe die Aktion "
        "aus, die auf meine Zustimmung wartete, kommentiere dann das Ergebnis am "
        "Ticket und verschiebe es in die richtige Spalte."
    ),
    "es": (
        "Retoma el ticket «{title}» (id {ticket_id}): haz la acción que esperaba "
        "mi visto bueno, comenta el resultado en el ticket y muévelo a la columna "
        "correcta."
    ),
    "it": (
        "Riprendi il ticket «{title}» (id {ticket_id}): esegui l'azione che "
        "aspettava il mio consenso, poi commenta il risultato sul ticket e "
        "spostalo nella colonna giusta."
    ),
    "zh-CN": (
        "继续处理工单“{title}”（id {ticket_id}）：执行等待我同意的那一步，"
        "然后在工单上评论结果，并把它移到正确的列。"
    ),
}


#: How to answer a confirmation LIA put on the ticket (lot 7). The comment IS
#: the answer since 2026-09-09: asking for the ticket back as well was a second
#: gesture for one decision, and a ticket left « à confirmer » with the answer
#: already written on it is the exact shape of work that never moves.
_HOW_TO_ANSWER: dict[str, str] = {
    "en": (
        "Answer with a comment and I take it from there: « yes » and I do it, "
        "« no » and I drop it, or tell me what to change."
    ),
    "fr": (
        "Réponds par un commentaire et je m'en occupe : « oui » et je le fais, "
        "« non » et j'abandonne, ou dis-moi ce qu'il faut changer."
    ),
    "de": (
        "Antworte mit einem Kommentar, den Rest übernehme ich: « ja » und ich "
        "mache es, « nein » und ich lasse es, oder sag mir, was zu ändern ist."
    ),
    "es": (
        "Responde con un comentario y yo me encargo: « sí » y lo hago, « no » y "
        "lo dejo, o dime qué cambiar."
    ),
    "it": (
        "Rispondi con un commento e ci penso io: « sì » e lo faccio, « no » e "
        "lascio perdere, oppure dimmi cosa cambiare."
    ),
    "zh-CN": "用评论回复即可，剩下的交给我：「是」我就执行，「否」我就放弃，或者告诉我要改什么。",
}

#: The bare approvals, in the six languages. Matched on the WHOLE answer once
#: folded (``domains/workboard/answers.py``): « oui mais… » is never here.
ANSWER_APPROVAL_PHRASES: frozenset[str] = frozenset(
    {
        # fr
        "oui",
        "ok",
        "okay",
        "d'accord",
        "dac",
        "vas-y",
        "allez-y",
        "go",
        "confirme",
        "confirmé",
        "je confirme",
        "c'est bon",
        "c'est ok",
        "valide",
        "validé",
        "je valide",
        "approuvé",
        "j'approuve",
        "fais-le",
        "envoie",
        "envoie-le",
        "oui vas-y",
        "oui d'accord",
        "ok vas-y",
        "oui ok",
        "ok oui",
        "parfait",
        "très bien",
        "ça marche",
        "bien sûr",
        # en
        "yes",
        "yep",
        "yeah",
        "sure",
        "fine",
        "confirm",
        "confirmed",
        "i confirm",
        "approve",
        "approved",
        "i approve",
        "go ahead",
        "do it",
        "proceed",
        "send it",
        "yes go ahead",
        "yes do it",
        "ok go ahead",
        "all good",
        "sounds good",
        "looks good",
        "lgtm",
        "of course",
        # de
        "ja",
        "jawohl",
        "einverstanden",
        "bestätigt",
        "ich bestätige",
        "mach das",
        "mach es",
        "los",
        "weiter",
        "in ordnung",
        "passt",
        "ja mach das",
        "ja bitte",
        "genehmigt",
        # es
        "sí",
        "vale",
        "adelante",
        "confirmo",
        "confirmado",
        "de acuerdo",
        "hazlo",
        "procede",
        "sí adelante",
        "está bien",
        "perfecto",
        "aprobado",
        # it
        "sì",
        "va bene",
        "vai",
        "confermo",
        "confermato",
        "d'accordo",
        "procedi",
        "fallo",
        "sì vai",
        "perfetto",
        "approvato",
        # zh
        "是",
        "是的",
        "好",
        "好的",
        "可以",
        "行",
        "确认",
        "同意",
        "继续",
        "没问题",
        "执行",
        "做吧",
        "去吧",
        "好的谢谢",
    }
)

#: The bare refusals. « Non, envoie plutôt à Paul » is an amendment, not one
#: of these: the answer must be nothing but a refusal.
ANSWER_REFUSAL_PHRASES: frozenset[str] = frozenset(
    {
        # fr
        "non",
        "nan",
        "annule",
        "annuler",
        "annulé",
        "annule tout",
        "laisse tomber",
        "laisse",
        "stop",
        "arrête",
        "refusé",
        "je refuse",
        "pas d'accord",
        "surtout pas",
        "abandonne",
        "non merci",
        "pas maintenant",
        # en
        "no",
        "nope",
        "nah",
        "cancel",
        "cancelled",
        "canceled",
        "cancel it",
        "don't",
        "do not",
        "dont",
        "abort",
        "refuse",
        "refused",
        "declined",
        "never mind",
        "nevermind",
        "forget it",
        "drop it",
        "no thanks",
        "not now",
        # de
        "nein",
        "nee",
        "abbrechen",
        "abbruch",
        "abgebrochen",
        "stopp",
        "nicht",
        "lass es",
        "lass das",
        "vergiss es",
        "nein danke",
        "auf keinen fall",
        # es
        "cancela",
        "cancelar",
        "cancelado",
        "para",
        "detente",
        "no lo hagas",
        "déjalo",
        "olvídalo",
        "no gracias",
        # it
        "annulla",
        "annullato",
        "annullare",
        "ferma",
        "fermati",
        "lascia perdere",
        "lascia stare",
        "non farlo",
        "no grazie",
        # zh
        "不",
        "不要",
        "不行",
        "取消",
        "停止",
        "别",
        "算了",
        "不用了",
        "不同意",
    }
)

#: Politeness an answer may carry without changing what it says.
ANSWER_POLITE_WORDS: frozenset[str] = frozenset(
    {
        "merci",
        "stp",
        "svp",
        "thanks",
        "thank",
        "you",
        "please",
        "pls",
        "danke",
        "bitte",
        "gracias",
        "por favor",
        "grazie",
        "prego",
        "谢谢",
        "请",
    }
)

#: The small words a bare answer leans on (« annule tout », « cancel it »).
ANSWER_FILLER_WORDS: frozenset[str] = frozenset(
    {
        "ça",
        "cela",
        "tout",
        "le",
        "la",
        "les",
        "it",
        "this",
        "that",
        "das",
        "es",
        "lo",
        "eso",
        "esto",
        "quello",
        "questo",
        "它",
        "这个",
    }
)


class WorkboardMessages:
    """Factory for the sentences a run leaves on a ticket, six languages."""

    @staticmethod
    def confirming(language: str, *, question: str) -> str:
        """What a run writes when it built an action the person must confirm.

        Args:
            language: Any locale spelling; normalised here.
            question: What LIA asked in the chat — the card and the question,
                one stream since lot 14, in the person's language already.

        Returns:
            The comment body: the question, then how to answer.
        """
        code = normalize_language(language)
        sentence = _HOW_TO_ANSWER.get(code, _HOW_TO_ANSWER[_DEFAULT])
        return "\n\n".join(part for part in (question.strip(), sentence) if part)

    @staticmethod
    def waiting(language: str, capability: str | None = None) -> str:
        """What a run writes when it stopped and needs the person.

        Args:
            language: Any locale spelling; normalised here, the single entry
                point for raw codes.
            capability: The capability the gate refused, already rendered for a
                reader. None when the turn asked a question instead — the
                sentence then names no capability rather than inventing one.

        Returns:
            The comment body, in the reader's language.
        """
        code = normalize_language(language)
        if capability:
            table = _WAITING_FOR_CAPABILITY
            return table.get(code, table[_DEFAULT]).format(capability=capability)
        return _WAITING_FOR_YOU.get(code, _WAITING_FOR_YOU[_DEFAULT])

    @staticmethod
    def finish_in_chat(title: str, ticket_id: str, language: str) -> str:
        """The instruction a stopped ticket's chat link carries.

        Args:
            title: The ticket's own title.
            ticket_id: Its id, because a board may hold two tickets with the
                same title and the wrong one is worse than a question.
            language: Any locale spelling; normalised here.

        Returns:
            The sentence, in the reader's language.
        """
        code = normalize_language(language)
        template = _FINISH_IN_CHAT.get(code, _FINISH_IN_CHAT[_DEFAULT])
        # The title is a VALUE: « Payer {montant} » must not raise.
        return template.format(title=title, ticket_id=ticket_id)


__all__ = [
    "ANSWER_APPROVAL_PHRASES",
    "ANSWER_FILLER_WORDS",
    "ANSWER_POLITE_WORDS",
    "ANSWER_REFUSAL_PHRASES",
    "WorkboardMessages",
]
