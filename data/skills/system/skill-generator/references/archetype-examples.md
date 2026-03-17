# Skill Archetype Examples

Three complete SKILL.md examples — one per archetype.
These examples follow the EXACT same structure as the existing system skills.
Use them as templates when generating new skills.

---

## 1. Prompt Expert — coaching-productivite (real system skill)

Pure instructions. No tools. The LLM follows expert guidance.

---
name: coaching-productivite
description: >
  Provides productivity coaching with prioritization frameworks (Eisenhower,
  Pomodoro) and habit-building strategies. Use when the user asks for help
  organizing tasks, managing time, or improving productivity.
category: productivite
priority: 50
---

# Coaching Productivité

## Instructions

Tu es un coach en productivité personnelle. Aide l'utilisateur à mieux
s'organiser, prioriser ses tâches et développer des habitudes efficaces.
Adapte tes conseils au contexte et aux contraintes de l'utilisateur.

## Frameworks disponibles

### Matrice d'Eisenhower
Classifier chaque tâche selon 2 axes :
- Urgent + Important → Faire immédiatement
- Important + Non urgent → Planifier (bloc calendrier)
- Urgent + Non important → Déléguer si possible
- Ni urgent ni important → Éliminer ou reporter

### Méthode Pomodoro
- Blocs de 25 min de focus intense
- Pause de 5 min entre chaque bloc
- Pause longue de 15-30 min après 4 blocs

## Approche

1. Écouter le contexte : charge actuelle, contraintes, énergie
2. Diagnostiquer : identifier le frein principal
3. Proposer un framework adapté avec des actions concrètes
4. Simplifier : commencer par 1-2 changements, pas une refonte totale

## Ressources disponibles

- references/matrice-eisenhower.md — Guide complet de la matrice d'Eisenhower
- references/techniques.md — Fiches détaillées : Pomodoro, GTD, Time Blocking

---

## 2. Advisory — preparation-reunion (real system skill)

Structured methodology. The LLM uses tools organically (calendar, contacts, emails).

---
name: preparation-reunion
description: >
  Prepares meeting materials by gathering calendar details, participant contacts,
  and recent email history. Use when the user mentions preparing for a meeting,
  reviewing attendees, or creating an agenda.
category: organisation
priority: 65
---

# Préparation de Réunion

## Instructions

1. Identifier la réunion cible dans le calendrier (la plus proche ou celle spécifiée)
2. Extraire les détails : titre, date/heure, lieu/lien, participants
3. Pour chaque participant : récupérer les coordonnées et le contexte récent
4. Chercher les échanges email récents avec les participants
5. Compiler un dossier de préparation structuré

## Format de sortie

### Informations de la réunion
- Titre, date, heure, durée
- Lieu ou lien de visioconférence
- Organisateur

### Participants
Pour chaque participant :
- Nom, fonction/titre
- Email, téléphone
- Dernier échange (date + résumé 1 ligne)

### Contexte
- Sujets en cours avec les participants
- Points en suspens des échanges récents

### Ordre du jour suggéré
1. Point sur [sujet 1]
2. Discussion [sujet 2]
3. Prochaines étapes

## Ressources disponibles

- references/template-agenda.md — Template d'ordre du jour prêt à remplir

---

## 3. Plan Template — briefing-quotidien (real system skill)

Deterministic automation. Fixed tool calls, bypasses the LLM planner.

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
      description: Récupérer les 5 derniers emails reçus aujourd'hui
---

# Briefing Quotidien

## Instructions

1. Récupérer les rdv du jour et du lendemain via calendar
2. Lister les tâches prioritaires, en retard et à venir via tasks
3. Obtenir la météo locale (aujourd'hui + tendance 3 jours)
4. Récupérer les 5 derniers emails reçus dans la boîte de réception aujourd'hui
5. Formater en sections structurées : Agenda → Tâches → Météo → Emails → À noter
6. Commencer par le plus urgent, terminer par les suggestions proactives

## Format de sortie

### 📅 Agenda du jour
- Lister chaque rdv avec heure, titre et lieu
- Mettre en évidence les conflits horaires éventuels

### ✅ Tâches prioritaires
- Tâches en retard (avec date d'échéance dépassée)
- Tâches du jour classées par priorité

### 🌤 Météo
- Conditions actuelles (température, ciel, vent)
- Prévisions pour la journée
- Tendance sur 3 jours

### 📧 Emails du jour
- Les 5 derniers emails reçus aujourd'hui
- Expéditeur, objet et résumé court

### 💡 À noter
- Suggestions proactives basées sur le contexte

## Ressources disponibles

- references/output-format.md — Template détaillé du format de sortie
