# Format de sortie — Briefing Quotidien

## Structure attendue

### 1. En-tete

📅 Briefing du [date]
<hr />

### 2. Agenda du jour
Classement par échéance :
🔴 date et heure de début <= 1 heure
🟡 1 heure < date et heure de début <= 4 heures
🟢 4 heures < date et heure de début

Pour chaque rdv, afficher :
- **Heure** — Titre du rdv
Lieu (si disponible)
Participants cles (si reunion)

Si aucun evenement : "Aucun rdv planifie."
Si des evenements du lendemain necessitent une preparation, les mentionner (🟢).

<hr />

### 3. Taches prioritaires
Classement par urgence :
🔴 Taches en retard ou a echeance aujourd'hui
🟡 Taches prioritaires a venir
🟢 Taches sans echeance immediate

Pour chaque tache, afficher :
- **Date** — Titre de la tâche
Titre - Description

Si aucune tache : "Aucune tache en cours"

<hr />

### 4. Meteo
🔴 Alerte météo
🟡 Pluie/Neige

- **Aujourd'hui** : Conditions, vent km/h et direction, temperature min/max, precipitations
- **Tendance 3 jours** : Resume en une ligne par jour
- Alertes meteo si pertinent

<hr />

### 5. Emails du jour
Classement par importance/urgence estimée ou explicite :
🔴 email important ou urgent
🟡 email nécessitant un vigilance
🟢 email standard ou inutile

Pour chaque email (5 derniers) :
- **Expediteur** — Objet du mail
**Date et heure** — Date et heure de réception
Resume court (1 ligne)
Signaler les emails importants ou urgents necessitant une action

Si aucun email : " Aucun email recu aujourd'hui"

<hr />

### 6. Rappels
Classement par échéance :
🔴 date et heure de début <= 1 heure
🟡 1 heure < date et heure de début <= 4 heures
🟢 4 heures < date et heure de début

Pour chaque rappel en attente :
- **Heure de declenchement** - Objet/contenu du rappel

Si aucun rappel : " Aucun rappel aujourd'hui"

<hr />

### 7. A noter
Points d'attention proactifs :
- Conflits d'agenda detectes
- Taches en retard depuis plusieurs jours
- Changement meteo notable (pluie prevue, chute de temperature)
- Emails importants ou necessitant une reponse urgente
- Rappels imminents (dans l'heure)
- Suggestions contextuelles (parapluie, prevoir plus de temps pour un trajet, etc.)
