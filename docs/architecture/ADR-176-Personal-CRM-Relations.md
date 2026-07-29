# ADR-176 : CRM personnel — agrégation en lecture seule, identité assumée best-effort

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Date**: 2026-07-29
**Décideurs**: Équipe LIA (programme UX Actions 2026-07-28, lot G / N-09)

## Contexte

N-09 veut capitaliser sur ce que LIA sait déjà des personnes : dernières
interactions, sujets ouverts, engagements, préparation 360°. Trois signaux
portent déjà un nom de personne en base : les open loops (`counterparty`,
ADR-139), les appels (`callee_display`), et les mémoires (texte libre).

Le point dur, identifié dès la conception, est la **résolution d'identité** :
rien ne relie « Gérard Dupont » d'un open loop au « gérard dupont » d'un appel
ni à un contact du carnet d'adresses. Une fausse fusion (deux personnes) ou un
faux clivage (une orthographe manquée) est inévitable sans référentiel de
contacts unifié.

## Décision

**v1 = agrégation en lecture seule, sur le pattern `domains/briefing`.**

- Nouveau domaine borné `relations/` : pas de LangGraph, **pas de nouvelle
  table** — il lit les domaines existants. Deux endpoints GET
  (`/relations` overview, `/relations/{name}` détail 360°), aucune surface
  d'écriture : agir sur une relation se fait dans le chat (le front pose un
  `?intent=`, ADR-173).
- **Identité best-effort, énoncée** : les noms sont repliés (NFKD + casefold) ;
  un groupe dont toutes les orthographes brutes sont identiques est `EXACT`,
  sinon `NORMALIZED`. Le détail affiche un bandeau d'avertissement sur un
  match `NORMALIZED` — l'incertitude est dite, jamais maquillée en précision.
- **Concurrence** : une poignée de requêtes indexées par requête, exécutées
  SÉQUENTIELLEMENT sur une session (guidance CLAUDE) — pas de `asyncio.gather`,
  donc pas de risque de session partagée.
- **Pas de cache en v1** : deux requêtes indexées, et la fraîcheur prime pour
  un CRM ; aucun coût fournisseur à amortir. (Le cache se justifiera en
  phase 2 avec les anniversaires/contacts — le préfixe de nommage est réservé
  dans la doctrine, pas de code mort.)
- **Périmètre honnête** : les anniversaires (« prochains moments importants »)
  exigeraient le connecteur contacts ET une surface d'identité contact↔relation
  — c'est la **phase 2**, documentée ici plutôt qu'à moitié câblée. Le champ
  correspondant a été retiré des schémas pour ne pas laisser de donnée morte.
- **Accès** : la page `/dashboard/relations` est atteinte par l'en-tête de la
  carte For-you (qui porte déjà les counterparties) et par la recherche des
  réglages — PAS une 6ᵉ destination de nav (R01 a déjà poussé l'en-tête à 5,
  qui clippe entre 768 et 1024 px).

## Alternatives écartées

- **Table CRM persistante + résolution d'identité forte** : le vrai référentiel
  de contacts unifié est un projet en soi ; le livrer avant d'avoir prouvé
  l'usage serait spéculatif (YAGNI). L'agrégation lecture seule teste la valeur
  au coût le plus bas.
- **6ᵉ entrée de navigation** : l'en-tête clippe déjà à 5 destinations en
  fr/de/es/it (R01) ; une de plus ferait de la nav mobile-menu la norme desktop.
- **Cache de l'overview** : masquerait des changements récents (un engagement
  qu'on vient de clore) pour économiser deux requêtes indexées — mauvais
  compromis pour un CRM.
- **Matching mémoire sémantique (embeddings)** : la recherche par sous-chaîne
  de nom est grossière mais transparente ; un rapprochement sémantique
  surprendrait (« pourquoi cette mémoire ? ») sans le budget d'explication.
