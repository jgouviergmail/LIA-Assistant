# Lot 5 — Une veille a une fin, et un courriel attendu mérite la minute

**Spécification** : [design](../specs/2026-09-11-anticipated-moments-design.md) §9
**Méthode** : TDD strict. Inline, aucun sous-agent, aucune action git.

---

## Le manque, mesuré

Une « veille » est une routine `trigger_kind=condition` : elle évalue sa
condition à chaque tick et ne s'exécute que si le fait est neuf. Le mécanisme
existe. Deux choses lui manquent, et les deux sont vérifiées dans le code :

1. **Aucune fin.** `ScheduledAction` n'a pas de colonne d'expiration. La requête
   des routines dues filtre sur `is_enabled` et `status`, et rien ne les passe à
   faux sauf un échec répété (`consecutive_failures`) ou la personne. Une veille
   posée pour un courriel qui n'arrivera jamais tourne pour toujours — et une
   veille est exactement le genre de chose qu'on pose puis qu'on oublie.
2. **Aucune urgence.** La condition n'est évaluée qu'au tick de la récurrence,
   plafonnée à douze par jour (ADR-268). « Préviens-moi quand Marie répond »
   attend donc jusqu'à deux heures, alors que le balayage des réveils ADR-261
   tient déjà le delta Gmail en main, à la minute, et ne fait rien de ces
   veilles. `TriggerKind` documente d'ailleurs le vrai événementiel comme « une
   phase 2 » : c'est celle-ci.

---

## T5.1 — Une routine finie se ferme

> **Correction apportée pendant l'implémentation.** Ce lot devait ajouter une
> colonne `scheduled_actions.expires_at`. Elle a été écrite, appliquée en dev,
> puis **retirée avant livraison** — la migration supprimée et la base de dev
> ramenée en arrière.
>
> La raison, vérifiée dans le code plutôt que supposée : `SeriesEnd`
> (`core/recurrence/spec.py`) répond déjà à « quand cette série s'arrête »,
> avec trois formes (`never`, `on_date`, `after_count`). Prouvé en exécutant le
> moteur : passé `end.on_date`, `next_occurrence` rend `None`. Et ce
> `SeriesEnd` est stocké, validé, **éditable dans le studio**
> (`RecurrenceEditor.tsx`) et **raconté en six langues** (`describe`).
>
> `expires_at` aurait donc été une **seconde autorité** sur la fin d'une
> routine, dont une seule des deux aurait été montrée à la personne.

Ce qui manquait vraiment n'était pas une borne, c'était une **fermeture** :

- une série finie porte `next_trigger_at = NULL` — la définition du modèle —
  et la requête des routines dues l'exclut par construction, `NULL <= now()`
  valant UNKNOWN en SQL (donc **aucun filtre à écrire**) ;
- mais rien ne fermait la ligne : elle restait activée et « active » pour
  toujours, indiscernable d'une routine mise en pause ;
- `close_finished()` la passe à `is_enabled = False`, `status = COMPLETED`,
  à l'étape 0b du tick de l'exécuteur — désactivée, jamais supprimée.

Le gain est plus large que la colonne abandonnée : la fermeture couvre les
**trois** façons dont une série se termine, pas seulement une date.

**Tests** : ce que SQL fait d'un déclencheur NULL (la prémisse, vérifiée contre
un vrai PostgreSQL) ; une routine encore armée reste due ; une routine finie est
fermée, avec le bon statut et non supprimée ; la fermeture est idempotente ; une
routine en pause est laissée tranquille ; une routine en cours d'exécution
aussi.

## T5.2 — Le réveil sert les veilles courriel

Dans le balayage ADR-261, une fois le delta Gmail en main et **avant** de rendre
la main : évaluer les veilles `mail_match` de ce compte contre CE delta.

Trois règles :

- **aucune lecture de plus.** Les messages sont déjà là ; ré-appeler
  `fetch_mails` serait payer deux fois ce que la passe tient.
- **l'empreinte de déduplication est celle de l'exécuteur**, pas une seconde :
  une veille servie par le réveil ne doit pas re-tirer au tick suivant.
- **le réveil ne fait pas tourner la routine.** Il avance `next_trigger_at` à
  maintenant ; l'exécuteur, qui est le seul à savoir exécuter une routine, la
  prend au tick suivant. Un second exécuteur serait une seconde autorité sur ce
  qui tourne pour le compte de quelqu'un.

**Tests** : une veille dont la condition matche le delta est armée ; une qui ne
matche pas ne l'est pas ; une veille non `mail_match` est ignorée ; un compte
sans veille ne coûte rien ; l'empreinte empêche le double tir ; une erreur
n'arrête pas le réveil.

**Ajouté pendant l'implémentation**, après vérification du code :

- **l'armement dépasse le TTL publié du cache de recherche Gmail** (60 s). Sans
  cela, l'exécuteur (qui tourne lui aussi toutes les 60 s) pouvait être servi
  par un cache antérieur au courriel, répondre « non remplie », et **consommer**
  l'armement en repartant vers son créneau suivant ;
- **`SKIP LOCKED`** : une ligne que l'exécuteur détient verra son échéance
  réécrite à la fin de son passage ; l'armer serait une écriture perdue, et
  attendre mettrait le réveil derrière la transaction de quelqu'un d'autre ;
- **un test de concordance** entre les deux lectures de « ce courriel
  correspond-il » (ressource Gmail brute contre projection d'affichage), sur
  onze courriels logiques, avec la seule divergence légitime écrite.

## T5.3 — Le geste

Une puce « Surveiller » sur les cartes de courriel du briefing, composant la
condition et appelant `POST /scheduled-actions`. i18n × 6.

Le passage par l'API plutôt que par une intention de chat n'est pas un choix de
confort : `create_scheduled_action_tool` ne crée que des routines `time`, et son
en-tête reporte explicitement l'écriture de conditions en langage naturel.

**Ajouté pendant l'implémentation** : la puce **lit ce que le compte détient
avant d'écrire**. Deux courriels du même expéditeur sont ordinaires, et cliquer
sur les deux aurait créé deux veilles identiques — chacune consommant un des
vingt créneaux et chacune notifiant, donc une seule réponse attendue annoncée
**deux fois**. C'est l'agacement même que ce programme existe pour éviter.

## T5.4 — Portes, migration, revue à froid

`task lint`, suites backend et frontend, cliquets.

**Aucune migration ne sort de ce lot** : la seule qui avait été écrite a été
retirée avec la colonne qu'elle ajoutait, et la base de dev ramenée à
`c7e3b2d5f1a8`, tête unique. `ScheduledActionStatus.COMPLETED` n'en demande
pas : `status` est une colonne `String(20)` portant un énuméré Python, jamais un
type SQL natif.

Aucune variable `.env` nouvelle non plus — l'armement lit un réglage qui
existait déjà (`EMAILS_CACHE_SEARCH_TTL_SECONDS`).
