# ADR-223 : un tarif qui varie avec l'heure est porté par la ligne de prix, pas par le code

**Statut**: ✅ IMPLEMENTED (2026-08-17) — amendé le 2026-09-23 (jours de la semaine, voir la fin)
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

## Amendement 2026-09-23 — une fenêtre porte aussi ses jours

**Constat.** La page tarifaire de DeepSeek, relue le 2026-09-23, dit : « Peak
hours are 01:00 - 04:00 and 06:00 - 10:00 UTC, Monday through Friday, excluding
Chinese public holidays » — « All other hours are off-peak, including
weekends ». Les fenêtres n'avaient pas de jour : chaque appel du samedi ou du
dimanche dans ces heures était valorisé au tarif plein, deux fois ce que le
fournisseur facture, et deux fois ce qu'il prélève des plafonds ADR-272.
`LLM_PROVIDERS.md` écrivait déjà « en semaine » pendant que le code appliquait
les fenêtres tous les jours. Mesuré en dev : les tours ReAct du week-end dans
ces heures coûtaient environ 0,02 € au lieu de 0,01 €. La prod porte les mêmes
fenêtres sur trois modèles — `deepseek-flash`, `deepseek-v4-flash` et
`deepseek-v4-pro`, ce dernier saisi par l'interface d'administration.

**Décision.**

1. **Une fenêtre peut nommer ses jours** : `weekdays`, jours ISO (1 = lundi …
   7 = dimanche) du jour UTC où la fenêtre **commence**. Une fenêtre qui passe
   minuit appartient à son jour de début : vendredi 22:00 → 02:00 couvre le
   samedi jusqu'à 02:00, et celle du dimanche déborde sur le lundi. Sans jours,
   la fenêtre vaut tous les jours — comportement antérieur inchangé, et la clé
   n'est pas écrite. **Une seule orthographe** (`canonical_weekdays`) : triée,
   dédoublonnée, la semaine entière s'écrit « pas de jours » ; une liste vide
   est refusée (422, comme une fenêtre de longueur nulle) ; un booléen n'est
   pas un jour (entiers stricts).
2. **Résolution et chevauchement sur le cercle de la semaine** (10 080 minutes),
   une seule projection (`_week_segments`) pour les deux ; l'équivalence entre
   « pas de jours » et « les sept jours » est épinglée sur les 10 080 minutes.
   La même heure sur des jours disjoints ne se chevauche pas — un tarif de
   semaine et un tarif de week-end pour la même fenêtre est exactement ce que
   les jours permettent. Un jour stocké corrompu fait ignorer la fenêtre (tarif
   de base), comme toute entrée corrompue ; une fenêtre stockée de longueur
   nulle ne couvre plus rien (elle couvrait la journée entière).
3. **Administration** : le sélecteur de jours de l'éditeur de récurrence est
   extrait en composant partagé (`components/recurrence/WeekdayToggleGroup`,
   règle « jamais zéro jour », raccourcis tous les jours / en semaine /
   week-end, coupure avant le week-end), désormais groupe accessible nommé ;
   chaque fenêtre du dialogue Tarifs LLM le porte. Une fenêtre « tous les
   jours » n'envoie aucun jour.
4. **Classeur (ADR-228, format v4)** : colonne `weekdays` sur l'onglet des
   plages (codes `mon`…`sun`, liste de référence), résumé des fenêtres avec
   leurs jours sur la ligne du modèle. Un fichier v3 est refusé par sa version :
   lu comme « tous les jours », il remettrait chaque week-end au tarif plein.
5. **Données** : migration `e4a7c2f9b1d6` et graine de référence alignées,
   tenues égales par un garde. **Exception au §5, approuvée par le propriétaire
   le 2026-09-23** : la migration corrige les lignes en place, mais seulement
   les tarifs ACTIFS du fournisseur DeepSeek (clé fournisseur et non liste de
   noms, qui aurait oublié `deepseek-v4-pro`), et seulement les fenêtres aux
   heures publiées qui ne portent pas encore de jours — une fenêtre retaillée
   par un administrateur reste la sienne, une seconde exécution ne change rien.
   Le retour arrière, lui, retire TOUS les jours, quel qu'en soit l'auteur,
   comme on supprime une colonne : la révision précédente n'en lit aucun (son
   `TimeSlotPrice` refuse une clé inconnue, donc un seul jour laissé en place
   casserait sa liste d'administration) et sa tarification les ignorait déjà.
6. **Le cache des prix se reconstruit depuis la base au démarrage** : il
   partait du blob Redis quand il en existait un, et un worker garde ses prix
   en mémoire toute sa vie. Mesuré en dev : l'API redémarrée après la migration
   a repris un blob de 47 minutes et facturait encore le samedi au double.
   Seule l'invalidation entre workers (ADR-063) adopte le blob, que le worker
   écrivain vient de republier. Un démarrage dont la lecture de la base échoue
   adopte le blob publié plutôt que rien : un tarif ancien vaut mieux qu'un
   coût nul pour toute la vie du worker.
7. **Chaque écrivain de tarifs prévient tous les workers.** Créer, modifier,
   désactiver un tarif, importer le classeur, recharger le cache — et écrire
   le taux USD→EUR (route d'administration, synchronisation quotidienne),
   avec lequel le cache convertit chaque coût en euros — appellent, APRÈS
   leur `commit`, `refresh_and_publish_pricing_cache` : reconstruction depuis
   la base, PUIS publication de l'invalidation ADR-063 — jamais après une
   reconstruction ratée. Défaut antérieur trouvé par la revue : ces écrivains
   ne reconstruisaient que LEUR worker ; avec `WEB_CONCURRENCY=4`, un tarif
   modifié n'atteignait qu'un worker sur quatre, les trois autres facturant
   l'ancien prix jusqu'à leur redémarrage — une correction de jours de la
   semaine faite dans l'interface aurait donc été appliquée une fois sur
   quatre. Les écrivains du taux ne reconstruisaient même pas leur propre
   worker : un taux synchronisé n'atteignait aucun coût avant un redémarrage.
   Le rechargement ne vide plus la copie locale avant de reconstruire :
   une reconstruction ratée laissait le worker facturer chaque appel à zéro.

**Limites assumées.**

- Les jours fériés chinois ne sont pas exprimés (décision du propriétaire) :
  ils restent valorisés au tarif plein — une surestimation, jamais l'inverse.
- Le registre déjà écrit (`token_usage_logs`) n'est pas réécrit : les
  surestimations passées du week-end restent dans l'historique, qui fait foi à
  l'instant de l'appel.
- Pendant un déploiement progressif, un ancien worker ignore les jours
  (comportement antérieur) et sa liste d'administration peut échouer le temps
  de la bascule (`extra="forbid"`).

**Preuves.** Docker dev, par le service de tarification réel : un même appel
ReAct à 02:00 UTC coûte 2,00 fois plus le mardi que le samedi, pour les trois
modèles DeepSeek ; le cache synchrone du suivi de jetons applique les jours
après redémarrage. Classeur réel du catalogue dev (136 modèles, 6 fenêtres)
écrit, relu sans anomalie, réimporté tel quel sans aucun changement. Migration
exécutée sur PostgreSQL réel (`tests/integration/test_deepseek_peak_weekdays_migration.py`),
rejeu depuis une base vide (`db:migrate:replay-check`), parcours navigateur
réel à 390 px (`e2e/smoke/admin-pricing-time-slot-days.spec.ts`).
