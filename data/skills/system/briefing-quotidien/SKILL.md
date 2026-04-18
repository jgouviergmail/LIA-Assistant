---
name: briefing-quotidien
description: >
  Generates a comprehensive today briefing combining calendar events, priority tasks,
  weather forecast, recent emails, and pending reminders. Use when the user asks
  for a briefing, daily summary, or "what's on my schedule today".
category: quotidien
priority: 70
plan_template:
  deterministic: true
  steps:
    - step_id: get_events
      agent_name: event_agent
      tool_name: get_events_tool
      parameters:
        days_ahead: 2
        max_results: 5
      depends_on: []
      description: Récupérer les événements du jour et du lendemain
    - step_id: get_tasks
      agent_name: task_agent
      tool_name: get_tasks_tool
      parameters:
        show_completed: false
      depends_on: []
      description: Lister les tâches en cours et prioritaires
    - step_id: get_weather
      agent_name: weather_agent
      tool_name: get_weather_forecast_tool
      parameters:
        days: 3
      depends_on: []
      description: Météo aujourd'hui + tendance 3 jours
    - step_id: get_emails
      agent_name: email_agent
      tool_name: get_emails_tool
      parameters:
        query: "in:inbox newer_than:1d"
        max_results: 5
      depends_on: []
      description: Récupérer les 5 derniers emails reçus aujourd'hui dans la boîte de réception
    - step_id: get_reminders
      agent_name: reminder_agent
      tool_name: list_reminders_tool
      parameters: {}
      depends_on: []
      description: Lister les rappels en attente pour la journée
---

# Briefing Quotidien

## Instructions

1. Récupérer les rdv du jour et du lendemain via calendar
2. Lister les tâches prioritaires, en retard et à venir via tasks
3. Obtenir la météo locale (aujourd'hui + tendance 3 jours)
4. Récupérer les 5 derniers emails reçus dans la boîte de réception aujourd'hui
5. Lister les rappels en attente pour la journée
6. Formater en sections structurées : Agenda → Tâches → Météo → Emails → Rappels → À noter
7. Commencer par le plus urgent, terminer par les suggestions proactives

## Ressources disponibles

- `references/output-format.md` — Template détaillé du format de sortie du briefing
