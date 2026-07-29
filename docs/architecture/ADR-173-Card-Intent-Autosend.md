# ADR-173 : `?draft=` préremplit, `?intent=` exécute — deux verbes, deux liens

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Date**: 2026-07-29
**Décideurs**: Équipe LIA (arbitrage utilisateur A1, programme UX Actions 2026-07-28)

## Contexte

L'arbitrage A4 (UXR Lot 8) avait posé un contrat clair : tout ce qui remplit le
composer — commandes slash, chips de suite, liens `?draft=` des cartes du
briefing (QW-9) — **préremplit et n'envoie jamais**. Ce contrat protège une
chose précise : un texte que l'utilisateur n'a pas encore lu ne part pas en son
nom.

QW-24 introduit un objet différent : un **bouton d'action nommé** sur un item
de carte (« Résumer », « Préparer une réponse », « Terminé », « Reporter »,
« Itinéraire », « Préparer un message »). Ici le libellé du bouton EST la
demande, affichée avant le clic — le clic est l'acte délibéré. Forcer un second
Entrée dans le chat n'ajoutait aucune information, seulement un détour.

## Décision

Un second paramètre de deep-link, `?intent=`, **sémantiquement disjoint** de
`?draft=` qui reste inchangé :

- `?draft=` — préremplir, ne jamais envoyer (contrat A4, intact) ;
- `?intent=` — envoyer automatiquement, une seule fois, par **le chemin exact
  d'un message tapé** (`sendMessageFromPresent` — la règle du retry W3 : jamais
  une seconde route d'envoi subtilement différente).

Garde-fous du côté page (`useAutoSendIntent`, consommé-une-fois via ref,
paramètre retiré de l'URL **avant** l'envoi — un rechargement ou un retour
arrière ne renvoie jamais) :

- session bloquée par quota → l'intent est **sauvé comme brouillon persistant**
  et dit à voix haute (toast), jamais envoyé de force ni perdu ;
- API indisponible ou tour en cours de streaming → l'envoi **attend** le
  changement d'état (l'effet se rejoue), sans timeout artificiel ;
- auth non résolue → rien ne part.

**Approbation** : l'intent hérite exactement du niveau de protection du
pipeline chat — ni plus, ni moins qu'en tapant la même phrase. Les écritures
gardées par un brouillon HITL (mails, mises à jour de tâches classées
`task_update`) présentent leur carte de confirmation ; `complete_task` s'exécute
directement car cocher une tâche est réversible (se décoche) — c'est le
comportement du chat, pas une exception créée par ce lien.

Une action qui exige les mots de l'utilisateur reste un `?draft=` : « Poser une
question sur ce document » préremplit « Au sujet du document “X” : » — envoyer
un tronçon vide serait du bruit.

## Conséquences

- Les chips d'action sont des **frères** du bouton principal de l'item (un
  bouton dans un bouton est invalide en HTML et inatteignable au lecteur
  d'écran) ; leur nom accessible est la phrase d'intent complète.
- `chatIntentHref` vit à côté de `chatDraftHref` (`lib/briefing-utils.ts`) ;
  les intents exécutables vivent sous `dashboard.briefing.intents_exec.*`
  (6 langues), distincts des intents de préremplissage QW-9.
- Épinglé par `hooks/__tests__/useAutoSendIntent.test.ts` (envoi unique sous
  StrictMode, attente sur API/streaming, repli brouillon derrière le mur de
  quota) et `dashboard/__tests__/cards-actions.test.tsx` (chips frères,
  encodage, itinéraire seulement si lieu, « question » = draft).

## Alternatives écartées

- **Étendre `?draft=` avec un flag `&send=1`** : un seul paramètre aux deux
  sémantiques, le contrat A4 devient conditionnel — exactement le flou que A4
  avait éliminé.
- **Endpoints REST directs par action** (compléter la tâche sans passer par le
  chat) : duplique la logique HITL et le relevé d'erreurs des connecteurs hors
  du pipeline qui les possède ; une nouvelle surface d'écriture à auditer pour
  zéro gain utilisateur.
- **Auto-envoi sans repli quota** : forcer l'envoi contre un mur 429 aurait
  transformé un clic honnête en erreur ; le brouillon persistant garde la
  demande.
