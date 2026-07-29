# ADR-174 : Le débriefing d'appel est persisté — extension consciente de D-8

**Statut**: ✅ IMPLEMENTED (2026-07-29)
**Date**: 2026-07-29
**Décideurs**: Équipe LIA (programme UX Actions 2026-07-28, lot E / T01)

## Contexte

La minimisation D-8 posait : après un appel sortant, seuls `summary` +
`structured_data` (extraction fournisseur minimale) survivent ; le transcript
brut n'est jamais stocké. Le retour utilisateur était une phrase à la première
personne (`proposal_text`), livrée par notification et enrichie d'une
suggestion de rendez-vous déterministe (P14).

T01 demande un débriefing exploitable : engagements pris, tâches et rappels de
suivi, brouillon de message, points à vérifier. Deux faits contraignent la
conception :

1. Ces éléments sont un produit de **notre** synthèse LLM — pas de l'extraction
   fournisseur : c'est `ReturnProposal` qui s'étend (champs additifs, un modèle
   qui renvoie la forme v1 valide toujours), **pas** `StructuredCallData`.
2. La surface A6 (« Appels récents ») existe précisément parce qu'un retour
   uniquement notifié se perd : un débriefing embarqué dans la seule
   notification aurait recréé le défaut qu'A6 corrigeait.

## Décision

- Nouvelle colonne `phone_calls.debrief` (JSONB nullable) : `commitments`,
  `follow_up_tasks`, `follow_up_reminders`, `follow_up_draft`, `uncertainties`.
  Un débriefing **entièrement vide persiste comme NULL** — l'absence, pas du
  bruit ; c'est aussi le chemin du repli quand la synthèse échoue.
- **Même rétention que `summary`** : le reaper D-8 efface `debrief` dans le
  même UPDATE. L'extension de périmètre est donc bornée : mêmes données
  dérivées, même TTL, même purge.
- Le débriefing voyage aussi dans les **metadata de notification**
  (`type: proactive_phone_call`) — même surface PII que le texte qu'il
  accompagne — pour la carte chat.
- Un composant unique `CallDebrief`, deux postures : **informatif** dans la
  bulle chat (l'utilisateur répond au rapport naturellement) ; **actionnable**
  dans « Appels récents » — chaque tâche/rappel part en `?intent=` (ADR-173),
  le brouillon part en `?draft=` (un message à un tiers exige la relecture de
  l'utilisateur, jamais d'envoi automatique).

## Alternatives écartées

- **Débriefing seulement dans la notification** : perdu à la première
  notification manquée — la leçon A6, réapprise.
- **Étendre `structured_data`** : mélangerait extraction fournisseur et
  synthèse maison dans un même sac JSONB, en brouillant qui produit quoi (la
  correction de trajectoire exacte de la conception de ce lot).
- **Étendre la collecte ElevenLabs** : configurerait l'agent vocal du
  fournisseur pour un travail que notre synthèse fait déjà avec le transcript
  complet sous les yeux.
