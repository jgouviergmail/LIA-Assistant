# ADR-138 : Feedback 👍/👎 sur les réponses ordinaires

**Statut** : Accepté — implémenté (backend + frontend), preuve runtime dev bout-en-bout.
**Date** : 2026-07-22
**Contexte produit** : QW-5 du chantier « Quick Wins UX » (spec
`docs/superpowers/specs/2026-07-21-quick-wins-ux-program.md`), suit
[ADR-133](ADR-133-Execution-Trace-Per-Message.md) /
[ADR-134](ADR-134-Actionable-Connector-Error-Notices.md) (Lot 1 du même chantier).

## Contexte

Le pattern de feedback complet n'existait que pour les notifications
proactives d'intérêt (boutons dédiés, `POST /interests/{id}/feedback`,
`feedback_submitted` relu cross-device). Les réponses ordinaires n'avaient
qu'un bouton Copier : aucune mesure directe de satisfaction sur le cœur du
produit, et aucun canal utilisateur vers les compteurs evidence/contradiction
des journaux (ADR-135) pourtant conçus pour encaisser ce signal.

## Décision

- **Endpoint** : `POST /conversations/me/messages/{message_id}/feedback`
  (`{verdict: thumbs_up|thumbs_down, comment?}`). Verdict persisté dans
  `message_metadata.response_feedback` par **UPDATE `jsonb_set` atomique
  scopé propriétaire** (pattern exact de `mark_interest_feedback_submitted`) ;
  message étranger/non-assistant → 404 (existence cachée). Module dédié
  `conversations/response_feedback.py` (le repository est à 9 SLOC de son cap
  ratchet).
- **Identification du message** : le chunk `done` porte
  `archived_message_id` (l'archive précède le done — vérifié) ; les lignes
  d'historique portent leur id DB via `metadata.message_db_id` injecté par
  `toUiMessage`. Le `done` synthétisé d'un run annulé (ADR-117) n'a pas d'id →
  les boutons apparaissent après rechargement.
- **Couplage journaux par PORT injecté** : `journals` dépendant déjà de
  `conversations`, importer journals depuis conversations (même paresseusement)
  fermait un cycle de domaine (ratchet F009, attrapé par le garde). Le port
  `JournalFeedbackHooks` (Protocol) vit côté conversations ; l'implémentation
  `journals/feedback_hooks.py` est enregistrée au démarrage
  (`startup/registries.init_response_feedback_hooks`) — la couche composition
  autorisée à voir les deux domaines. Hooks absents + flag actif → warning
  loggé (jamais de mort silencieuse).
- **Compteurs au PREMIER verdict seulement** : 👍 → `evidence`, 👎 →
  `contradiction` sur les entrées de `injected_journal_ids` (IDs archivés avec
  le message à l'archive — aucun contenu). Les compteurs n'ont pas de chemin
  de décrément : un changement de verdict (autorisé — souveraineté) met à jour
  le verdict stocké et la métrique, jamais les compteurs. IDs étrangers,
  disparus ou malformés silencieusement ignorés, cap défensif
  `RESPONSE_FEEDBACK_JOURNAL_IDS_MAX`.
- **Commentaire du 👎** : stocké avec le verdict, et déposé comme entrée
  **L0 `user_correction`** (même forme que le levier feedback-portrait) **sans
  consolidation** — pas de coût LLM par pouce (arbitrage 2026-07-21).
- **Métrique** : `response_feedback_total{verdict}` — première mesure directe
  de satisfaction sur les réponses ordinaires (les proactives gardent
  `proactive_feedback_total`).
- **Frontend** : `ResponseFeedbackButtons` — chips 👍/👎 à côté de Copier
  (révélées au survol sur desktop, visibles sur mobile, même idiome d'opacité),
  `aria-pressed` sur le verdict actif, hydratation depuis le metadata persisté,
  champ « qu'est-ce qui n'allait pas ? » optionnel déplié au 👎
  (Entrée envoie, Échap ferme). Exclusions : notifications proactives (boutons
  dédiés conservés), messages système, stream actif, message sans id archivé.
  **Jamais de re-génération automatique** — l'utilisateur décide.

## Preuves

- Backend : 6 tests d'intégration sur vraie DB (verdict persisté + evidence,
  changement de verdict sans re-comptage, commentaire → L0, journaux
  désactivés, ownership/404, IDs étrangers ignorés) ; suite unit fast
  10 644 verts ; garde cycles 31/31 baseline ; lint global vert.
- Frontend : 4 tests composant (soumission, correction 👎, hydratation +
  changement, Échap) ; contrat `toUiMessage` verrouillé ; suite 2 282 verts ;
  ratchet CC **abaissé** (max 74 → 60, extraction des helpers purs de
  ChatMessage).
- Runtime dev bout-en-bout : tour réel → `done.archived_message_id` observé →
  `POST feedback {thumbs_down, comment}` → metadata relu
  `{"verdict": "thumbs_down", "comment": "Trop générique."}` → id étranger 404 ;
  `response_feedback_journal_hooks_registered` au boot.
