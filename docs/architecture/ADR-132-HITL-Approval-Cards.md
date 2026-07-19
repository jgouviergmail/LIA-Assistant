# ADR-132 : Cartes d'approbation HITL one-click (Lot 1 P1-V1)

**Statut** : Accepté — implémenté (backend + frontend), preuves runtime dev.
**Date** : 2026-07-18
**Contexte produit** : P1 du chantier « UX cœur conversationnel » (specs 2026-07-18).

## Contexte

Le HITL de LIA (7 types d'interactions, `services/hitl/interactions/`) émettait
des payloads riches (`hitl_interrupt_metadata` : `action_requests`,
`available_actions` stylés, contextes typés) mais le frontend n'en rendait
rien : la réponse passait exclusivement par le texte libre, classifié par un
LLM (`hitl_classifier`) à chaque approbation. Le composant `<LARSCard>` cité
dans les docstrings backend et le hook `useDraftActions` (LOT 6) n'avaient
jamais été câblés.

L'inventaire runtime préalable (captures SSE réelles, deux modes) a établi :

- **Un seul outil `hitl_required=True` dans tout le système** (délégation
  sub-agent) : le flux dominant réel est `draft_critique` (avec connecteurs)
  et `clarification` (validations sémantiques) — le phasage a été inversé en
  conséquence (draft + destructive + for_each + tool ensemble en V1).
- **Fait protocolaire** : un flux d'interruption se termine SANS chunk `done`
  (metadata → question tokens → complete → fermeture SSE).
- Le contrat unifié `HitlInterruptPayload` est partiellement aspirationnel :
  les émissions sont des dicts par interaction ; `available_actions` manquait
  sur `tool_confirmation` et les `keyboard_shortcut` ne sont jamais émis.

## Décision

### Préambule de sécurisation (bugs latents corrigés avant l'UI)

1. **Cancel ADR-117 × pending_hitl** : un stop utilisateur après
   `save_interrupt` laissait un pending orphelin → le message suivant était
   mal routé en reprise. `_finalize_abnormal` nettoie sur `cancelled` ;
   `killed` (drain) préserve volontairement (question encore répondable après
   redémarrage). Tests d'intégration Redis réels.
2. **Cache de détection** : le cache in-memory (TTL 5 s) n'était jamais
   invalidé → un clic plus rapide que le TTL était mal routé. Extrait vers
   `utils/hitl_cache.py`, invalidé au chokepoint `HITLStore.save/delete` ;
   nouveau setting `HITL_DETECTION_CACHE_TTL_SECONDS` (borne le seul résiduel
   cross-worker).
3. **Abort de clarification** : « annule » sur une clarification bouclait
   (fast-path plan-level ignoré par le nœud, phrase complète re-planifiée
   comme information). Branche dédiée `_classify_clarification` (fast-path
   mots exacts + classifier REJECT ≥ seuil sans edited_params) → resume
   `{"clarification", "cancelled": True}` ; branche abort du nœud (contrat
   plan-rejection existant) ; edge conditionnel clarification → response avec
   signal auto-nettoyant `clarification_cancelled` (l'état persiste entre
   tours via le checkpointer). Prouvé E2E runtime.

### Option B — décision structurée, classifier bypassé

- `ChatRequest.hitl_decision` (`{message_id, action}`, optionnel — ignoré par
  les canaux). Le contenu `message` du clic est le libellé localisé du bouton
  (bulle historique + repli langage-naturel gracieux).
- `build_structured_decision` (orchestration/approval_decision.py) mappe
  déterministiquement vers le resume par type — **parité octet pour octet**
  avec le chemin conversationnel (testée) — et **fail-closed** :
  `HitlDecisionStaleError` sur pending absent, `message_id` divergent
  (désormais persisté dans le pending) ou action non supportée → chunk
  `error` typé `hitl_decision_stale` (i18n ×6) + `done`, jamais un nouveau
  tour. Double garde : lecture Redis autoritaire au router quand un clic
  arrive (le cache ne route jamais un bouton), exception typée côté service.
- Ids d'action du fil transmis **verbatim** par le front ; alias canonisés
  côté serveur (`confirm_delete`, `confirm_all`, `approve` → confirm ;
  `reject` → cancel) — source de vérité unique.
- Économie : un appel LLM classifier par approbation supprimé
  (`classifier_bypassed: true` prouvé dans les logs).

### Réhydratation et frontend

- `GET /agents/hitl/pending` (lecture autoritaire, `Cache-Control: no-store`,
  corps `null` si rien) : le chunk d'interruption n'étant pas dans
  l'historique archivé, c'est la seule source de reconstruction de la carte
  après un reload. Appelé au mount du chat quand aucun run vivant n'est
  reattaché (le replay ADR-117 ré-arme la carte lui-même sinon).
- Frontend : branche `hitl` de la FSM du chat-reducer
  (`awaiting → submitting → resolved(confirmed|cancelled|via_text)` /
  `expired`, dernier-arrivé-gagne, erreur transport ré-arme, réponse tapée
  résout `via_text` — le canal conversationnel reste premier) ;
  normalisateur `lib/hitl-payload.ts` des formats de facto (fixtures = les
  payloads capturés, null défensif hors périmètre) ; composant
  `HitlActionCard` (4 types, tonalité par sévérité, boutons pilotés par le
  fil) ; i18n `chat.hitl.*` ×6.

### Périmètre

- **V1 (livré)** : confirm/cancel sur draft_critique, tool_confirmation
  (available_actions ajouté à l'émission), destructive_confirm,
  for_each_confirmation. Clarification et plan approval restent texte.
- **V2 (différé)** : édition structurée des drafts (`updated_content`) —
  l'action `edit` est **rejetée fail-closed** tant que le chemin nœud n'est
  pas vérifié pour elle. **V3** : chips clarification/disambiguation.

## Findings consignés (hors périmètre, à arbitrer)

- **Autonomie post-refus en ReAct** : après un refus de délégation, la boucle
  a poursuivi (haïku auto-rédigé, image générée, skill importé sans
  confirmation — `import_user_skill` non gaté). Un refus ne borne pas la
  suite du run.
- **Politique validateur** : `wrong_parameters` n'est pas « confirmation-
  only » — une adresse placeholder explicitement confirmée par l'utilisateur
  ne peut jamais être acceptée telle quelle.
- `ConversationalHitlResumption` (resumption_strategies.py) n'est pas le
  chemin emprunté par le chat (approval_decision.py l'est) — clarifier ou
  retirer.

## Preuves

- ~180 tests spécifiques backend (TDD rouge→vert systématique) + 10 420 verts
  au gate unit fast ; 1 344 verts frontend (167 fichiers) ; 13 E2E Playwright
  hermétiques (dont 4 nouveaux : réhydratation, cancel one-click, stale →
  expired, réponse tapée → via_text).
- Runtime dev : bypass + 2 gardes stale tracés dans les logs ; boucle de
  clarification fermée ; carte prouvée navigateur réel (hydratation sans
  message, reload, clic Annuler → badge) en mode ReAct ; draft capturé sur
  compte réel avec `google_api_requests=0`.
- Ratchets : CC frontend amélioré et verrouillé ; hotspot backend décomposé
  (`hitl_pending.py`, `attachments_injection.py` extraits de service/router,
  fichiers gelés revenus sous leurs caps).

## Conséquences

- Le moment le plus critique du produit (approuver une action à effet de
  bord) devient un geste à un tap, sans régression du canal texte/voix ni
  des canaux Telegram/WhatsApp (non-régression testée).
- Deux modules API nouveaux (`hitl_pending`, `attachments_injection`) ;
  `.env.example` ×2 enrichis d'un setting.
- Le fix onboarding (le CTA final persiste `onboarding_completed`) est livré
  dans le même lot (volet A ; pages actionnables = lot ultérieur).

## P1-V2 — Édition inline des drafts (2026-07-19)

Extension livrée : le bouton `edit` émis par `draft_critique` (jusqu'ici
filtré côté front, rejeté fail-closed côté serveur) devient un **formulaire
d'instructions inline** sur la carte draft.

- **Investigation préalable** : le chemin `updated_content` (édition par
  champs sans LLM) est **mort sur toute la chaîne** — `_process_draft_action`
  (hitl_dispatch_node) n'a aucun appelant, `resumption_strategies` est le
  chemin apparent mort documenté au Lot 1, le draft executor l'ignore. Le
  chemin VIVANT est `action="edit"` + `modification_instructions` (texte) →
  boucle `draft_modifier` LLM → draft re-présenté (itérations, retype
  DELETE→UPDATE). La V2 route ce chemin vivant, sans réanimer le mort.
- **Backend** : `HitlDecisionRequest.modification_instructions` (optionnel,
  ≤2000) ; `_structured_resume_payload` accepte `edit` UNIQUEMENT sur
  `draft_critique` avec instructions non vides → resume
  `{"action": "edit", "draft_id", "modification_instructions"}` — parité
  exacte avec la branche EDIT du classifier, bypassé. `updated_content` seul
  reste rejeté (fail-closed).
- **Frontend** : le normaliseur garde `edit` sur les cartes draft seulement
  (filtré ailleurs — le serveur l'y rejette) ; sur la carte, `Modifier`
  bascule vers un textarea (auto-focus, Échap = retour, submit désactivé à
  vide) ; les instructions partent comme message visible (parité NL) avec la
  décision structurée. Le mode édition est **dérivé par messageId** — une
  carte re-présentée (last-wins) quitte l'édition automatiquement, sans
  effect. i18n `chat.hitl.edit.*` + `chat.hitl.actions.edit` ×6.
- **Preuves** : backend 26 tests structurés (6 nouveaux : accepté avec
  instructions, rejeté sans/blanc/mauvais type/updated_content seul) ;
  front 15 tests carte (5 nouveaux : toggle, submit+instructions, Échap,
  reset par messageId, non-draft sans toggle) + normaliseur 10 (fixture
  réelle : `['confirm','edit','cancel']` conservés sur draft, filtrés sur
  tool) ; suites 1 377 front / 10 435 backend vertes ; ratchets tenus ;
  preuve navigateur réelle (draft email de test → Modifier → instructions →
  draft régénéré re-présenté avec le sujet modifié → Annuler, rien envoyé).

## Onboarding volet B — pages actionnables (2026-07-19)

Complément du fix volet A (persistance) livré au Lot 1 : l'onboarding passe
de descriptif à actionnable, en respectant la contrainte structurelle
découverte au Lot 1 — le dialog se re-monte à CHAQUE navigation tant que
`onboarding_completed` est faux, donc **tout CTA complète d'abord la
persistance, puis navigue** (échec de persistance = on reste dans le
tutoriel, pas de navigation).

- **Page 2 (Connecteurs)** : CTA « Connecter mes services » →
  `settings?section=connectors` (seul deep-link supporté par la page
  réglages ; le param est consommé par l'auto-expand puis nettoyé de l'URL —
  comportement nominal).
- **Page 7 (Exemples)** : chaque exemple devient un bouton →
  `chat?draft=<exemple>` ; nouveau prop `ChatInput.initialMessage`
  (initializer seul, jamais synchronisé ensuite) pré-remplit l'input **sans
  jamais envoyer** — l'utilisateur garde la main. Lecture du param via un
  helper module-level (`readDraftParam`) pour ne pas toucher la worst
  function de la page chat (ratchet CC au plafond) ; même extraction côté
  ChatInput (`initialDraft`).
- i18n `onboarding.page2.cta` + `onboarding.page7.examples_hint` ×6.
- Preuves : 7 tests (CTA complète-puis-navigue, échec = pas de navigation,
  exemple → href draft encodé, prefill sans envoi, prefill éditable) ;
  navigateur réel : tutoriel → CTA → atterrissage Réglages sans réouverture
  du dialog (flag restauré true par le flux) ; deep-link → textarea
  pré-remplie, zéro envoi. Suites 1 382 front vertes, ratchets tenus.

## Amendement cycle de vie — la carte résolue disparaît (2026-07-19)

Retour utilisateur : une fois l'action confirmée ou annulée, la carte restait
affichée indéfiniment avec son badge de résolution — bruit redondant, la
bulle de réponse (« OK, c'est annulé. ») étant déjà le feedback. Nouveau
contrat de fin de vie :

- `STREAM_DONE` **efface** une carte `submitting` (flux bouton) ou `resolved`
  (flux via_text). Les badges de résolution ne sont plus visibles que pendant
  le streaming du tour de reprise (transitoires, testés au niveau composant).
- Une carte `expired` **reste** affichée (son tour n'a produit aucun résultat,
  la note explique pourquoi) et s'efface au prochain envoi (`SEND_MESSAGE`).
- Le flux d'édition est préservé : la carte re-présentée (nouvel interrupt,
  `awaiting` last-wins) arrive avant le `done`, et la garde `awaiting`
  historique la protège.

Preuves : matrice reducer réécrite (18 tests, 3 nouveaux), 2 E2E hermétiques
alignés (disparition au done), preuve navigateur réelle (draft de test →
Annuler → carte disparue après la réponse).
