"""The routine a recurring-need proposal creates, in the person's language (ADR-375).

A proposal to automate a recurring need creates an ordinary time routine: its
title and its instruction are the person's own data from then on (shown on
the routine card, editable, run by the agent like any routine they wrote).
Each automatable domain carries one title and two instructions — ``day`` for a
daily or working-days cadence, ``week`` for a weekly one — phrased as the
person would ask. The set of domains is held equal to
``habits.need_domains.automatable_domains`` by the module's test.
"""

from __future__ import annotations

from typing import Literal

from src.core.i18n import resolve_language
from src.core.i18n_types import Language

Horizon = Literal["day", "week"]

#: language → domain → (title, day instruction, week instruction).
HABIT_ROUTINE_COPY: dict[Language, dict[str, tuple[str, str, str]]] = {
    "fr": {
        "event": (
            "Mon agenda",
            "Fais-moi le point sur mon agenda d'aujourd'hui : mes rendez-vous, "
            "leurs horaires et leurs lieux.",
            "Fais-moi le point sur mon agenda de la semaine à venir : mes rendez-vous "
            "jour par jour.",
        ),
        "email": (
            "Mes e-mails",
            "Résume mes e-mails non lus importants et dis-moi lesquels attendent une réponse.",
            "Résume les e-mails importants de ma semaine et dis-moi lesquels attendent "
            "encore une réponse.",
        ),
        "task": (
            "Mes tâches",
            "Quelles sont mes tâches à faire aujourd'hui, et lesquelles sont en retard ?",
            "Quelles sont mes tâches à faire cette semaine, et lesquelles sont en retard ?",
        ),
        "weather": (
            "Ma météo",
            "Quel temps fera-t-il aujourd'hui là où je suis ?",
            "Quel temps fera-t-il cette semaine là où je suis ?",
        ),
        "health": (
            "Ma santé",
            "Résume mes données de santé d'hier : activité, sommeil et ce qui sort de "
            "l'ordinaire.",
            "Résume mes données de santé de la semaine passée : activité, sommeil et tendances.",
        ),
        "sms": (
            "Mes SMS",
            "Résume mes SMS non lus et dis-moi lesquels attendent une réponse.",
            "Résume les SMS de ma semaine et dis-moi lesquels attendent encore une réponse.",
        ),
    },
    "en": {
        "event": (
            "My agenda",
            "Give me a rundown of my agenda for today: my appointments, their times and places.",
            "Give me a rundown of my agenda for the coming week: my appointments day by day.",
        ),
        "email": (
            "My emails",
            "Summarise my important unread emails and tell me which ones are waiting for a "
            "reply.",
            "Summarise the important emails of my week and tell me which ones are still "
            "waiting for a reply.",
        ),
        "task": (
            "My tasks",
            "Which tasks are due today, and which ones are overdue?",
            "Which tasks are due this week, and which ones are overdue?",
        ),
        "weather": (
            "My weather",
            "What will the weather be like today where I am?",
            "What will the weather be like this week where I am?",
        ),
        "health": (
            "My health",
            "Summarise my health data from yesterday: activity, sleep and anything out of "
            "the ordinary.",
            "Summarise my health data from the past week: activity, sleep and trends.",
        ),
        "sms": (
            "My texts",
            "Summarise my unread text messages and tell me which ones are waiting for a reply.",
            "Summarise the text messages of my week and tell me which ones are still "
            "waiting for a reply.",
        ),
    },
    "de": {
        "event": (
            "Mein Kalender",
            "Gib mir einen Überblick über meinen heutigen Kalender: meine Termine, ihre "
            "Uhrzeiten und Orte.",
            "Gib mir einen Überblick über meinen Kalender der kommenden Woche: meine "
            "Termine Tag für Tag.",
        ),
        "email": (
            "Meine E-Mails",
            "Fasse meine wichtigen ungelesenen E-Mails zusammen und sag mir, welche auf eine "
            "Antwort warten.",
            "Fasse die wichtigen E-Mails meiner Woche zusammen und sag mir, welche noch auf "
            "eine Antwort warten.",
        ),
        "task": (
            "Meine Aufgaben",
            "Welche Aufgaben sind heute fällig, und welche sind überfällig?",
            "Welche Aufgaben sind diese Woche fällig, und welche sind überfällig?",
        ),
        "weather": (
            "Mein Wetter",
            "Wie wird das Wetter heute dort, wo ich bin?",
            "Wie wird das Wetter diese Woche dort, wo ich bin?",
        ),
        "health": (
            "Meine Gesundheit",
            "Fasse meine Gesundheitsdaten von gestern zusammen: Aktivität, Schlaf und alles "
            "Ungewöhnliche.",
            "Fasse meine Gesundheitsdaten der vergangenen Woche zusammen: Aktivität, Schlaf "
            "und Tendenzen.",
        ),
        "sms": (
            "Meine SMS",
            "Fasse meine ungelesenen SMS zusammen und sag mir, welche auf eine Antwort warten.",
            "Fasse die SMS meiner Woche zusammen und sag mir, welche noch auf eine Antwort "
            "warten.",
        ),
    },
    "es": {
        "event": (
            "Mi agenda",
            "Hazme un resumen de mi agenda de hoy: mis citas, sus horarios y sus lugares.",
            "Hazme un resumen de mi agenda de la próxima semana: mis citas día a día.",
        ),
        "email": (
            "Mis correos",
            "Resume mis correos importantes no leídos y dime cuáles esperan una respuesta.",
            "Resume los correos importantes de mi semana y dime cuáles siguen esperando una "
            "respuesta.",
        ),
        "task": (
            "Mis tareas",
            "¿Qué tareas vencen hoy y cuáles están atrasadas?",
            "¿Qué tareas vencen esta semana y cuáles están atrasadas?",
        ),
        "weather": (
            "Mi tiempo",
            "¿Qué tiempo hará hoy donde estoy?",
            "¿Qué tiempo hará esta semana donde estoy?",
        ),
        "health": (
            "Mi salud",
            "Resume mis datos de salud de ayer: actividad, sueño y lo que se salga de lo "
            "normal.",
            "Resume mis datos de salud de la semana pasada: actividad, sueño y tendencias.",
        ),
        "sms": (
            "Mis SMS",
            "Resume mis SMS no leídos y dime cuáles esperan una respuesta.",
            "Resume los SMS de mi semana y dime cuáles siguen esperando una respuesta.",
        ),
    },
    "it": {
        "event": (
            "La mia agenda",
            "Fammi il punto sulla mia agenda di oggi: i miei appuntamenti, i loro orari e i "
            "luoghi.",
            "Fammi il punto sulla mia agenda della prossima settimana: i miei appuntamenti "
            "giorno per giorno.",
        ),
        "email": (
            "Le mie email",
            "Riassumi le mie email importanti non lette e dimmi quali aspettano una risposta.",
            "Riassumi le email importanti della mia settimana e dimmi quali aspettano ancora "
            "una risposta.",
        ),
        "task": (
            "Le mie attività",
            "Quali attività scadono oggi e quali sono in ritardo?",
            "Quali attività scadono questa settimana e quali sono in ritardo?",
        ),
        "weather": (
            "Il mio meteo",
            "Che tempo farà oggi dove mi trovo?",
            "Che tempo farà questa settimana dove mi trovo?",
        ),
        "health": (
            "La mia salute",
            "Riassumi i miei dati di salute di ieri: attività, sonno e ciò che esce "
            "dall'ordinario.",
            "Riassumi i miei dati di salute della settimana scorsa: attività, sonno e tendenze.",
        ),
        "sms": (
            "I miei SMS",
            "Riassumi i miei SMS non letti e dimmi quali aspettano una risposta.",
            "Riassumi gli SMS della mia settimana e dimmi quali aspettano ancora una risposta.",
        ),
    },
    "zh-CN": {
        "event": (
            "我的日程",
            "帮我梳理今天的日程：我的约会、时间和地点。",
            "帮我梳理接下来一周的日程：按天列出我的约会。",
        ),
        "email": (
            "我的邮件",
            "总结我未读的重要邮件，并告诉我哪些在等待回复。",
            "总结我这一周的重要邮件，并告诉我哪些仍在等待回复。",
        ),
        "task": (
            "我的任务",
            "我今天有哪些到期任务，哪些已经逾期？",
            "我这周有哪些到期任务，哪些已经逾期？",
        ),
        "weather": (
            "我的天气",
            "我所在的地方今天天气怎么样？",
            "我所在的地方这周天气怎么样？",
        ),
        "health": (
            "我的健康",
            "总结我昨天的健康数据：活动、睡眠以及任何异常情况。",
            "总结我过去一周的健康数据：活动、睡眠和趋势。",
        ),
        "sms": (
            "我的短信",
            "总结我未读的短信，并告诉我哪些在等待回复。",
            "总结我这一周的短信，并告诉我哪些仍在等待回复。",
        ),
    },
}


def routine_copy(domain: str, horizon: Horizon, language: str | None) -> tuple[str, str]:
    """The title and the instruction of the routine automating a need.

    Args:
        domain: An automatable domain (``habits.need_domains``).
        horizon: ``day`` for a daily or working-days cadence, ``week`` for a
            weekly one.
        language: Any raw language code (normalised; the declared language
            when absent).

    Returns:
        ``(title, instruction)``.

    Raises:
        KeyError: When the domain cannot be automated.
    """
    title, day, week = HABIT_ROUTINE_COPY[resolve_language(language)][domain]
    return title, day if horizon == "day" else week
