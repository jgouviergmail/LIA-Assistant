# ADR-276 — Le workboard : un ticket a un cycle de vie, un porteur et un résultat

**Statut :** Accepté — 2026-09-09
**Amende :** ADR-263 (les trois registres, la porte d'exécution), ADR-185 (un
compte affiché est exact ou n'existe pas), ADR-184 (ce qu'un système impose, il
le publie), ADR-180 (connexions entre utilisateurs), ADR-117 (archive-first)

---

## Contexte

La personne demande à LIA des choses qui ne sont pas un tour de conversation :
une recherche à mener la semaine prochaine, un projet à décomposer, quelque
chose qu'un pair doit traiter, quelque chose à valider plus tard.

Trois surfaces existantes hébergent aujourd'hui ces demandes, et chacune a été
construite pour autre chose :

| Surface | Ce qu'elle est | Ce qu'elle n'est pas |
|---|---|---|
| Tâches Google/Apple/Microsoft | la liste de choses à faire d'un fournisseur | ni un cycle de vie, ni un porteur, ni un résultat |
| Rappels (ADR-051, ADR-268) | une poussée à un instant | rien ne subsiste après la sonnerie |
| Routines (ADR-140) | une instruction répétée sur un calendrier | rien qui se termine |

Aucune ne tient « une unité de travail avec un cycle de vie, un porteur et un
résultat ». C'est ce que le workboard ajoute.

## Décisions

### Ce qu'est un ticket

**D1 — Sept colonnes, un ordre unique** (amendé par D54, qui a ajouté
`confirming`, et par D60, qui a retiré `cancelled`). `idea, todo, in_progress,
waiting, confirming, validating, done`. L'ordre d'affichage est DÉRIVÉ de
l'énumération (`STATUS_ORDER`), jamais re-listé : une seconde liste est une
seconde autorité, et celle qui dérive est toujours celle que personne ne
regarde.

**D2 — Une seule ligne par ticket, partagée.** Le tableau de U est
« propriétaire = U OU assigné = U ». Pas de copies par tableau, donc les deux
côtés ne peuvent pas se contredire sur l'état d'un ticket.

**D3 — Les sous-tickets sont des tickets enfants, sur UN niveau.** Un enfant est
un ticket complet, que LIA peut donc exécuter ; un petit-enfant est refusé par le
service. La suppression du parent emporte ses enfants ; sa clôture, non — une
cascade de clôture « terminerait » en silence un travail que personne n'a fait.

### Ce que la base peut porter, et ce qu'elle ne peut pas

**D4 — Un assigné NUL signifie « le propriétaire le détient », et la clé
étrangère est `SET NULL`.** Quatre chemins suppriment durement une ligne
`users` et un seul passe par la purge de compte : la purge du démonstrateur, le
nettoyage des comptes non vérifiés, la suppression administrateur et la
suppression RGPD. `CASCADE` détruirait le ticket du PROPRIÉTAIRE au départ de
son pair — son propre travail, sur son propre tableau ; `RESTRICT` bloquerait
les trois chemins qui ne libèrent pas, transformant un filet de sécurité en
panne d'exploitation. `SET NULL` rend le ticket à son propriétaire sur tous les
chemins présents et futurs. La purge libère EN PLUS explicitement, parce que la
suppression de compte SCRUBBE la ligne `users` au lieu de la supprimer et
qu'aucune action de clé étrangère n'y joue — deux mécanismes, chacun couvrant ce
que l'autre ne peut pas.

**D5 — Aucune contrainte `CHECK` ne croise deux colonnes qu'une clé étrangère
peut modifier.** La première conception stockait `peer_connection_id` avec un
`CHECK` la liant à `assignee_user_id`. **Prouvé sur PostgreSQL réel le
2026-09-09** : supprimer le compte du pair déclenche DEUX actions de clé
étrangère indépendantes sur la même ligne, appliquées séquentiellement, et le
`CHECK` rejette l'état intermédiaire — quel que soit le sens choisi, puisque
l'ordre des cascades n'est pas garanti. `CHECK` ne peut pas être `DEFERRABLE`
en PostgreSQL. La colonne a donc disparu, pas l'invariant : la PAIRE
(propriétaire, assigné) EST la connexion, `peer_connections` ne tenant qu'une
ligne par paire à vie, et le service la résout à chaque écriture — ce qui est
exactement la règle D8 des pairs : un partage se revérifie à l'exécution,
jamais depuis une ligne stockée.

**D6 — Le registre d'événements n'est jamais mis à jour** (`created_at` seul, le
précédent `peer_access_log`). Il tient ce que les HUMAINS ont fait ; ce que LIA
a fait est aussi dans les trois registres d'ADR-263, sous l'identifiant du run.
Les deux ne s'additionnent pas et ne se joignent jamais.

### Ce que le compte affiche

**D7 — La page et ses compteurs sortent du MÊME énoncé filtré** (ADR-185). Un
en-tête de colonne annonçant 7 au-dessus d'une colonne en montrant 3 est pire
que pas d'en-tête. Toute colonne déclarée est présente, à zéro si vide : une clé
absente se lirait « il n'y a pas cette colonne » plutôt que « il n'y a rien
dedans ».

**D8 — Toute lecture paginée se termine sur la clé primaire.** Sans ordre total,
deux tickets partageant une clé de tri se répètent ou disparaissent à la
frontière d'une page.

### Ce que LIA fait d'un ticket

**D9 — Un ticket affecté à LIA est exécuté hors tour, par le moteur des
routines**, extrait et partagé (lot 2). Les trois registres, les deux plafonds de
quota et la garde HITL viennent alors par construction.

**D10 — Le run archive ses deux lignes comme tout tour, marquées `hidden`, et
c'est la LECTURE de l'historique qui les exclut.** Ne rien archiver aurait
laissé la ligne de décision d'ADR-263 avec ses deux pointeurs nuls — indistincte
d'une conversation supprimée. La règle du propriétaire (« pas de bruit dans le
chat sauf si je suis le ticket ») est tenue à la lecture, pas en détruisant
l'enregistrement.

**D11 — La volumétrie cachée est BORNÉE et VISIBLE.** Mesuré le 2026-09-08 :
2,4 Ko par ligne archivée, index compris, soit environ 5 Ko par run. Bornes :
une ligne cachée vit exactement aussi longtemps que son ticket,
`WORKBOARD_MAX_RUNS_PER_TICKET` plafonne les runs d'un ticket (10 par défaut,
« Lancer maintenant » compris), et une rétention supprime les lignes cachées
d'un ticket clos depuis plus de `WORKBOARD_HIDDEN_ROWS_RETENTION_DAYS`
(90 jours). Visibilité : deux jauges (`lia_hidden_run_rows`,
`lia_hidden_run_bytes`) et une phrase dans les réglages. Une croissance que
personne ne voit est une croissance que personne n'arrête.

**D12 — Un run qui a besoin de la personne S'ARRÊTE.** La porte d'ADR-263 refuse
un outil `confirm` en source non assistée ; elle refusera de même un outil
`draft` (amendement, lot 2), et le refus est lu depuis un signal STRUCTURÉ,
jamais depuis la prose. Le ticket passe en « en attente retour », un commentaire
dit ce qui manque, et une notification porte un lien `?intent=` pour terminer
dans le chat, où les cartes de confirmation existent.

**D13 — La délégation inter-comptes est refusée.** Un pair ne peut pas confier à
SA LIA un ticket dont un autre a écrit l'instruction, et un propriétaire ne peut
pas déléguer à LIA un ticket qu'un pair détient. C'est la même règle vue des deux
côtés : l'instruction appartient au propriétaire, et l'exécuter sans surveillance
avec les outils de l'autre compte mettrait les données de ce compte dans un
commentaire que le propriétaire lit.

### Ce que le chat en fait

**D14 — Un ticket se nomme par identifiant ou par titre UNIQUE plié.** Deux
correspondances sont refusées, jamais devinées : un faux positif remet le sort
d'un ticket à une question qui portait sur un autre (la règle d'ADR-269 sur
l'annuaire du débrief, appliquée à un tableau). **Le pliage décide, et aucun
filtre SQL ne le précède** : mesuré le 2026-09-09, un `ILIKE` sur le besoin brut
paraît une optimisation anodine et est PLUS STRICT que le pliage qu'il alimente,
donc il écarte exactement les lignes que le pliage existe pour attraper
(« reserver la salle » ne trouvait rien quand le tableau portait « Réserver la
salle »). **Un filtre de rétrécissement est plus permissif que le décideur,
jamais moins.**

**D15 — Qui a créé un ticket est stocké** (`created_by`), et l'outil de création
est appelable depuis n'importe quel tour. LIA n'en crée qu'à la demande dans la
conversation en v1 ; une création de sa propre initiative sera un NOUVEL APPELANT
d'une porte existante, pas une nouvelle porte.

### Où on entre

**D16 — Pas d'entrée dans l'en-tête.** Il est à sept destinations, sa largeur
mesurée maximale. Le tableau s'atteint depuis une section de réglages et depuis
chaque notification de ticket dans le chat, et le hub des notifications porte un
badge « a besoin de vous » — un ensemble à décider, jamais un décompte de tout ce
que le compte possède.

**D17 — Glisser-déposer ET liste déroulante.** L'équivalence clavier est une
règle de correction dans ce dépôt, pas une option : chaque carte porte un
`<select>` natif de statut en plus du déplacement à la souris — la liste de
l'application depuis le lot 20 (D79).

**D18 — `WORKBOARD_ENABLED` vaut `true` par défaut**, contrairement aux autres
drapeaux de programme : le tableau est une surface centrale de l'assistant, pas
un sous-système optionnel. Une instance qui n'en veut pas l'éteint explicitement.

### Ce que la revue à froid des trois lots a changé

**D19 — La suppression confirmée a SON exécuteur.** La relecture générique d'un
brouillon `TOOL_CALL` appelle la coroutine de l'outil avec ses seuls arguments,
sans `runtime` : un outil natif qui lit son identité dans le runtime ne peut pas
être rejoué par elle. C'est la raison d'être des exécuteurs dédiés
(`execute_ticket_delete_draft`, la forme d'`event_delete` et de `task_delete`),
et l'exécuteur rend le TITRE parce que la phrase de succès est rendue depuis le
RÉSULTAT, jamais depuis le brouillon.

**D20 — Un ticket est connu du système de contexte.** `context_domain` sur un
outil de lecture est une promesse que le système de contexte ne tient qu'avec
un `RegistryItemType`, un `ContextTypeDefinition` enregistré et des
`registry_updates` émis — mesuré le 2026-09-09 : la déclaration seule était
inerte, rien n'était sauvé, et une suppression confirmée laissait le ticket
« courant ». Désormais : `RegistryItemType.TICKET` classé EXTERNAL (un pair
écrit dedans : titre, description, commentaires — la doctrine de
`TRUST_BY_REGISTRY_TYPE` résout l'ambiguïté vers EXTERNAL), le type de contexte
`tickets` — le `result_key` du domaine, une seule orthographe pour le magasin,
la référence de plan et les manifestes — déclaré en `context_key` sur les deux
manifestes de lecture (ce que le chargeur vérifie au démarrage), une LISTE
alimentée par le listage, un ticket LU qui devient le courant SANS toucher la
liste (« celui-là » est le ticket lu, « le deuxième » reste le tableau montré),
et une suppression confirmée qui retire la ligne du contexte
(`_DRAFT_TYPE_TO_TCM_DOMAIN`) et nomme le ticket comme référence du registre
(`ticket_id` dans `PROVIDER_REF_ORDER`).

**D21 — Tout lecteur direct de la table des messages DÉCLARE sa portée**
(`conversations/message_readers.py`). Le repository applique le prédicat
`hidden` à chaque lecture qu'il possède, et cela ne dit rien des modules qui
construisent leur propre `select` sur la même table : mesuré le 2026-09-09,
dix-neuf modules référencent le modèle et le « dernier message de la personne »
du heartbeat prenait la question synthétique d'un run pour ses derniers mots.
Onze lecteurs, deux portées — `VISIBLE_ONLY` (la sonde d'activité,
l'agrégateur du heartbeat, la consolidation des journaux) et `WHOLE_RECORD`
avec sa raison écrite (mesures,
exports, purge, jointures, rôles qu'un run n'écrit jamais) — et une garde AST
qui refuse un lecteur non déclaré, une déclaration périmée, et un `VISIBLE_ONLY`
dont le code ne porte aucune exclusion. La déclaration a trouvé un défaut
plus ancien qu'elle : les deux lectures d'enrichissement de la consolidation
des journaux filtraient les rôles `human`/`ai` que le repository n'écrit
jamais (`user`/`assistant`) — mortes depuis la v1.7.0, invisibles aux tests
unitaires qui doublent la session — et lisaient l'heure UTC comme celle de la
personne. Réparées et prouvées sur PostgreSQL.

**D22 — Un run dit qu'il commence APRÈS le bail, jamais à la revendication** :
une revendication rendue ensuite (quota, conversation occupée) serait un
« LIA a commencé » pour rien. Trois défauts voisins fermés par la même revue :
le moissonneur NOMME ce qu'il a fait (`workboard_run_reaped`, plutôt que de
répéter le message du run précédent sous un « échoué » neuf) ; `run_now` remet
les tentatives à zéro (un ticket relancé à la main après trois échecs était
immédiatement abandonné) ; la rétention purge aussi les lignes cachées
ORPHELINES d'un ticket supprimé, qu'aucun `ticket_id` vivant ne nommait plus.

**D23 — Un run qui parle deux fois revendique deux fois.** L'effet de
notification proactive (ADR-263) prenait UNE revendication par run
(`{run_id}:notification`), écrite pour des balayages qui ne parlent qu'une
fois : mesuré en conteneur le 2026-09-09, un ticket SUIVI a reçu « LIA a
commencé » puis « LIA a terminé » — les deux distribuées, les deux comptées —
et le registre n'en tenait qu'une, la seconde revendication perdue comme un
rejeu de la première. La couture porte désormais un champ NOMMÉ,
`occurrence`, la clé le compose (`{run_id}:notification:{occurrence}`), le
runner nomme ce qu'il dit (`run_started`, `run_finished`, `waiting`). Un
balayage qui parle une fois garde la clé qu'il avait : aucune ligne déjà
écrite ne change de sens. **Et une notification qu'aucun run n'a causée
nomme l'ACTE qui l'a causée** : un transfert de ticket est annoncé par le
service, dans la requête de la personne, sans balayage sous lequel filer la
ligne — l'adaptateur substituait l'identifiant du ticket en silence. Le run
est désormais l'événement `ASSIGNED` lui-même (`ticket-event:<id>`,
`event_run_id`), une ligne que les registres peuvent joindre, et la couture
EXIGE un `run_id` : un défaut y filerait des lignes sous un substitut.

**D24 — Un ticket est « 工单 » en chinois, jamais « 任务 ».** Le nom du
domaine des tâches est « 任务 » ; l'employer pour un ticket mettait deux
choses sous un mot dans le bloc de synthèse du modèle, le registre des
effets et les notifications. Un mot par chose, dans chaque table qui le
nomme (nom du brouillon, phrase de succès, domaine des traitements, intitulé
de synthèse, titre et corps des notifications, phrase d'intention, libellés
d'effets, locales du front), tenu par un test.

### Ce que le lot 4 (l'écran) a décidé

**D25 — L'écran a DEUX routes et UN composant.** La conception disait
« `?ticket=` » ; le back livré construit `ticket_url` comme un CHEMIN
(`/dashboard/workboard/<id>`) et le met dans CHAQUE notification de ticket.
Mesuré le 2026-09-09 avant le lot : cette adresse répondait **404**.
`app/[lng]/dashboard/workboard/page.tsx` (qui lit `?ticket=`) et
`.../[id]/page.tsx` montent donc le même `WorkboardPage`, et le ticket ouvert
est DÉRIVÉ de l'URL, jamais recopié dans un état — un panneau est un lien qu'on
envoie, et le bouton retour le ferme.

**D26 — La carte ne porte pas de badge de statut, et son badge de priorité
marque l'exception.** La carte est DANS sa colonne (et sous `lg` la colonne est
nommée juste au-dessus) : un badge y répéterait l'évidence. Le statut est porté
par une liste — native alors, celle de l'application depuis D79 — qui est à la
fois l'affichage et l'équivalence clavier.
Le badge de priorité n'apparaît que pour `high` et `urgent` : `medium` est le
défaut (une mer d'ambre sur chaque carte) et `low` tomberait sur le ton gris que
la règle du propriétaire réserve aux éléments INACTIFS. Les quatre niveaux sont
nommés en toutes lettres dans le panneau et dans le filtre.

**D27 — La poignée de glisser n'est PAS le titre.** Le capteur clavier de
dnd-kit s'active sur Espace/Entrée et annule le comportement par défaut : posé
sur le titre, il ferait DÉMARRER UN GLISSER là où le pointeur OUVRE le ticket,
et l'action principale de la carte deviendrait inatteignable sans passer par le
menu de rangée. Deux contrôles, deux noms, chacun atteignable au pointeur et au
clavier.

**D28 — Sous `lg`, aucun glisser du tout.** Une colonne à la fois, choisie par
une liste portant son compteur — native alors, celle de l'application depuis
D79 —, plus deux flèches. Le capteur tactile
prend une contrainte d'activation (délai + tolérance) pour qu'un doigt qui fait
défiler ne saisisse jamais une carte, et le déplacement passe par le `<select>`
de la carte — LA MÊME mutation que le glisser, donc une seule implémentation et
une seule façon de se tromper. La garde `dvh` du dépôt a attrapé un
`max-h-[90vh]` sur le panneau : sur un téléphone dont les barres sont visibles,
le bas de la fenêtre — donc ses actions — sortait de l'écran.

**D29 — Un plafond est ÉNONCÉ.** Le tableau lit la page par défaut du serveur
(200) et affiche le total EXACT ; quand les deux diffèrent, une ligne le dit
plutôt que de laisser un en-tête de colonne annoncer 87 au-dessus de douze
cartes (ADR-185). Pour la même raison, le compteur d'étapes d'une carte
n'apparaît QUE si la page tient tout le tableau : un « 1/2 » dérivé d'une page
partielle serait un compte faux.

**D30 — Un paramètre de requête peut être une LISTE.** `apiClient` ne savait
envoyer que des scalaires (`String(value)`), or le tableau filtre par plusieurs
colonnes et plusieurs priorités, que FastAPI lit en paramètres RÉPÉTÉS. La
généralisation est faite UNE fois dans le client (`QueryParamValue`), pas dans
chaque appelant, et une liste vide n'émet rien — comme `undefined`.

### Ce que le lot 5 (la fin d'une relation) a décidé

**D31 — Une connexion qui se termine rend le travail en vol, et la dépendance
est INVERSÉE.** `WorkboardService.release_pair` existait, était testé, et
n'avait **aucun appelant de production** : retirer une connexion laissait chaque
ticket partagé assigné à quelqu'un qui ne pouvait plus atteindre le tableau où
il vit. `workboard` importe `peers` (le service revérifie la connexion à chaque
écriture, D8), donc `peers` important le tableau fermerait un cycle — et le
ratchet de couplage compte aussi les imports LOCAUX, si bien que le cacher dans
une fonction ne ferait que rendre l'arête plus difficile à voir. La couture est
`domains/shared/peer_release_sink`, exactement la forme du registre de
consultation et du répartiteur proactif : le tableau s'y installe à l'import,
`peers` appelle la couture sans importer personne. Sans rien d'installé l'appel
répond « rien n'a bougé » plutôt que de lever — une sonde ou un test étroit n'a
pas de tableau ouvert — mais **le démarrage REFUSE une couture muette**, parce
qu'un effet de bord d'import que personne ne déclare est un effet de bord qui
cesse le jour où quelqu'un réordonne un module (ADR-270).

**D32 — Trois sorties de relation, trois comportements, et l'une d'elles lisait
un statut déjà réécrit.** Le retrait tranche une paire ACCEPTÉE, donc du travail
peut être en vol : on libère, et on dit à chaque côté ce qui LUI est revenu. Le
blocage libère de la même façon et **ne notifie personne** — « l'utilisateur
bloqué ne doit rien observer », et rendre les tickets ne doit pas devenir la
notification qu'un blocage refuse d'envoyer. Le refus d'une demande met fin à
une paire jamais acceptée, donc aucun ticket n'a jamais pu y être assigné :
appeler le tableau serait une requête pour rien. Le défaut : dans `block_peer`
le statut était lu APRÈS `transition_status`, qui venait de le réécrire en
`removed` — la libération était donc toujours sautée, pour toute paire. **Seul
le test PostgreSQL l'a vu** : en unitaire, un `MagicMock` garde le statut qu'on
lui a donné.

**D33 — La libération est TOUT OU RIEN.** La couture avale un échec du tableau
pour ne jamais coûter la séparation — mais elle répond alors « rien n'a bougé »,
et **c'est cette réponse que les deux côtés reçoivent**. Mesuré le 2026-09-09
sur un vrai serveur, sans garde : le tableau meurt après avoir libéré un ticket
sur deux, la couture avale, la notification annonce « 0 », et le `commit` de
l'appelant écrit la moitié déjà mutée. Un compte montré à une personne est exact
ou n'existe pas (ADR-185), donc la libération s'exécute dans un SAVEPOINT
(l'idiome que le journal des routines utilise déjà, ADR-265) : un échec défait
ses propres écritures, l'annonce redevient vraie par construction, et la
séparation survit parce que `transition_status` est un UPDATE serveur déjà parti
sur le fil avant l'appel.

**D34 — Le compte est celui du DESTINATAIRE, et il rejoint la phrase qui
existe.** Une paire tient presque toujours du travail dans les deux sens : un
total de paire dirait à chacun quelque chose qui n'est pas vrai de lui. Le
tableau compte donc **par PROPRIÉTAIRE**, et le répartiteur ne lit que la clé du
destinataire. La phrase est AJOUTÉE au corps du retrait plutôt qu'envoyée en
seconde notification — deux messages à une seconde d'intervalle pour un seul
événement sont du bruit, et ce chemin atteint déjà les deux côtés. Rien n'est
ajouté quand rien n'a bougé : « 0 ticket vous est revenu » est du bruit à son
tour. Preuve runtime du 2026-09-09 sur les deux comptes connectés : « 2 tickets
du tableau vous sont revenus. » d'un côté, « 1 ticket du tableau vous est
revenu. » de l'autre.

### Ce que le lot 6 (la relance du heartbeat) a décidé

**D35 — La source a dû se faire de la place avant d'exister.** Mesuré avant
d'écrire une ligne : `context_aggregator.py` était **gelé à 705 SLOC et en
comptait 700**, et sa fonction de répartition portait une **complexité
cyclomatique de 35**. Ajouter une source coûte au minimum cinq lignes, donc la
mise en œuvre naïve faisait rougir le ratchet de taille — et faire passer 35 à
36 violait la règle du point chaud sans qu'aucune garde ne s'en aperçoive. La
chaîne de quatorze `elif` était une **table de correspondance écrite en
branches** : elle devient `heartbeat/source_placement.py`, une table plus un
assert de complétude au démarrage (ADR-085), et les deux seules formes qui ne
sont pas des affectations — la météo, qui pose quatre valeurs sous trois
conditions, et l'activité, qui dépile une paire — restent écrites en clair et
DÉCLARÉES comme telles. Résultat mesuré : complexité 35 → 4, fichier 700 → 676
(plafond resserré à 690), fonctions au-dessus de CC 15 dans le dépôt 329 → 328.
Une contrainte de ratchet n'est pas un budget à négocier : c'est le signe que la
forme est fausse.

**D36 — Quatre motifs nommés, et le rétrécissement se fait en SQL.** Un ticket
remonte parce qu'il est `overdue`, `due_soon`, `waiting` ou `validating`, et
**le motif voyage avec la ligne** : c'est ce qui permet au prompt de dire
pourquoi plutôt que de le deviner. Quand deux motifs sont vrais du même ticket,
`overdue` gagne — la personne a besoin du plus tranchant des deux, pas des deux.
Deux règles que la revue à froid a ajoutées au premier jet : **une échéance
n'est celle de la personne que tant qu'elle tient le ticket** — sur un ticket
que LIA tient, le retard est celui de LIA, le balayage l'exécute et sa propre
notification d'échec parle s'il n'y arrive pas, donc la relancer serait du
bruit ; et **un ticket arrêté sur la personne est CITÉ, jamais paraphrasé** —
le commentaire du run porte la question de LIA (`waiting`) ou ce qu'elle a
livré (`validating`), et une consigne demandant de « dire ce qu'il attend » sans
ce texte fabriquait la question. L'extrait est celui de la notification push
(`excerpt_of`, une implémentation), lu en une requête pour l'ensemble. Tout le
rétrécissement vit dans `WorkboardRepository.list_nudge_worthy` et non dans le
récupérateur : un tableau peut porter des milliers de tickets et la décision en
veut huit, donc lire l'ensemble pour en garder huit ferait du plafond une
formalité. Le plafond est un réglage publié (`workboard_nudge_max_items`) et il
s'applique sous un **tri explicite** — priorité, puis échéance la plus proche,
puis clé primaire — parce qu'un `LIMIT` sans `ORDER BY` rend les lignes les plus
anciennes (mesuré en production, ADR-273). Les colonnes closes ne remontent
jamais, et `idea` non plus : une note que personne n'a engagée ne peut pas être
en retard.

**D37 — Le refroidissement démarre à la DÉLIVRANCE, jamais à la lecture.**
Estampiller au moment du `fetch` ferait taire pendant deux jours un ticket que
la décision a vu et choisi de ne pas mentionner, ce qui est l'inverse de ce
qu'un refroidissement sert à faire. `_bump_used_workboard` ne tourne donc que si
`WORKBOARD` figure dans les sources RÉELLEMENT utilisées, et le compteur est
incrémenté côté serveur — deux ticks qui se croisent perdraient sinon un
incrément. Le `user_id` de la clause n'est pas décoratif : il est ce qui empêche
un identifiant venu d'ailleurs de toucher le ticket d'autrui.

**D38 — Deux portes, et le registre ne connaissait que l'une.** L'agrégateur
filtrait les sources sur le refus de la PERSONNE, et enregistrait comme
« consultées » toutes celles qui passaient cette porte. Or cinq récupérateurs se
court-circuitent sur un **drapeau de déploiement** et rendent `None` sans rien
ouvrir : sur toute instance ayant coupé l'un d'eux, le registre revendiquait
donc une lecture qui n'avait jamais eu lieu — la famille exacte qu'ADR-263
ferme (« un succès de cache n'est pas une consultation ; la boîte n'a jamais été
ouverte »). Trouvé en branchant la sixième source, pas par une garde.
`HEARTBEAT_SOURCE_FEATURE_FLAGS` déclare les cinq, `is_source_available` répond,
et l'agrégateur honore les deux portes dans ses deux passes. Corollaire côté
écran : **une source publiée sans libellé s'affiche par sa clé brute**, dans les
six langues à la fois, avec toutes les gardes vertes — une garde le refuse
désormais, et elle a été falsifiée pour prouver qu'elle sait rougir.

**D39 — L'historique dit « rendu », pas « confié », quand le ticket revient.**
Trouvé en relisant les lots 4 et 5 ENSEMBLE : le chemin de libération écrit un
événement `assigned` (acteur : personne, raison : `connection_removed`), et le
panneau rendait chaque `assigned` par « Confié ». Une personne dont le pair
venait de partir lisait l'inverse de ce qui s'était passé, sur le ticket même
qui lui revenait — alors que le test d'intégration du lot 5 affirmait que le
journal « est ce qu'une personne lit pour comprendre un ticket revenu tout
seul ». Le sélecteur de libellé (`eventLabelKey`) lit la charge utile que le
service écrit : `released` quand la connexion a pris fin, `returned` quand un
détenteur a rendu le ticket de lui-même, `assigned` sinon. Et la même garde que
pour les sources : **chaque genre d'événement que le tableau écrit a un libellé
dans les six langues**, les deux libellés dérivés sont déclarés, et un libellé
qu'aucun genre ne produit plus ne survit pas.

### Ce que la passe d'ergonomie a corrigé (2026-09-09, après revue du propriétaire)

**D40 — La carte n'a plus de contrôle de colonne, et le glisser prend toute la
carte.** Le `<select>` de statut (D26) répétait ce que l'en-tête de colonne dit
déjà, au prix d'une ligne entière sur une carte haute de cinq. La poignée
dédiée (D27) était pire : 16 px de cible sur un écran tactile, quand la carte
est ce qu'un doigt vise. Les écouteurs passent donc sur la carte entière, la
pastille de préhension reste comme **affordance** et le titre reste la porte —
il arrête le pointeur et les touches avant qu'ils n'atteignent les écouteurs,
si bien qu'ouvrir un ticket ne peut jamais être lu comme un début de glisser.
Conséquence d'accessibilité qu'il fallait traiter et non subir : une carte
déplaçable **est** un contrôle (dnd-kit lui donne `role="button"`), donc elle
est nommée pour ce que la SAISIR fait, jamais par le titre — le bouton titre
qu'elle contient porte déjà ce nom, et deux contrôles répondant à un seul nom
sont une impasse pour un lecteur d'écran. Le glisser marche désormais aussi
sous `lg`, où il réordonne la colonne affichée ; changer de colonne sur un
téléphone reste le travail du panneau.

**D41 — Un conteneur étroit ne se demande pas la largeur de la FENÊTRE.**
`RowActions` ouvrait ses trois boutons icône à partir de `sm`, ce qui est la
bonne question pour une rangée pleine largeur et la mauvaise pour une rangée
dans une colonne de 208 px : mesuré à 1440 px, il restait **64 px au titre**,
qui se repliait un mot par ligne, sous les icônes. Le composant partagé prend
un mode `compact` qui force le menu « ⋮ » à toute largeur, et la carte pose ses
actions **avec les badges**, jamais sur la ligne du titre. Un parcours mesure
désormais le chevauchement plutôt que de l'apprécier à l'œil : aucun élément de
la rangée des actions ne dépasse le bord gauche du bouton.

**D42 — Le tableau se lit avant d'être lu.** Une arête colorée classe la
priorité sur quatre niveaux — un DÉGRADÉ là où le badge n'a que trois tons,
parce que `high` et `urgent` y partagent « fort » et qu'une arête identique
pour les deux ne dirait rien. Le retard est dit **trois fois** (un anneau, une
icône, la phrase), la couleur n'étant jamais le seul porteur. Chaque colonne et
chaque libellé de filtre portent leur icône, et les trois détenteurs — moi, LIA,
un pair — ont trois glyphes distincts, le mot restant à côté pour qui ne voit
pas la forme.

**D43 — Les colonnes se partagent la largeur.** Une largeur fixe de 288 px
montrait cinq colonnes sur sept à 1440 px et faisait du tableau une chasse
latérale ; `flex-1` sur un plancher de 208 px en montre six et demie. Les sept
ne tiennent pas à cette taille sans descendre sous 163 px par colonne, ce qui
n'est pas lisible : le plafond est donc énoncé plutôt que promis.

**D44 — Ce qu'on affecte, on doit pouvoir le réaffecter.** L'écran créait un
ticket avec un détenteur et ne permettait plus jamais d'en changer, alors que le
service et l'outil de LIA le savaient tous les deux depuis le lot 3. Le panneau
porte le contrôle : la liste complète pour le propriétaire, et pour un pair qui
le détient un seul bouton « le rendre » — lui offrir la liste serait un menu
dont toutes les entrées sauf une sont refusées. La règle de lecture (`null`
signifie « le propriétaire le détient ») vit dans un sélecteur pur testé à part.

**D45 — Un fil de commentaires se date.** La question d'un run et la réponse
qu'elle a appelée ne se lisent comme une conversation que si l'ordre est
visible. Et le panneau d'un ticket ne reprend plus le sous-titre de la PAGE :
il dit ce que ce panneau permet.

**Trois défauts trouvés parce que le parcours a enfin TOURNÉ.** Le parcours e2e
du lot 4 attendait un `<form>` que le tableau ne contient pas : ses trois cas
expiraient, en local comme en CI, où le mode géré aurait rougi le job. Il n'y
avait donc jamais eu de preuve navigateur. Corrigé, il en compte cinq, dont la
mesure du chevauchement et l'affectation depuis le panneau.

**D46 — Quand LIA passe la main, elle rend le ticket.** Un run qui s'arrête sur
une QUESTION ou qui livre un résultat À VALIDER a passé la balle : le ticket
retourne à son propriétaire **dans l'énoncé même qui solde le run**, et un
événement dit pourquoi (`reason: handed_back`), pour que le panneau le
distingue d'une remise à un pair et d'une connexion qui a pris fin. Une question
que personne ne détient est une question à laquelle personne ne répond. Un
ÉCHEC ne rend pas la main : rien ne le rejoue, mais rien n'est demandé à la
personne non plus, et la carte doit continuer de dire que c'est LIA qui a
trébuché.

**D47 — « LIA y travaille » se lit sur la REVENDICATION, jamais sur la
colonne.** Un run échoué laisse le ticket dans le « en cours » où il l'a
trouvé : lire le statut faisait dire « LIA y travaille » pour toujours et
**masquait la ligne d'erreur**, qui ne s'affiche que sur l'état `failed`. Lire
l'issue d'abord aurait été l'erreur symétrique — un run en vol porte encore
l'issue du précédent. `run_claimed_at` existait en base et n'atteignait pas
l'écran ; il y est publié, et c'est la seule chose qui veut dire « maintenant ».
Corollaire : une carte ne porte plus de badge que la colonne énonce déjà, donc
« LIA y travaille » et « Attend votre retour » — tous deux déduits du statut —
ont disparu ; un échec et un résultat livré restent.

**D48 — Les mots de LIA sont stockés en texte brut.** Un modèle répondant en
HTML mettrait ses balises devant la personne à quatre endroits d'un coup : le
panneau, l'extrait de la notification, la citation du heartbeat et l'export
lisible du registre. Aplaties UNE fois, là où le run écrit, avec le nettoyeur
que les surfaces de chat utilisent déjà — il ne touche ni le Markdown ni la
prose, donc « budget < 200 € » reste intact.

**D49 — Une entrée d'historique porte ses deux valeurs.** « Priorité modifiée »
énonce un fait sur lequel personne ne peut agir ; « Priorité : moyenne →
urgente » dit ce qui s'est passé. Le service enregistrait les dates SANS charge
utile — le seul genre d'événement qui ne pouvait pas être raconté — et les porte
désormais, une entrée par date qui a réellement bougé. Les valeurs voyagent
BRUTES (une clé de statut, un instant ISO) : les traduire et les formater est
l'affaire du lecteur, la même entrée se lisant en six langues et dans son propre
fuseau.

**D50 — Un ticket s'exécute dans la boucle ReAct, et le chat garde son
propre réglage.** Mesuré : `stream_chat_response` prend `user_execution_mode`
avec « pipeline » pour défaut, et AUCUN appelant hors tour ne le passait —
routines et tickets tournaient donc le planificateur quel que fût le choix de
la personne pour son chat. Le mode devient une décision de l'APPELANT, portée
par `StreamRequest.execution_mode` : une routine garde le pipeline déterministe
qu'elle a toujours eu (le défaut du champ), un ticket demande la boucle
(`react` par défaut ; réglage d'INSTANCE alors, colonne de la LIGNE depuis
D62), et rien ne lit jamais `user.execution_mode` sur ce chemin — le commutateur de l'en-tête
continue de ne parler que du chat. Une garde lit la source du runner et refuse
toute consultation de la préférence. Le coût est celui de ReAct (quatre à huit
fois le pipeline) sur des runs déjà bornés par le délai et le budget
d'itérations d'ADR-256 ; un ticket est une tâche à étapes sans personne pour
piloter un plan, ce qui est exactement le cas que la boucle sert.

**D51 — La carte dit si CE compte suit le ticket.** Un glyphe à côté du badge
de priorité, lu sur le drapeau du côté qui regarde — la cloche du propriétaire
n'est pas celle du détenteur. Un ÉTAT, pas le commutateur : le commutateur vit
dans le menu de la rangée, et un glyphe qui agirait au clic serait un contrôle
sans nom. Il porte le sien (`role="img"`) pour qui ne voit pas la forme.

### Ce que le lot 7 (la confirmation sur le ticket) a décidé

Trois demandes du propriétaire : une colonne « À confirmer » qui n'apparaît que
si une confirmation attend, une réponse écrite sur le ticket, et un traitement
qui reprend tout seul selon la réponse — vers « À faire » + LIA, ou
« Terminé » + la personne (« Annulé » alors ; D60 a supprimé la colonne).

**D52 — Un run de ticket DEMANDE au lieu de refuser.** Le refus hors tour
d'ADR-263 (amendé par D5) vaut pour une origine qui ne peut porter aucun
brouillon à la personne — une routine. Une origine qui le PEUT
(`RunOrigin.can_carry_draft`, posé par le runner du workboard et par lui seul)
traverse la porte comme un tour de chat : un outil `confirm` devient le
brouillon `TOOL_CALL` que le chat aurait montré, un outil `draft` construit le
sien. La décision reste une fonction pure (`decide_effect(..., carrier=)`), et
le drapeau est celui de la SURFACE, jamais de la source — une routine garde le
refus que D5 lui a donné, un rejeu approuvé est enregistré et exécuté.

**D53 — L'interruption est LUE dans les chunks que le flux émet vraiment.**
Mesuré 2026-09-09 : le moteur hors tour attendait un chunk `hitl_interrupt`
que RIEN n'émet — un run arrêté sur une clarification se soldait `success`
avec les jetons diffusés avant la question. Le flux dit
`hitl_interrupt_metadata` (les action requests), les jetons de la question,
puis `hitl_interrupt_complete` (`generated_question`). `TurnInterrupt(kind,
question, draft)` porte ce que le solde doit savoir, et le générateur est
consommé jusqu'à sa fin parce que sa queue commet la comptabilité des jetons.
Un `_StreamReader` lit chunk par chunk : `_one_attempt` était monté à CC 15
pile, le seuil interdit.

**D54 — Le ticket PORTE le brouillon et passe « À confirmer ».** Colonne
`confirming`, entre « En attente » et « En validation », dessinée par le
tableau seulement si son compte est non nul (`CONDITIONAL_STATUSES`) — une
huitième colonne vide sur chaque tableau serait le prix d'une situation que
la plupart ne rencontrent jamais. Le solde écrit `pending_action` (JSONB :
`draft_id, draft_type, draft_content, tool_name, question, approved`, migration
`7c1e9a4d52b6`), rend le ticket à la personne et dépose UN commentaire : la
question que LIA aurait posée, l'aperçu détaillé par le MÊME rendu que la
carte du chat (`render_detailed_preview`, aplati en texte), et comment
répondre — six langues. La clé HITL Redis du fil est effacée, comme pour
`waiting`. Un échec (délai, transport) laisse `pending_action` intact
(`KEEP_PENDING_ACTION`) pour qu'un « Lancer maintenant » rejoue l'approbation
au lieu de redemander. La notification `confirming` atteint le détenteur quels
que soient les drapeaux et pointe vers le ticket ; le heartbeat lit
`[confirming]` comme un ticket arrêté sur la personne.

**D55 — La réponse est un COMMENTAIRE, lue quand le ticket revient à LIA.**
Pas d'appel modèle : un lexique en six langues (`core/i18n_workboard`),
replié comme la réponse (accents, casse, ponctuation, `fold_name`), classe
la DERNIÈRE note du propriétaire depuis le dernier run — et seulement du
propriétaire, par la FORME de la requête (`owner_notes_since` prend l'auteur en
paramètre et épingle le genre `user` ; un pair signe `peer`, une couture qui ne
peut pas rendre ses mots quel que soit l'appelant). Approbation nue (« oui »,
« ok, vas-y », « yes please », « ja », « sí », « 好的 ») → « À faire » + LIA,
`pending_action.approved = true` ; refus nu (« non merci », « annule »,
« nein », « 取消 ») → « Terminé » depuis D60 (« Annulé » alors), le ticket
reste à la personne ; TOUT LE
RESTE est un amendement → « À faire » + LIA, brouillon effacé, et les notes
du propriétaire entrent dans le brief (`workboard_brief_notes`, plafond
`WORKBOARD_BRIEF_MAX_NOTES`). La direction sûre : « oui mais… » coûte une
question de plus, jamais une action que personne n'a voulue. Sans note, la
réaffectation est refusée (`workboard_answer_required`) — tourner sans
réponse ne ferait que redemander, au prix d'un run. Quitter « À confirmer »
par n'importe quel chemin (un glisser vers une autre colonne) efface le
brouillon. « En cours » suit au tour de balayage suivant (≤
`WORKBOARD_RUN_SWEEP_SECONDS`), par le chemin de revendication ordinaire : un
ticket ne se met jamais « en cours » sans revendication, car c'est aussi la
colonne d'un run échoué que rien ne doit relancer tout seul.

**D56 — Le rejeu tourne DANS le graphe, sous verrou d'empreinte.** Rien en
production n'installe de contexte d'exécution hors graphe (piège n° 2 de la
revue du lot 3) ; le brief cite donc l'action approuvée à la lettre
(`workboard_brief_approved_action`) et le run publie
`RunOrigin.approved_draft = (type, draft_digest(contenu))`. Quand l'outil
reconstruit son brouillon, le nœud HITL demande d'abord au run
(`nodes/draft_preapproval.py::decide_draft` — un module et un appel, pas une
branche : le nœud est gelé par le ratchet de taille et
`_handle_draft_critique` est à CC 29) : identité EXACTE → décision `confirm`,
l'exécuteur du chat exécute sous portée approuvée avec le vrai contexte et la
ligne d'effet porte `draft_digest` ; différente → interruption, nouvelle
capture, nouvel aperçu à confirmer. L'approbation est DÉPENSÉE au premier
match (objet partagé, jamais la ContextVar : un nœud tourne dans une copie du
contexte) — un second brouillon identique dans le même run redemande. **Un LOT
de brouillons est UNE identité** (`drafts_digest` sur la liste, dans l'ordre) :
le chunk de métadonnées transmet désormais l'outil et le lot entier, le ticket
en montre chaque aperçu, et l'approbation du premier de trois ne confirme
jamais les deux autres sans qu'ils aient été vus — la carte du chat, elle,
confirme un lot d'un seul geste parce qu'elle l'a affiché.
`workboard_replays_total{result}` mesure les non-correspondances (tableau
29). Limite énoncée : un corps de courriel n'est pas toujours reproduit à
l'octet ; la personne revoit alors un aperçu, et rien ne s'exécute sans
surveillance qui ne soit identique à ce qui a été montré (ADR-092).

**D57 — La sonde « une question est pendante » lit l'autorité du chat.**
`conversation_has_pending_hitl` lisait le point de reprise LangGraph ; après un
run qui a déplacé sa question sur le ticket, ce point de reprise dit
« interrompu » jusqu'à la prochaine entrée, et CHAQUE ticket suivant du compte
s'écartait (`SKIPPED_BUSY`) pour une question que personne ne pouvait plus
voir. Elle lit désormais l'enregistrement Redis que le chat lui-même consulte
pour router une réponse — celui que le run efface. Les deux sens de
l'indépendance tiennent et sont testés : N tickets « À confirmer » ne bloquent
ni le chat ni les autres tickets ; une question pendante DANS LE CHAT écarte
toujours les runs, délibérément.

**D58 — Un tour archive TROIS lignes, pas deux, et une notification n'en est
pas une.** Mesuré le 2026-09-09 sur le compte de dev, à partir d'un vrai run de
ticket : la question HITL — l'aperçu complet du brouillon de suppression — était
archivée comme un message d'assistant ORDINAIRE (`hidden=False`, sans tampon) et
s'affichait dans le chat de la personne, là où y répondre ne fait rien ; et la
ligne était **impurgeable**, la rétention cherchant `hidden` ET le tampon. La
cause est de forme : un tour archive jusqu'à trois lignes — la question de la
personne, la réponse, et, quand il s'arrête sur une interruption, la question
que LIA a posée À LA PLACE de la réponse — et seules les deux premières
passaient par un constructeur ; la troisième était un dictionnaire écrit sur
place. Le commentaire du lot 2 (« les DEUX lignes du run ») était vrai quand il
a été écrit : ce chemin était inatteignable pour un run de ticket jusqu'à ce que
le lot 7 lui permette de poser une question. `build_*_metadata` devient donc la
porte unique (`api/archive_metadata.py`), et une garde AST refuse un
dictionnaire écrit sur place à tout site d'archivage du paquet — falsifiée : en
remettant le défaut, elle nomme `service.py:1140`. **Une notification, elle,
reste LISIBLE** : elle porte l'identifiant du run mais n'est pas une ligne du
run, c'est ce que la personne doit lire. Réparer par l'identifiant de run seul
les confond — dix bulles de notification ont été cachées par le script de
réparation avant d'être rendues : un prédicat de réparation nomme la NATURE de
la ligne, jamais sa seule clé de corrélation.

**D59 — Le drapeau régit aussi les questions de LIA, et une question n'est
offerte qu'à son détenteur** (arbitrage du propriétaire, 2026-09-09, amendant
D6). Jusqu'ici « en attente » et « à confirmer » ignoraient
« Me dire ce qui se passe sur ce ticket », au motif qu'une question que personne
n'entend est un ticket qui ne bougera plus jamais. Trois lots ont retiré cette
prémisse : le tableau dessine « À confirmer » dès qu'elle tient un ticket (lot
7), le badge du hub compte ce qui attend la personne (`needs_me`), et le
heartbeat relance un ticket arrêté depuis plus de
`WORKBOARD_NUDGE_WAITING_HOURS` **sans lire le drapeau** (lot 6). Ce qui restait
était une phrase de chat qui contredisait la promesse du drapeau lui-même
(« LIA travaille en silence »), sur un drapeau désactivé par défaut. Le drapeau
dit désormais la vérité, et l'aide le dit en toutes lettres : le silence vaut
aussi quand LIA a besoin de vous, et « À confirmer » retient ce qui attend votre
réponse. Deux propriétés que le changement NE touche pas : une question n'est
offerte qu'au DÉTENTEUR — le côté qui ne peut pas y répondre ne la reçoit pas,
fût-il abonné, et c'est le drapeau du détenteur qui décide, jamais celui de
l'autre — et `assigned` reste le seul événement qu'aucun drapeau ne filtre :
personne ne s'abonne à un ticket qu'il ne sait pas encore détenir. Risque
assumé et énoncé : sur un ticket non suivi, un blocage peut dormir jusqu'à la
relance du heartbeat.

### Ce que les lots 8 à 13 (les treize retours) ont décidé

Treize retours du propriétaire après usage réel, dont un qu'il a lui-même
annulé en arbitrage (« Terminé » à la fin d'un run : « En validation » reste,
c'est la personne qui valide). Découpés en six lots, dont deux ne sont pas des
réglages d'écran : le mode d'exécution devient une propriété de la LIGNE
(lot 10) et la mise en forme des messages HITL change de langue (lot 13).

**D60 — « Annulé » disparaît, « Terminé » porte le refus.** Sept colonnes pour
un tableau personnel, c'était une de trop : sur un téléphone comme sur un
écran, la largeur perdue coûtait plus que la distinction gagnée. Un ticket
refusé est un ticket qu'on ne fera pas, et c'est exactement ce que « Terminé »
dit déjà — l'ÉVÉNEMENT garde la raison (`refused`), qui est l'endroit où elle
est utile. La migration REQUALIFIE les lignes existantes
(`UPDATE … SET status='done' WHERE status='cancelled'`) et sa descente est un
no-op documenté : rien ne sait quel « terminé » fut jadis un « annulé », et
inventer ce partage serait pire que l'assumer. `CLOSED_STATUSES` n'a plus qu'un
membre, et c'est le seul endroit qui le sait.

**D61 — Le commentaire EST la réponse.** Sur un ticket « À confirmer », envoyer
un commentaire ne demande plus rien d'autre : la réponse est classée
(approuve / refuse / amendement, six langues, sans modèle), le ticket repart
vers LIA en « À faire », et ses compteurs de tentative sont remis à zéro. Le
seul cas qui ne repart pas est le refus, qui clôt. La règle vaut pour le
PROPRIÉTAIRE du ticket et pour lui seul — un pair qui commente commente, il ne
répond pas à une confirmation qui ne lui a pas été posée. Et le plafond de runs
est vérifié AVANT la relance : une approbation ne doit pas pouvoir contourner
`WORKBOARD_MAX_RUNS_PER_TICKET`.

**D62 — Le mode d'exécution est une colonne de la LIGNE.** Il existait un
réglage d'instance (`WORKBOARD_RUN_EXECUTION_MODE`) : un opérateur choisissait
pour tout le monde, pour toujours, et une action planifiée n'avait même pas le
choix. Chaque ticket et chaque action planifiée porte désormais son mode
(`execution_mode`, NOT NULL, défaut `react`), modifiable tout au long de la vie
du ticket et lu à la PROCHAINE exécution — jamais au milieu d'un run. Le
réglage d'instance, sa constante et ses lignes `.env` ont été supprimés : deux
autorités sur la même question, c'est une de trop, et celle qui reste est celle
que la personne voit. Un seul champ de formulaire
(`ExecutionModeField`) sert le ticket, le panneau et les actions planifiées.

**D63 — Le ticket porte sa consommation, et c'est celle du compte.** Le détail
d'un ticket affiche IN / OUT / CACHE / GOOGLE et le coût, cumulés sur tous les
traitements, avec le même vocabulaire que le chat (`ContextUsagePill`) et sous
le même drapeau (`tokens_display_enabled`). Rien n'est compté deux fois : les
colonnes `total_*` sont l'ADDITION des `last_run_*`, écrites par arithmétique
de colonnes dans la transaction du settle, et la source est
`MessageTokenSummary` — la ligne que le tracker écrit déjà pour le compte. Le
ticket ne crée aucune comptabilité : il LIT la sienne.

**D64 — Le tableau se relit tout seul, et ne dérange jamais.** Une relecture
toutes les 30 s, qui ne lève pas l'indicateur d'occupation (le bouton
« rafraîchir » ne doit pas tourner seul), garde le dernier tableau confirmé si
elle échoue (un tableau d'une minute vaut mieux qu'une page d'erreur pour ce
que personne n'a demandé), et s'abstient dans trois cas : onglet caché, carte
en cours de déplacement, écriture en vol. Le compteur d'écritures est un
COMPTEUR, pas un booléen : deux écritures qui se chevauchent ne doivent pas
rouvrir la porte à la première qui finit.

**D65 — Ce qui bouge le dit, ce qui presse se voit.** Une colonne qui tient des
tickets respire (`motion-safe`, jamais quand elle est vide : le mouvement est
le signal), « En cours » tourne parce que son glyphe EST un compteur, et
« Urgent » prend un fond rose pâle — mesuré, un badge rouge et un badge
« warning » se lisent comme un même niveau quand on parcourt le tableau. La
poignée de déplacement disparaît : la carte entière se glisse, et un glyphe qui
désigne une poignée inexistante coûte de la largeur et ment.

**D66 — Le HITL parle UNE langue de forme, et c'est le Markdown.** Le rendu des
confirmations émettait `<br/>` en tête de CHAQUE ligne *et* comme séparateur :
tout aperçu s'ouvrait sur une ligne vide et chaque champ était séparé par deux.
Mesuré sur un ticket réel : `<br/>**Titre**: Réserver la salle<br/><br/>**Étapes**: 2`.
Le vocabulaire est désormais unique — une liste Markdown (`_row`), un
paragraphe pour un texte (`_block`), une ligne sans libellé (`_note`), jointes
par un simple saut de ligne. Trois raisons, et la troisième est la vraie : le
chat rend le Markdown sans greffon de saut dur, donc une LISTE est la forme qui
tient un champ par ligne sans balise ; une surface qui ne rend AUCUNE des deux
(un commentaire de ticket) peut aplatir du Markdown en quelque chose de
lisible, là où `<br/>` était lu tel quel ; et un aperçu qui n'a qu'une forme
n'a qu'un endroit à corriger. L'aplatissement a lui aussi UNE porte
(`markdown_to_plain_text`, à côté de `strip_html_if_markup`), appelée à
l'endroit unique qui écrit les mots de LIA — il ne fait que RACCOURCIR, donc le
plafond du commentaire tient toujours. Quatre défauts que le filet doré
épinglait sont partis avec la forme : un bloc « Message » vide sur un transfert
sans mot ajouté, un événement sans horaire affichant « Début : » au-dessus de
rien, la ligne des pièces jointes tombant APRÈS le corps du message, et la
ligne vide d'ouverture. Le filet a été régénéré et les 85 cas relus un par un :
c'est la relecture qui prouve qu'un changement de forme n'a touché que la
forme.

**D67 — Chaque brouillon a un NOM, dans la langue du lecteur.** La cascade de
`Draft.get_summary` finissait sur `f"Draft ({type.value})"`, et **neuf des
vingt-six types l'atteignaient** : on demandait à quelqu'un d'approuver
« 📄 Brouillon créé: Draft (ticket_delete) » — une valeur d'énumération, en
anglais, dans les six langues. La cascade devient une table de dispatch
(`summary_renderer.py`) avec sa garde de complétude au démarrage (ADR-085,
comme le rendu détaillé à côté d'elle), et dix libellés nouveaux dans les six
langues. Un renderer NOMME un libellé, il n'en formate pas : il rend la clé
i18n et ses paramètres, donc aucun d'eux ne peut embarquer une langue à lui.

**D68 — La ponctuation entre un libellé et sa valeur appartient à la langue.**
Un `": "` littéral dans le renderer publiait de la ponctuation anglaise dans
six langues. Le séparateur voyage avec les libellés — espace insécable avant le
deux-points en français, deux-points pleine chasse en chinois — et une ligne se
demande par CLÉ (`_row(lbl, "to", …)`) pour pouvoir lire les deux. Les dix-sept
libellés français du résumé, dont un seul respectait la règle, ont suivi.

### Ce que le lot 14 (la carte HITL a un seul auteur) a décidé

Deux captures du propriétaire, après le lot 13. Dans le chat, la carte de
confirmation s'étalait sur l'écran — un paragraphe par champ — et ses `---`
s'affichaient tels quels ; sur le ticket, l'e-mail était montré deux fois.

**D69 — Le renderer écrit la carte, le modèle écrit la question.** La carte
était ÉCRITE PAR LE MODÈLE sous un prompt qui la décrivait (titre, champs,
règles `---`) : sa forme était celle que le modèle voulait bien produire ce
jour-là. Mesuré le 2026-09-09 : des champs séparés par des lignes vides, donc
des paragraphes avec leur marge ; un `---` suivi d'un seul saut de ligne, que
le convertisseur de sauts durs (`_with_markdown_hard_breaks`) transformait en
`---<br/>`, qui n'est plus une règle. Corriger le convertisseur n'aurait
corrigé que la moitié. La carte a désormais un auteur —
`render_confirmation_card` (`drafts/preview_renderer.py`), l'emoji et le
titre lus dans le registre d'affichage, le corps étant l'aperçu du lot 13 —
et l'interaction la streame AVANT le premier jeton du modèle, puis `---` entre
deux lignes vides, puis la question. Le prompt ne décrit plus aucune carte :
« elle est déjà affichée au-dessus de ta réponse ; écris la question seule ».
C'est la doctrine d'ADR-274 (« the renderer owns the form, the model owns the
meaning ») appliquée au HITL, et elle coûte MOINS de jetons : le modèle ne
recopie plus les champs. Trois corollaires : le repli sans modèle montre la
même carte puis une phrase localisée (la question de suppression sous son
avertissement pour un type destructif, la phrase générique sinon), ce qui a
supprimé `draft_fallback_summary.py` et `_DRAFT_SUMMARIES` — une TROISIÈME
copie du vocabulaire de la carte que seul le repli lisait, et qui avait un
jour oublié `label_delete` ; le convertisseur ne colle plus jamais `<br/>` à
une règle horizontale, défense en profondeur ; et sur le ticket, le commentaire
est la question telle que streamée (elle PORTE la carte) suivie de la consigne
— `WorkboardMessages.confirming` n'a plus d'argument `preview`, et rien n'est
rendu deux fois.

### Ce que le lot 15 (la passe de design du ticket) a décidé

Dix remarques du propriétaire sur l'écran du ticket, avec un verdict d'ensemble :
« l'UI et l'UX ne sont pas au niveau d'excellence attendu ».

**D70 — Sept panneaux, un seul cadre.** Le détail d'un ticket était une colonne
de titres de poids inégaux, avec deux blocs (dernière exécution, coût) qui ne
s'alignaient pas. Chaque section est désormais un `Panel` — même cadre, même
titre avec son icône dans la couleur du thème, région nommée par son titre pour
un lecteur d'écran — chacun sur sa propre ligne, à pleine largeur. La revue à
froid a d'abord essayé la dernière exécution et le coût côte à côte : une
moitié de dialogue ne tient pas la ligne de coût, qui se repliait sur deux —
or le coût tient sur UNE ligne PAR CONTRAT, dans le vocabulaire du compteur
du chat (🟠 IN · 🟢 OUT · 🔵 CACHE · 🟣 GOOGLE · euros, deux décimales comme la
pastille de conversation), le nombre de runs en suffixe du titre ;
« Consommation de ce ticket » devient « Coût ». Et « Dernière exécution » dit
le VERDICT du run, jamais la colonne : un run en échec laisse le ticket dans la
colonne où il l'a trouvé, si bien que « À faire » sous « Dernière exécution »
ne disait rien du run. Six verdicts, les six du backend (`RunOutcome`, dont
`confirming` que le type frontend ignorait), dans les mots du panneau — un
run reporté est nommé (quota atteint, conversation en cours), jamais accusé
(ADR-272) — avec la ligne du run à six décimales comme celle d'un message, et
les chiffres suivent le commutateur de l'en-tête comme partout.

**D71 — Les mots sont ceux que l'application emploie déjà, sans notice.** Le
mode d'exécution offre « Mode Pipeline » / « Mode ReAct », les mots du
commutateur de l'en-tête du chat, sans paragraphe explicatif ; le suivi devient
« Notifier l'avancement dans le chat », sans paragraphe non plus — une notice
sous chaque réglage transformait un formulaire en manuel. Dans l'historique,
« Rendu » ne disait rien : un run qui rend le ticket écrit « LIA vous rend le
ticket », un pair qui le rend « Rendu au propriétaire ». La tuile « Registres »
de l'accueil dit « Tracer les actions ». Le libellé du mode est celui de
l'application, « Mode d'exécution », et non une périphrase. Deux défauts de
contenu trouvés par la même revue : la ponctuation entre un libellé de
l'historique et sa valeur était un littéral « : » — de la ponctuation
française publiée en six langues, le piège que le lot 13 avait fermé côté
backend — et voyage désormais avec les libellés (`workboard.history.separator`,
espace insécable avant le deux-points en français, deux-points pleine chasse
en chinois) ; et le REGISTRE du namespace avait dérivé : l'application
vouvoie en allemand (« Sie », 253 contre 32 dans `settings`) et en chinois
(« 您 », 134 contre 28) et tutoie en espagnol (133 contre 53), le workboard
faisait l'inverse dans les trois — mesuré, puis aligné, chaîne par chaîne.

**D72 — La carte dit d'abord à qui elle est, et jamais sa priorité en mots.**
La cloche puis le porteur ouvrent la carte, au-dessus du titre, le menu « ⋮ » à
leur droite : un tableau se parcourt pour « à qui est-ce » avant d'être lu. Le
badge de priorité disparaît — l'arête colorée et le fond d'urgent la disent
déjà, et « Élevée » en toutes lettres répétait l'arête — mais son nom reste,
masqué visuellement, pour un lecteur qui ne voit pas la couleur : la couleur
n'est jamais le seul porteur. Et le tableau se relit après un commentaire (la
réponse à une confirmation déplace le ticket côté serveur) et à la fermeture du
panneau : ce que la personne y a fait doit déjà se voir derrière.

### Ce que le lot 17 (la carte, les commentaires, le téléphone) a décidé

Sept remarques du propriétaire (2026-09-10), cinq pour ce lot.

**D73 — La cloche précède l'échéance, et un retard ne remplace jamais la
date.** Le lot 15 avait mis la cloche en tête de carte, devant le porteur ;
elle descend sous le titre, devant l'échéance, parce que « le chat me
préviendra-t-il, et pour quand » se lit d'une seule ligne. Et « En retard » ne
remplace plus la date : c'est une SECONDE ligne sous elle — la date dit pour
quand, la ligne dit que c'est passé. Remplacer l'une par l'autre perdait la
date le jour où elle comptait le plus.

**D74 — Les commentaires n'ont plus de filets : la tête datée de chaque tour,
sur un bandeau pastel du thème, est la séparation.** Un filet entre deux tours
et une barre à gauche de chacun dessinaient des cases ; l'auteur et l'instant,
sur `bg-primary/10`, disent où un tour commence sans rien tracer.

**D75 — Sur un téléphone rien ne se glisse : on balaie, on tape, on choisit.**
Le tableau à une colonne se parcourt par un balayage horizontal (au moins
48 px, nettement plus latéral que vertical — sinon c'est le défilement qu'il
ressemble), les deux flèches et la liste restant l'équivalent clavier et lecteur
d'écran. Aucune carte ne se soulève sous `lg` : la porte du titre S'ÉTEND sur
toute la carte par un pseudo-élément, le menu au-dessus, si bien qu'un doigt
posé sur la date ou la cloche ouvre le ticket. Dans le panneau, la colonne et
le porteur passent en tête des réglages : ce sont les deux listes par lesquelles
un ticket bouge là où rien ne se glisse. Au passage, le pas des flèches
parcourait `TICKET_STATUSES` alors que la liste affichée exclut « à confirmer »
quand elle est vide : depuis « terminé », « précédent » tombait sur une colonne
cachée — une seule fonction `step` sur les colonnes DESSINÉES sert les flèches
et le balayage.

**Le bouton « Rafraîchir » disparaît.** Le tableau se relit seul (toutes les
30 s, au retour sur l'onglet, après chaque écriture — lot 12) ; un bouton pour
le faire disait le contraire. **Et les filtres partent de l'URL** : un lien
`?overdue=1&assignee=lia` ouvre le tableau déjà réduit — c'est ce que la page
des réglages pointera (lot 18) — et l'URL SUIT ensuite les filtres, jamais
l'inverse pendant qu'on tape : une zone de recherche dont la valeur revient
par le routeur asynchrone perdait une frappe sur deux.

### Ce que le lot 18 (la page des réglages) a décidé

**D76 — La section Réglages › Workboard est le tableau en un coup d'œil.**
C'était une phrase et un bouton — « c'est ridicule d'avoir une page vide avec
un bouton » (propriétaire, 2026-09-10) — alors que D15 en fait la PORTE du
tableau. Elle lit désormais `GET /workboard/summary` : chaque chiffre est un
AGRÉGAT sur l'ensemble entier (ADR-185) — jamais la longueur d'une page que
personne n'a demandée — et chaque chiffre est un lien vers le tableau réduit à
lui (`?overdue=1`, `?assignee=lia`, `?status=todo`, les filtres du lot 17).
Les comptes courent sur ce que le compte VOIT (possédé ou détenu), les sommes
sur ce qu'il POSSÈDE : un run travaille avec les outils du propriétaire et lui
est facturé, si bien qu'un ticket qu'un pair m'a confié est dans mes colonnes
mais ni dans mes runs ni dans mes euros. Le plafond que l'instance impose est
PUBLIÉ avec les chiffres (ADR-184) et dessiné en jauge — « 7 / 200 tickets » —
et le coût des exécutions s'affiche dans le vocabulaire du compteur du chat,
sous le commutateur de l'en-tête comme partout. Les requêtes vivent dans
`summary_queries.py`, à côté du dépôt et non dedans : le fichier du dépôt est
sous le plafond de taille logique, et ces énoncés n'appartiennent qu'au résumé
— le filtre du dépôt est devenu public (`filtered_stmt`) pour que le résumé
compte sur le MÊME prédicat de visibilité que la page.

### Ce que le lot 19 (trois retours du 2026-09-10) a décidé

**D77 — Là où rien ne se glisse, la colonne et le porteur sont des LISTES
sur la carte, entre le titre et l'échéance.** Le lot 12 avait retiré la
liste de colonne de la carte parce que la colonne se change en glissant et
que le titre de colonne au-dessus la répétait ; sur un téléphone rien ne se
glisse (D75), et le propriétaire a demandé les deux listes sur la carte
elle-même. Elles ne sont dessinées que sans poignée de glisser — sur le
tableau large la colonne reste le geste et la carte ne porte aucune liste —,
au-dessus de la porte étendue (D75) pour rester des listes, nommées avec le
ticket (« Colonne de … », « Porteur de … ») parce qu'une colonne de cartes
disant toutes « Colonne » ne dit rien à un lecteur d'écran, et elles écrivent
les MÊMES patchs que le panneau. Un porteur qui n'est pas le propriétaire n'a
que la colonne : le service ne lui permet que de rendre le ticket, et une
liste à une seule réponse n'est pas une liste — le panneau offre le retour en
bouton. UN composant `HolderSelect` sert la carte et le panneau, comme
`StatusSelect` : deux listes de porteurs ne peuvent pas se contredire.

**Les panneaux du détail sont des cartes.** `bg-muted/20` sur le fond du
dialogue mesurait 94,6 % de clarté sur 95 % : invisible en mode clair
(propriétaire, 2026-09-10). Chaque panneau est désormais `bg-card` avec une
bordure pleine et une ombre — visible dans les deux modes, la carte étant plus
claire que le fond en clair et plus claire que le fond en sombre.

### Ce que le lot 20 (quatre retours du 2026-09-10) a décidé

**D78 — Sur la carte, la colonne PUIS le porteur, l'une sous l'autre.** Le
lot 19 les avait posées côte à côte en deux demi-largeurs ; sur un téléphone
chacune tronquait ses propres options. La colonne d'abord — c'est elle qui
déplace le ticket —, le porteur dessous, à la même marge, à pleine largeur.
Le navigateur le mesure (parcours à 390 px) : le porteur commence sous le
pied de la colonne, au même bord gauche.

**D79 — Chaque item des deux listes porte son glyphe devant son nom, et la
liste est celle de l'application.** Un `<option>` natif ne contient que du
texte ; la marque d'une colonne (celle de l'en-tête et des puces des réglages,
`columnIcon`) et celle d'un porteur (celle du badge de la carte, `partyIcon`,
DÉPLACÉ dans `lib/workboard/icons.tsx` pour qu'un badge et une liste ne
portent jamais deux marques pour une idée) ne peuvent pas y entrer. Les deux
listes passent donc au `Select` du dépôt (Radix), par UN composant
`GlyphSelect` dont `StatusSelect` et `HolderSelect` sont les deux
vocabulaires : l'item est un glyphe puis un mot, le déclencheur fermé reflète
l'item choisi glyphe compris, une pression ou une touche sur le déclencheur
n'atteint aucun ancêtre (Radix compose ses propres gestionnaires APRÈS et
ouvre quand même — le test le lit sur l'événement lui-même), et un geste
commencé DANS la liste ouverte lui appartient : l'arbre React traverse le
portail, mesuré par une sonde — sans cela un balayage sur un item atteignait
le balayage de colonnes du tableau et changeait de page au lieu de choisir.
Le sélecteur de colonne du téléphone (D28) est la MÊME liste avec ses
compteurs exacts (`statuses`, `counts`). Ce que D17 et D28 avaient acheté
avec le natif est réexaminé : le sélecteur de la plateforme est cédé à la
demande du propriétaire, et la raison technique — une liste portée en
portail se disputant le pointeur avec les capteurs de glisser — ne tient
plus nulle part où ces listes sont dessinées : sous `lg` aucune carte n'est
un élément triable, et le panneau est un dialogue. Deux pièges de jsdom que
les tests nomment : une liste ouverte cache le reste de la page à l'arbre
d'accessibilité (une région se relit APRÈS fermeture), et un corps sous
`pointer-events: none` refuse le second clic. Les filtres de la barre
restent natifs : ils n'ont pas de glyphe par item.

**D80 — « En retard » aligné sous la cloche, et un contour rouge qui
respire.** L'icône du retard est logée dans la même case de 20 px que la
cloche au-dessus d'elle, avec le même écart : le mot commence exactement
sous la date (le navigateur mesure les deux abscisses). Un ticket en retard
porte un contour (`outline`, 2 px — jamais la bordure : le bord gauche reste
la priorité) qui respire entre 35 % et 100 % de l'encre `destructive` sur
2,8 s en `ease-in-out` — lent, jamais un clignotement — et seulement sous
`motion-safe` : un lecteur qui a demandé moins de mouvement garde le contour
immobile, à pleine force, l'état FINAL de l'animation et non son absence
(doctrine du système de design). Le navigateur le prouve deux fois : sous
`reduce` (le réglage de la suite) aucune animation et un contour plein de
2 px, sous `no-preference` une `CSSAnimation` nommée `overdue-pulse` d'au
moins deux secondes.

*Amendé le jour même (lot 21).* Le contour est un CADRE INTÉRIEUR, et il
part de la couleur d'un bord normal. Un `outline` entourait la carte entière,
liseré de priorité compris ; le propriétaire a demandé que ce liseré reste
DEHORS et que la pulsation parte d'un bord ordinaire plutôt que d'un rouge
atténué. Le cadre est un pseudo-élément `::before` posé sur la boîte de
remplissage (`absolute inset-0` se mesure depuis le bord intérieur des
bordures, par définition CSS) : à gauche il commence APRÈS les 4 px du
liseré, qui garde sa teinte de priorité, et sur les trois autres côtés juste
sous la bordure de 1 px. Il respire entre la couleur de bordure de la carte
(`border` à 60 %) et `destructive`, sous `motion-safe` seulement ; immobile
il est rouge, l'état qui porte l'information. `pointer-events: none`, sous
le contenu et sous la porte étendue. Le navigateur lit le pseudo-élément
(`getComputedStyle(el, '::before')`, `getAnimations({ subtree: true })`) :
cadre de 2 px, animation portée par `::before`, liseré gauche de 4 px d'une
autre couleur que le cadre.

**D81 — Toutes les listes du tableau sont la même liste à glyphes.** Un
panneau qui mêle deux familles de contrôles (chevron natif contre chevron
Lucide) se lit comme deux applications ; le propriétaire a tranché :
aligner, avec glyphe (2026-09-10). `PrioritySelect` (les quatre niveaux
portent une marque RANGÉE — `ChevronsUp`, `ChevronUp`, `Minus`,
`ChevronDown` — dans l'encre du liseré de leur priorité, `priorityInk`
déclaré à côté de `priorityAccent` pour qu'un bord et une liste ne se
contredisent jamais), `ExecutionModeField` (les marques du basculeur du
bandeau de chat, `Workflow` et `Zap` : les mêmes mots, les mêmes signes),
et les trois filtres de la barre — porteur, priorité, tri — sur
`GlyphSelect`, qui porte désormais le glyphe de FAMILLE dans son étiquette
(`labelGlyph`, ce qui a absorbé `FieldLabel`). « Tout le monde » et « Toute
priorité » partagent UNE marque, l'astérisque : c'est la même idée, « n'importe
lequel ». Radix refuse un item à valeur vide, donc « toute priorité » voyage
sous une sentinelle (`PRIORITY_ANY`) que le filtre traduit en `undefined` —
un filtre non posé ne coûte toujours aucun paramètre de requête. Le
formulaire de création perd ses deux `<select>` copiés (priorité, porteur)
pour les listes partagées : trois surfaces, un vocabulaire.

**D82 — Les glyphes de personnes portent la couleur du thème, partout sur le
tableau.** L'étincelle de LIA la portait seule ; « Moi » et une connexion
restaient gris (propriétaire, 2026-09-10). `partyIcon` teinte les trois —
badge de la carte, ligne « appartient à », listes de porteur, items du filtre
« Détenu par » — et laisse `unknown` neutre : ce n'est pas une personne.

## Conséquences

Ce que le lot 1 met en place et que les gardes tiennent désormais :

- trois tables classées dans `user_data_map`, couvertes par la purge (avec la
  libération explicite) et par l'export bilatéral ;
- un vocabulaire unique, dont l'ordre des colonnes, les priorités, les genres
  d'acteur et vingt-et-un codes d'erreur stables épinglés par un test de contrat ;
- une porte de visibilité unique, réutilisée par toutes les lectures ;
- 137 tests unitaires et 27 tests d'intégration PostgreSQL, dont la preuve du
  comportement de cascade qui a invalidé la première conception.

Le lot 2 livre l'exécution hors tour et l'amendement de la porte :

- un moteur unique pour « LIA exécute une instruction hors tour »
  (`infrastructure/scheduler/out_of_turn_run.py`), EXTRAIT de l'exécuteur de
  routines et repris par lui sans qu'aucun de ses 102 tests de caractérisation
  ne change — sa complexité cyclomatique est passée de 46 à 27 au passage ;
- l'amendement d'ADR-263 : `draft` rejoint `confirm` parmi les politiques qui
  exigent quelqu'un, parce qu'elle pose la même question par un autre moyen —
  elle LÈVE une interruption HITL, et sur le chemin des routines cette
  interruption devenait une `RuntimeError` non réessayable en RESTANT sur le fil,
  de sorte que le message suivant de la personne était lu comme une décision
  qu'elle n'avait jamais prise ;
- **les deux lignes d'un run sont archivées et cachées** : ne rien archiver
  était la première conception et elle était fausse — le registre de décisions
  POINTE vers la question et la réponse avec des pierres tombales `SET NULL`, et
  un run sans lignes aurait été indiscernable d'une conversation supprimée. Le
  tampon vit dans les métadonnées, la colonne en est DÉRIVÉE au seul endroit qui
  construit la ligne ; les avoir séparés a coûté un défaut que seule une
  exécution réelle a vu (2026-09-09, toute la suite verte, les deux lignes
  visibles dans le chat) ;
- le balayage, sa revendication `SKIP LOCKED`, son moissonneur, sa rétention,
  le brief versionné construit des seuls mots du propriétaire, les notifications
  filtrées par le suivi et cinq métriques dessinées sur le tableau de bord 29 ;
- 91 tests unitaires de plus et 40 tests d'intégration PostgreSQL, dont la
  course à deux workers indépendants et sa **falsification** (sans
  `SKIP LOCKED`, le perdant attend 0,82 s derrière le gagnant).

Le lot 3 ouvre le tableau au chat : le domaine `ticket`, l'agent
`ticket_agent` et six outils qui ne portent AUCUNE règle métier — le service
possède les droits, les bornes, les transitions et la résolution des pairs, et
chaque borne qu'il applique est publiée dans le manifeste depuis les réglages
(ADR-184). Trois décisions y ont été prises contre le premier jet :

- **l'agent s'appelle `ticket_agent`, pas `workboard_agent`** : la garde de
  nommage DÉRIVE l'agent du domaine, et une seconde orthographe casserait cette
  dérivation pour un gain cosmétique ;
- **la suppression déclare `draft`, pas `confirm`** : `confirm` est réservé aux
  outils MCP tiers, où la politique est DÉDUITE des annotations du serveur, et
  la forme native de tout outil destructeur ici est la carte de brouillon. La
  conséquence est celle qu'on veut : un run sans surveillance ne supprime rien,
  puisque la porte refuse `draft` quand personne ne peut répondre ;
- **la notification « ce ticket t'a été confié » passe par une COUTURE**
  (`domains/shared/proactive_sink`), parce que `agents` importe maintenant
  `workboard` et que le distributeur importe `agents`. Le démarrage déclare ce
  câblage et refuse une couture muette : ADR-270 a mesuré ce que coûte un effet
  de bord d'import que personne ne déclare — un no-op silencieux sur le chemin
  exact qu'un balayage empruntait.

Le routage est MESURÉ : 12 familles × 6 langues, dont trois familles négatives
(une tâche du fournisseur, un rappel, une routine) qui doivent partir ailleurs.
La moitié déterministe tourne en CI sans réseau ; la moitié fournisseur est un
script (`task workboard:corpus:measure`), parce qu'un test qui se saute sur une
clé absente est vert et pourrit (ADR-155). Mesuré le 2026-09-09 : **72/72 sur
`deepseek-v4-flash` et 72/72 sur `gpt-5.6-luna`**, pour une dépense d'environ
0,02 $ par passage — hors registre, comme le script de récurrence qu'il imite :
une mesure d'ingénierie n'est pas une action de LIA. Le script réchauffe
lui-même le cache des clés fournisseur depuis la base (`provider_api_keys`),
comme le démarrage le fait : sans cela, un script autonome tourne sur les
valeurs par défaut et chaque appel répond 401.

Le lot 5 branche le crochet qui manquait, et il a trouvé en chemin une chose
qu'il ne corrige PAS : **le répartiteur de notifications des pairs appelle le
distributeur directement**, sans passer par la couture qui revendique un effet,
si bien qu'aucun de ses quatre genres d'événement ne laisse de ligne dans
`agent_effects` (mesuré le 2026-09-09 ; le plan de ce lot attendait le
contraire, et l'attente était fausse). Ce n'est pas une omission de câblage :
un événement de pair n'a aucun des trois auteurs qu'ADR-263 distingue — ce
n'est ni un balayage, ni une instruction différée de la personne, ni une page
qu'elle vient d'ouvrir, mais le RELAIS de l'acte d'un tiers, et il n'a pas
d'identifiant de run unique (une paire peut être retirée, redemandée, retirée à
nouveau, et la même clé se relirait comme un rejeu). Lui donner un auteur et
une clé est une décision, pas une réparation : elle appartient au domaine
`peers`, pas au tableau.

Le lot 6 clôt le programme : la source heartbeat, la table de placement qui
lui a fait de la place, et la seconde porte que le registre ignorait.

## Ce que cette décision ne fait pas

Pas de tickets récurrents (une routine existe), pas de pièces jointes sur les
commentaires, pas d'étiquettes, pas de tableaux multiples, pas de modèles de
ticket, pas de synchronisation temps réel entre deux navigateurs, et pas de
second niveau de hiérarchie.
