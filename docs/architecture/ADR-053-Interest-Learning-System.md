# ADR-053: Interest Learning System

> **Date** : 2026-01-27
> **Statut** : Accepted
> **Decideurs** : Architecture Team
> **Impacts** : Backend (domains/interests), Frontend (settings), LangGraph (response_node)

---

## Contexte

LIA a besoin d'un systeme d'apprentissage des centres d'interet utilisateur pour :

1. Personnaliser les reponses en fonction des preferences
2. Permettre des notifications proactives pertinentes (phase future)
3. Enrichir le profil utilisateur de maniere automatique

Le systeme doit s'integrer de maniere non-bloquante dans le flow conversationnel existant.

---

## Decision

### Architecture Choisie

**Pattern Fire-and-Forget avec extraction LLM**

```
[response_node] ─────────────────────────────────────┐
       │                                              │
       ▼                                              ▼
safe_fire_and_forget(                    safe_fire_and_forget(
  extract_memories_background()            extract_interests_background()
)                                        )
                                                      │
                                                      ▼
                                         InterestExtractionService
                                         - LLM analysis (0-2 interests)
                                         - Dedup via string similarity
                                         - Consolidate or create
```

### Choix Techniques

| Aspect | Decision | Justification |
|--------|----------|---------------|
| **Extraction** | LLM (gpt-4o-mini) | Analyse semantique des signaux d'interet |
| **Deduplication** | String similarity | Simple et efficace (embedding prevu en phase 2) |
| **Poids** | Algorithme Bayesien Beta(2,1) | Robuste avec peu de donnees, converge rapidement |
| **Decay** | 1% par jour | Evite la stagnation sans etre trop agressif |
| **Stockage** | PostgreSQL + pgvector | Coherent avec l'existant, pret pour embeddings |
| **Cache** | Redis (TTL 5min) | Evite les appels LLM redondants |

### Structure des Donnees

**Table `user_interests`** :
- `topic` : Description de l'interet (max 200 chars)
- `category` : Enum (technology, science, culture, etc.)
- `positive_signals` / `negative_signals` : Compteurs pour poids Bayesien
- `status` : active, blocked, dormant
- `embedding` : ARRAY(Float()) pour dedup semantique (E5-small, 384 dims)

**Algorithme de Poids** :
```python
weight = (PRIOR_ALPHA + positive_signals) / (PRIOR_ALPHA + PRIOR_BETA + positive_signals + negative_signals)
effective_weight = weight * max(0.1, 1.0 - days_since_mention * decay_rate)
```

### Integration LangGraph

L'extraction est declenchee dans `response_node` apres l'envoi de la reponse, via `safe_fire_and_forget()`. Cela garantit :

1. Aucun impact sur la latence de reponse
2. Extraction systematique sur chaque message utilisateur
3. Gestion des erreurs silencieuse (logging uniquement)

### Format du Prompt

Le prompt d'extraction utilise le format `USER:` pour correspondre au format reel de la conversation :

```
USER: J'adore l'astronomie, j'ai passe des heures hier soir a observer Jupiter
Sortie: [{"topic": "astronomie, observation des planetes", "category": "science", "confidence": 0.95}]
```

Regles cles :
- Exclure les actions quotidiennes (email, calendrier, meteo)
- Niveau d'abstraction intermediaire (categories, pas produits specifiques)
- Confiance minimale 0.6

---

## Alternatives Considerees

### Option A : Extraction via Rules-Based
- **Avantage** : Zero cout LLM
- **Inconvenient** : Trop rigide, mauvaise detection des signaux d'interet
- **Decision** : Rejete

### Option B : Embeddings-Only
- **Avantage** : Plus rapide, moins couteux
- **Inconvenient** : Pas de categorisation, pas de filtrage des actions quotidiennes
- **Decision** : Rejete

### Option C : LLM dans le flow synchrone
- **Avantage** : Resultats immediats
- **Inconvenient** : Latence ajoutee de 500-1000ms
- **Decision** : Rejete

---

## Consequences

### Positives

1. **Personnalisation** : Profil utilisateur enrichi automatiquement
2. **Non-intrusif** : Aucun impact sur la latence de reponse
3. **Evolutif** : Architecture prete pour notifications proactives
4. **Controlable** : Utilisateur peut gerer ses interets (feedback, blocage)

### Negatives

1. **Cout LLM** : ~1000 tokens par message (~$0.0001)
2. **Complexite** : Nouveau domaine a maintenir
3. **Dependance** : Qualite de l'extraction depend du LLM

### Metriques de Suivi

```python
interest_extraction_total{status="success|failed|skipped"}
interest_extraction_duration_seconds
interest_created_total
interest_consolidated_total
interest_feedback_total{type="thumbs_up|thumbs_down|block"}
```

---

## Implementation

### Phases

| Phase | Contenu | Statut |
|-------|---------|--------|
| 1 | Modeles, extraction, repository | ✅ Complete |
| 2 | Evolution poids, deduplication | ✅ Complete |
| 3 | API endpoints, frontend settings | ✅ Complete |
| 4 | Debug panel integration | ✅ Complete |
| 5 | Notifications proactives | ✅ Complete |

### Infrastructure Proactive (Phase 5)

L'infrastructure proactive utilise le pattern **transactions autonomes** :

```
ProactiveTaskRunner
    ├── Query users (sans FOR UPDATE)
    ├── track_proactive_tokens()     ← transaction autonome
    └── on_notification_sent()       ← transaction autonome
```

**Protection contre doublons** : `max_instances=1` + cooldowns (2h global, 24h/topic)

> Voir [INTERESTS.md](../technical/INTERESTS.md#24-infrastructure-proactive) pour details.

### Fichiers Cles

```
apps/api/src/domains/interests/
├── models.py                    # UserInterest, InterestNotification
├── schemas.py                   # Pydantic schemas
├── repository.py                # Queries + Bayesian weight
├── router.py                    # API endpoints
└── services/extraction_service.py

apps/api/src/domains/agents/prompts/v1/
└── interest_extraction_prompt.txt

apps/web/src/components/settings/
├── InterestsSettings.tsx
└── InterestsDialog.tsx
```

---

## References

- [docs/technical/INTERESTS.md](../technical/INTERESTS.md) - Documentation technique complete
- [ADR-013-LangMem-Long-Term-Memory](./ADR-013-LangMem-Long-Term-Memory.md) - Pattern similaire pour memoire
- [ADR-046-Background-Job-Scheduling](./ADR-046-Background-Job-Scheduling.md) - Infrastructure jobs
