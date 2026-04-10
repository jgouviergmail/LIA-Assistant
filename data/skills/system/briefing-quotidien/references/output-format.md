# Format de sortie — Briefing Quotidien

## Structure attendue

### 1. En-tete
```
📅 Briefing du [date] — [jour de la semaine]
```

### 2. Agenda du jour
Pour chaque rdv, afficher :
- **Heure** — Titre du rdv
- Lieu (si disponible)
- Participants cles (si reunion)

Si aucun evenement : "Journee libre — pas d'evenements planifies."

Si des evenements du lendemain necessitent une preparation, les mentionner.

### 3. Taches prioritaires
Classement par urgence :
1. **🔴 Urgent** — Taches en retard ou a echeance aujourd'hui
2. **🟡 Important** — Taches prioritaires a venir
3. **🟢 A planifier** — Taches sans echeance immediate

Si aucune tache : "Aucune tache en cours — c'est le moment d'en planifier."

### 4. Meteo
- **Aujourd'hui** : Conditions, temperature min/max, precipitations
- **Tendance 3 jours** : Resume en une ligne par jour
- Alertes meteo si pertinent

### 5. Emails du jour
Pour chaque email (5 derniers) :
- **Expediteur** — Objet du mail
- Resume court (1 ligne)
- Signaler les emails importants ou urgents necessitant une action

Si aucun email : "Aucun email recu aujourd'hui."

### 6. Rappels
Pour chaque rappel en attente :
- **Heure de declenchement** — Objet/contenu du rappel
- Rappels en retard (heure depassee) signales en priorite avec indicateur visuel

Si aucun rappel en attente : ne pas afficher cette section.

### 7. A noter
Points d'attention proactifs :
- Conflits d'agenda detectes
- Taches en retard depuis plusieurs jours
- Changement meteo notable (pluie prevue, chute de temperature)
- Emails necessitant une reponse urgente
- Rappels imminents (dans l'heure)
- Suggestions contextuelles (parapluie, prevoir plus de temps pour un trajet, etc.)
