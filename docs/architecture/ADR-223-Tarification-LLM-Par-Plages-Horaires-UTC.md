# ADR-223 : un tarif qui varie avec l'heure est porté par la ligne de prix, pas par le code

**Statut**: ✅ IMPLEMENTED (2026-08-17)
**Date**: 2026-08-17
**Origine**: tarification DeepSeek par heures pleines/creuses (vérifiée le 2026-08-17 sur api-docs.deepseek.com)

## Contexte

DeepSeek facture désormais ses modèles texte selon l'heure UTC de l'appel :
fenêtres pleines 01:00–04:00 et 06:00–10:00 UTC, tout le reste en heures
creuses à exactement 50 % du tarif plein (v4-flash : 0,44/0,014/1,32 $ par
million de tokens en pleine contre 0,22/0,007/0,66 en creuse). Le catalogue
LIA ne connaissait qu'un prix plat par ligne active : les lignes DeepSeek
portaient le tarif plein, appliqué 24 h/24 — chaque appel en heures creuses
était survalorisé d'un facteur 2, y compris sur le démonstrateur public dont
tous les emplacements LLM pointent sur `deepseek-v4-flash` et dont le
plafond de dépense (ADR-216) lit précisément ce ledger.

Le terrain était favorable à une correction sans dette : les coûts sont
valorisés **à l'instant de l'appel** et persistés (`TokenUsageLog`), jamais
recalculés sur le chemin nominal ; toute la valorisation converge vers deux
chokepoints (`get_cached_cost_usd_eur` synchrone, `AsyncPricingService`
asynchrone) ; et le versioning temporel des prix (désactivation + insertion,
`effective_from`) existe déjà.

## Décision

### 1. Le créneau est une donnée de la ligne de prix

Colonne JSONB nullable `time_slots` sur `llm_model_pricing` : liste de 1..n
fenêtres `{start_utc, end_utc, input_unit_price, cached_input_unit_price,
output_unit_price}`. Sémantique : `[début, fin)` à la minute, en UTC ; une
fin avant le début passe minuit ; les fenêtres ne se chevauchent pas
(validé à l'écriture, 422) ; les colonnes de base restent le tarif par
défaut hors fenêtre ; `NULL`/`[]` = tarif plat, comportement antérieur
inchangé octet pour octet. Générique par construction : tout provider, tout
modèle `per_1m_tokens`, 1..n créneaux — rien de spécifique à DeepSeek dans
le code. Les créneaux voyagent avec la ligne versionnée : l'historique des
coûts recalculés à une date passée utilise les fenêtres de la ligne
effective à cette date.

Écartés : table enfant (duplication à chaque version temporelle, jointure
sur le chemin chaud) ; lignes de prix multiples par créneau (casse
l'invariant « une ligne active par modèle » sur lequel reposent
`get_active_model_price().first()`, l'UI d'administration et la garde
`unbillable_model` du démonstrateur).

### 2. Une seule implémentation de la résolution

`src/domains/llm/pricing_time_slots.py` : schéma Pydantic `TimeSlotPrice`
(+ `validate_time_slot_list`, non-chevauchement sur le cercle des 1440
minutes) et `find_active_slot(time_slots, at)` — fail-soft sur le chemin
chaud (une entrée corrompue est ignorée en DEBUG, jamais un crash de
callback). Les deux chokepoints la consomment : `get_cached_cost_usd_eur`
et `calculate_token_cost` gagnent un paramètre optionnel `at: datetime |
None = None` (défaut : maintenant UTC — l'instant de l'appel, celui qui est
persisté avec le log) ; `calculate_token_cost_at_date` résout à `at_date`.
L'arithmétique par million, jusqu'ici dupliquée entre les deux jumeaux du
service asynchrone, est factorisée dans `_token_cost_usd` — le créneau s'y
résout en un seul endroit.

Convention assumée : un appel à cheval sur une frontière est valorisé au
tarif de l'instant de complétion (celui du calcul). Le blob Redis du cache
de prix est compatible dans les deux sens de déploiement : un ancien blob
se charge avec `time_slots=None` (tarif plat), un blob nouveau lu par un
ancien worker déclenche le drop-and-rebuild existant.

### 3. L'effacement s'exprime par la liste vide, jamais par null

`LLMModelService.update` construit son change-set avec
`model_dump(exclude_unset=True, exclude_none=True)` : un `null` explicite y
disparaît silencieusement. Le contrat de fil est donc : champ omis =
héritage des créneaux de la ligne courante sur la nouvelle version (une
hausse de prix sans rapport ne doit pas rétrograder le modèle au tarif
plat) ; `[]` = effacement (stocké `NULL`) ; liste non vide = remplacement.
L'état FUSIONNÉ est validé côté service (`TimeSlotsUnitMismatchError`,
attrapée avant le `ValueError` générique du routeur qui répondrait 409) :
basculer `pricing_unit` vers une unité audio en laissant des créneaux
hérités est refusé — l'admin efface explicitement dans le même appel.

### 4. Administrable là où les tarifs vivent déjà

Le dialogue Tarifs LLM gagne un interrupteur « tarification par plages
horaires (UTC) » (visible uniquement en `per_1m_tokens`), un éditeur de
fenêtres (heures UTC avec rappel du fuseau local de l'admin, trois prix par
fenêtre, ajout/retrait), la validation miroir côté client (le serveur reste
l'autorité), et un badge « Horaire » sur les lignes fenêtrées du tableau.
i18n sur les 6 locales.

### 5. Pas de backfill des bases existantes

Décision propriétaire (2026-08-17) : les prix de prod et du démonstrateur
ont été saisis par l'UI d'administration et ne sont pas écrasés par
migration ; la migration n'ajoute que la colonne nullable, et le
propriétaire saisit les fenêtres DeepSeek via l'UI. Le seed de référence
(`llm_pricing_seed.sql`) reste une extraction de prod : il omet la colonne
(NULL = plat) et son en-tête exige que la PROCHAINE extraction l'emporte —
même classe de défaut que la perte historique des lignes audio-hour.

## Conséquences

- Le ledger du démonstrateur et le plafond ADR-216 deviennent exacts dès
  que les fenêtres sont saisies — sans redéploiement.
- `TokenUsageLog` reste la vérité comptable ; Langfuse, qui valorise depuis
  son propre registre, diverge en heures creuses comme il divergeait déjà.
- `business_metrics.py` (métrique Prometheus non facturante) valorise en
  fin de run : un run traversant une frontière y est valorisé au tarif de
  fin de run — approximation documentée, sans effet sur le ledger.
- Étendre à un futur provider horaire = saisir ses fenêtres dans l'UI.

## Preuves

- Simulation d'équivalence sur les 1440 minutes du jour entre les deux
  représentations du même tarif (base creuse + fenêtres pleines vs base
  pleine + fenêtres creuses enjambant minuit).
- `tests/unit/domains/llm/test_pricing_time_slots.py` (38 tests : bornes,
  minuit, chevauchements, round-trip JSONB), `test_schemas_time_slots.py`,
  sections dédiées de `test_service.py`, `test_pricing_cost_computation.py`
  et `test_pricing_cache_tokens.py` (compat blob Redis dans les deux sens) ;
  côté web, `admin-llm-pricing-helpers.test.ts` et
  `ModelPricingModal.test.tsx`.
