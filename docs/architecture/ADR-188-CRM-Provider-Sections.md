# ADR-188 : le CRM peut sortir de la base, à condition de dire ce qu'il a regardé

**Statut**: ✅ IMPLEMENTED (2026-07-31), amendé le même jour (§7-§12)
**Date**: 2026-07-31
**Décideurs**: Équipe LIA
**Révise**: [ADR-176](ADR-176-Personal-CRM-Relations.md) (« aucun appel fournisseur », phase 2 documentée)
**Complète**: [ADR-185](ADR-185-Exact-CRM-Counts-And-Readable-Relayed-Messages.md)

## Contexte

ADR-176 avait tranché : v1 en **lecture seule sur la base**, aucun appel
fournisseur, pas de cache. Le raisonnement tenait — prouver l'usage au coût le
plus bas — et il notait déjà la suite : contacts et anniversaires exigeraient
« le connecteur contacts ET une surface d'identité contact↔relation »,
explicitement renvoyés en phase 2 plutôt qu'à moitié câblés.

La demande produit ferme cette phase 2 : voir la **fiche contact**, les
**emails échangés** et les **rendez-vous partagés** avec la personne.

## Le point dur : une relation est un NOM, un fournisseur veut une ADRESSE

Vérifié dans le code avant de concevoir :

- **la recherche d'emails par nom d'affichage ne marche pas.** La requête est
  appariée contre des en-têtes MIME ; un nom y ramène des inconnus et en rate
  d'autres.
- **`list_events(query=)` n'a aucune parité inter-fournisseurs** — Google
  cherche en plein texte, Apple filtre localement sur son propre jeu de
  champs, Microsoft exécute du KQL — et aucun ne promet « cette personne est
  **participante** » plutôt que « cette chaîne apparaît quelque part ».
- **une requête unique « from OU to » est impossible** : `convert_imap_query`
  (Apple) construit un **ET** de critères, `build_search_filter` (Microsoft)
  route vers la boîte de réception par défaut, et Gmail conjoint aussi les
  opérateurs séparés par une espace.

## Décision

### 1. La fiche contact est la clé de voûte, et elle est vérifiée

Le carnet d'adresses de l'utilisateur est **le seul** endroit où un nom de CRM
devient une adresse. La recherche fournisseur est donc une **piste, jamais un
verdict** : chaque candidat est replié par `fold_name` — le même point de
passage sur lequel le CRM regroupe les personnes — et rejeté s'il ne
correspond pas exactement. Sous-matcher coûte une section vide ; sur-matcher
attacherait les adresses de quelqu'un d'autre, et **tout le reste en découle**.

Le carnet est aussi la **seule** source d'adresses. L'email de compte d'un pair
n'est pas utilisé, alors qu'il est connu : l'exposer relève du réglage dédié du
chantier C-bis, pas d'un effet de bord du CRM.

### 2. Une recherche par direction, et c'est le seul contrat portable

> Amendé par le §7 : la copie compte, donc **trois** recherches par adresse.

Chaque direction est demandée à ses propres conditions (`from:<adresse>` puis
`in:sent to:<adresse>`), et chaque réponse porte la direction qui l'a produite.
Une recherche qui échoue ne vide jamais l'autre : une moitié d'échange est une
loupe incomplète, une section vide serait un **faux négatif**.

Le calendrier, lui, demande une **fenêtre** et filtre les participants
localement — la seule formulation à la fois portable et exacte sur ce qu'elle
veut dire.

### 3. Pas de compte, mais une portée

ADR-185 interdit un compte qui n'est pas exact, et une page de fournisseur ne
prouve jamais combien de lignes existent derrière elle. Ces sections ne
comptent donc **rien** : elles disent la **fenêtre** regardée (« les 90 derniers
jours et les 90 prochains ») et le nombre d'adresses sur lesquelles la réponse
repose. C'est la même exigence qu'ADR-185, appliquée à une source qui ne peut
pas donner de total : on énonce la portée au lieu d'inventer un chiffre.

### 4. « Je n'ai pas pu regarder » n'est pas « je n'ai rien trouvé »

Cinq statuts par section, dont un qui n'existe pas dans le briefing :
`no_address` — la fiche existe mais ne porte aucune adresse, donc la question
n'a **jamais été posée**. Rendre cela comme « aucun email » serait un négatif
non vérifié, exactement ce qu'ADR-184 a supprimé ailleurs.

À l'écran, une seule phrase à la fois, classée par ce sur quoi l'utilisateur
peut agir : brancher un compte, puis mettre une adresse sur la fiche. Trois
encarts « connectez un compte » sur chaque relation seraient du harcèlement ;
le silence total rendrait la fonction invisible.

### 5. Un endpoint séparé, un cache par section

`GET /relations/{name}/context` est distinct du détail 360° : il sort du
réseau, il est lent et il échoue autrement. Le détail ne doit jamais l'attendre
— il s'affiche, et ces sections se remplissent derrière. Cache Redis par
section avec des TTL alignés sur le rythme de chaque source (6 h pour un
carnet d'adresses, 15 min pour le courrier et l'agenda), clé **hachée** sur
l'identité repliée : un nom d'affichage n'a rien à faire brut dans une clé
Redis, et deux orthographes d'une personne doivent partager son entrée.

Deux emprunts au briefing sont **refusés** : le *stale-while-error* (une donnée
datée sous un nom de personne vaut moins qu'un manque énoncé) et les comptes.

### 6. Pilotable

`RELATIONS_PROVIDER_SECTIONS_ENABLED` (défaut activé) rend au CRM sa posture
d'origine ADR-176 : à false, il ne sort plus jamais de la base et les sections
n'existent pas. Le reste est borné par des réglages parce que chaque borne est
un **coût** : `MAX_ADDRESSES` (trois recherches chacune — §7), `WINDOW_DAYS`,
`EMAIL_WINDOW_DAYS` (§8), `MAX_ITEMS`, et le quota par utilisateur.

## Amendements (retour produit, même jour)

### 7. Trois recherches par adresse, pas deux : la copie compte

« Envoyé à cette personne » inclut **être en copie**. Or `cc:` n'était reconnu
par aucun des deux convertisseurs (`from|to|subject|after|before|label|is|has|in`)
— chez Apple il serait tombé en recherche plein-texte, chez Microsoft en KQL
brut. Deux comportements différents pour une même requête, donc des faux
positifs. `cc:` a donc été **appris aux convertisseurs** (critère `cc`
d'imap_tools, terme KQL) plutôt que bricolé dans la requête : côté Microsoft
le résultat était déjà correct **par accident**, et un accident n'est pas un
contrat.

### 8. Une fenêtre sur le courrier aussi

Les rendez-vous avaient une fenêtre, le courrier non. La fenêtre borne la
**pertinence** et ce que le fournisseur balaie — **pas le quota** : une
recherche coûte un appel quelle que soit son étendue. Ce qui borne le quota,
c'est le **nombre d'appels** (1 + 3×N + 1) et le garde-fou par utilisateur.
Le courrier remonte plus loin que l'agenda (365 j contre 90) : la
correspondance est plus clairsemée que les réunions.

### 9. Le calendrier de l'utilisateur, jamais `primary`

Le premier jet lisait le calendrier par défaut du client. C'est exactement le
défaut que `connectors/preferences` existe pour fermer : il a déjà répondu
qu'un pair était libre à 10 h alors que son agenda — dans un calendrier
nommé — contenait une réunion. `resolve_owner_calendar_id` est désormais
appelé, ce qui a fait remonter la session et le type de connecteur dans le
contexte client (`CategoryClient`).

### 10. Participant et organisateur sont deux faits

Les deux comptent — un rendez-vous que la personne a **organisé** est partagé
avec vous aussi sûrement qu'un auquel elle assiste — et ils sont distingués.
**Apple n'expose aucun organisateur** : plutôt que de tout étiqueter
« participant » (un rôle que personne n'a vérifié), la charge indique que la
distinction est **inconnue**, et l'écran n'affiche alors aucun rôle. La
détection se fait **sur les données** (« un événement de cette fenêtre
portait-il un organisateur ? »), pas sur le nom du fournisseur : un agenda
vide ne prétend rien non plus.

### 11. Le cache se rafraîchit à la demande, une fois

La fiche contact vit six heures : sans commande, une correction du carnet
d'adresses reste invisible une demi-journée. `GET …/context?refresh=…`
court-circuite le cache des sections nommées ; une section inconnue est
**ignorée** (un contournement de cache n'est pas une surface de commande, et
un client périmé ne doit jamais transformer une lecture en erreur).

Côté écran, ce rafraîchissement est un **appel impératif ponctuel**, pas une
clé de requête : `?refresh=` collé à l'endpoint aurait fait court-circuiter le
cache à **chaque** relecture ultérieure du panneau — un bouton prévu pour être
pressé une fois serait devenu « ne plus jamais utiliser le cache », et aurait
dépensé du quota pour de bon. Un échec de rafraîchissement **laisse la réponse
en place** : la remplacer par du vide transformerait « je n'ai pas pu regarder
à nouveau » en « je n'ai rien trouvé ».

### 12. L'ordre et le repli

Les sections suivent l'ordre demandé — fiche contact, engagements, souvenirs,
appels, emails, rendez-vous, puis le reste — et les fournisseurs sont
**entrelacés** plutôt qu'ajoutés à la fin : ils arrivent plus tard, mais ils
appartiennent là où le lecteur les attend, pas là où le réseau les place.
Chaque section se replie (`aria-expanded` + `aria-controls` sur un vrai
bouton) et **démarre repliée** : une fiche empile jusqu'à huit sections, et
sans repli la page devient un défilement que personne ne finit. Le lecteur
arrive sur un **index compact** de la relation — chaque titre avec son compte
exact — et ouvre ce qu'il est venu chercher, au lieu de faire défiler sept
sections pour atteindre la huitième. C'est aussi pourquoi la pastille de
compte est sur le bouton et non dans le panneau : replié, le compte est la
seule chose qui reste pour choisir.

Une sélection d'emails peut être **résumée dans le chat** via `?intent=`
(auto-envoyé) et non `?draft=` : cocher des messages puis presser un bouton
nommé EST l'acte délibéré, et la demande s'adresse à LIA — `?draft=` reste
réservé à ce qui écrit à un **humain**.

## Conséquences

**Positives**

- La fiche 360° répond enfin « qui est cette personne » et pas seulement « ce
  que LIA a noté d'elle ».
- Une section défaillante ne coûte que sa propre carte.
- Les trois fournisseurs passent par un seul analyseur : les clients Apple et
  Microsoft normalisent déjà vers la forme Google (`{"results": [{"person"}]}`,
  `{"items": [...]}` avec `attendees[].email`).

**Négatives / assumées**

- Ouvrir une fiche peut coûter jusqu'à 1 + 3×N + 1 appels fournisseur (N
  adresses), amortis par le cache. C'est le prix d'une question qu'on ne pose
  qu'en ouvrant explicitement une carte.
- Sans fiche contact, il n'y a ni emails ni rendez-vous. C'est dit, pas caché.
- Les anniversaires restent hors périmètre : ils demandent une surface
  d'identité contact↔relation persistante, pas une recherche à la volée.

## Alternatives écartées

| Alternative | Pourquoi non |
|---|---|
| Chercher emails et agenda par NOM | Prouvé cassé : en-têtes MIME côté courrier, aucune parité `query=` côté agenda, et aucune notion de « participant » |
| Une seule requête « from OU to » | Le convertisseur IMAP construit un ET, Microsoft reste sur la boîte de réception : l'échange perdrait sa moitié envoyée |
| Filtrer les participants côté fournisseur | Aucun des trois ne l'offre de façon comparable ; le filtre local est portable ET exact |
| Utiliser l'email de compte du pair comme adresse | Contournerait le réglage dédié de C-bis par un effet de bord |
| Fusionner ces sections dans `GET /relations/{name}` | Ferait attendre au détail — instantané et local — la latence et les pannes du réseau |
| Afficher un total d'emails ou de rendez-vous | Une page de fournisseur ne prouve aucun total (ADR-185) |
| Réutiliser `briefing.CardStatus` | Lierait `relations` à `briefing` pour cinq constantes, sans le statut `no_address` dont cette surface a besoin |
