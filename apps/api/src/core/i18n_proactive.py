"""Centralized i18n for proactive notification surface strings (ADR-131).

Replaces the inline titles table that lived in
infrastructure/proactive/notification.py — which was keyed "zh" while
User.language is backend-canonical "zh-CN", silently sending English
titles to Chinese users.

Supported languages: fr, en, es, de, it, zh-CN (systemic i18n rule).
"""


class ProactiveMessages:
    """Factory for proactive notification strings, 6 languages.

    Same pattern as APIMessages: dict-based translations keyed by the
    backend-canonical language code, English fallback.
    """

    _TITLES: dict[str, dict[str, str]] = {
        "interest": {
            "fr": "Pour toi",
            "en": "For you",
            "es": "Para ti",
            "de": "Für dich",
            "it": "Per te",
            "zh-CN": "为你推荐",
        },
        "birthday": {
            "fr": "Anniversaire",
            "en": "Birthday",
            "es": "Cumpleaños",
            "de": "Geburtstag",
            "it": "Compleanno",
            "zh-CN": "生日",
        },
        "event": {
            "fr": "Événement",
            "en": "Event",
            "es": "Evento",
            "de": "Ereignis",
            "it": "Evento",
            "zh-CN": "活动",
        },
        "summary": {
            "fr": "Résumé",
            "en": "Summary",
            "es": "Resumen",
            "de": "Zusammenfassung",
            "it": "Riepilogo",
            "zh-CN": "摘要",
        },
        "heartbeat": {
            "fr": "Notification proactive",
            "en": "Proactive notification",
            "es": "Notificación proactiva",
            "de": "Proaktive Benachrichtigung",
            "it": "Notifica proattiva",
            "zh-CN": "主动通知",
        },
        # Meeting minutes ready (ADR-258) — the dispatcher receives an explicit
        # title from core.i18n_meetings; this entry keeps the task type known here.
        "meeting": {
            "fr": "Compte rendu de réunion",
            "en": "Meeting minutes",
            "es": "Acta de la reunión",
            "de": "Besprechungsprotokoll",
            "it": "Verbale della riunione",
            "zh-CN": "会议纪要",
        },
        # Used by the scheduled-action executor, which kept its own inline
        # table keyed "zh" — reproducing here the exact bug this module was
        # created to fix (User.language is backend-canonical "zh-CN", so
        # Chinese users silently received the English title).
        "scheduled_action": {
            "fr": "Action planifiée",
            "en": "Scheduled action",
            "es": "Acción programada",
            "de": "Geplante Aktion",
            "it": "Azione pianificata",
            "zh-CN": "计划操作",
        },
        # Used by the reminder scheduler, which kept its OWN inline table keyed
        # "zh" — the third occurrence of the very bug this module exists for.
        # It sends both the FCM title and the external-channel title, so a
        # Chinese user was getting "Reminder" in English on every reminder.
        "reminder": {
            "fr": "Rappel",
            "en": "Reminder",
            "es": "Recordatorio",
            "de": "Erinnerung",
            "it": "Promemoria",
            "zh-CN": "提醒",
        },
        # Peers program (Lot 3): incoming connection requests…
        "peer_request": {
            "fr": "Demande de connexion",
            "en": "Connection request",
            "es": "Solicitud de conexión",
            "de": "Verbindungsanfrage",
            "it": "Richiesta di connessione",
            "zh-CN": "连接请求",
        },
        # Relayed peer messages (Lot 4): the recipient's assistant delivers
        # the message under this title, named after the sender at call time.
        "peer_message": {
            "fr": "Message d'un contact",
            "en": "Message from a contact",
            "es": "Mensaje de un contacto",
            "de": "Nachricht von einem Kontakt",
            "it": "Messaggio da un contatto",
            "zh-CN": "来自联系人的消息",
        },
        # …and every other connection-lifecycle update (accepted, declined,
        # removed) rides this one.
        "peer_connection": {
            "fr": "Connexions",
            "en": "Connections",
            "es": "Conexiones",
            "de": "Verbindungen",
            "it": "Connessioni",
            "zh-CN": "用户互联",
        },
        # The workboard (ADR-276). ONE title for every ticket event: a person
        # reading their notifications recognises the surface, and the body says
        # which ticket and what happened.
        "workboard": {
            "fr": "Tableau de bord",
            "en": "Workboard",
            "es": "Tablero de trabajo",
            "de": "Aufgabenboard",
            "it": "Bacheca",
            "zh-CN": "工单板",
        },
    }

    _SOURCES_LABEL: dict[str, str] = {
        "fr": "Sources",
        "en": "Sources",
        "es": "Fuentes",
        "de": "Quellen",
        "it": "Fonti",
        "zh-CN": "来源",
    }

    # N-07 propose-first mode: the tick notifies instead of executing; the
    # markdown link carries the routine's prompt as a chat ?intent= (ADR-173),
    # so the actual run flows through the normal pipeline + HITL.
    # Peers program (Lot 3): connection-lifecycle chat bodies. The requester's
    # note is rendered as QUOTED PLAIN TEXT (third-party content — provenance
    # doctrine, never instructions). Links target the settings deep link; the
    # `?intent=` accept/refuse upgrade ships with the agents lot.
    _PEER_REQUEST_BODIES: dict[str, str] = {
        "fr": "{name} souhaite se connecter avec toi.{note} [Voir la demande]({url})",
        "en": "{name} would like to connect with you.{note} [View the request]({url})",
        "es": "{name} quiere conectar contigo.{note} [Ver la solicitud]({url})",
        "de": "{name} möchte sich mit dir verbinden.{note} [Anfrage ansehen]({url})",
        "it": "{name} vuole connettersi con te.{note} [Vedi la richiesta]({url})",
        "zh-CN": "{name} 希望与你建立连接。{note}[查看请求]({url})",
    }
    _PEER_REQUEST_NOTE: dict[str, str] = {
        "fr": " Son message : « {note} »",
        "en": " Their note: “{note}”",
        "es": " Su mensaje: «{note}»",
        "de": " Ihre Notiz: „{note}“",
        "it": " Il suo messaggio: «{note}»",
        "zh-CN": " 对方留言：“{note}”",
    }
    _PEER_ACCEPTED_BODIES: dict[str, str] = {
        "fr": "{name} a accepté ta demande de connexion. Tu peux maintenant gérer vos partages. [Ouvrir les connexions]({url})",
        "en": "{name} accepted your connection request. You can now manage what you share. [Open connections]({url})",
        "es": "{name} aceptó tu solicitud de conexión. Ya puedes gestionar lo que compartís. [Abrir conexiones]({url})",
        "de": "{name} hat deine Verbindungsanfrage angenommen. Du kannst jetzt eure Freigaben verwalten. [Verbindungen öffnen]({url})",
        "it": "{name} ha accettato la tua richiesta di connessione. Ora puoi gestire le condivisioni. [Apri le connessioni]({url})",
        "zh-CN": "{name} 已接受你的连接请求。现在可以管理你们的共享了。[打开连接]({url})",
    }
    _PEER_DECLINED_BODIES: dict[str, str] = {
        "fr": "{name} n'a pas accepté ta demande de connexion.",
        "en": "{name} did not accept your connection request.",
        "es": "{name} no aceptó tu solicitud de conexión.",
        "de": "{name} hat deine Verbindungsanfrage nicht angenommen.",
        "it": "{name} non ha accettato la tua richiesta di connessione.",
        "zh-CN": "{name} 没有接受你的连接请求。",
    }
    _PEER_REMOVED_BODIES: dict[str, str] = {
        "fr": "Ta connexion avec {name} a été supprimée. Tous les partages entre vous ont cessé.",
        "en": "Your connection with {name} has been removed. All sharing between you has stopped.",
        "es": "Tu conexión con {name} se ha eliminado. Todo lo compartido entre vosotros ha cesado.",
        "de": "Deine Verbindung mit {name} wurde entfernt. Alle Freigaben zwischen euch wurden beendet.",
        "it": "La tua connessione con {name} è stata rimossa. Tutte le condivisioni tra voi sono cessate.",
        "zh-CN": "你与 {name} 的连接已被移除。你们之间的所有共享均已停止。",
    }

    #: What came back when the pair ended (ADR-276 lot 5), appended to the
    #: removal sentence above. Two tables rather than one templated string: a
    #: « 1 tickets » is the kind of seam a reader notices immediately, and zh
    #: has no plural form so both of its entries are the same sentence.
    _PEER_REMOVED_RELEASED_ONE: dict[str, str] = {
        "fr": " {count} ticket du tableau vous est revenu.",
        "en": " {count} workboard ticket has come back to you.",
        "es": " {count} ticket del tablero ha vuelto a ti.",
        "de": " {count} Workboard-Ticket ist an dich zurückgegangen.",
        "it": " {count} ticket della bacheca è tornato a te.",
        "zh-CN": "{count} 个工单已回到你手中。",
    }

    _PEER_REMOVED_RELEASED_MANY: dict[str, str] = {
        "fr": " {count} tickets du tableau vous sont revenus.",
        "en": " {count} workboard tickets have come back to you.",
        "es": " {count} tickets del tablero han vuelto a ti.",
        "de": " {count} Workboard-Tickets sind an dich zurückgegangen.",
        "it": " {count} ticket della bacheca sono tornati a te.",
        "zh-CN": "{count} 个工单已回到你手中。",
    }

    # Lot 4: sender-side confirmations for relayed messages.
    _PEER_MESSAGE_DELIVERED_BODIES: dict[str, str] = {
        "fr": "Ton message pour {name} a bien été transmis par son assistant.",
        "en": "Your message for {name} has been delivered by their assistant.",
        "es": "Tu mensaje para {name} ha sido entregado por su asistente.",
        "de": "Deine Nachricht an {name} wurde von ihrem Assistenten übermittelt.",
        "it": "Il tuo messaggio per {name} è stato consegnato dal suo assistente.",
        "zh-CN": "你发给 {name} 的消息已由对方的助手转达。",
    }
    _PEER_MESSAGE_FAILED_BODIES: dict[str, str] = {
        "fr": "Ton message pour {name} n'a pas pu être transmis. Tu peux réessayer plus tard.",
        "en": "Your message for {name} could not be delivered. You can try again later.",
        "es": "Tu mensaje para {name} no pudo entregarse. Puedes intentarlo más tarde.",
        "de": "Deine Nachricht an {name} konnte nicht übermittelt werden. Versuche es später erneut.",
        "it": "Il tuo messaggio per {name} non è stato consegnato. Riprova più tardi.",
        "zh-CN": "你发给 {name} 的消息未能送达。请稍后重试。",
    }

    #: What a workboard notification says, per event (ADR-276). Written
    #: sentences, never a model call: a notification about a ticket is a fact,
    #: and paying for prose to say « LIA a terminé ce ticket » would be worse
    #: than saying it plainly. Six languages, like everything a reader sees.
    _WORKBOARD_BODIES: dict[str, dict[str, str]] = {
        "run_started": {
            "fr": "LIA a commencé « {title} ».",
            "en": "LIA has started “{title}”.",
            "es": "LIA ha empezado «{title}».",
            "de": "LIA hat „{title}“ begonnen.",
            "it": "LIA ha iniziato «{title}».",
            "zh-CN": "LIA 已开始处理“{title}”。",
        },
        "run_finished": {
            "fr": "LIA a terminé « {title} » : {excerpt}",
            "en": "LIA has finished “{title}”: {excerpt}",
            "es": "LIA ha terminado «{title}»: {excerpt}",
            "de": "LIA hat „{title}“ abgeschlossen: {excerpt}",
            "it": "LIA ha terminato «{title}»: {excerpt}",
            "zh-CN": "LIA 已完成“{title}”：{excerpt}",
        },
        "run_failed": {
            "fr": "LIA n'a pas pu terminer « {title} ». Le ticket reste en cours.",
            "en": "LIA could not finish “{title}”. The ticket stays in progress.",
            "es": "LIA no ha podido terminar «{title}». El ticket sigue en curso.",
            "de": "LIA konnte „{title}“ nicht abschließen. Das Ticket bleibt in Arbeit.",
            "it": "LIA non è riuscita a completare «{title}». Il ticket resta in corso.",
            "zh-CN": "LIA 未能完成“{title}”。该工单仍在进行中。",
        },
        "assigned": {
            "fr": "Un ticket t'a été confié : « {title} ».",
            "en": "A ticket has been handed to you: “{title}”.",
            "es": "Te han asignado un ticket: «{title}».",
            "de": "Dir wurde ein Ticket übergeben: „{title}“.",
            "it": "Ti è stato affidato un ticket: «{title}».",
            "zh-CN": "有一个工单交给你了：“{title}”。",
        },
        "confirming": {
            "fr": (
                "« {title} » attend ton accord : LIA a préparé une action et te la "
                "présente sur le ticket. [Répondre sur le ticket]({ticket_url})"
            ),
            "en": (
                "“{title}” is waiting for your go-ahead: LIA prepared an action and "
                "laid it out on the ticket. [Answer on the ticket]({ticket_url})"
            ),
            "es": (
                "«{title}» espera tu visto bueno: LIA ha preparado una acción y te la "
                "presenta en el ticket. [Responder en el ticket]({ticket_url})"
            ),
            "de": (
                "„{title}“ wartet auf dein Okay: LIA hat eine Aktion vorbereitet und "
                "sie im Ticket dargelegt. [Im Ticket antworten]({ticket_url})"
            ),
            "it": (
                "«{title}» aspetta il tuo via libera: LIA ha preparato un'azione e te "
                "la presenta sul ticket. [Rispondi sul ticket]({ticket_url})"
            ),
            "zh-CN": (
                "“{title}”正在等你的确认：LIA 准备了一项操作，已在工单上列出。"
                "[在工单上回复]({ticket_url})"
            ),
        },
        "waiting": {
            "fr": "« {title} » attend ta réponse. [Terminer dans le chat]({intent_url})",
            "en": "“{title}” is waiting for you. [Finish it in the chat]({intent_url})",
            "es": "«{title}» te está esperando. [Terminarlo en el chat]({intent_url})",
            "de": "„{title}“ wartet auf dich. [Im Chat abschließen]({intent_url})",
            "it": "«{title}» sta aspettando te. [Concludilo nella chat]({intent_url})",
            "zh-CN": "“{title}”正在等你。[在对话中完成]({intent_url})",
        },
    }

    _ROUTINE_APPROVAL_BODIES: dict[str, str] = {
        "fr": "Ta routine « {title} » est prête à s'exécuter. [Lancer maintenant]({intent_url})",
        "en": "Your routine “{title}” is ready to run. [Run it now]({intent_url})",
        "es": "Tu rutina «{title}» está lista para ejecutarse. [Ejecutarla ahora]({intent_url})",
        "de": "Deine Routine „{title}“ ist bereit zur Ausführung. [Jetzt ausführen]({intent_url})",
        "it": "La tua routine «{title}» è pronta per essere eseguita. [Eseguila ora]({intent_url})",
        "zh-CN": "您的例行任务“{title}”已准备好执行。[立即执行]({intent_url})",
    }

    @staticmethod
    def notification_title(task_type: str, language: str) -> str:
        """Localized push/chat title for a proactive task type.

        The code is normalized through the single chokepoint before keying the
        table: callers hold raw locales of every spelling (``zh`` from the
        frontend, ``fr-FR`` from a header, ``zh_CN`` from a legacy row), and
        keying on a raw locale is precisely the defect this module was created
        to fix. Normalizing here makes every call site safe by construction
        rather than by discipline.

        Args:
            task_type: Proactive task type (interest, birthday, ...).
            language: Any locale spelling; normalized internally.

        Returns:
            The localized title; English fallback per task type, then a
            generic "Notification" for unknown task types.
        """
        from src.core.i18n import normalize_language

        task_titles = ProactiveMessages._TITLES.get(task_type, {})
        return task_titles.get(normalize_language(language), task_titles.get("en", "Notification"))

    #: What a reminder says when the model could not compose its message.
    #:
    #: This is the NOTIFICATION BODY, not prompt scaffolding: it reaches the
    #: reader verbatim. It was `if language == "fr": ... else: <English>`, so
    #: four readers out of six were told "It's time!" in a language they may
    #: not read — and precisely on the path where something had already gone
    #: wrong.
    _REMINDER_FALLBACKS: dict[str, str] = {
        "fr": "C'est l'heure ! Rappel ({stamp}) : {content}",
        "en": "It's time! Reminder ({stamp}): {content}",
        "es": "¡Es la hora! Recordatorio ({stamp}): {content}",
        "de": "Es ist so weit! Erinnerung ({stamp}): {content}",
        "it": "È ora! Promemoria ({stamp}): {content}",
        "zh-CN": "时间到了！提醒（{stamp}）：{content}",
    }

    #: The header introducing recalled memories inside the reminder prompt.
    _MEMORY_HEADERS: dict[str, str] = {
        "fr": "MÉMOIRES PERTINENTES :",
        "en": "RELEVANT MEMORIES:",
        "es": "RECUERDOS RELEVANTES:",
        "de": "RELEVANTE ERINNERUNGEN:",
        "it": "RICORDI RILEVANTI:",
        "zh-CN": "相关记忆：",
    }

    @staticmethod
    def reminder_fallback_body(stamp: str, content: str, language: str) -> str:
        """The reminder message to send when generation failed.

        Args:
            stamp: Localized "asked on ..." fragment.
            content: What the reader asked to be reminded of.
            language: Any locale spelling; normalized internally.

        Returns:
            The localized body (English fallback).
        """
        from src.core.i18n import normalize_language

        template = ProactiveMessages._REMINDER_FALLBACKS.get(
            normalize_language(language), ProactiveMessages._REMINDER_FALLBACKS["en"]
        )
        return template.format(stamp=stamp, content=content)

    @staticmethod
    def reminder_memory_header(language: str) -> str:
        """The header the reminder prompt puts above recalled memories.

        Args:
            language: Any locale spelling; normalized internally.

        Returns:
            The localized header (English fallback).
        """
        from src.core.i18n import normalize_language

        return ProactiveMessages._MEMORY_HEADERS.get(
            normalize_language(language), ProactiveMessages._MEMORY_HEADERS["en"]
        )

    @staticmethod
    def routine_approval_body(title: str, intent_url: str, language: str) -> str:
        """Localized propose-first body for a routine awaiting approval (N-07).

        Args:
            title: The routine's user-facing title.
            intent_url: Absolute chat deep link carrying the routine prompt
                as ``?intent=`` (ADR-173).
            language: Any locale spelling; normalized internally.

        Returns:
            The localized markdown body (English fallback).
        """
        from src.core.i18n import normalize_language

        template = ProactiveMessages._ROUTINE_APPROVAL_BODIES.get(
            normalize_language(language), ProactiveMessages._ROUTINE_APPROVAL_BODIES["en"]
        )
        return template.format(title=title, intent_url=intent_url)

    @staticmethod
    def workboard_body(
        event: str,
        title: str,
        language: str,
        *,
        excerpt: str = "",
        intent_url: str = "",
        ticket_url: str = "",
    ) -> str:
        """Localized body of one workboard notification (ADR-276).

        Args:
            event: A :class:`WorkboardEvent` value — bounded, never user
                text.
            title: The ticket's own title, already bounded by its column.
            language: Any locale spelling; normalized internally.
            excerpt: The beginning of what LIA wrote on the ticket, bounded by
                the caller.
            intent_url: Chat deep link that finishes a stopped run (ADR-173).
            ticket_url: Where the ticket lives, for the events answered there.

        Returns:
            The localized body; an unknown event yields an empty string rather
            than a placeholder sentence — a notification nobody can read is
            worse than none.
        """
        from src.core.i18n import normalize_language

        table = ProactiveMessages._WORKBOARD_BODIES.get(event)
        if table is None:
            return ""
        template = table.get(normalize_language(language), table["en"])
        # The ticket's title and LIA's excerpt are VALUES here, never a format
        # string: a title reading « payer la facture {montant} » must not raise.
        return template.format(
            title=title, excerpt=excerpt, intent_url=intent_url, ticket_url=ticket_url
        )

    @staticmethod
    def _peer_template(table: dict[str, str], language: str) -> str:
        """Resolve a peers body template through the normalization chokepoint."""
        from src.core.i18n import normalize_language

        return table.get(normalize_language(language), table["en"])

    @staticmethod
    def peer_request_body(
        requester_name: str, context_message: str | None, url: str, language: str
    ) -> str:
        """Chat body for an incoming connection request (Lot 3).

        Args:
            requester_name: Display name of the requesting user.
            context_message: Optional requester note — rendered quoted, as
                plain third-party TEXT (provenance doctrine).
            url: Settings deep link to the « Connexions » section.
            language: Recipient language (any spelling; normalized).

        Returns:
            Localized markdown body.
        """
        note = ""
        if context_message:
            note = ProactiveMessages._peer_template(
                ProactiveMessages._PEER_REQUEST_NOTE, language
            ).format(note=context_message)
        return ProactiveMessages._peer_template(
            ProactiveMessages._PEER_REQUEST_BODIES, language
        ).format(name=requester_name, note=note, url=url)

    @staticmethod
    def peer_accepted_body(peer_name: str, url: str, language: str) -> str:
        """Chat body telling the requester their request was accepted.

        Args:
            peer_name: Display name of the accepting user.
            url: Settings deep link to the « Connexions » section.
            language: Recipient language.

        Returns:
            Localized markdown body.
        """
        return ProactiveMessages._peer_template(
            ProactiveMessages._PEER_ACCEPTED_BODIES, language
        ).format(name=peer_name, url=url)

    @staticmethod
    def peer_declined_body(peer_name: str, language: str) -> str:
        """Chat body telling the requester their request was declined (no reason).

        Args:
            peer_name: Display name of the declining user.
            language: Recipient language.

        Returns:
            Localized body.
        """
        return ProactiveMessages._peer_template(
            ProactiveMessages._PEER_DECLINED_BODIES, language
        ).format(name=peer_name)

    @staticmethod
    def peer_message_delivered_body(peer_name: str, language: str) -> str:
        """Sender confirmation after a relayed message reached its recipient.

        Args:
            peer_name: Recipient display name.
            language: Sender language.

        Returns:
            Localized body.
        """
        return ProactiveMessages._peer_template(
            ProactiveMessages._PEER_MESSAGE_DELIVERED_BODIES, language
        ).format(name=peer_name)

    @staticmethod
    def peer_message_failed_body(peer_name: str, language: str) -> str:
        """Sender notice after a relayed message exhausted its attempts.

        Args:
            peer_name: Recipient display name.
            language: Sender language.

        Returns:
            Localized body.
        """
        return ProactiveMessages._peer_template(
            ProactiveMessages._PEER_MESSAGE_FAILED_BODIES, language
        ).format(name=peer_name)

    @staticmethod
    def peer_removed_body(peer_name: str, language: str, released: int = 0) -> str:
        """Chat body telling either side a connection was removed (spec §5.3).

        The workboard sentence is APPENDED rather than sent as a second
        notification (ADR-276 lot 5): two messages a second apart about one
        event is noise, and this path already reaches both sides. Nothing is
        added when nothing moved — « 0 ticket came back » is noise of its own.

        Args:
            peer_name: Display name of the other side.
            language: Recipient language.
            released: How many workboard tickets came back to THIS recipient.

        Returns:
            Localized body.
        """
        body = ProactiveMessages._peer_template(
            ProactiveMessages._PEER_REMOVED_BODIES, language
        ).format(name=peer_name)
        if released <= 0:
            return body
        table = (
            ProactiveMessages._PEER_REMOVED_RELEASED_ONE
            if released == 1
            else ProactiveMessages._PEER_REMOVED_RELEASED_MANY
        )
        return body + ProactiveMessages._peer_template(table, language).format(count=released)

    @staticmethod
    def sources_label(language: str) -> str:
        """Localized label prefixing the source links block.

        Args:
            language: Backend-canonical language code.

        Returns:
            The localized "Sources" label (English fallback).
        """
        return ProactiveMessages._SOURCES_LABEL.get(
            language, ProactiveMessages._SOURCES_LABEL["en"]
        )
