# GoogleApiCallsUnaccounted — Runbook

**Sévérité** : warning
**Composant** : connectors
**Impact** : un appel Google Maps Platform payant (Places, Routes, Geocoding,
Weather, Air quality, Pollen, Static Maps, Street View) a été fait sur la clé
de la plateforme **sans qu'aucun grand livre ne le reçoive** : pas de ligne
`google_api_usage_logs`, pas de contribution à `message_token_summary`, pas
d'incrément de `user_statistics.cycle_google_api_cost_eur`, et le plafond de
dépense quotidien de l'instance (ADR-216 / ADR-272) ne l'a pas vu. C'est un
euro dépensé par la plateforme pour une personne, et jamais refacturé.

---

## Définition

```promql
sum by (api_name) (increase(google_api_calls_unaccounted_total[1h])) > 0
```

Le seuil zéro est volontaire : aucun appel payant ne doit se terminer sans
comptage. Le compteur est incrémenté par `track_google_api_call`
(`connectors/clients/google_api_tracker.py`) quand **aucun `TrackingContext`
n'est ambiant** au moment où un client Google enregistre un appel facturé ; le
même événement produit un log `google_api_call_unaccounted` en WARNING avec
`api_name` et `endpoint`. Un résultat servi par le cache Redis n'est pas
compté : Google n'a rien facturé.

### Pourquoi cette alerte existe

La comptabilité est ambiante : un client enregistre dans le tracker qu'un
ancêtre a publié. Jusqu'au 2026-09-19 le compteur « ne faisait rien » sans
tracker, et rien ne le disait : sur dev, 3 020 lignes `google_api_usage_logs`,
**aucune** hors d'un tour de chat, alors que le heartbeat calculait un conseil
de départ sur Routes, le briefing lisait Google Weather, une réunion
géocodait son lieu et les proxys d'images servaient des cartes facturées. La
même famille de défaut que `LLMCallsWithoutUsage`, un rang plus loin.

Chaque surface hors tour ouvre désormais sa propre comptabilité et la route
est **déclarée** (`domains/google_api/spend_roads.py`, garde
`test_google_spend_road_completeness.py`) — l'alerte est la preuve à
l'exécution que la déclaration dit vrai.

---

## Diagnostic

### 1. Quelle API, quel volume ?

```promql
sum by (api_name) (increase(google_api_calls_unaccounted_total[24h]))
```

Croiser avec les logs pour le point d'entrée (le `endpoint` et la pile qui a
appelé le client) :

```bash
docker logs lia-api-prod 2>&1 | grep google_api_call_unaccounted
```

### 2. Quelle surface a appelé le client ?

Le module qui importe le client est nécessairement déclaré dans
`GOOGLE_SPEND_ROADS` — sinon la garde aurait rougi la CI. Trois cas :

- **Route `TURN`** (un outil) exécuté **hors** d'un tour : un nouvel
  exécuteur d'outils (un nouveau canal, un nouveau job) a appelé l'outil sans
  publier de tracker. Modèle à imiter : `agents/telephony/live_tools.py`
  (`VoiceToolHost`), qui ouvre un `TrackingContext` sur le run id de l'appel
  ou de la session.
- **Route `ACCOUNTED` ou `CALLER`** dont le tracker ne couvre pas TOUT ce que
  la surface lit : l'appel Google est fait avant l'ouverture du tracker ou
  après sa fermeture (le collecteur de consultations a eu exactement ce défaut
  en 2026-09 — 824 runs, zéro ligne). Ouvrir le tracker autour de l'acte
  entier par la porte `infrastructure/proactive/tracking.out_of_turn_spend`,
  comme `infrastructure/proactive/runner.py` et `briefing/service.py::build_cards`.
- **Un nouveau client Google** qui appelle `track_google_api_call` depuis un
  module qui n'importe aucun module « payant » déclaré : ajouter le module à
  `PAID_GOOGLE_MODULES` pour que ses importeurs soient marchés par la garde.

### 3. La dépense manquante

Le montant n'est pas récupérable a posteriori (rien n'a été écrit). L'ordre
de grandeur se lit dans la table tarifaire `google_api_pricing`
(Places Text Search ≈ 0,03 €, Routes ≈ 0,004 €, Geocoding ≈ 0,004 €,
Static Maps ≈ 0,002 €).

---

## Résolution

1. Identifier la surface (étape 2) et lui faire ouvrir un `TrackingContext`
   sur le run id de son acte — ou, si elle en tenait déjà un, l'étendre
   autour de l'appel.
2. Déclarer la route dans `GOOGLE_SPEND_ROADS` (la garde refuse une omission
   et un accountant qui n'ouvre aucune porte).
3. Vérifier sur dev que la ligne arrive : `google_api_usage_logs.run_id`
   porte le run de la surface, `message_token_summary` s'incrémente, le
   registre journalier de l'instance aussi.

---

## Références

- ADR-272 — chaque token que la plateforme paie répond aux deux plafonds
  (amendement 2026-09-20 : la règle n'est pas propre au modèle)
- `docs/runbooks/alerts/LLMCallsWithoutUsage.md` — la même famille, côté modèle
- `apps/api/src/domains/google_api/spend_roads.py` — la déclaration des routes
- `apps/api/src/domains/usage_limits/cost_bearers.py` — qui paie quoi
