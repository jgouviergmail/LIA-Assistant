# ADR-139 : Registre des boucles ouvertes (open loops) et relance heartbeat

**Statut** : Accepté — implémenté (backend), preuve runtime dev.
**Date** : 2026-07-22
**Contexte produit** : P5 du programme « Interdomain Intelligence »
(spec `docs/superpowers/specs/2026-07-22-lot2-open-loops-design.md`,
programme `docs/superpowers/specs/2026-07-21-interdomain-intelligence-program.md`).

## Contexte

Aucun sous-système ne suivait les engagements exprimés en conversation :
« je dois rappeler le plombier », « Marie doit m'envoyer le devis ». Ces
boucles ouvertes mouraient avec le fil de discussion — l'assistant ne
relançait jamais, ni l'utilisateur sur ses promesses, ni sur ce qu'il
attendait d'autrui. C'est le différenciateur « assistant qui n'oublie
rien » identifié comme pilier n° 1 de l'analyse produit du 2026-07-21.

## Décision

- **Nouveau bounded context `domains/open_loops/`** : table `open_loops`
  (sujet, contrepartie, `direction` ∈ {user_owes, waiting_on_other},
  `due_hint` UTC consultatif, statut open/closed/expired, `last_nudged_at` +
  `nudge_count` pour l'anti-harcèlement), index partiel `(user_id) WHERE
  status='open'`. Transitions par **UPDATE conditionnel atomique**
  (`close_loop`, `expire_stale` — jamais SELECT→mutate→flush).
- **Extraction = 5e extraction post-réponse** (même point d'insertion et
  mêmes gardes que mémoire/intérêts/journaux/psyché :
  `_schedule_post_response_extractions`, sources automatisées et messages
  triviaux exclus, `safe_fire_and_forget`). Une passe LLM structurée
  (`open_loop_extraction`, nouveau type LLM tier LOW) voit la queue de
  conversation ET les boucles ouvertes existantes (ids inclus) → émet
  `open` (nouvelles boucles) et `close` (clôture conversationnelle
  « c'est fait »). Règles d'application déterministes et testées à part
  (`apply_extraction`) : cap par utilisateur, cap par tour, doublons de
  sujet ignorés, `due_hint` ISO parsé avec tolérance.
- **Relance via le heartbeat** : nouvelle source `open_loops`
  (`context_sources.fetch_open_loops_context`) — expiry **paresseuse**
  (pas de job scheduler dédié), filtre « nudge-worthy » (échéance sous
  `OPEN_LOOPS_NUDGE_DUE_HOURS` ou dépassée, ou stagnation ≥
  `OPEN_LOOPS_NUDGE_STALE_DAYS`) hors cooldown
  (`OPEN_LOOPS_NUDGE_COOLDOWN_DAYS`). Règle 19 du prompt de décision
  (ton « rappel utile », une boucle max par notification, jamais de
  répétition). Le bump du cooldown a lieu **après notification délivrée**
  et seulement si la décision a réellement utilisé le label `OPEN_LOOPS`
  (un bump au fetch supprimerait des boucles que le LLM a choisi d'écarter)
  — même emplacement transactionnel que le ledger intérêts ADR-135.
- **API v1 minimale** sous flag (`GET /open-loops`,
  `POST /open-loops/{id}/close`, 404 à existence cachée) ; l'UI arrive avec
  la section briefing (Lot 4 du programme).
- **Flag `OPEN_LOOPS_ENABLED` (défaut false)** + module de config dédié
  (7 réglages `OPEN_LOOPS_*` dans `.env`). Pas d'opt-out utilisateur en v1 :
  la surface proactive est déjà bornée par l'opt-in heartbeat par
  utilisateur (fenêtres + budgets/jour) ; à revoir avec l'UI Lot 4.

## Alternatives rejetées

- **Clôture par scan des fils email en v1** : coût API récurrent des scans
  de threads — différée en v2 (arbitrage D3 du programme).
- **Dédoublonnage vectoriel** : colonne embedding + seuils = complexité
  prématurée ; le prompt reçoit les boucles existantes et dédoublonne
  en passe, avec garde exact-match en ceinture-bretelles.
- **Job scheduler d'expiration** : l'expiry paresseuse dans le fetcher
  suffit (aucune exigence de fraîcheur hors cycle heartbeat).

## Conséquences

- La qualité de l'extraction est le risque principal (faux positifs =
  nuisance) : prompt volontairement conservateur (« an empty list is the
  NORMAL output »), caps serrés, mesure J+14 prévue après release.
- `sources_used` gagne le label `OPEN_LOOPS` (enum `HeartbeatSourceLabel`).
- Vérification : TDD intégral (48 tests unitaires nouveaux sur le lot),
  suite complète verte, migration à tête unique, preuve runtime dev.

## Suite (2026-08-02, v1.27.7) : corriger n'est pas créer

L'API v1 laissait une seule sortie à un engagement mal extrait : le classer
sans suite. Autrement dit, **perdre** l'information plutôt que la corriger —
alors que la cause n'est pas l'engagement mais la façon dont la conversation
a été lue.

**`PATCH /open-loops/{loop_id}`** ouvre exactement deux champs : le `subject`
(1 à 500 caractères, jamais vide) et le `due_hint`. Un booléen `clear_due_hint`
distingue « laisse l'échéance tranquille » de « il n'y a finalement pas
d'échéance », ce qu'un champ nullable ne sait pas exprimer avec `None` seul.

**`direction` et `counterparty` restent en lecture seule**, et c'est la
décision de fond : les changer ne corrigerait pas cet engagement, cela en
décrirait un autre. Ce qui fait la valeur du registre est qu'il reflète ce
qui a été dit ; un registre que l'utilisateur peut réécrire entièrement n'est
plus un registre automatique, c'est une liste de tâches manuelle — la
fonctionnalité que l'ADR-139 avait explicitement écartée.

La correction porte la **même réclamation atomique** que `close_loop` :
propriété et statut dans la clause `WHERE`, si bien qu'un engagement clos,
expiré ou appartenant à quelqu'un d'autre n'est jamais touché et que
l'appelant l'apprend par la valeur de retour. Une modification vide est un
no-op explicite plutôt qu'un `UPDATE` qui ne changerait que `updated_at`.

**Surface** : les quatre gestes (fait, relancer, plus d'actualité, corriger)
sont désormais offerts depuis la fiche d'une relation autant que depuis les
réglages — le moment où l'on pense à un engagement est celui où l'on regarde
la personne concernée. La section est renommée « Engagements » et remonte
dans Réglages → Fonctionnalités ; le lexique de la recherche des réglages
conserve les deux termes, un renommage qui efface l'ancien mot rendant la
section introuvable pour qui l'a connue sous son premier nom.
