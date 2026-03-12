---
name: briefing-quotidien
description: >
  Generates a comprehensive today briefing combining calendar events, priority tasks,
  and weather forecast. Use when the user asks for a briefing, daily summary,
  or "what's on my schedule today".
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
---

# Briefing Quotidien

## Instructions

1. Récupérer les rdv du jour et du lendemain via calendar
2. Lister les tâches prioritaires, en retard et à venir via tasks
3. Obtenir la météo locale (aujourd'hui + tendance 3 jours)
4. Récupérer les 5 derniers emails reçus dans la boîte de réception aujourd'hui
5. Formater en sections structurées : Agenda → Tâches → Météo → Emails → À noter
6. Commencer par le plus urgent, terminer par les suggestions proactives
7. Si aucune tâche/événement : mentionner "journée libre" et suggérer des activités
8. Si aucun email : mentionner "aucun email reçu aujourd'hui"

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

### 💡 À noter
- Suggestions proactives basées sur le contexte (agenda, tâches, météo, emails)
- Rappels utiles (parapluie, vêtements chauds, réponses urgentes, etc.)

## Ressources disponibles

- `references/output-format.md` — Template détaillé du format de sortie du briefing
