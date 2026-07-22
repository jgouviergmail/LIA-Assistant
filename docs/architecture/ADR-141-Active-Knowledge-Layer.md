# ADR-141 : Couche de connaissance active — domaine documents et personne 360°

**Statut** : Accepté — implémenté (backend), preuve runtime dev.
**Date** : 2026-07-22
**Contexte produit** : P1 + P3 du programme « Interdomain Intelligence »
(spec `docs/superpowers/specs/2026-07-22-lot5-knowledge-layer-design.md`) ;
suit [ADR-140](ADR-140-Chat-Piloted-Automations.md).

## Contexte

Deux connaissances de premier ordre restaient passives : les espaces
documentaires RAG de l'utilisateur n'étaient interrogés que par l'injection
automatique sur le dernier message (aucune itération planner/ReAct possible,
aucun croisement dirigé), et aucune capacité n'agrégeait ce que l'assistant
sait d'une personne (chaque domaine cherchait isolément).

## Décision

- **P1 — Domaine routable `document`** : `search_user_documents_tool`
  (read-only, sans OAuth) sur `retrieve_rag_context` (recherche hybride
  existante), extraits plafonnés, session propre. Routabilité **filtrée au
  chokepoint `_build_available_domains`** quand `RAG_SPACES_ENABLED` est off
  (pattern téléphonie exact — `is_routable` est statique). L'injection
  passive du response node est inchangée : les deux mécanismes coexistent
  (appoint automatique + capacité dirigée).
- **P3 — `get_person_overview_tool`** sur le `contact_agent` (foyer
  person-centrique) : 4 sous-fetches en parallèle, chacun avec sa session et
  sa frontière d'échec — fiche contact (résolution de provider dynamique
  Google/Apple/Microsoft, pattern heartbeat), derniers emails, événements à
  30 jours mentionnant la personne, mémoires pertinentes (embedding du nom).
  **Partialité honnête** : `partial_failures` liste les blocs indisponibles ;
  un connecteur absent = bloc vide, pas d'échec ; contact introuvable =
  `person_not_found`.
- **Budget du loader gelé** : les enregistrements du programme passent par
  UN agrégateur (`registry/program_manifests.py::register_program_manifests`)
  — coût net zéro dans `catalogue_loader` par nouveau domaine.

## Alternatives rejetées

- **Espaces RAG en simple paramètre du domaine `file`** : sémantiques
  disjointes (Drive = fichiers cloud par nom/type ; spaces = connaissance
  sémantique) — les fusionner dégrade le routage des deux.
- **Colonne `Memory.linked_contact_id` dès v1** : migration + écriture
  extracteur pour un gain incertain avant la mesure J+14 de P5 — différée
  (l'embedding du nom suffit au rappel v1).
- **Sous-fetches Drive/rappels dans la personne 360°** : différés — les
  quatre blocs v1 couvrent la préparation de réunion/appel, cas d'usage
  cible.

## Conséquences

- « Compare le devis du PDF avec l'email de Paul » et « prépare mon call
  avec Marie » deviennent des chaînages natifs du planner/ReAct.
- Le skill `preparation-reunion` gagne une source d'agrégation en un appel.
- Vérification : TDD (10 tests nouveaux ciblés + smoke registre outils
  auto-couvrant), suites complètes vertes, preuve runtime dev.
