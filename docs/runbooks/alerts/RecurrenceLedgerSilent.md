# RecurrenceLedgerSilent — Runbook

**Sévérité** : warning
**Composant** : habits
**Impact** : les demandes récurrentes ne peuvent plus être apprises. Le
registre (ledger Redis) qui compte « même type de demande, jour après jour »
ne reçoit aucune occurrence alors que des tours actionnables humains ont bien
eu lieu. Sans occurrences : aucun candidat « en observation » dans le panneau
Habitudes, aucun verrou de forme (quotidien / jours ouvrés / hebdomadaire /
intermittent), aucune habitude récurrente promue, aucune suggestion
d'automatisation.

---

## Définition

```promql
(sum(increase(product_outcomes_total{result_type="action", evidence="E3"}[7d])) > 20)
and
((sum(increase(recurrence_ledger_writes_total{outcome="written"}[7d])) or vector(0)) == 0)
and
((sum(increase(post_response_extraction_scheduled_total{kind="recurrence", outcome="feature_disabled"}[7d])) or vector(0)) == 0)
```

Trois compteurs, trois questions :

| compteur | question | qui l'incrémente |
|---|---|---|
| `product_outcomes_total{action, E3}` | y a-t-il eu du trafic actionnable **humain** ? | le routeur, une fois par tour humain (les runs automatisés n'écrivent rien) — la même valeur dont le tableau de bord produit dérive |
| `recurrence_ledger_writes_total{written}` | le ledger a-t-il **écrit** ? | l'écriture elle-même (`record_occurrence`), pas la porte qui la remet au fond |
| `post_response_extraction_scheduled_total{recurrence, feature_disabled}` | la fonctionnalité est-elle coupée ? | la porte, quand `RECURRENCE_SUGGESTION_ENABLED=false` |

Plus de 20 tours actionnables humains sur 7 jours, **zéro écriture atterrie**,
fonctionnalité active = le ledger est affamé. La règle lit le compteur
d'**écriture** et non l'outcome `scheduled` de la porte : une porte qui
planifie vers un Redis qui avale chaque écriture compterait `scheduled` toute
la semaine sans qu'une seule occurrence existe.

`or vector(0)` est indispensable : un compteur étiqueté qui n'a jamais tiré
n'expose **aucune série**. Sans ce repli, la comparaison `== 0` est vide et
l'alerte ne peut jamais se déclencher — exactement le silence qu'elle doit
rompre.

### Pourquoi cette alerte existe

Mesuré en production le 2026-09-11 : la porte lisait
`get_qi_attr(state, "intent")`, un attribut que `QueryIntelligence` n'a
jamais déclaré (le champ s'appelle `immediate_intent`). `getattr` avec un
défaut rend `None` sans rien signaler ; `None != "action"` est toujours vrai ;
227 tours actionnables ont été refusés, 0 occurrence écrite, pendant des
semaines, sous des tableaux de bord verts et 40 tests unitaires verts — les
tests fabriquaient la clé que le lecteur attendait au lieu de prendre la
forme du producteur.

Le compteur de décisions existait depuis le début. Personne ne le regardait :
il figurait dans le référentiel des métriques aveugles
(`metric_coverage_baseline.json`).

---

## Diagnostic

### 1. Le store a-t-il vu passer les écritures ?

```promql
sum by (outcome) (increase(recurrence_ledger_writes_total[7d]))
```

| outcomes présents | signification |
|---|---|
| aucune série | rien n'a atteint `record_occurrence` : la porte refuse tout → aller en 2 |
| `redis_unavailable` | `get_redis_cache()` rend None — Redis ou sa configuration, pas la porte |
| `failed` | l'écriture lève — lire les logs `recurrence_record_failed` (warning, avec `error_type`) |
| `written > 0` | l'alerte ne tire pas ; si elle tire quand même, le fenêtrage Prometheus est en cause |

### 2. La distribution des décisions de la porte

```promql
sum by (outcome) (increase(post_response_extraction_scheduled_total{kind="recurrence"}[7d]))
```

| outcomes présents | signification |
|---|---|
| `not_applicable` seul (ou avec `automated_source`) alors que des tours `action` existent | la porte ne reconnaît plus un tour actionnable → aller en 3. **Après le correctif du 2026-09-11, `not_applicable` est le sort normal des tours de conversation** : sa seule présence ne prouve rien, c'est son exclusivité face à des `product_outcomes` `action` qui accuse |
| `feature_disabled` | `RECURRENCE_SUGGESTION_ENABLED=false` : l'alerte ne tire pas par construction ; si le ledger doit vivre, vérifier l'env |
| `no_user` | l'identité runtime manque au nœud de réponse (ADR-231) → contexte runtime non installé sur ce chemin |
| `error` | la planification a levé — lire les logs `recurrence_record_scheduling_failed` (error, avec traceback) |
| `scheduled > 0` et `written = 0` | la porte planifie, le store n'atterrit pas → étape 1 |

### 3. Ce que le routeur écrit et ce que la porte lit

La porte passe par **une seule déclaration** :
`src/domains/agents/analysis/query_intelligence_helpers.py::resolve_actionable_domain`.
Elle lit `routing_history[-1].intention == INTENTION_ACTION` (objet **ou**
dict — un checkpoint msgpack rend un dict) et
`get_qi_attr(state, "primary_domain")`.

Vérifier que la forme n'a pas bougé :

```bash
cd apps/api
.venv/Scripts/pytest tests/unit/test_qi_attr_contract_guard.py \
  tests/unit/domains/agents/analysis/test_resolve_actionable_domain.py -q
```

Le garde de contrat refuse toute lecture `get_qi_attr(state, "x")` dont `x`
n'est pas un attribut déclaré de `QueryIntelligence` — sous ses trois formes
(positionnelle, `attr=`, appel qualifié par module). Si un renommage de champ
ou de clé d'état a eu lieu, c'est lui qui rougit en premier.

### 4. Le chemin d'écriture lui-même

Sonde à blanc (clé de test, supprimée ensuite) :

```bash
docker exec -i lia-api-prod python - <<'PY'
import asyncio
from datetime import date
async def main():
    from src.core.config import settings
    from src.domains.agents.services.recurrence_ledger import record_occurrence
    from src.infrastructure.cache import recurrence_store
    from src.infrastructure.cache.redis import get_redis_cache
    await record_occurrence("00000000-0000-0000-0000-000000000000", "zzz_probe",
                            local_date=date.today(), local_hour=9.0, settings=settings)
    r = await get_redis_cache()
    key = recurrence_store.redis_key("00000000-0000-0000-0000-000000000000", "zzz_probe")
    print("ecrit:", bool(await r.get(key))); await r.delete(key)
asyncio.run(main())
PY
```

`ecrit: False` → Redis ou le store (`infrastructure/cache/recurrence_store.py`,
familles de clés ADR-260) — pas la porte.

---

## Actions

1. **Ne pas** relancer de seed du ledger (`ledger_seed.py`) pour « remplir »
   : le seed n'écrit que sur un ledger vide, et un ledger figé n'est pas un
   ledger vide.
2. Corriger la lecture (étape 3) ou le store (étape 1) ; le garde de contrat
   doit passer.
3. Après déploiement, vérifier sous 24 h que `recurrence_ledger_writes_total{outcome="written"}`
   monte sur un tour actionnable réel, puis que le panneau Habitudes montre un
   candidat « en observation ».
4. Si le ledger contenait des lignes figées antérieures à la panne, les
   purger **avant** le déploiement du correctif : un verrou calculé sur des
   données mortes serait promu au premier tour du domaine concerné
   (mesuré 2026-09-11 : `web_search` portait un verrou `daily@3.1h` issu d'un
   ancien seed défectueux, sans cooldown).
5. Au démarrage, `RECURRENCE_LEDGER_MAX_ENTRIES < RECURRENCE_WINDOW_DAYS` est
   **refusé** (le cap de jours tronquerait chaque fenêtre) : un `.env`
   partiellement mis à jour ne boote pas, il ne s'affame pas en silence.

## Références

- ADR-214 — Habitudes utilisateur (apprentissage déterministe), amendements
  du 2026-09-11
- ADR-255 — deux lectures d'une déclaration divergent toujours
- `apps/api/tests/unit/test_qi_attr_contract_guard.py` — garde de classe
