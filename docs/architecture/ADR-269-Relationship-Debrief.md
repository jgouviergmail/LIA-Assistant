# ADR-269 : Un débrief par relation, écrit une fois par jour, et lu par le chat

**Date** : 2026-09-07
**Statut** : Accepté
**Amende** : ADR-176, ADR-184, ADR-190

## Contexte

La fiche d'une relation empile dix sections. Personne ne lit dix sections. Ce
que le lecteur cherche d'abord — *où j'en suis avec cette personne, et qu'est-ce
qu'il faut aborder* — est une synthèse qu'aucun agrégat ne produit.

La même synthèse vaut dans le chat : nommer quelqu'un ne devrait pas faire
annoncer une recherche pour des faits que la base détient déjà.

## Ce qui existait, et la découverte qui a décidé de la forme

| Pièce | Où | Ce qu'elle donne |
|---|---|---|
| Moitié locale | `RelationsService.build_detail` | engagements, appels, souvenirs, messages relayés — pages **plus totaux exacts** |
| Moitié fournisseur | `RelationContextService.build` | fiche contact, mails, rendez-vous ; statut par section, cache Redis |
| Périmètre | `RelationOverviewScope` | ce qu'un « point 360° » a le droit de lire |
| **Assemblage des preuves** | `get_person_overview_tool` | **tout ce qui précède, sous le périmètre, avec `unavailable`** |

La quatrième ligne est la découverte : l'assemblage dont un débrief a besoin
**existait déjà**, dans un outil d'agent. En écrire un second aurait créé deux
autorités sur « ce qu'un point 360° lit » — la classe de défaut qu'ADR-185 existe
pour empêcher.

## Décision

**(1) L'assemblage est EXTRAIT** de `agents/tools/person_tools` vers
`domains/relations/overview` (`blocks` / `recall` / `fallback` / `evidence`), et
l'outil en devient le premier consommateur. Le refactor est épinglé par un
fichier doré (`golden_overview_payloads.json`) capturé sur le code AVANT
extraction : 18 cas de périmètre, charge utile et message comparés à l'octet.

**(2) Un défaut de coût est fermé au passage.** L'assemblage appelait
`RelationContextService.build()` **inconditionnellement**, puis jetait les blocs
que le périmètre excluait. Un lecteur ayant décoché `contact`, `emails` et
`events` payait quand même jusqu'à **onze appels externes** (trois recherches
mail par adresse × trois adresses, plus la fiche et l'agenda). C'est le piège
d'ADR-184 pointé vers le coût : une sélection publiée, puis non honorée. La
lecture fournisseur est désormais rétrécie, ce qui demande un troisième statut,
`NOT_REQUESTED` : « je n'ai pas regardé, exprès » n'est ni « rien trouvé » ni
« je n'ai pas pu ».

**(3) Le débrief obéit au périmètre.** Le seul endroit où l'utilisateur a
déclaré ce qu'un point sur cette personne peut lire gouverne aussi ce que le
débrief lit — ce qui borne du même coup le coût fournisseur et la taille du
prompt (`max_items`).

**(4) Construit paresseusement, à l'ouverture de la fiche, jamais par un
ordonnanceur.** `relations_total` n'est borné par rien : un balayage nocturne
serait N utilisateurs × M relations appels LLM par jour.

**(5) Au plus une fois par jour LOCAL** — « une fois par jour » est une promesse
sur la journée du lecteur, et une frontière UTC reconstruirait à 2 h du matin
pour la moitié de l'Europe. Trois reconstructions sont légitimes : un changement
de langue, un changement de périmètre, et la demande explicite du lecteur. Les
deux premières laisseraient sinon un texte stocké contredire les réglages de
celui qui le lit.

**(6) L'empreinte des preuves n'est comparée qu'avec les preuves en main.** Un
drapeau passif « les données ont bougé » énoncerait un négatif que personne n'a
vérifié (ADR-184). En revanche, à la construction, il gagne sa place : une
reconstruction forcée sur des preuves identiques **n'appelle aucun modèle** et
reporte le JOUR sans toucher à la date d'écriture des mots — exact, parce que
cela vient d'être vérifié. Et le raccourci n'est PAS pris quand la langue ou le
périmètre ont changé : les preuves sont les mêmes, le texte dû ne l'est pas.

**(7) Rien n'est inventé.** Aucune preuve → `empty` : pas d'appel, pas de
paragraphe générique. Un échec **conserve** ce que le lecteur avait déjà, sous
une ligne disant que l'actualisation a échoué — remplacer une synthèse encore
utile par un panneau vide transforme « je n'ai pas pu rafraîchir » en « il n'y a
rien », qui est une autre réponse, et fausse.

**(8) La revendication est une seule instruction SQL** —
`INSERT … ON CONFLICT DO UPDATE … WHERE … RETURNING` — donc deux onglets ne
dépensent jamais deux appels. `held_until` porte deux sens qui se lisent
pareil (« indisponible avant cet instant ») : le bail d'un constructeur mort, et
le refroidissement d'un échec. Chaque clôture cite son `claim_owner` : un
constructeur dont le bail a expiré n'écrase pas la réponse d'un autre.

**(9) Dans le chat, le débrief REJOINT le bloc pair, il ne le remplace pas** — et
sa directive est l'**inverse**. Le bloc pair dit que ses faits sont EXACTS et
qu'il faut répondre sans chercher : c'est vrai d'une lecture en base faite dans
le tour même. Appliquée à une synthèse de plusieurs jours, la même phrase est
une machine à affirmations fausses. Le gabarit du débrief dit qu'il est **daté**,
et renvoie aux outils toute date, tout compte, tout statut. Une correspondance
**ambiguë n'injecte rien** : l'annuaire des débriefs contient toutes les
relations ouvertes, noms d'entreprise et numéros compris, et un faux positif ne
dégrade pas une réponse — il tend le dossier d'une personne à une question qui
portait sur une autre.

**(10) L'injection réutilise le créneau existant** (`_inject_peer_context`) :
`fetch_response_context` porte une complexité cyclomatique de 67 que la porte
d'audit gèle, et son `asyncio.gather` est typé par des surcharges qui s'arrêtent
à six awaitables. Une seconde injection aurait coûté les deux.

**(11) L'utilisateur peut couper**, depuis la page Relations, à l'endroit même où
le résultat s'affiche — et coupée, la capacité se réduit à la ligne qui la
rallume : une fonctionnalité qui disparaît sans retour est un défaut.

**(12) Ce que le débrief a coûté est écrit à côté de ce qu'il a produit.**
Le nombre de jetons et le prix en euros sont stockés sur la ligne (`usage`,
JSONB) et affichés sous le texte, dans le même badge que la synthèse du jour
(`LLMUsageBadge`, remonté en `components/ui/`) — un seul concept, un seul
composant, sinon deux surfaces finissent par chiffrer différemment la même
chose. Trois règles portent cette colonne :

- **Les chiffres voyagent avec les mots.** `settle_ready` écrit le corps ET son
  coût ; `settle_empty` efface les deux ; `settle_failed` n'écrit ni l'un ni
  l'autre, donc une reconstruction ratée laisse intacts le texte précédent et
  son prix. Un coût orphelin décrirait un texte qui n'est plus là.
- **Un coût nul est une AFFIRMATION**, pas une absence : une ligne écrite avant
  cette colonne, ou dont le cache tarifaire n'a pas su répondre, rend `None` et
  n'affiche rien. Jamais « 0,00 € ».
- **C'est un résumé d'AFFICHAGE, jamais une comptabilité.** L'enregistrement qui
  fait foi reste `token_usage_logs`, écrit séparément et conservé au-delà de la
  suppression du compte.

Le badge n'est **pas** gardé par `tokens_display_enabled`, et c'est délibéré :
cette préférence gouverne la bande de débogage par message du chat — une aide à
l'inspection présente à chaque tour — pas le prix d'un artefact que LIA a écrit.
Les trois surfaces qui montrent un artefact daté (synthèse du jour, carte
d'accueil, débrief) le montrent donc toujours. Confondre les deux portes ferait
rencontrer le même chiffre sous deux règles différentes selon l'écran.

## Ce que la factorisation a supprimé

- `person_tools._resolve_provider_client` dupliquait `open_category_client`, en
  moins sûr : il rendait un client portant un `ConnectorService` lié à une
  session déjà fermée, donc un rafraîchissement OAuth sur ce chemin écrivait sur
  une session morte.
- Le lecteur de prompt par CHEMIN existait en **trois copies** (telephony,
  meetings, document_generation) et une quatrième allait naître : une seule
  reste, `core/prompt_store.py`, chaque domaine gardant son vocabulaire typé et
  son exception.
- Le détecteur de mention de nom descend dans `domains/shared/name_mentions.py` :
  `relations` en a besoin et `agents` importe `relations`, donc l'y laisser
  aurait refermé un cycle — et un import local n'aurait fait que le cacher.

## Rejetés

- **Un balayage nocturne** : coût non borné (voir 4).
- **Construire pendant un tour de chat** : latence sur le chemin de réponse, et
  un vecteur de dépense déclenché par du texte libre.
- **Injecter dans le planificateur et la boucle ReAct** : des tokens sur trois
  chemins au lieu d'un, et trois fichiers gelés par les ratchets.
- **Un historique des débriefs** : la seule valeur de l'artefact est d'être le
  dernier, et toutes ses sources appartiennent déjà au compte.

## Conséquences

Nouvelle table `relation_debriefs` (une ligne par identité canonique, purgée
avec le compte, exportée dans l'archive RGPD), nouveau type LLM
`relation_debrief`, deux prompts versionnés, une bascule par compte, quatre
panneaux sur le tableau de bord 05. Une fusion ou une scission **supprime** les
débriefs concernés : la clé est l'identité, et un texte gardé décrirait quelqu'un
que le CRM n'a plus.
