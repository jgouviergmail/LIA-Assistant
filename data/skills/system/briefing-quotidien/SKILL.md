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
  max_missing_domains: 2
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
8. Si aucune tâche/événement : mentionner "journée libre" et suggérer des activités
9. Si aucun email : mentionner "aucun email reçu aujourd'hui"
10. Si aucun rappel : mentionner "aucun rappel aujourd'hui"

## Format de sortie

### 📅 Agenda du jour
- Lister chaque rdv avec heure, titre et lieu
- Mettre en évidence les conflits horaires éventuels
- Mentionner les événements du lendemain s'ils nécessitent une préparation

### ✅ Tâches prioritaires
- Tâches en retard (avec date d'échéance dépassée)
- Tâches du jour classées par priorité
- Tâches à venir nécessitant une action aujourd'hui

### 🌤 Météo
- Conditions actuelles (température, ciel, vent)
- Prévisions pour la journée
- Tendance sur 3 jours
- Alertes météo si pertinent

### 📧 Emails du jour
- Les 5 derniers emails reçus aujourd'hui dans la boîte de réception
- Expéditeur, objet et résumé court pour chaque email
- Signaler les emails importants ou urgents nécessitant une action

### 🔔 Rappels
- Pour chaque rappel : **heure de déclenchement** + **objet/contenu** du rappel
- Rappels en retard (heure dépassée) signalés en priorité
- Si aucun rappel en attente, ne pas afficher cette section

### 💡 À noter
- Suggestions proactives basées sur le contexte (agenda, tâches, météo, emails, rappels)
- Rappels utiles (parapluie, vêtements chauds, réponses urgentes, etc.)

## Ressources disponibles

- `references/output-format.md` — Template détaillé du format de sortie du briefing
