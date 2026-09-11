# ADR-281 — Revenir à l'instant qui compte, et servir une veille à la minute

- **Statut** : Accepté
- **Date** : 2026-09-11
- **Amende** : ADR-261 (réveil par poussée), ADR-268 (récurrence générique),
  ADR-184 (ce qui est appliqué est publié), ADR-214 (contrôle avant
  exploitation), ADR-263 (registres d'effets et de consultations), ADR-280
  (un commutateur par capacité)
- **Périmètre** : `domains/moments/` (nouveau), `proactive_moments` (nouvelle
  table), `infrastructure/scheduler/moment_sweep.py`, garde « en réunion »,
  `users.moment_kinds_disabled`, `scheduled_actions.status = completed`,
  `domains/scheduled_actions/mail_watches.py`, puce « Surveiller »

## Contexte

### Le battement ne sait pas revenir à un instant

Le battement autonome (`HEARTBEAT_AUTONOME.md`) passe toutes les trente minutes
sur un lot d'utilisateurs tiré au sort. Il est **périodique**, et c'est
exactement ce qui l'empêche de servir un instant : une réunion importante se
termine à 15 h 00, la passe suivante tombe à 15 h 22 sur un lot dont la personne
ne fait peut-être pas partie, et la question « comment ça s'est passé ? » arrive
une heure plus tard ou jamais.

Deux faits vérifiés dans le code avant d'écrire quoi que ce soit :

- la fenêtre calendrier du contexte part de `now` et regarde **devant**
  (`HEARTBEAT_CONTEXT_CALENDAR_HOURS`), donc une réunion **terminée** est
  invisible pour la décision ;
- le tick ne peut pas servir un instant : il tire un lot, il ne cible pas un
  compte.

ADR-261 avait déjà résolu la seconde moitié du problème pour les poussées
Google : `user_ids=[uid]` plus `skip_probabilistic_gate=True` sert **un** compte
sous le contrôle d'éligibilité **complet**. Le précédent existe ; il manquait
une source d'instants.

### Un faux négatif corrigé avant d'écrire du code

La première analyse concluait qu'il fallait construire la boucle de réponse —
récupérer ce que la personne répond à une notification proactive et l'injecter
dans la conversation. C'était faux : `_inject_proactive_messages`
(`agents/orchestration/service.py`) le fait déjà, borné par
`PROACTIVE_INJECT_MAX_MESSAGES` et `PROACTIVE_INJECT_LOOKBACK_HOURS`, en lisant
les notifications archivées `visible_only`. Le lot prévu a été supprimé et
remplacé par treize tests de caractérisation qui figent ce comportement
existant.

### Une veille attend jusqu'à deux heures

Une « veille » est une routine `trigger_kind=condition` : « préviens-moi quand
Marie répond ». Sa condition n'est évaluée qu'au tick de sa propre récurrence,
plafonnée à douze par jour (ADR-268) — donc la réponse arrive avec jusqu'à deux
heures de retard. Pendant ce temps, le balayage des réveils ADR-261 tient déjà
le delta Gmail **à la minute** et n'en fait rien. `TriggerKind` documente
d'ailleurs le vrai événementiel comme « une phase 2 ».

## Décision

### Une table d'instants, un registre de genres, un seul balayage

Un **moment anticipé** est une ligne de `proactive_moments` : un compte, un
genre, une référence de source, une échéance. Un balayage dédié le détecte, le
revendique, le sert et le solde.

- L'identité est `(user_id, kind, source_ref)`, en contrainte d'unicité : une
  réunion ne peut pas produire deux moments, quel que soit le nombre de passes.
- La revendication est atomique — `FOR UPDATE SKIP LOCKED` plus un `UPDATE`
  conditionnel dans la **même** transaction, avec un jeton de propriétaire, et
  le solde est conditionné à ce jeton.
- Les genres vivent dans un registre (`kinds.py`) avec une assertion de
  complétude au démarrage (ADR-085) : un genre sans détecteur refuse de
  démarrer plutôt que de disparaître en silence.
- Un moment est **revalidé** au moment d'être servi. Le monde a pu changer
  entre la détection et l'échéance : la réunion a été annulée, la personne a
  déjà écrit. Un moment qui ne tient plus est soldé `revalidation_failed`, pas
  envoyé.

### Un moment contourne les reports, jamais les garde-fous

Un moment est servi sous le contrôle d'éligibilité **complet** — fenêtre
horaire, quota quotidien, cooldowns global, croisé et d'activité. Ce qu'il
contourne est le lissage probabiliste et le rythme appris, exactement comme un
réveil ADR-261, et pour la même raison : **un instant ne se reporte pas**.
Reporter « comment s'est passée ta réunion ? » de deux heures, c'est ne pas la
poser.

*Précision du 2026-09-11* : cette phrase décrivait le réveil ADR-261 avant
que le code ne la tienne — `check_eligibility` ne contournait le rythme que
pour un moment, et un réveil était différé comme un tick (latent,
`PUSH_WAKE_ENABLED` étant faux partout). Le réveil contourne désormais le
rythme (il est consommé quand il est servi, « plus tard » voudrait dire
« perdu ») mais **s'écarte pour une réunion en cours** : le tick suivant relit
le courrier depuis l'ancre que le réveil refusé n'a pas avancée. Et le
rythme lui-même ne cache jamais un rendez-vous : le verdict d'agenda porte
le prochain début d'événement, et un tick dont l'événement tombe dans la
fenêtre de garde n'est pas différé (`heartbeat_rhythm_escapes_total`).

### La question est posée, jamais l'évaluation

La règle 23 du prompt de décision : **une** question ouverte, au plus deux
faits, l'étape suivante formulée comme une question, jamais d'évaluation de la
personne, jamais deux moments empilés, jamais deux fois la même question. Un
assistant qui commente la façon dont quelqu'un a mené sa réunion n'est pas
proche, il est pesant.

### La garde « en réunion »

Rien ne servait de revenir vers quelqu'un pendant qu'il est en réunion. La
garde (`busy_gate.py`) lit le calendrier, met son verdict en cache Redis, et
**ne compte pas une consultation sur un cache servi** : Redis a répondu, la
boîte n'a pas été ouverte (ADR-263). Une lecture qui échoue est déclarée
`failed`, jamais lue comme un silence.

Depuis le 2026-09-11 (ADR-214 c, A11) le balayage d'intérêts pose la même
question sur le même verdict mis en cache — un compte, une lecture — et
consigne sa lecture VIVE sous sa propre surface (`interest:calendar`, domaine
`event`). Le verdict porte aussi le prochain début d'événement, que le
rythme appris lit pour ne pas différer un tick qui a un rendez-vous à
servir.

### Le contrôle avant l'exploitation

Chaque genre de moment se coupe indépendamment
(`users.moment_kinds_disabled`), la capacité entière a son commutateur
(ADR-280), et la lecture est **tolérante** là où l'écriture est **stricte** :
un genre inconnu stocké par une version future est ignoré à la lecture et
refusé à l'écriture. Les commutateurs sont livrés **avec** la fonctionnalité,
jamais après (ADR-214).

### Une routine finie se ferme, et sa fin a une seule autorité

`SeriesEnd` ferme déjà une série : date atteinte, `after_count` épuisé,
occurrence unique consommée. Les trois aboutissent au **même** état —
`next_trigger_at` NULL, ce que le modèle définit déjà comme « rien ne suit » —
et la requête des routines dues l'exclut par construction, `NULL <= now()`
valant UNKNOWN en SQL.

Ce que rien ne faisait, c'était **fermer** cette ligne : elle restait activée et
« active » pour toujours, indiscernable d'une routine mise en pause. Le balayage
de l'exécuteur la ferme désormais (`is_enabled = false`,
`status = completed`) — désactivée, jamais supprimée : la personne doit pouvoir
voir ce qu'elle avait posé.

**Une colonne `expires_at` a été écrite, puis retirée avant livraison.** Elle
aurait été une **seconde autorité** sur la fin d'une routine, à côté d'un
`SeriesEnd` déjà stocké, validé, éditable dans le studio et raconté en six
langues — et une seule des deux aurait été montrée. Ce qui manquait n'était pas
une colonne, c'était la fermeture.

### Le réveil sert les veilles, l'exécuteur reste seul juge

Dans le balayage ADR-261, les veilles `mail_match` du compte sont évaluées
contre le delta Gmail **avant toute porte du battement** — pas seulement avant
le verdict du pré-filtre.

*Corrigé après coup, sur une question du propriétaire.* Câblé d'abord à
l'intérieur de `_gmail_signal`, l'armement se retrouvait **derrière** trois
contrôles qui ne le concernent pas : le cooldown de réveil de vingt minutes,
`heartbeat_enabled`, et le refus de la source « emails ». Le premier était le
pire : le courrier arrive par rafales, donc une veille aurait été écartée
régulièrement parce que LIA avait parlé un quart d'heure plus tôt. Le précédent
était cinq lignes plus haut dans la même fonction — l'indexation des sources
courriel tourne « avant toute porte » parce qu'indexer n'est pas une décision.
Un armement a exactement cette forme. La revue à froid ne l'avait pas vu parce
qu'elle avait relu le module et son point d'insertion, pas la chaîne de portes
au-dessus de ce point.

La boîte n'est ouverte que pour un compte qui **détient** une veille : une
lecture Gmail dépense le quota de la personne, une recherche indexée répond
d'abord. Et elle est lue **une seule fois** — le delta est passé à la décision
du réveil plutôt que relu.

Quatre règles, aucune n'est une convention :

- **le réveil ne fait pas tourner la routine.** Il avance `next_trigger_at` et
  s'arrête là. L'exécuteur est le seul à savoir exécuter une routine — la
  revendiquer, la réessayer, enregistrer son passage, solder son effet — et un
  second exécutant serait une seconde autorité sur ce qui tourne pour le compte
  de quelqu'un.
- **aucune seconde déduplication.** L'empreinte `condition_state` de
  l'exécuteur décide déjà si un fait est neuf, donc armer deux fois tire une
  fois.
- **on avance une échéance, on ne ressuscite pas une série.** Un
  `next_trigger_at` NULL veut dire que la série est finie ; l'armer relancerait
  ce qui s'est terminé. Et l'armement ne peut que **rapprocher** un passage,
  jamais le repousser.
- **l'armement dépasse le cache qu'il fait lire.** L'exécuteur réévalue via
  `fetch_mails`, dont la recherche Gmail est mise en cache pendant
  `EMAILS_CACHE_SEARCH_TTL_SECONDS` : un cache rempli quelques secondes avant
  l'arrivée du courriel répond « non remplie », et **ce verdict consomme
  l'armement** — la routine repart vers son créneau suivant et le réveil est
  perdu. Armer au-delà du TTL publié rend l'évaluation vivante par
  construction, et le délai est lu dans le réglage qui le possède (ADR-184).

Le pré-filtre du réveil n'a **pas voix au chapitre** : il répond « est-ce que
ça vaut de réveiller le battement », une veille répond « est-ce que c'est ce
que j'attends ». Un courriel que le filtre juge sans importance est exactement
ce qu'une veille peut guetter.

### Deux lectures d'une même question, épinglées

Une veille est lue deux fois, et ce n'est pas évitable : le réveil tient une
ressource Gmail brute sans projection d'affichage, l'exécuteur tient une
projection sans en-têtes. Aucune ne peut servir l'autre. Un test de concordance
(`test_mail_match_agreement.py`) compare les deux verdicts sur onze courriels
logiques identiques ; élargir une lecture sans l'autre fait rougir le test.

La seule divergence légitime est **écrite** plutôt que découverte : la
projection lit `is:unread in:inbox`, donc un courriel lu entre le réveil et le
tick de l'exécuteur sort de sa vue et la veille se solde « non remplie ». C'est
le bon résultat — la personne l'a vu — et c'est une différence de **données**,
pas de prédicat.

### La puce « Surveiller » demande avant d'écrire

Le geste vit sur les cartes de courriel du briefing. Il **écrit**, là où les
deux autres puces ouvrent le chat pré-rempli : le chat ne peut pas composer une
veille, `create_scheduled_action_tool` ne créant que des routines `time` par
décision écrite.

Trois choix portent la forme, tous dans un module unique (`lib/mail-watch.ts`) :
l'**expéditeur** est la requête et jamais le sujet (un sujet dérive à travers
les `Re:` et se partage entre fils sans rapport), la **fin** passe par le
`SeriesEnd` de la récurrence, et la **cadence** de deux évaluations par jour
n'est qu'un filet pour un compte sans canal de poussée.

Et la puce **lit ce que le compte détient avant d'écrire**. Deux courriels du
même expéditeur, c'est ordinaire ; cliquer sur les deux créerait deux veilles
identiques, chacune consommant un des vingt créneaux de routines et chacune
notifiant — donc **une seule réponse attendue annoncée deux fois**. C'est
précisément l'agacement que ce programme existe pour éviter.

## Ce que la revue adversariale à froid a trouvé

Quatre défauts, tous dans le code du programme lui-même, tous corrigés avec
leurs tests. Aucun n'était visible avec une suite verte.

### Une revendication abandonnée était immortelle

**Mesuré contre le vrai serveur** : un moment revendiqué puis jamais soldé
n'était atteint par **aucune** instruction du module. `expire_stale` lit les
lignes `pending`, `purge_settled` lit les états soldés, `claim_due` lit
`pending` — une ligne `claimed` n'est dans aucun des trois. Elle était encore
là, intacte, à +365 jours.

Trois événements ordinaires en produisent une : un processus tué entre le
commit de la revendication et celui du solde, un pool qui refuse une connexion
au moment de solder, un service qui lève quelque chose que le gestionnaire par
compte du balayage avale. La personne n'est jamais interrogée, la ligne n'est
jamais libérée, et rien ne le dit.

C'est exactement le « stale shutdown with two independent actors » que la règle
des revendications durables nomme — et le docstring du dépôt affirmait le
contraire, qu'une ligne éphémère voit sa fenêtre se fermer d'elle-même. Une
fenêtre qui se ferme ne fait rien à une ligne revendiquée.

`reclaim_stale` la rend à `pending` en lisant l'**âge de la revendication** et
jamais la fenêtre, ce qui permet de **réessayer** le moment tant qu'il vaut
encore quelque chose ; une ligne dont la fenêtre s'est fermée aussi est reprise
puis expirée dans la même passe, d'où l'ordre du ménage. Le bail est généreux
par construction : plus court qu'un service réel, il donnerait le même moment à
un second travailleur pendant que le premier parle.

### La règle de chaîne ne voyait pas la réunion suivante

`is_chained` demande si une autre réunion commence dans les minutes qui suivent
la fin de celle-ci. La lecture s'arrêtait à `now` : une réunion **pas encore
commencée** était simplement absente de la liste, et la règle répondait « rien
ne suit » d'un bloc dont elle ne voyait pas la fin.

La conséquence n'était ni théorique ni rattrapable. Un moment déposé par une
passe précoce n'est jamais retiré (l'insertion est le seul écrivain, et elle
entre en conflit plutôt que de supprimer), la revalidation relit **un** seul
événement et ne peut donc pas voir un voisin, et un moment contourne
délibérément la garde « en réunion ». LIA demandait donc « comment ça s'est
passé ? » au milieu de la réunion suivante — précisément ce que la règle de
bloc existe pour empêcher.

La fenêtre va désormais jusqu'à `now + gap`, exactement aussi loin que la règle
teste et pas plus loin. Ce qui revient de la moitié future sert **uniquement**
de brise-bloc : `_candidate_for` refuse tout ce qui n'est pas terminé.

### La revalidation ne lisait pas le refus de participation

Son propre docstring le promettait — « ou que la personne l'a décliné entre
temps » — et le code ne vérifiait que l'annulation et le déplacement. Or
l'écart entre le dépôt et le service est de quelques minutes à quelques heures
**par construction**, ce qui est exactement le temps qu'il faut à une réponse
pour changer. Une réunion qu'on a déclinée n'est pas une réunion qu'on a eue.

### Le refus de participation avait deux implémentations

`is_declined_by_self` existait dans `calendar_reading` et le scoreur portait une
**copie inline** de la même expression — dans un module qui importait déjà les
briques (`is_self`, `attendees_of`) de la fonction partagée. Les deux lectures
lisent maintenant la même, et un test le vérifie sur la source.

### Deux observations mesurées, délibérément non corrigées

- **Les deux passes de ménage sont des balayages séquentiels** (plan mesuré sur
  le serveur) : il n'y a d'index ni sur `settled_at` ni sur `claimed_at`. À
  l'échelle réelle du produit — quelques comptes, quelques dizaines de lignes —
  un balayage est le bon plan et un index coûterait des écritures pour rien.
  À retenir si une instance dépassait le millier de comptes.
- **Le titre d'une réunion atteint le prompt sans enveloppe « contenu non
  fiable »**. C'est le comportement **préexistant** du battement, qui injecte
  déjà les sujets de courriels et les titres d'événements de la même façon ; le
  changer relève du prompt du battement entier, pas de ce programme.

### Un résiduel laissé à l'arbitrage

Un moment contourne la garde « en réunion » — c'est la décision écrite plus
haut, et la correction de la règle de chaîne retire désormais le cas de loin le
plus fréquent (deux réunions collées ne produisent plus rien du tout).

Reste un cas étroit : un moment que les quotas ou un cooldown retardent d'une
heure peut être servi pendant une réunion **sans rapport**, sa fenêtre valant
trois heures. Le corriger n'est pas un réglage mais un changement de forme —
une garde « en réunion » sur un moment devrait le **rendre** à `pending` plutôt
que le solder, sans quoi il serait consommé. La machinerie existe désormais
(`reclaim_stale`), mais c'est un arbitrage sur l'équilibre « arriver près de
l'instant » contre « ne jamais interrompre », et non un défaut à corriger dans
une revue.

## Conséquences

### Ce que ça donne

- LIA revient à l'instant qui compte plutôt qu'au prochain créneau qui tombe.
- Un courriel attendu est servi en une à deux minutes au lieu de deux heures,
  sans une seule lecture supplémentaire : le delta est déjà en main.
- Une routine finie se voit comme finie.
- Deux dérives de documentation corrigées en chemin : le guide du battement
  annonçait un cooldown de 2 h (réel : 1 h) et 6 h de calendrier (réel : 4 h),
  et nommait un modèle précis à cinq endroits alors que le modèle réellement
  utilisé est celui que `llm_config_overrides` porte pour le poste (ADR-244).

### Ce que ça coûte

- Une table, un balayage, un verrou de planificateur de plus. Le balayage est
  gigué (ADR-254) et son TTL de verrou est lié à son intervalle — un verrou
  retenu 300 s sur un balayage de 300 s fait sauter une passe sur deux.
- La garde « en réunion » ouvre le calendrier, borné par un cache Redis.
- La puce coûte une lecture de la liste des routines par clic.

### Ce qui n'est délibérément pas fait

- **Pas de puce de réponse rapide sur un moment.** Une question ouverte ne se
  répond pas par une pastille ; en proposer une, c'est reprendre d'une main la
  conversation qu'on ouvrait de l'autre.
- **Pas de genre `deadline_eve` ni `counterparty_silence`.** Vérifié dans le
  code : `fetch_open_loops_context` (48 h d'échéance, 7 j de dormance, 3 j de
  cooldown) et `_nudge_reason` (24 h, 48 h, 2 j) les couvrent déjà. Les
  ajouter, c'était deux compteurs de cooldown pour un même objet.
- **Pas d'appel vocal** dans ce lot ; il fait l'objet d'un travail à part.

### Un défaut préexistant signalé, puis corrigé

`heartbeat_wake_sweep` tournait toutes les 120 s avec un `SchedulerLock` dont
le TTL par défaut est 300 s, et ce verrou n'est **jamais** relâché à la
sortie : il sautait une passe sur deux. Le balayage des moments liait son
propre TTL à 90 % de son intervalle pour éviter ça. Depuis le 2026-09-11 la
règle a UNE implémentation, `scheduler_lock.ttl_for_interval` (90 % de la
période, plancher 30 s), lue par les deux balayages et par le garde
`test_scheduler_lock_timing_guard.py`, qui n'avait jamais listé le balayage
des réveils — un job enregistré après l'écriture du garde y était invisible.
