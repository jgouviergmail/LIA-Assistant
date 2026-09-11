# Proactivité par moments anticipés — spécification

**Statut** : validée par le propriétaire le 2026-09-11 (analyse en trois passes,
arbitrages ci-dessous pris par défaut).
**Périmètre** : rendre LIA capable de revenir vers la personne **à un instant
attendu** plutôt qu'au rythme d'une horloge, et de tenir le fil de ce qu'elle a
demandé.
**Hors périmètre, traité en dernier et séparément** : l'appel vocal *vers* la
personne (spécification propre, lot final).

---

## 1. Intention réelle derrière le besoin

Le besoin exprimé — « que LIA demande si la réunion s'est bien passée » — n'est
pas une source d'information de plus. C'est trois capacités que le système n'a
pas :

1. **réagir à un instant** (la fin d'un événement) et non à un tick de 30 min ;
2. **savoir de quoi elle parle** quand la personne répond ;
3. **tenir un fil** : ce qu'elle savait avant, ce qu'elle apprend après.

Le débrief post-réunion est le premier cas d'une famille. La spécification pose
la famille, puis ses membres.

---

## 2. Faits vérifiés dans le code (aucune extrapolation)

| Fait | Preuve |
|---|---|
| La fenêtre calendrier du heartbeat part de `now` vers l'avant : un événement terminé est invisible | `context_aggregator.py:508`, `HEARTBEAT_CONTEXT_CALENDAR_HOURS_DEFAULT = 4` (`constants.py:2296`) |
| Le nudge « veux-tu que je prépare cette réunion » n'existe qu'AVANT (règle 21) | `heartbeat_decision_prompt.txt` |
| Le tick ne peut pas servir un instant : 30 min, lot de 50 comptes tirés au hasard, lissage probabiliste | `constants.py:2175`, `runner.py:63`, `runner.py:402` |
| Servir UN compte hors tirage, sous éligibilité complète, a un précédent complet | `heartbeat_wake_sweep.py`, `runner.py:418` (`skip_probabilistic_gate`) |
| Aucun fournisseur de push ne signale « événement terminé » | `push_channels/models.py:20` |
| Les routines CONDITION `calendar_event` répondent « un événement COMMENCE dans la fenêtre » | `condition_evaluators.py:149` |
| Une réunion enregistrée par LIA envoie déjà un message post-réunion, liée par `calendar_event_id` | `meetings/processing.py:443`, `meetings/models.py:184` |
| Rien n'empêche d'interrompre pendant une réunion : seul le cooldown d'activité existe | `infrastructure/proactive/eligibility.py` |
| Les trois fournisseurs de calendrier normalisent `attendees` dans la forme Google, avec `responseStatus` | Google natif ; `microsoft_calendar_normalizer.py:60-78` (`_EVENT_SELECT_FIELDS` inclut toujours `attendees` + `organizer`) ; `calendar_normalizer.py:135` (PARTSTAT) |
| `fetch_agenda` renvoie un projeté d'AFFICHAGE (`start_local` chaîne, ni `id` ni participants) : inutilisable pour dater ou dédoublonner | `briefing/schemas.py:200`, `briefing/fetchers.py:243` |
| Une routine a bien une fin (`SeriesEnd` : `never` / `on_date` / `after_count`), mais rien ne FERME la ligne : elle reste activée et « active » pour toujours | `core/recurrence/spec.py:248` ; prouvé en exécutant le moteur — passé `end.on_date`, `next_occurrence` rend `None` — et `scheduled_actions/repository.py` ne remet jamais `is_enabled` à faux hors échecs répétés |

### 2.1 Le faux négatif corrigé — la boucle de réponse EXISTE

L'analyse initiale affirmait que la notification proactive n'entre jamais dans
l'état que le graphe lit, et proposait de l'y écrire. **C'est faux, et le
mécanisme existant est complet** :

`OrchestrationService._inject_proactive_messages`
(`agents/services/orchestration/service.py:203`), appelé par
`load_or_create_state` (`:538`), lui-même appelé sur l'unique chemin de tour
(`agents/api/service.py:806`) :

- lit `conversation_messages` dont `role = assistant` et
  `metadata.type LIKE 'proactive_%'`, créés **après le `created_at` du dernier
  point de reprise** (`conversations/repository.py:1008`) ;
- passe par `visible_only`, donc les lignes cachées d'un run de ticket ne
  remontent jamais ;
- les convertit en `AIMessage` portant `additional_kwargs.proactive_notification`
  et les insère **avant** le `HumanMessage` du tour (`:547`) ;
- borné par `PROACTIVE_INJECT_MAX_MESSAGES` (5) et
  `PROACTIVE_INJECT_LOOKBACK_HOURS` (24) — publiés dans `.env.example:1276` ;
- fail-open intégral.

Conséquences, toutes trois vérifiées par lecture :

1. le routeur, le planificateur, le nœud de réponse et les six extractions
   post-réponse voient la question de LIA, puisqu'elles lisent toutes
   `state["messages"]` ;
2. la double injection est impossible par construction : le tour persiste ces
   `AIMessage` dans le point de reprise, donc le `created_at` du point de
   reprise suivant est postérieur ;
3. le chemin canal externe (Telegram) et le moteur hors tour passent par
   `stream_chat_response`, donc en héritent.

**Le lot « boucle de réponse » est supprimé du programme.** Ce qui le remplace :
un test de caractérisation qui épingle ce comportement (lot 1, tâche 1.0), parce
qu'un mécanisme dont dépend tout le programme et que rien ne teste explicitement
est un mécanisme qui peut disparaître sans bruit.

---

## 3. Ce qui est réutilisé, et ne doit pas être réinventé

| Besoin | Brique existante |
|---|---|
| Servir un compte nommé, hors tirage, sous éligibilité complète | `ProactiveTaskRunner(user_ids=[...], skip_probabilistic_gate=True)` |
| Décider de parler ou se taire, anti-redondance, personnalité, psyché, quota, audit, pouce | `HeartbeatProactiveTask` + `heartbeat_decision_prompt` |
| Dire au modèle pourquoi il est réveillé maintenant | `HeartbeatContext.wake_trigger` + `fresh_section` |
| Ne pas relancer deux fois sur le même ticket / la même boucle | `_bump_used_workboard`, `_bump_used_open_loops` |
| Réclamation atomique à deux acteurs | `WorkboardRepository` (`with_for_update(skip_locked=True)` + UPDATE conditionnel) |
| Jitter obligatoire sur tout job périodique | `jitter_seconds_for` (ADR-254) |
| La personne répond, LIA comprend | `_inject_proactive_messages` (§2.1) |
| Registres | `record_surface_consultations`, effets hors tour, `CLIENT_CALL_RECORDERS` |

---

## 4. Décision d'architecture

### 4.1 Une table, un registre de genres, un balayage

**`proactive_moments`** : une ligne = « à tel instant, il y aura quelque chose à
dire à telle personne à propos de telle chose ».

**Le registre des genres** (`domains/moments/kinds.py`) déclare, pour chaque
genre : son détecteur, sa règle d'échéance, sa section de prompt, son libellé
i18n, ses dépendances de capacité. Un assert de complétude au boot refuse un
genre incomplet (doctrine ADR-085).

**Un seul job périodique** (`infrastructure/scheduler/moment_sweep.py`) fait, par
passe et par compte éligible : **détecter, insérer, réclamer, servir**.

Détecter et enregistrer dans la même passe est une décision, pas un raccourci :
`fetch_agenda` étant un projeté d'affichage (§2), l'enregistrement demande une
lecture calendrier propre ; en faire une passe séparée doublerait ces lectures
sans rien apprendre de plus.

### 4.2 Le moment est SERVI par le heartbeat, il n'est pas une source de plus

`HeartbeatProactiveTask(moment=...)`, exactement comme `wake=...` :
`HeartbeatContext.moment` est posé après `aggregate()`, rendu comme une section
FRESH en tête du prompt, et la ligne d'audit porte `trigger = "moment"`.

Conséquences voulues : le moment hérite de l'anti-redondance, de la personnalité,
de la voix intérieure, du quota, de l'historique et du pouce, sans une ligne de
code de plus. Et le modèle garde le droit de **se taire** : un moment est une
occasion de parler, jamais une obligation.

**Un moment exige `heartbeat_enabled`.** Il est servi par le heartbeat : le
refuser à un compte qui a éteint la proactivité n'est pas une restriction, c'est
la seule lecture cohérente de son choix. Publié dans les réglages.

**Ce qu'un moment contourne, et pourquoi — revue adversariale du 2026-09-11.**
`HeartbeatProactiveTask.check_eligibility` applique aujourd'hui le report de
rythme (`should_defer_tick_for_rhythm`, ADR-214 §11.2) et se verra ajouter la
garde « en réunion » (§8). Les deux **différeraient un moment vers plus tard**,
c'est-à-dire vers jamais : un moment porte une fenêtre de validité courte, et le
différer de deux heures le fait expirer sans être servi. Un tick reporté revient ;
un moment reporté meurt.

Donc, quand `self.moment is not None`, `check_eligibility` répond sur le seul
drapeau du compte. Rien d'autre n'est contourné : fenêtre horaire, quota du jour,
cooldown global, cooldown croisé et cooldown d'activité sont tenus par
`EligibilityChecker` et s'appliquent intégralement, comme pour un réveil push.
Un test nomme cette décision, dans les deux sens.

**Le moment déclare son label.** `ANTICIPATED_MOMENT` rejoint le Literal
`HeartbeatSourceLabel` : sans lui, la décision n'a aucun moyen de dire qu'elle
s'est appuyée sur le moment, l'anti-redondance de niveau source est aveugle et
les statistiques par source sous-comptent. Ce Literal est distinct de
`HEARTBEAT_SOURCE_ORDER` (le vocabulaire des interrupteurs, tenu par
`test_frontend_source_labels.py`), donc l'ajout ne crée aucune dette de parité
front.

**Pas de nouvelle clé dans `HEARTBEAT_SOURCE_KEYS`.** Les interrupteurs des
sources répondent à « de quoi LIA a le droit de m'interrompre » ; les genres
répondent à « à quels moments LIA revient vers moi ». Ce sont deux questions, et
les mélanger produirait deux niveaux d'interrupteur pour un seul effet.

### 4.4 Une capacité, un commutateur (ADR-280)

Les moments sont une fonctionnalité que la personne éprouve : ils exigent donc
`PlatformCapability.MOMENTS`, son plafond `settings.moments_enabled`, sa clé
`SystemSettingKey`, son libellé, sa famille, et son entrée dans la liste
`EXPECTED_CAPABILITIES` que tient une personne
(`tests/unit/domains/feature_switches/test_capability_coverage.py`). Le
commutateur est lu **au moment du balayage** (`is_capability_enabled`, à chaud),
jamais `settings.moments_enabled` en dur : un commutateur basculé après le
démarrage doit prendre effet sans redémarrage.

### 4.3 Le score d'importance est déterministe et publié

Aucun appel de modèle pour décider s'il faut réveiller : c'est le résultat mesuré
de « Do proactive agents really need an LLM to decide when to wake » (un
déclencheur déterministe bat un LLM en F1 et en latence de deux ordres de
grandeur), et c'est déjà la doctrine ADR-261 (« pas de pré-filtre LLM : dépenser
un appel pour décider d'un appel, c'est le bruit »).

Le score vit dans `domains/moments/importance.py`, pur, et ses seuils sont des
réglages publiés (ADR-184).

---

## 5. Le registre des genres

| Genre | Détecteur (lit) | Échéance `due_at` | Validité `not_after` | Clé `source_ref` |
|---|---|---|---|---|
| `event_followup` | calendrier du fournisseur actif | fin + `MOMENTS_EVENT_FOLLOWUP_DELAY_MINUTES` (15) | + `MOMENTS_EVENT_FOLLOWUP_WINDOW_MINUTES` (180) | id d'événement du fournisseur |
| `deadline_eve` | `workboard_tickets` tenus par la personne, `open_loops.due_hint` | veille locale à l'ouverture de la fenêtre horaire | fin de la fenêtre du jour | `ticket:{uuid}` / `loop:{uuid}` |
| `counterparty_silence` | `open_loops` `waiting_on_other` sans mouvement depuis un palier | ouverture de la fenêtre horaire | fin de la fenêtre du jour | `loop:{uuid}:{palier}` |
| `return_from_absence` | marqueur de présence (`presence:last:{uid}`) | immédiat | +120 min | `absence:{date locale}` |

Le lot 1 ne livre que `event_followup`. Le registre existe dès le lot 1 avec un
seul membre : c'est ce qui rend le lot 4 additif au lieu de refondateur.

### 5.1 Le score de `event_followup`

Un événement mérite un débrief si **toutes** les conditions nécessaires tiennent
et si le total des points atteint `MOMENTS_EVENT_FOLLOWUP_MIN_SCORE` (2).

Nécessaire (une seule qui manque, pas de moment) :
- au moins un participant autre que la personne ;
- durée supérieure ou égale à `MOMENTS_EVENT_MIN_DURATION_MINUTES` (30) ;
- pas un événement « journée entière » ;
- la personne n'a pas décliné (`responseStatus != "declined"`) ;
- l'événement n'est pas annulé (`status != "cancelled"`).

Points :
- 1 point : au moins deux participants autres que la personne ;
- 1 point : un lieu ou un lien de visioconférence ;
- 1 point : la personne est organisatrice ;
- 1 point : un participant est une relation favorite (`relation_favorites`) ;
- 1 point : un ticket ouvert ou une boucle ouverte cite un participant.

Exclusions dures :

- un événement dont une réunion LIA porte le `calendar_event_id`
  (**arbitrage 1**, valeur retenue : exclusion, le compte rendu tient déjà lieu
  de retour) ;
- un événement **suivi d'un autre** événement à participants qui commence dans
  les `MOMENTS_EVENT_CHAIN_GAP_MINUTES` (15) après sa fin. C'est la règle de
  fusion des blocs enchaînés, et elle appartient au détecteur, pas au service :
  trois réunions d'affilée ne produisent qu'un moment, celui du bloc, sinon
  l'anti-redondance ferait le tri après coup en ayant déjà dépensé deux
  décisions et occupé deux places de quota.

---

## 6. Modèle de données

```
proactive_moments
  id                uuid PK
  user_id           uuid FK users(id) ON DELETE CASCADE, indexé
  kind              varchar(32)  NOT NULL
  source_ref        varchar(255) NOT NULL
  due_at            timestamptz  NOT NULL
  not_after         timestamptz  NOT NULL
  state             varchar(16)  NOT NULL DEFAULT 'pending'
  claim_owner       varchar(64)  NULL
  claimed_at        timestamptz  NULL
  settled_at        timestamptz  NULL
  skip_reason       varchar(64)  NULL
  payload           jsonb        NOT NULL DEFAULT '{}'
  created_at/updated_at (TimestampMixin)

  UNIQUE (user_id, kind, source_ref)
  INDEX partiel (due_at) WHERE state = 'pending'
```

États : `pending` vers `claimed` vers `served | skipped | expired | cancelled`.

`payload` porte le strict nécessaire pour **dédoublonner et scorer**, pas pour
rédiger : `{title, start, end, score, reasons[], attendee_count}`. Ni adresse de
courriel, ni nom de participant, ni corps d'événement — la revalidation de
l'étape 4 relit l'événement de toute façon, donc stocker les personnes serait de
la donnée personnelle conservée pour rien. Le titre y est parce que la règle de
fusion des blocs et le journal d'exploitation en ont besoin.

Ce n'est pas un registre : les lignes closes sont purgées après
`MOMENTS_RETENTION_DAYS` (30). La trace durable, c'est `agent_effects` et
`heartbeat_notifications`.

---

## 7. Le balayage

`SCHEDULER_JOB_MOMENT_SWEEP`, leader-élu, intervalle
`MOMENTS_SWEEP_INTERVAL_MINUTES` (5), **jitté** (ADR-254), `max_instances=1`.

Par passe :

0. **Purge** des lignes closes hors rétention et **expiration** des `pending`
   dont `not_after < now` (une instruction bornée chacune).
1. **Sélection des comptes** : `moments_enabled` d'instance, compte actif, au
   moins un genre non refusé, **dans sa fenêtre horaire heartbeat**, non inactif
   au-delà de `HEARTBEAT_INACTIVE_SKIP_DAYS`. Hors fenêtre, rien n'est ni détecté
   ni servi : un moment détecté ne serait jamais servi et coûterait une lecture.
2. **Détection** : pour chaque genre actif du compte, le détecteur produit des
   candidats ; insertion en `ON CONFLICT (user_id, kind, source_ref) DO NOTHING`.
3. **Réclamation** : `FOR UPDATE SKIP LOCKED` et UPDATE conditionnel dans la même
   transaction, jeton propriétaire, **un moment à la fois par compte**.
4. **Revalidation** : le genre revalide son fait (pour `event_followup` :
   `get_event`, annulé, déplacé ou décliné donne `cancelled`).
5. **Service** : `ProactiveTaskRunner(task=HeartbeatProactiveTask(moment=...),
   user_ids=[uid], skip_probabilistic_gate=True)`. Fenêtre, quota du jour,
   cooldown global, cooldown croisé, cooldown d'activité s'appliquent **tous**.
6. **Règlement explicite** : `served` si une notification est partie, `skipped`
   avec une raison bornée sinon (`not_eligible`, `llm_skip`, `quota`,
   `cancelled`, `revalidation_failed`). Jamais depuis l'absence d'exception.

Chaque ligne finit dans exactement un état, et chaque état est compté.

---

## 8. La garde « en réunion »

Dans `HeartbeatProactiveTask.check_eligibility`, après le drapeau et avant le
scoring de rythme : si un événement avec au moins un participant autre que la
personne est **en cours** à cet instant, différer.

- lecture par le cache de l'agenda (aucune lecture supplémentaire quand elle est
  chaude), fail-open intégral ;
- réglage propre `MOMENTS_BUSY_GUARD_ENABLED`, défaut ON (c'est une réduction de
  bruit, pas une capacité nouvelle) ;
- métrique `heartbeat_ticks_deferred_total` — elle existe déjà avec un libellé
  `day_class` : elle sera **étendue** d'un libellé `reason`, pas dupliquée ;
- **un moment n'est jamais différé par cette garde** : un débrief se sert
  précisément quand la réunion vient de finir, et un moment porte déjà sa propre
  fenêtre de validité.

---

## 9. Les veilles (« surveille ceci »)

Une veille est une routine `trigger_kind=condition` que la personne crée d'un
geste depuis une carte. Trois manques réels, trois correctifs :

1. **Une routine finie se ferme.** *(Corrigé en implémentation : une colonne
   `expires_at` était prévue ici ; elle aurait été une SECONDE autorité sur la
   fin d'une routine, à côté d'un `SeriesEnd` déjà stocké, validé, éditable
   dans le studio et raconté en six langues. Elle a été écrite puis retirée.)*
   Les trois formes de fin aboutissent au même `next_trigger_at = NULL`, que la
   requête des routines dues exclut par construction ; ce qui manquait était la
   **fermeture** de la ligne, que l'exécuteur fait désormais à son étape 0b
   (`is_enabled = False`, `status = COMPLETED`) — désactivée, jamais supprimée.
2. **Un courriel attendu mérite la minute, pas le tick.** Le balayage des
   réveils ADR-261 tient déjà le delta Gmail en main : il évalue les veilles
   `mail_match` du compte **avec ce delta**, sans lecture supplémentaire. C'est
   la « phase 2 événementielle » que `TriggerKind` documente comme à venir.
3. **Le geste.** Une puce « Surveiller » sur les cartes de courriel, d'agenda et
   de boucle ouverte compose la condition et appelle `POST /scheduled-actions`.

Auteur `scheduled` par construction : les registres sont justes sans code.
Créer une veille depuis le chat reste hors périmètre (extension différée de
`create_scheduled_action_tool`, documentée comme telle dans son module).

---

## 10. Registres, quotas, coûts

| Question | Réponse |
|---|---|
| Qui paie la décision et le message | Poste LLM du heartbeat, clé d'instance : les deux plafonds d'ADR-272 s'appliquent déjà par le runner (`is_user_blocked_for_llm`) |
| Combien de jetons de plus | Zéro pour décider de réveiller (score déterministe). Un moment servi coûte un cycle heartbeat, avec un contexte plus petit qu'un tick complet |
| Combien de notifications de plus | Aucune : le moment consomme le quota heartbeat du jour (**arbitrage 2**, valeur retenue : quota partagé) |
| Lecture de données personnelles | Surface `moment` déclarée dans `CONSULTATION_SURFACES` et `CONSULTATION_RECORDERS` ; module détecteur énuméré dans `CLIENT_CALL_RECORDERS` |
| Commutateur d'exploitation | `PlatformCapability.MOMENTS` (§4.4), lu à chaud au balayage |
| Où se règlent les genres | Sur l'API des réglages heartbeat déjà en place (`GET/PATCH /heartbeat/settings`), enrichie de `moment_kinds_disabled`, `all_moment_kinds` et `moment_kind_dependencies` — un routeur de plus pour trois champs serait une deuxième autorité sur les mêmes réglages |
| Action de LIA | L'effet est déjà réclamé et réglé par le runner (`out_of_turn_effects`) |
| Clés Redis | `moments:agenda:{uid}` (`USER_CACHE`), déclarée dans `key_families.py` |
| Route de dépense | Inchangée : `heartbeat/prompts.py` reste `CALLER` de `proactive_task.py` |

---

## 11. Front

- **Réglages « Moments »**, sous les notifications proactives : un interrupteur
  par genre, avec sa dépendance publiée par l'API (`event_followup` requiert un
  connecteur calendrier), replié par défaut.
- **Historique** : libellé `trigger_moment` à côté de `trigger_push`
  (`HeartbeatHistory.tsx:92`).
- **Puces de réponse** sous la bulle, alimentées par les métadonnées, envoyées
  par `?intent=` (**arbitrage 3**, valeur retenue : le libellé de la puce EST la
  demande, donc envoi — contrat ADR-173, rejeu interdit ADR-210). Boutons
  natifs, nom accessible traduit, empilés sous `sm`, jamais porteurs du sens par
  la couleur seule.
- **Puce « Surveiller »** sur les cartes de courriel, d'agenda et de boucle.
- i18n en six langues, `zh` incluse, parité stricte.

---

## 12. Cas limites (à couvrir par des tests, pas par de la prose)

Événement annulé, déplacé ou décliné entre la détection et l'échéance. Réunions
enchaînées (un seul débrief à la fin du bloc). Instance d'une récurrence
(`singleEvents=True`, id suffixé). Réunion qui déborde sur la suivante. Fin à
21:50 avec fenêtre close à 22:00 (**arbitrage 4**, valeur retenue : expiration,
pas de report au lendemain, « hier soir » n'est plus un moment). Personne
absente plusieurs jours. Compte inactif. Plafond de dépense atteint (journalisé
« skipped », jamais « failed », ADR-272). Redis ou fournisseur indisponible.
Deux workers. Changement d'heure et fuseau de la personne. Réunion enregistrée
par LIA. Participants sans nom d'affichage. La personne écrit d'elle-même avant
l'échéance (cooldown d'activité, puis expiration naturelle). Un moment et un tick
sur le même ticket (compteurs de relance partagés).

---

## 13. Plan de test directeur

| Niveau | Cibles |
|---|---|
| Caractérisation | `_inject_proactive_messages` : une notification archivée après le point de reprise remonte en `AIMessage` avant le `HumanMessage` ; une ligne cachée ne remonte pas ; le plafond et la fenêtre sont ceux des réglages |
| TU purs | score d'importance (table de cas exhaustive) ; échéances et validité avec changement d'heure ; fusion des blocs enchaînés ; complétude du registre des genres dans les deux sens |
| TU backend | source `moment` du contexte (rendu du prompt, `has_meaningful_context`, `trigger`) ; garde « en réunion » ; détecteurs ; règlement explicite ; gardes transverses (clés Redis, dépense, surfaces, appelants directs, jitter, fuseau, taille de fichier, métriques, capacité) |
| Intégration PostgreSQL | réclamation à deux acteurs ; unicité ; expiration ; purge ; règlement tardif ignoré par le jeton |
| Intégration runner | l'éligibilité complète s'applique, seul le lissage est contourné ; un refus de quota journalise « skipped » |
| Front vitest | réglages par genre, libellé d'historique, puces (rendu, nom accessible, clavier), puce « Surveiller » |
| E2E hermétique | bulle reçue par SSE mocké, clic de puce, envoi unique, rechargement sans rejeu |
| Runtime Docker | événement terminant dans deux minutes, moment détecté, servi, réponse tapée, mémoire extraite |

---

## 14. Lots

| Lot | Contenu | Dépend de |
|---|---|---|
| 0 | Mesures (**fait**) | — |
| 1 | Caractérisation de la boucle de réponse ; domaine `moments` ; migration ; registre des genres ; détecteur et score `event_followup` ; balayage ; réglages ; métriques | 0 |
| 2 | Source `moment` du heartbeat, section FRESH, règle de prompt, `trigger`, exclusion des réunions enregistrées | 1 |
| 3 | Garde « en réunion » | — |
| 4 | Genres `deadline_eve`, `counterparty_silence`, `return_from_absence` | 1 |
| 5 | Veilles : fermeture d'une routine finie, évaluation au réveil, puce « Surveiller » | — |
| 6 | Front : réglages, historique, puces | 2 |
| 7 | Docs, ADR, surfaces de release, mesure J+14 | tout |

---

## 15. Arbitrages, valeurs retenues par défaut

1. Réunion enregistrée par LIA : **pas de débrief** (le compte rendu tient lieu
   de retour).
2. Quota : **partagé** avec le heartbeat.
3. Puces : **envoi** par `?intent=`.
4. Fin hors fenêtre horaire : **expiration**, pas de report au lendemain.

Chacun est réversible par un réglage ou une ligne, et chacun est épinglé par un
test qui nomme la décision.

---

## 16. Risques et parades

| Risque | Parade |
|---|---|
| Perçu comme de la surveillance | Proposer, jamais évaluer ; une question ; aucune relance ; le pouce baissé coupe le genre ; quota partagé |
| Doublon avec le compte rendu de réunion | Exclusion par `calendar_event_id` et fenêtre anti-redondance |
| Double relance ticket ou boucle par tick et par moment | Compteurs de relance partagés, test croisé |
| Coût des lectures calendrier | Détection seulement dans la fenêtre horaire, un compte à la fois, cache court |
| Fichiers gelés (`context_aggregator.py` 690, `agents/api/service.py` 1037) | Modules neufs uniquement |
| Le registre des genres devient un fourre-tout | Assert de complétude bidirectionnel, un genre égale un détecteur pur et une table de cas |
