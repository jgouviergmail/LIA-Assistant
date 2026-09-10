# Workboard — le tableau de tickets

> Une unité de travail avec un cycle de vie, un porteur et un résultat.

**ADR** : [ADR-276](../architecture/ADR-276-Workboard.md)
**Drapeau** : `WORKBOARD_ENABLED` (défaut `true`)
**Domaine** : `apps/api/src/domains/workboard/`

---

## Vue d'ensemble

Le workboard tient ce qu'aucune surface existante ne tenait. Les tâches d'un
fournisseur sont une liste sans cycle de vie ni porteur ; un rappel est une
poussée à un instant, dont rien ne subsiste après la sonnerie ; une routine est
une instruction répétée, qui ne se termine jamais.

Un ticket porte un titre, une description, une priorité, une date de début et
une échéance, un porteur, des sous-tickets, des commentaires et une histoire. Il
traverse sept états, dont six sont toujours à l'écran :

| Colonne | Ce qu'elle veut dire |
|---|---|
| `idea` | noté, pas encore engagé — jamais exécuté par LIA |
| `todo` | prêt à être pris |
| `in_progress` | en cours, humain ou LIA |
| `waiting` | arrêté, en attente d'une décision de la personne |
| `confirming` | LIA a construit une action qu'elle ne peut pas mener seule — **dessinée seulement quand elle tient un ticket** |
| `validating` | LIA a rendu son résultat, il reste à le valider |
| `done` | terminé, refus compris |

« Annulé » n'existe plus (lot 8) : un ticket refusé est un ticket qu'on ne fera
pas, ce que « Terminé » dit déjà, et la colonne gagnée vaut plus que la
distinction perdue — l'ÉVÉNEMENT garde la raison (`refused`), qui est l'endroit
où elle sert.

L'ordre d'affichage est DÉRIVÉ de l'énumération (`STATUS_ORDER` dans
`constants.py`) : une seconde liste serait une seconde autorité.

## Qui détient un ticket

Un ticket est détenu par un couple `(assignee_kind, assignee_user_id)` :

| Couple | Signification |
|---|---|
| `('human', NULL)` | le propriétaire, de ses propres mains |
| `('lia', NULL)` | la LIA du propriétaire — c'est elle qui l'exécutera |
| `('human', <pair>)` | un pair connecté |

**`NULL` signifie « le propriétaire le détient ».** Cette convention n'est pas un
raccourci d'écriture : elle est ce qui permet à la clé étrangère `SET NULL` de
rendre automatiquement le ticket à son propriétaire quand le compte du pair
disparaît, sur les quatre chemins de suppression dure, présents et futurs.
`effective_assignee_id` la résout en un seul endroit.

La quatrième combinaison que la forme autorise — un pair déléguant à SA propre
LIA — est refusée par le service (`workboard_cross_account_delegation`), dans
les deux sens : l'instruction appartient au propriétaire, et l'exécuter sans
surveillance avec les outils de l'autre compte mettrait les données de ce
compte dans un commentaire que le propriétaire lit.

## Le tableau de qui

Un ticket est sur le tableau de U si **U le possède OU U le détient**. Ce
prédicat est écrit une seule fois (`WorkboardRepository.visible_predicate`) et
toutes les lectures le réutilisent.

Un ticket que l'appelant ne voit pas répond 404, exactement comme un ticket qui
n'existe pas : personne ne peut sonder l'existence d'un identifiant.

Le filtre « détenu par » a trois valeurs et elles sont **disjointes du point de
vue du lecteur** : `me` accepte les deux écritures de « je le tiens » (mon
identifiant, et le NULL qui veut dire que le propriétaire le tient), `lia` lit
le genre, et `peer` veut dire **quelqu'un d'autre** — donc jamais le lecteur
lui-même. Un pair lit aussi son propre tableau, et chaque ticket qu'il détient
porte SON identifiant : sans cette exclusion, « Une connexion » lui rendait son
propre travail sous un libellé qui dit le contraire, et « Moi » rendait les
mêmes lignes.

L'historique d'un ticket distingue trois faits que le journal range sous un
seul genre `assigned` : **confié** à quelqu'un, **rendu** par son détenteur, et
**rendu parce que la connexion a pris fin** — le panneau lit la charge utile de
l'événement, jamais le seul genre, sinon un ticket revenu au départ d'un pair se
lirait « Confié ».

## Quand la relation se termine

Un pair qui s'en va ne doit pas emporter le travail. Trois sorties, trois
comportements, et aucun n'est celui d'un autre :

| Sortie | Ce que le tableau fait | Ce que les gens lisent |
|---|---|---|
| retrait d'une connexion acceptée | libère les tickets des DEUX sens | les deux côtés, chacun avec SON compte |
| blocage | libère de la même façon | **rien** — un blocage n'observe rien |
| refus d'une demande | rien du tout | rien |

Un refus met fin à une paire qui n'a jamais été acceptée : aucun ticket n'a pu
y être assigné, donc interroger le tableau serait une requête pour rien.

**La paire EST la connexion.** `peer_connections` porte une ligne par paire à
vie, donc aucun ticket ne stocke d'identifiant de connexion qui pourrait
périmer : la libération se retrouve par ses deux participants
(`list_held_between`, appelé dans les deux sens).

**Le tableau est atteint par une couture, jamais par un import.**
`workboard` importe `peers`, donc `peers` important le tableau fermerait un
cycle — et le ratchet de couplage compte aussi les imports locaux.
`domains/shared/peer_release_sink` porte la couture, `release_adapter`
l'installe à l'import, et le démarrage refuse une couture muette.

**La libération est tout ou rien.** Elle s'exécute dans un SAVEPOINT : la
couture répond « rien n'a bougé » quand le tableau échoue, et c'est cette
réponse que les deux côtés reçoivent — une libération à moitié écrite ferait
d'un compte affiché un mensonge (ADR-185). La séparation elle-même est en
dehors : `transition_status` est un UPDATE serveur déjà parti sur le fil.

**Le compte est celui du destinataire.** Une paire tient presque toujours du
travail dans les deux sens, donc le tableau compte par PROPRIÉTAIRE et chacun
lit sa propre clé. La phrase rejoint le corps du retrait au lieu d'être une
seconde notification, et n'apparaît pas quand rien n'a bougé.

Un quatrième chemin existe et ne passe pas par là : la **suppression de
compte** NETTOIE la ligne `users` au lieu de la supprimer, donc aucune action
de clé étrangère ne se déclenche — `build_workboard_release` est la libération
de ce chemin-là, écrite en ligne dans `users` qui n'importe aucun domaine.

## Droits

| Action | Propriétaire | Pair détenteur |
|---|---|---|
| Changer le statut, la priorité, les dates | oui | oui |
| Commenter | oui | oui |
| Régler SON suivi | oui | oui |
| Rendre le ticket | — | oui |
| Modifier le titre ou la description | oui | non |
| Réaffecter à un tiers | oui | non |
| Confier à LIA | oui, si personne d'autre ne le détient | non |
| Supprimer | oui | non |
| Ajouter un sous-ticket | oui | non |

Le drapeau de suivi de l'assigné est remis à faux à chaque réaffectation : le
porteur suivant n'hérite jamais de l'abonnement de quelqu'un d'autre.

## Ce que la base garantit, et ce qu'elle ne peut pas

Trois tables : `workboard_tickets`, `workboard_comments` et
`workboard_ticket_events` (celle-ci en ajout seul, sans `updated_at`).

**La base ne peut PAS porter l'invariant « une affectation à un pair est
autorisée par une connexion acceptée ».** Une contrainte `CHECK` croisant deux
colonnes qu'une action de clé étrangère peut modifier est violable quel que soit
son sens, l'ordre des cascades n'étant pas fixé, et PostgreSQL refuse un `CHECK`
`DEFERRABLE`. L'invariant vit donc dans le service, qui revérifie la connexion à
chaque écriture — ce qui est aussi la bonne règle : un partage se revérifie à
l'exécution et ne se lit jamais depuis une ligne stockée.

Ce que la base garantit :

| Situation | Effet |
|---|---|
| Le pair détenteur supprime son compte | le ticket survit, rendu au propriétaire ; son commentaire reste, sans auteur |
| Le propriétaire supprime son compte | le ticket, ses enfants, ses commentaires et son histoire partent |
| Suppression d'un ticket parent | ses enfants partent avec lui |
| Suppression de compte (scrub) | la purge libère explicitement ce que le compte détenait sans le posséder |

## API

Toutes les routes sont sous `/api/v1/workboard`, protégées par la session, et
montées seulement si `WORKBOARD_ENABLED`.

| Route | Ce qu'elle fait |
|---|---|
| `GET /tickets` | une page du tableau, le total EXACT, un compte exact par colonne |
| `GET /needs-me` | ce qui attend l'appelant, et ce qui est en retard |
| `GET /tickets/{id}` | un ticket, ses enfants, son fil et son histoire |
| `POST /tickets` | créer |
| `PATCH /tickets/{id}` | modifier sous les droits de l'appelant |
| `POST /tickets/{id}/move` | déplacer vers une colonne et une place |
| `POST /tickets/{id}/run-now` | armer un ticket LIA pour le prochain balayage |
| `POST /tickets/{id}/comments` | commenter |
| `DELETE /tickets/{id}` | supprimer (propriétaire seul) |

La page et ses compteurs sortent du même énoncé filtré : un en-tête de colonne
annonçant 7 au-dessus d'une colonne en montrant 3 serait pire que pas
d'en-tête. Toute colonne déclarée est présente, à zéro si vide.

Les refus sont des **codes stables** (`workboard_*`), jamais des phrases : ce
sont des clés de traduction que le frontend résout dans les six langues.

Il y a **deux familles de codes, et deux tables** : un REFUS répond à une
demande que la personne vient de faire (`WorkboardError`, montré en toast),
tandis qu'un ÉCHEC D'EXÉCUTION est ce qu'un balayage a écrit sur le ticket des
heures plus tôt (`RunError`, stocké dans `last_run_error` et lu sur la carte et
dans le panneau). Les deux se résolvent dans les locales — `WORKBOARD_ERROR_KEYS`
et `WORKBOARD_RUN_ERROR_KEYS` — et `test_frontend_error_keys.py` tient chaque
famille à sa table, dans les deux sens. `last_run_error` porte le code puis,
parfois, un message technique borné après `: ` ; la phrase traduite est ce que
la personne lit, le message technique reste comme preuve (l'infobulle sur la
carte, une ligne atténuée dans le panneau) — jamais comme titre.

## Réglages

Chaque borne est un réglage, dont le défaut vit dans `core/constants.py`, et la
même valeur est publiée à qui produit la donnée (règle ADR-184).

| Variable | Défaut | Ce qu'elle borne |
|---|---|---|
| `WORKBOARD_ENABLED` | `true` | la fonctionnalité entière |
| `WORKBOARD_RUN_SWEEP_SECONDS` | 60 | l'intervalle du balayage d'exécution |
| `WORKBOARD_RUN_TIMEOUT_SECONDS` | 600 | la durée d'un run, et l'âge d'une réclamation périmée |
| `WORKBOARD_RUN_MAX_ATTEMPTS` | 3 | les tentatives d'UN run |
| `WORKBOARD_QUOTA_RETRY_MINUTES` | 30 | le report après un refus de quota |
| `WORKBOARD_MAX_TICKETS_PER_USER` | 2000 | les tickets qu'un compte possède |
| `WORKBOARD_MAX_CHILDREN_PER_TICKET` | 50 | les sous-tickets d'un ticket |
| `WORKBOARD_MAX_RUNS_PER_TICKET` | 10 | les runs d'un ticket dans sa vie |
| `WORKBOARD_HIDDEN_ROWS_RETENTION_DAYS` | 90 | la conservation des transcriptions cachées après clôture |
| `WORKBOARD_TITLE_MAX_CHARS` | 200 | le titre |
| `WORKBOARD_DESCRIPTION_MAX_CHARS` | 8000 | la description |
| `WORKBOARD_COMMENT_MAX_CHARS` | 4000 | un commentaire |
| `WORKBOARD_CLOSED_HIDE_DAYS_DEFAULT` | 30 | le filtre « masquer les tickets clos » |
| `WORKBOARD_NUDGE_DUE_HOURS` | 24 | la fenêtre d'échéance du heartbeat |
| `WORKBOARD_NUDGE_WAITING_HOURS` | 48 | l'attente jugée trop longue |
| `WORKBOARD_NUDGE_COOLDOWN_DAYS` | 2 | l'intervalle entre deux relances |

Le réglage refuse au démarrage un délai d'expiration inférieur à l'intervalle du
balayage : le moissonneur libérerait des runs encore en vol.

## Quand LIA exécute un ticket toute seule

Un balayage toutes les minutes (`SCHEDULER_JOB_WORKBOARD_RUN_SWEEP`, avec
gigue — un job périodique sans gigue s'aligne pour toujours sur ses diviseurs)
fait trois choses, dans cet ordre :

1. **du ménage** : il libère les revendications qu'un worker mort tient encore,
   et supprime les transcriptions cachées des tickets clos au-delà de la
   rétention. Les deux d'abord, pour qu'un ticket échoué soit reproposé dans le
   même tour.
2. **il revendique UN ticket** — `FOR UPDATE SKIP LOCKED` et un `UPDATE`
   conditionnel dans la même transaction, validée avant que le moindre travail
   commence. Un seul à la fois : un worker qui en aurait pris cinq avant d'être
   tué en abandonnerait cinq.
3. **il l'exécute, puis solde depuis un résultat EXPLICITE** — jamais depuis
   l'absence d'exception.

Trois refus peuvent arrêter un ticket revendiqué, et **aucun n'est un échec** :
un compte inactif (permanent : le ticket garde sa colonne et dit pourquoi), un
plafond de quota et une conversation occupée (les deux RENDENT la
revendication, restituent le run au budget du ticket et se journalisent
« sauté »). Le solde cite son run (`last_run_id`) : une personne qui a déplacé
le ticket pendant l'exécution GAGNE, et le solde tardif n'écrit rien.

**Le mode d'exécution est une colonne de la LIGNE** (lot 10) : chaque ticket
et chaque action planifiée porte le sien (`execution_mode`, NOT NULL, `react`
par défaut), modifiable tout au long de la vie du ticket et lu à la PROCHAINE
exécution — jamais au milieu d'un run. Le réglage d'instance qui décidait pour
tout le monde a été supprimé, sa constante et ses lignes `.env` avec : deux
autorités sur la même question, c'est une de trop, et celle qui reste est celle
que la personne voit. Le commutateur de l'en-tête du chat ne parle que du chat,
et ne lit rien de tout cela.

### Ce que le ticket dit à LIA

L'instruction est composée à partir des **mots du propriétaire uniquement** :
titre, description, et — pour un ticket décomposé — le titre du parent et ceux
des frères. **Les commentaires n'y entrent jamais** : un pair qui détient un
ticket peut en écrire un, et un commentaire porté dans un tour sans surveillance
serait un inconnu dictant ce que LIA fait avec le compte, les outils et le quota
d'un autre. La règle tient par la FORME : le module ne demande au repository que
deux choses, et aucune n'est un commentaire.

**Un run dit qu'il commence APRÈS le bail, jamais à la revendication** : une
revendication rendue ensuite (quota, conversation occupée) serait un « LIA a
commencé » pour rien. `run_started` et `run_finished` sont des événements de
PROGRÈS, donc filtrés par le suivi ; « en attente de vous » ne l'est jamais. Le
moissonneur NOMME ce qu'il a fait (`workboard_run_reaped`) plutôt que de
répéter le message du run précédent sous un « échoué » neuf ; `run_now` remet
les tentatives à zéro (un ticket relancé à la main après trois échecs était
abandonné aussitôt) ; et la rétention purge aussi les lignes cachées ORPHELINES
d'un ticket supprimé, qu'aucun `ticket_id` vivant ne nommait plus.

**Chaque chose qu'un run dit est revendiquée à part** dans le registre des
effets (ADR-263). La revendication d'une notification proactive était UNE par
run, écrite pour des balayages qui ne parlent qu'une fois ; un run de ticket
parle jusqu'à trois fois (commencé, terminé, en attente) et, mesuré en
conteneur, le registre ne tenait que la première — la seconde perdue comme un
rejeu. La couture `send_proactive_notification` porte un champ nommé
`occurrence`, la clé d'idempotence le compose. Une notification qu'aucun run
n'a causée nomme l'acte qui l'a causée : le run d'un transfert est
l'événement `ASSIGNED` lui-même (`ticket-event:<id>`, `event_run_id`), et la
couture EXIGE un `run_id` — l'adaptateur substituait l'identifiant du ticket
en silence.

### Ce que la personne lit

| Issue | Colonne | Commentaire |
|---|---|---|
| une réponse | en validation | la réponse, telle quelle |
| un brouillon à confirmer (lot 7) | à confirmer | la question, l'aperçu détaillé du brouillon, comment répondre |
| une clarification, ou une capacité refusée faute d'accord | en attente | ce qui a été fait, ce qui est en attente, la question de LIA |
| aucune réponse, ou un échec | en cours (inchangée) | aucun ; un code typé sur le ticket |

Une réponse vide n'est pas une réponse : elle se solde en échec plutôt que de
déposer un commentaire vide et d'annoncer que quelque chose a été fait.

Les notifications suivent le drapeau par ticket, **à une exception près** :
« ce ticket t'a été confié » part toujours, parce que personne ne s'abonne à un
ticket qu'il ne sait pas encore détenir. Une question — « ça t'attend », « ça
attend ton accord » — suit le drapeau comme le reste depuis le 2026-09-09 (D59),
mais n'est offerte qu'au DÉTENTEUR : le côté qui ne peut pas y répondre ne la
reçoit pas, fût-il abonné.

### Quand LIA a besoin d'un accord (lot 7)

Un run rencontre un outil qui demande une confirmation (`confirm`) ou qui
construit un brouillon (`draft`). Hors tour, la porte des effets refusait les
deux ; un run de TICKET, lui, peut porter la question à la personne, donc la
porte le laisse demander (`RunOrigin.can_carry_draft`) et le moteur lit
l'interruption dans les chunks que le flux émet vraiment
(`hitl_interrupt_metadata` → jetons de la question → `hitl_interrupt_complete`).

Le solde écrit alors :

- le ticket en **« À confirmer »**, rendu à la personne — la colonne n'est
  dessinée que si elle tient au moins un ticket ;
- `pending_action` sur la ligne (`draft_id`, `draft_type`, `draft_content`,
  `tool_name`, `question`, `approved`) ;
- UN commentaire de LIA : exactement ce que le chat a montré — la carte
  écrite par le renderer et la question écrite par le modèle, un seul flux
  depuis le lot 14 — puis la consigne « réponds par un commentaire — oui, non,
  ou ce qu'il faut changer ». Rien n'y est rendu deux fois : jusqu'au lot 14
  la question portait déjà la carte du modèle et le solde y ajoutait l'aperçu
  du renderer, donc l'e-mail se lisait deux fois sur le ticket ;
- une notification `confirming` au détenteur **s'il suit le ticket** (D59) —
  le drapeau régit aussi les questions depuis le 2026-09-09 : désactivé, LIA
  reste silencieuse même bloquée, et la confirmation attend sur le tableau, que
  le badge du hub compte et que le heartbeat relance après
  `WORKBOARD_NUDGE_WAITING_HOURS`.

La clé HITL du fil de conversation est effacée : rien n'attend dans le chat.

**Ce que le run écrit dans la conversation, et ce que la personne y lit.** Un run
qui s'arrête sur une confirmation écrit TROIS lignes, de deux natures :

| Ligne | Dans le chat | Tampon du run | Purgée avec le ticket |
|---|---|---|---|
| le brief | non | oui | oui |
| la question de LIA (avec l'aperçu du brouillon) | non | oui | oui |
| la notification « attend ton accord » | **oui** | non | non (message ordinaire) |

Les deux premières sont des lignes DU RUN : le registre de décisions pointe
dessus, la lecture les tient hors du chat, la rétention les enlève quatre-vingt-
dix jours après la clôture du ticket. La troisième est ce que la personne doit
lire. Toute métadonnée archivée d'un tour est construite par un
`build_*_metadata` (`agents/api/archive_metadata.py`) — une garde refuse un
dictionnaire écrit sur place, parce que c'est exactement ainsi que l'aperçu d'une
suppression s'est retrouvé dans le chat.

**La réponse est un commentaire, lue quand le propriétaire confie le ticket à
LIA.** Sa dernière note depuis le dernier run est classée sans appel modèle,
par un lexique en six langues replié comme elle (accents, casse, ponctuation) :

| Réponse | Colonne | Détenteur | `pending_action` |
|---|---|---|---|
| approbation nue (« oui », « ok vas-y », « yes please », « ja », « sí », « 好的 ») | à faire | LIA | conservé, `approved: true` |
| refus nu (« non merci », « annule », « nein », « 取消 ») | terminé | la personne | effacé |
| tout le reste (« oui mais… », une précision, une question) | à faire | LIA | effacé ; la note entre dans le brief |
| aucune note | refus `workboard_answer_required` | inchangé | inchangé |

Seules les notes du PROPRIÉTAIRE comptent, par la forme de la requête
(`owner_notes_since` prend l'auteur en paramètre et épingle le genre `user`) ;
celles d'un pair, signées `peer`, n'atteignent ni le brief ni la décision. Le
balayage suivant revendique le ticket comme n'importe quel ticket « à faire »
tenu par LIA — « En cours » suit donc dans la minute.

**Envoyer le commentaire suffit** (lot 9) : sur un ticket « À confirmer » dont
on est le propriétaire, l'envoi classe la réponse, repasse le ticket à LIA en
« À faire » et remet ses compteurs de tentative à zéro — sans qu'il faille en
plus changer la colonne et le détenteur à la main. Le plafond de runs est
vérifié AVANT la relance : une approbation ne contourne pas
`WORKBOARD_MAX_RUNS_PER_TICKET`.

**La carte de confirmation a UN auteur, et c'est le renderer** (lot 14).
Dans le chat, la carte était écrite par le modèle sous un prompt qui la
décrivait : sa forme variait avec lui (des champs devenus paragraphes, un
`---` affiché tel quel). `render_confirmation_card` la rend désormais —
l'emoji et le titre du registre d'affichage, puis l'aperçu détaillé — et
l'interaction la streame avant le premier jeton du modèle, `---` entre deux
lignes vides, puis la question seule que le prompt lui demande. Même carte
dans le chat et sur le ticket, moins de jetons, et le repli sans modèle la
montre aussi.

**L'aperçu du brouillon a UNE forme, et c'est du Markdown** (lot 13). Le rendu
émettait `<br/>` en tête de chaque ligne *et* comme séparateur : tout aperçu
s'ouvrait sur une ligne vide et chaque champ était séparé par deux. Une liste
Markdown tient un champ par ligne sans balise dans le chat, et s'aplatit
proprement là où rien n'est rendu — c'est la même chaîne qui sert les deux
surfaces. Neuf des vingt-six types de brouillon n'avaient par ailleurs aucun
résumé et s'annonçaient « Draft (ticket_delete) » ; ils ont désormais le leur,
dans les six langues, sous une garde de complétude au démarrage.

**Le rejeu tourne dans le graphe, sous verrou d'empreinte.** Le brief cite
l'action approuvée à la lettre, le run publie l'identité de ce qui a été montré
(type de brouillon + `draft_digest` du contenu), et quand l'outil reconstruit
son brouillon, `decide_draft` (`nodes/draft_preapproval.py`) le laisse passer
sur cette identité exacte et sur rien de plus large : identique → confirmé,
exécuté par l'exécuteur du chat sous portée approuvée ; différent → nouvelle
question sur le ticket, avec le nouvel aperçu. L'approbation est dépensée au
premier match, et un lot de brouillons est une seule identité : chaque aperçu
est montré, et le lot entier — pas son premier élément — est ce qui est approuvé. `workboard_replays_total{result="matched"|"mismatched"}`
compte les deux issues (tableau 29).

**Indépendance avec le chat, dans les deux sens.** Un ou plusieurs tickets « À
confirmer » ne bloquent rien : le brouillon vit sur le ticket, la clé HITL
Redis est effacée, et la sonde du balayage (`conversation_has_pending_hitl`)
lit cet enregistrement — le même que le chat consulte pour router une réponse
— et non le point de reprise LangGraph, qui dit « interrompu » jusqu'à la
prochaine entrée. Dans l'autre sens, une question pendante DANS LE CHAT écarte
toujours les runs (`skipped_busy`) : un run ne doit pas marcher sur une
question que la personne est en train de répondre.

### Qui lit la table des messages, et avec quelle portée

Le repository applique le prédicat `hidden` à chaque lecture qu'il possède ;
cela ne dit rien des modules qui construisent leur propre `select` sur la même
table. Mesuré le 2026-09-09 : dix-neuf modules référencent le modèle, et le
« dernier message de la personne » du heartbeat prenait la question synthétique
d'un run pour ses derniers mots. `conversations/message_readers.py` fait de la
réponse une DÉCLARATION sur une liste COMPLÈTE (la doctrine de
`direct_client_callers`) : onze lecteurs, deux portées — `VISIBLE_ONLY` pour
ceux qui interprètent les lignes comme celles de la PERSONNE (la sonde
d'activité, l'agrégateur du heartbeat) et `WHOLE_RECORD`, avec sa raison écrite,
pour ceux qui mesurent, exportent, purgent, joignent ou se restreignent à des
lignes qu'un run n'écrit jamais. La consolidation des journaux est
`VISIBLE_ONLY` : ses deux lectures d'enrichissement filtraient des rôles que
le repository n'écrit jamais (`human`/`ai`) — mortes depuis la v1.7.0 — et
prenaient l'heure UTC pour celle de la personne ; réparées, prouvées sur
PostgreSQL (fuseau `Pacific/Kiritimati`). La garde AST refuse un lecteur non déclaré,
une déclaration périmée, et un `VISIBLE_ONLY` dont la source ne porte ni
`hidden.is_(False)` ni `visible_only(`.

### Ce que les lignes cachées coûtent

Un run archive sa question et sa réponse, cachées du chat mais gardées dans le
dossier. Deux bornes tiennent le volume — dix runs par ticket, et la fenêtre de
rétention — et il est **mesuré** plutôt que supposé : `lia_hidden_run_rows` et
`lia_hidden_run_bytes`, sur le tableau de bord 29 avec les issues des runs et
les notifications.

**Le tampon n'est pas la colonne.** L'origine écrit `hidden` dans les
métadonnées ; la colonne, elle, est DÉRIVÉE au seul endroit qui construit la
ligne (`create_message`). Mesuré le 2026-09-09 : sans cette dérivation, les deux
lignes d'un vrai run s'affichaient dans le chat alors que toute la suite était
verte — les tests d'intégration inséraient eux-mêmes `hidden=True` et ne
prouvaient donc que le filtre.

## Quand LIA relance d'elle-même

Le heartbeat porte une source `WORKBOARD` : les tickets du tableau de la
personne qui méritent un mot, avec **le motif qui les a fait remonter**.

| Motif | Ce qui le déclenche |
|---|---|
| `overdue` | l'échéance est passée, et la personne tient le ticket |
| `due_soon` | l'échéance tombe dans `workboard_nudge_due_hours`, et la personne tient le ticket |
| `waiting` | LIA a posé une question depuis plus de `workboard_nudge_waiting_hours` |
| `validating` | LIA a livré un résultat qui attend validation depuis plus de `workboard_nudge_waiting_hours` |

Quand deux motifs sont vrais du même ticket, `overdue` gagne : la personne a
besoin du plus tranchant des deux, pas des deux. **Un ticket que LIA tient n'est
jamais « en retard » pour la personne** : c'est le retard de LIA, le balayage
l'exécute et sa notification d'échec parle s'il n'y arrive pas. Les colonnes
closes ne remontent jamais, et `idea` non plus — une note que personne n'a
engagée ne peut pas être en retard.

**Un ticket arrêté est cité, jamais paraphrasé.** L'entrée d'un ticket
`waiting` ou `validating` porte l'extrait du dernier commentaire de LIA — sa
question, ou ce qu'elle a livré — borné comme la notification push. Sans ce
texte, la consigne « dis ce qu'il attend » fabriquait la question.

**Le rétrécissement vit en SQL** (`list_nudge_worthy`), jamais dans le
récupérateur : un tableau peut porter des milliers de tickets et la décision en
veut huit. Le plafond est un réglage (`workboard_nudge_max_items`) appliqué sous
un tri explicite — priorité, puis échéance la plus proche, puis clé primaire —
parce qu'un plafond sans tri rend les lignes les plus anciennes.

**Le refroidissement démarre à la délivrance**, pas à la lecture : estampiller
au moment du `fetch` ferait taire un ticket que la décision a vu et choisi de ne
pas mentionner. Il dure `workboard_nudge_cooldown_days` et il est compté côté
serveur.

**Deux portes commandent la source**, et elles ne disent pas la même chose : le
refus de la personne (l'interrupteur des réglages) et le drapeau du déploiement
(`WORKBOARD_ENABLED`). La seconde compte pour le registre autant que pour la
notification — une source coupée n'ouvre rien, donc elle n'est pas enregistrée
comme lue. Quand la source a servi, la lecture laisse une ligne de consultation
du domaine `ticket`.

## Ce que l'écran montre, et comment il se manipule

La carte ne porte **aucun contrôle de colonne** : elle est dans la colonne qui
la nomme. On la déplace en la saisissant — **toute la carte**, pas une poignée
— ou on ouvre son panneau d'un tap. Sous `lg`, le glisser réordonne la colonne
affichée et le panneau est l'endroit où l'on change de colonne.

Le tableau se lit avant d'être lu :

| Signe | Ce qu'il dit |
|---|---|
| l'arête colorée de la carte, et le fond d'un ticket urgent | la priorité, sur quatre niveaux — jamais en badge : son nom reste, masqué, pour un lecteur d'écran |
| le porteur, en tête de carte | qui le tient — avant même le titre |
| la cloche, sous le titre, devant l'échéance | si le chat en parlera, et pour quand — une seule ligne |
| « En retard », sur sa propre ligne sous la date | que l'échéance est passée ; la date reste (lot 17) |
| l'anneau + le triangle + la phrase | le ticket est en retard, dit trois fois |
| le glyphe du badge de détenteur | moi, LIA, ou un pair |
| l'icône de l'en-tête de colonne | de quelle colonne il s'agit |

Aucun de ces signes n'est seul : le mot est toujours à côté.

**Une échéance est un JOUR, et c'est le jour du lecteur.** Le champ parle en
jours (`YYYY-MM-DD`), l'API stocke un instant, et la conversion est faite une
seule fois (`lib/workboard/dates.ts`) : l'instant stocké est la **fin** du jour
choisi, dans le fuseau du lecteur, et le champ est dérivé de l'instant en heure
locale — jamais tranché dans la chaîne ISO. Minuit UTC rendait un ticket « en
retard » à midi le jour même de son échéance, et un lecteur à l'ouest de
Greenwich relisait le jour PRÉCÉDENT celui qu'il avait choisi.

**Une colonne ne dit « rien ici » que si son compteur le dit aussi.** La page
est plafonnée à 200 lignes là où un compte peut en posséder 2 000, donc une
colonne peut légitimement tenir des tickets que cette page ne porte pas : elle
dit alors qu'ils ne sont pas sur cette page, ce qui envoie vers les filtres,
plutôt que de contredire son propre en-tête (ADR-185).

**Le tableau se relit tout seul, et ne dérange jamais** (lot 12). Une
relecture toutes les 30 secondes, qui ne lève pas l'indicateur d'occupation (le
bouton « rafraîchir » ne doit pas tourner tout seul), garde le dernier tableau
que le serveur a confirmé si elle échoue — un tableau d'une minute vaut mieux
qu'une page d'erreur pour ce que personne n'a demandé — et s'abstient dans
trois cas : onglet caché, carte en cours de déplacement, écriture en vol (un
COMPTEUR, pas un booléen : deux écritures qui se chevauchent ne rouvrent pas la
porte à la première qui finit).

Une colonne qui tient des tickets **respire**, et une colonne vide est immobile
— le mouvement est le signal ; « En cours » tourne, parce que son glyphe EST un
compteur. Les deux animations sont `motion-safe` : qui a demandé l'immobilité
la garde. Et « Urgent » prend un fond rose pâle, mesuré nécessaire : un badge
rouge et un badge « élevé » se lisent comme un même niveau quand on parcourt le
tableau.

**Le panneau est l'endroit où l'on modifie, en sept panneaux d'un seul
cadre** (lot 15) : données (titre et description pour le propriétaire),
réglages — colonne, priorité, **qui détient le ticket** (la liste complète
pour le propriétaire, un simple « le rendre » pour un pair qui le détient,
parce que c'est la seule chose que le service lui permet), l'échéance, le
**mode d'exécution** du prochain run (« Mode Pipeline » / « Mode ReAct », les
mots de l'en-tête du chat) et « Notifier l'avancement dans le chat », tous
modifiables à tout moment du cycle de vie (lot 12) —, puis dernière exécution
(le VERDICT du run — répondu, en attente, à confirmer, en échec, reportée
pour quota ou pour conversation en cours — jamais la colonne), coût, étapes,
commentaires, historique, chacun sur sa ligne à pleine largeur. Chaque panneau
porte son titre avec l'icône du thème et nomme sa région pour un lecteur
d'écran.

**Sur un téléphone** (lot 17) : une colonne à la fois, que l'on change d'un
balayage horizontal, des deux flèches ou de la liste ; rien ne se glisse, un
doigt posé n'importe où sur une carte ouvre son détail, et la carte porte
deux listes entre son titre et son échéance, l'une sous l'autre — la colonne
puis le porteur (lots 19-20), chaque item son glyphe devant son nom dans la
liste de l'application (D79 : `GlyphSelect`, dont `StatusSelect` et
`HolderSelect` sont les deux vocabulaires ; le sélecteur de colonne du
téléphone est la même liste avec ses compteurs), les mêmes écritures que le
panneau, où elles sont aussi en tête des réglages. Un ticket en retard garde
sa date, dit « En retard » sous elle, aligné sur la cloche, et son contour
rouge respire lentement, un cadre INTÉRIEUR qui part de la couleur d'un bord
normal et laisse le liseré de priorité dehors — immobile, à pleine force,
sous `prefers-reduced-motion` (D80). Toutes les listes du tableau — colonne,
porteur, priorité, mode d'exécution, les trois filtres de la barre, et le
formulaire de création — sont la même liste à glyphes (D81), et les glyphes
de personnes portent la couleur du thème (D82). Le
tableau n'a pas de bouton « Rafraîchir » : il se relit seul. Ses filtres
partent de l'URL (`?overdue=1&assignee=lia`) et l'URL les suit ensuite.

**Sous `lg`, le bloc de filtres se replie** (2026-09-10). Cinq contrôles
au-dessus d'UNE colonne de cartes prennent tout le premier écran, et le
lecteur vient voir ses tickets. Replié, il reste un index : il dit le nombre
EXACT de rétrécissements actifs et les nomme avec les mots de leurs propres
contrôles — un résumé qui ne dit rien fait ouvrir le bloc pour savoir, ce que
le repli existe précisément pour éviter. Fermé signifie **démonté** (le
`<details>` natif de `components/ui/disclosure.tsx` ne rend ses enfants
qu'ouvert) et l'état des filtres vit dans la PAGE, donc replier ne coûte ni ne
perd rien. Au-dessus de `lg`, le bloc est inchangé. Le compte, la phrase et le
prédicat « le tableau est-il rétréci ? » viennent du même module
(`lib/workboard/active-filters.ts`) : l'état vide ne peut donc pas annoncer
« aucune correspondance » pendant que le résumé annonce « aucun filtre ». Le
**tri n'est pas un rétrécissement** — il change l'ORDRE, jamais l'ensemble.

**Réglages › Workboard est le tableau en un coup d'œil** (lot 18) :
`GET /workboard/summary` — total, en retard, chez LIA, à votre décision, un
compte exact par colonne, chacun un lien vers le tableau réduit ; la
capacité du compte contre le plafond de l'instance ; le coût des exécutions
dans le vocabulaire du compteur du chat. Les comptes portent sur ce que le
compte voit, les sommes sur ce qu'il possède.

**Ce que le ticket a coûté** y figure aussi (lot 11), quand « jetons et coûts
visibles » est actif dans l'en-tête de l'application : sur UNE ligne, 🟠 IN ·
🟢 OUT · 🔵 CACHE · 🟣 GOOGLE · euros, CUMULÉS sur tous les traitements, dans le
vocabulaire du compteur du chat, le nombre de runs à côté du titre « Coût ». Rien n'est compté deux fois : les colonnes `total_*` sont
l'addition des `last_run_*`, écrites par arithmétique de colonnes dans la
transaction du solde, et la source est la ligne que le tracker du compte écrit
déjà. Le ticket ne crée aucune comptabilité, il LIT la sienne — la dépense d'un
run est celle du compte, sous les mêmes plafonds.

Le fil de commentaires est daté, chaque tour séparé du suivant, et **les mots de
LIA y sont du texte brut** : un commentaire est un paragraphe de texte échappé,
donc les DEUX vocabulaires y étaient lus tels quels — le HTML d'un modèle et le
Markdown de sa propre prose. Ils sont aplatis par une porte unique
(`markdown_to_plain_text`) là où le run les écrit, donc le panneau, l'extrait de
notification, la citation du heartbeat et l'export du registre en profitent
ensemble.

L'historique porte les **deux valeurs** de chaque changement — « Priorité :
moyenne → urgente », « Échéance : aucune → 01/09/2026 » — et non le seul fait
que quelque chose a bougé.

**Quand LIA passe la main, elle rend le ticket.** Une question posée ou un
résultat à valider retournent au propriétaire dans l'écriture qui solde le run.
Un échec, non : rien ne le rejoue, mais rien n'est demandé non plus, et la carte
continue de dire que c'est LIA qui a trébuché — ce que seule la REVENDICATION
en cours permet de savoir, un run échoué laissant le ticket en « en cours ».

## Depuis le chat

Six capacités, agent `ticket_agent`, domaine `ticket` (drapeau
`workboard_enabled`) : créer un ticket, le modifier, le commenter, lister le
tableau, lire un ticket en entier, en supprimer un.

**Aucune règle métier n'est dans les outils.** `WorkboardService` possède les
droits, les bornes, les transitions et la résolution des pairs ; un outil qui
en redéciderait une serait une seconde autorité, et les deux finiraient par
diverger. Trois conséquences visibles :

- **un refus voyage sous son CODE** (`workboard_*`), jamais sous une phrase :
  le frontend le traduit, le modèle le reformule ;
- **les dates passent une seule fois** par `normalize_user_datetime` — le
  modèle écrit l'intention LOCALE de la personne, parfois avec le mauvais
  décalage ;
- **un ticket se nomme par id OU par titre exact**, et un titre ambigu est
  REFUSÉ plutôt que deviné : agir sur le mauvais ticket est pire que demander
  lequel.

Chaque borne que le service applique est **publiée** dans le manifeste, lue
depuis les réglages (ADR-184) : un `.env` modifié déplace la borne appliquée et
la borne publiée ensemble.

**La suppression demande d'abord.** Elle déclare `draft` — la forme native de
tout outil destructeur ici ; `confirm` est réservé aux outils MCP tiers, où la
politique est DÉDUITE des annotations du serveur. Le premier appel rend une
carte de confirmation, la suppression a lieu sur la relecture approuvée. Un run
sans surveillance ne supprime donc rien : la porte refuse une politique `draft`
quand personne ne peut répondre, et le ticket se solde « en attente retour ».

**Un ticket est connu du système de contexte.** `context_domain` sur un
outil de lecture n'est une promesse tenue qu'avec un `RegistryItemType`, un
`ContextTypeDefinition` enregistré et des `registry_updates` émis — mesuré le
2026-09-09, la déclaration seule était inerte. Le domaine a donc
(`agents/workboard/context.py`) : `RegistryItemType.TICKET`, classé EXTERNAL
dans `TRUST_BY_REGISTRY_TYPE` parce qu'un pair écrit dedans (titre,
description, commentaires d'un ticket qu'il a confié) ; le type de contexte
`tickets`, qui est le `result_key` du domaine — une seule orthographe pour le
magasin, la référence `$steps.<étape>.tickets` et la `context_key` des deux
manifestes de lecture, que le chargeur vérifie au démarrage ; une LISTE
alimentée par `list_tickets` ; un ticket LU par `get_ticket` qui devient le
COURANT sans toucher la liste (« celui-là » est le ticket lu, « le deuxième »
reste le tableau montré, mode `CURRENT`) ; et une suppression confirmée qui
retire la ligne du contexte (`_DRAFT_TYPE_TO_TCM_DOMAIN`) et nomme le ticket
comme référence de la ligne du registre (`ticket_id` dans `PROVIDER_REF_ORDER`).
La charge utile offerte au registre est la vue BORNÉE (`_ticket_summary`),
jamais la description : le modèle la paierait à chaque référence. En chinois
un ticket est « 工单 » dans chaque table qui le nomme, jamais « 任务 » — le
nom du domaine des tâches (`test_wording.py`).

**La suppression confirmée a SON exécuteur** (`execute_ticket_delete_draft`),
comme `event_delete` et `task_delete` : la relecture générique d'un brouillon
`TOOL_CALL` appelle la coroutine avec ses seuls arguments, sans `runtime`, et un
outil natif qui lit son identité dans le runtime ne peut pas être rejoué par
elle. L'exécuteur revérifie les droits (un délai arbitraire sépare la question
de la réponse, et le ticket peut avoir changé de mains), et rend le TITRE parce
que la phrase de succès est rendue depuis le RÉSULTAT, pas depuis le brouillon.
Une seconde confirmation du même brouillon est REFUSÉE par le registre (une
ligne, jamais deux) — mesuré en conteneur le 2026-09-09 par le moteur même que
la reprise HITL appelle.

**Le routage est mesuré, pas supposé** : 12 familles × 6 langues
(`tests/unit/domains/agents/workboard/routing_corpus.json`), dont **trois
familles NÉGATIVES** — une tâche du fournisseur, un rappel et une routine — qui
doivent partir ailleurs. La moitié déterministe est un test unitaire (le
vocabulaire atteint-il le domaine ?), la moitié fournisseur un script
(`task workboard:corpus:measure`) : un test qui se saute sur une clé absente est
vert et pourrit. Mesuré le 2026-09-09 : **72/72 sur `deepseek-v4-flash`, 72/72
sur `gpt-5.6-luna`**, environ 0,02 $ par passage, hors registre (une mesure
d'ingénierie n'est pas une action de LIA — même choix que le script de
récurrence). Le script réchauffe lui-même le cache des clés fournisseur depuis
la base, comme le démarrage : sans cela un script autonome tourne sur les
valeurs par défaut et chaque appel répond 401.

## L'écran

**Deux routes, un composant.** `/{lng}/dashboard/workboard` lit `?ticket=` ;
`/{lng}/dashboard/workboard/<id>` est la forme que `ticket_url` met dans CHAQUE
notification de ticket — et qui répondait 404 avant le lot 4 (mesuré le
2026-09-09). Les deux montent `WorkboardPage`, et le ticket ouvert est DÉRIVÉ de
l'URL : un panneau est un lien qu'on envoie, et le bouton retour le ferme.
Le tableau n'a **aucune destination d'en-tête** (D15) : on y arrive par la
section de réglages, par la section « Tickets » du hub des notifications, et par
chaque notification dans le chat. Un test le vérifie, pour que l'absence soit
une décision et non un oubli.

**De `lg` vers le haut** : les sept colonnes dans UN conteneur qui défile
horizontalement (le corps de page ne défile jamais latéralement), glisser au
pointeur ET au clavier (dnd-kit), chaque étape ANNONCÉE en nommant la COLONNE —
« déplacé en position 3 » ne dit rien à qui écoute. **Sous `lg`** : une colonne
à la fois, choisie par un `<select>` natif portant son compteur, et aucun
glisser — le capteur tactile prend une contrainte d'activation pour qu'un doigt
qui fait défiler ne saisisse jamais une carte. Le déplacement passe alors par le
`<select>` de la carte, qui appelle LA MÊME mutation que le glisser.

**La poignée de glisser n'est pas le titre** : le capteur clavier s'active sur
Espace/Entrée et annule le défaut, donc posé sur le titre il ferait démarrer un
glisser là où le pointeur ouvre le ticket. Deux contrôles, deux noms.

**La carte ne porte pas de badge de statut** — elle est dans sa colonne — et son
badge de priorité ne marque que `high` et `urgent` : `medium` est le défaut et
`low` tomberait sur le gris réservé aux éléments inactifs. Le compteur d'étapes
n'apparaît que si la page tient TOUT le tableau, et quand la page est partielle
une ligne l'énonce : un plafond est dit, jamais appliqué en silence (ADR-185).

**Ce que le tableau écrit** : un déplacement est optimiste et son retour arrière
restaure l'ordre EXACT (l'instantané d'avant, pas un déplacement inverse
reconstruit) ; création et suppression relisent le tableau, parce qu'elles
touchent des lignes que la page ne voit pas ; un refus voyage sous son CODE, que
le front traduit. Rien ne pousse le changement d'un pair vers un onglet ouvert
(hors périmètre) : la page relit au retour du focus.

## Ce que les lots 1 à 3 livrent, et ce qui suit

Livré : le vocabulaire, les trois tables et leurs migrations, la purge,
l'export, le repository, le service, les routes, le badge du hub, le moteur
d'exécution hors tour partagé avec les routines, le balayage, le brief versionné,
les notifications filtrées par le suivi, les métriques et leur tableau de bord,
les six outils d'agent, leur corpus de routage, le ticket dans le système de
contexte, l'exécuteur de la suppression confirmée, la déclaration des lecteurs
de la table des messages, et la notification « ce ticket t'a été confié » — qui part du SERVICE et traverse donc une couture
(`domains/shared/proactive_sink`), parce que `agents` importe désormais
`workboard` et que le distributeur importe `agents` : l'importer depuis le
domaine fermerait un cycle. Le démarrage DÉCLARE ce câblage et refuse une
couture muette, comme pour le registre de consultations (ADR-270).

Le lot 4 a livré l'écran : les deux routes, le tableau et ses sept colonnes,
la carte, le panneau, les filtres, la section de réglages (la porte du
tableau), la section « Tickets » du hub, la rangée d'actions sous une
notification de ticket dans le chat, l'i18n des six langues et le parcours e2e.

Le lot 5 a livré la fin d'une relation : la couture inversée et son refus d'un
câblage muet, la libération dans les deux sens sur le retrait comme sur le
blocage, le SAVEPOINT qui la rend tout ou rien, et la phrase par destinataire
dans les six langues.

Le lot 6 clôt le programme : la source heartbeat et ses trois motifs, la requête
plafonnée sous un tri explicite, le refroidissement à la délivrance, la table de
placement qui a libéré la place dans un fichier gelé, et la seconde porte que le
registre ignorait.

Le lot 7 ajoute la confirmation sur le ticket : la colonne « À confirmer » qui
n'existe que lorsqu'une confirmation attend, le brouillon porté par la ligne,
la réponse par commentaire classée sans modèle dans les six langues, le rejeu
dans le graphe sous verrou d'empreinte, et la sonde de question pendante
réalignée sur l'autorité du chat.
