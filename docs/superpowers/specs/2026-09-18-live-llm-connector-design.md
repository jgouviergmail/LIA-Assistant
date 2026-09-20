# Le mode Live : une conversation parlée en duplex qui confie chaque demande au moteur du chat, sur la clé de la personne

**Date** : 2026-09-18 · **Version** : 2 (révisée après trois retours du propriétaire, §0) · **Statut** :
ANALYSE, en attente d'arbitrage — zéro code · **ADR cible** : ADR-299 (ADR-298 est réservé par la spec
« bac à sable boîte à outils » du même jour ; à confirmer) — amende ADR-070 (modes d'exécution),
ADR-117 (runs détachés), ADR-245 (raisonnement), ADR-263 (registres), ADR-280 (capacités), ADR-284
(prompts), ADR-288/289 (brouillons), ADR-290 (téléphone comme canal), ADR-246 (coques natives) ·
**Sources externes lues** : blog Gemini 3.8 Live (2026-09-15), `ai.google.dev` Live API (overview,
capabilities, tools, session-management, ephemeral-tokens, best-practices, référence WebSocket, fiches
`gemini-3.8-live` et `gemini-3.8-live-extended-thinking`, pricing), `developers.openai.com` GPT-Live
(fiche `gpt-live-1`, guides live / live-conversations / live-delegation, 2026-09-10).

> Livrable demandé : analyse technique et fonctionnelle systémique AVANT tout code métier. Chaque
> hypothèse a été confrontée au code de l'arbre au 2026-09-18 (`a9699a16` + arbre de travail) ; les
> faits fournisseurs sont cités avec leur page. Ce qui ne peut être prouvé sans session réelle est
> en §9 (mesures du lot 0).

---

## 0. Ce qui a changé entre la version 1 et la version 2 (retours du propriétaire, 2026-09-18)

1. **La dépense de LIA pendant la session est comptée ET affichée** à la personne en fin de mode
   live (jamais celle du fournisseur, qui tourne sur la clé de la personne).
2. **Le mode Live n'est pas bridé** : une fois activé, il se substitue au mode écrit et permet TOUT ce
   que le chat permet (outils, actions, brouillons, sous-agents, documents, images…). La règle
   « lecture seule » du téléphone ne s'applique pas : elle existe parce que l'agent vocal du
   fournisseur y est un étranger au moteur de LIA, borné par le délai d'un webhook.
3. **Le fil de discussion rapporte en direct** ce que la personne dit et ce que LIA fait — pas une
   synthèse en fin de session comme le relais téléphonique.

Ces trois décisions convergent vers UNE architecture qui les satisfait toutes par construction : la
session vocale **délègue chaque demande au moteur du chat** (§3, A3). Le modèle live parle ; LIA
pense et agit, dans son propre graphe, avec ses gardes, ses registres, ses cartes et sa facture.

---

## 1. Dépouillement du besoin

### 1.1 Le besoin brut

« Ajouter une nouvelle modalité d'interaction à LIA, basée sur l'existant : l'utilisation de LLM
"live" (Gemini 3.8 Live / 3.8 Live Extended Thinking, plus tard GPT-Live-1), portée par un nouveau
connecteur utilisateur "Live" non spécifique à Google ; les jetons et coûts ne sont ni suivis ni
supportés par l'application. »

### 1.2 L'intention métier réelle

Une **conversation parlée, continue, en duplex** (la personne et LIA parlent et s'interrompent en
temps réel) qui reste **LIA** : sa personnalité, ce qu'elle sait, ce qu'elle peut faire — tout ce que
le mode écrit fait, à la voix — et sa trace (registres, archive de conversation, facture). La voix
actuelle (ADR-070 + voice mode) est un **tour par tour** : mot d'éveil → STT → pipeline/ReAct → TTS.
Le mode Live remplace l'ENVELOPPE (écoute, parole, interruption, latence perçue) par un modèle
speech-to-speech natif qui parle pendant que LIA travaille (fiche `gemini-3.8-live` : appels de
fonction `NON_BLOCKING` par défaut) — mais ne remplace PAS le moteur : ce que LIA sait et fait vit
dans son graphe (mémoire, espaces, planificateur, ReAct, HITL, registres), et une session qui
contournerait ce graphe perdrait exactement ce qui fait LIA.

### 1.3 Les contraintes implicites (non-dits explicités)

| Non-dit | Ce qu'il implique, vérifié dans le code |
|---|---|
| « sur l'existant » | La session confie ses demandes au chat par sa PROPRE porte : `POST /chat/stream` (`ChatRequest` porte déjà `stt_provider`, `attachment_ids`, `hitl_decision`, `directive`), `useChat.sendMessage` (le badge vocal l'appelle déjà via `sendMessageFromPresent`), `POST /runs/active/cancel` (`stopGeneration`), les cartes HITL du fil, le compteur de la bulle (`message_token_summary`), `get_token_summaries_by_run_ids` (facture agrégée, déjà lue par `GET /telephony/calls`), `markdown_to_plain_text` (`agents/display/plain_text.py`, l'aplatissement d'une réponse pour une surface sans balisage), la personnalité (`PersonalityService.get_prompt_instruction_for_user`), la machine à états vocale (`stores/voiceModeStore.ts`), les yeux (`expression-engine.ts` lit `voiceState`), le worklet PCM 16 kHz (`lib/audio/pcm-worklet.ts`), le bandeau d'appel (`telephony/ActiveCallBanner.tsx`, une ligne d'état au-dessus du fil hors de l'emplacement exclusif de `lib/chat-surfaces`). |
| « connecteur utilisateur non spécifique à Google » | Une **catégorie fonctionnelle** `live` de `CONNECTOR_FUNCTIONAL_CATEGORIES` (un fournisseur actif à la fois — le mécanisme email/calendar/weather), un premier type `GEMINI_LIVE`, une abstraction `LiveProvider` (dorsal) + `LiveTransport` (navigateur). |
| « les tokens et coûts ne sont ni suivis ni supportés » | `cost_bearers.COST_FAMILIES["live"] = USER` (le garde exige la famille déclarée ET absente de la somme des plafonds) ; directive 2026-09-16 : on ne MONTRE pas non plus la facture d'un service à clé personnelle. Ce que LIA dépense ELLE-MÊME (chaque tour délégué) est une dépense d'instance sous les deux plafonds (ADR-272), déjà comptée par le chat sous le run id du tour ; la session l'agrège et l'affiche à sa fin (retour 1). |
| « se substitue au mode écrit » | Un tour délégué EST un tour du chat : mode d'exécution du bandeau (pipeline/ReAct), planificateur, validateur, brouillons un par un (ADR-288), cartes (ADR-289), sous-agents, documents, images, registres, extractions post-réponse (mémoire, intérêts, journal, psyché, boucles, récurrence) — rien à réimplémenter, rien à brider. |
| « le fil rapporte en direct » | Un tour délégué se dessine dans le fil PENDANT qu'il tourne (SSE, étapes, cartes, HITL, compteur) exactement comme un message tapé ; un échange purement vocal est ajouté au fil dès qu'il est fini. Le relais « synthèse en fin d'appel » du téléphone n'est pas utilisé. |
| Multi-utilisateurs (directive 2026-09-17) | Aucune hypothèse tirée de l'usage du propriétaire : le modèle est CHOISI par la personne parmi ce que sa clé découvre ; les exemples des prompts sont en anglais et génériques ; aucune liste d'outils n'est écrite (le chat décide). |

### 1.4 Faits avérés (fournisseurs)

**Gemini Live API** (`ai.google.dev`, lu le 2026-09-18) :

- Modèles : `gemini-3.8-live` (défaut, raisonnement entrelacé, `thinking_level` NON supporté,
  `NON_BLOCKING` par défaut, `behavior: BLOCKING` pour l'ancien mode) et
  `gemini-3.8-live-extended-thinking` (`thinkingLevel` ∈ {low, medium, high}, jamais `minimal` ;
  **seul `NON_BLOCKING` est accepté, `BLOCKING` renvoie une erreur dure**). Entrée 131 072 jetons,
  sortie 65 536. Sur les modèles audio natifs `responseModalities` n'accepte que `AUDIO` ; le texte
  s'obtient par `outputAudioTranscription`. « Proactive audio » toujours activé sur 3.8.
- Transport : WebSocket
  `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent`.
  Audio entrant PCM 16 bits LE **16 kHz** (`audio/pcm;rate=16000`), sortant **24 kHz**. Morceaux
  de 20 à 40 ms recommandés.
- Messages client → serveur : `setup`, `clientContent`, `realtimeInput` (audio/video/text,
  `activityStart`/`activityEnd`, `audioStreamEnd`), `toolResponse`. Serveur → client :
  `setupComplete`, `serverContent` (`modelTurn`, `generationComplete`, `turnComplete`,
  `interrupted`, `inputTranscription`, `interimInputTranscription`, `outputTranscription`),
  `toolCall`, `toolCallCancellation`, `goAway` (`timeLeft`), `sessionResumptionUpdate`
  (`newHandle`, `resumable`), `usageMetadata` sur chaque message.
- `setup` : `model`, `generationConfig` (`speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName`,
  `temperature`, `responseModalities`), `systemInstruction` (texte), `tools`, `realtimeInputConfig`
  (VAD automatique : sensibilités, `prefixPaddingMs`, `silenceDurationMs` 500-800 ms),
  `sessionResumption{handle}`, `contextWindowCompression{slidingWindow.targetTokens, triggerTokens}`,
  `inputAudioTranscription`/`outputAudioTranscription`, `proactivity`, `historyConfig`.
- Durées : connexion ≈ **10 min**, session audio seule **15 min**, audio+vidéo **2 min** sans
  compression ; **illimitée avec compression** ; jeton de reprise valable **2 h** ; ≈ 25 jetons
  audio/s et **chaque tour refacture tout le contexte accumulé**.
- Interruption : `interrupted: true` → vider le tampon de lecture ; **les appels de fonction en
  attente sont annulés** (`toolCallCancellation`). Réponse d'un outil `NON_BLOCKING` : `scheduling` ∈
  {`INTERRUPT`, `WHEN_IDLE`, `SILENT`}. Google Search intégré disponible ; ni code execution, ni URL
  context, ni Maps sur les modèles Live.
- **Jetons éphémères** (`auth_tokens.create`, `api_version='v1alpha'` ; utilisés avec la Live API en
  **`v1beta` seulement**, `access_token` en query ou `Authorization: Token …`) : `uses` (1),
  `expire_time` (30 min), `new_session_expire_time` (1 min pour OUVRIR), `live_connect_constraints
  {model, config{…}}` + `lock_additional_fields` ; la reconnexion toutes les 10 min par
  `sessionResumption` marche **avec le même jeton malgré `uses: 1`**. Conçus pour le client → serveur.
- Facturation (information, jamais dans l'application) : audio 3 $/M entrée, 12 $/M sortie, texte
  0,75 $/M ; surcoût de transcription ; contexte entier refacturé à chaque tour.

**GPT-Live-1** (`developers.openai.com`) : `POST /v1/live/sessions` (pas la Realtime API) ; WebRTC
(le serveur échange l'offre/réponse SDP, média pair-à-pair) ou WebSocket (PCM16 24 kHz) ; un WebSocket
« sideband » serveur ; facturé à la durée (0,05 $/min, à la seconde), « backend model and tool usage
billed separately ». **Le modèle vocal ne raisonne ni n'appelle d'outil : il DÉLÈGUE** —
`delegation.type = "responses"` (un modèle dorsal OpenAI) ou `"client"` (l'application reçoit
`session.delegation.created`, reconstitue le contexte depuis `session.input_transcript.delta` /
`session.output_transcript.delta`, répond par `session.commentary.append` / `session.thinking.append`
/ `session.instructions.append` avec le `delegation_id`). Contexte 128 k, « replacement voice engine »
à 90 %.

**Ce que cela impose** : la délégation à un moteur dorsal est LA forme que le second fournisseur
prescrit, et que Gemini permet par un appel de fonction `NON_BLOCKING`. L'abstraction porte donc la
**session** et la **délégation** (une demande → un tour du chat → un résultat rendu à la voix) ;
le fil (JSON WebSocket Gemini, WebRTC + data channel OpenAI) reste propre à chacun.

### 1.5 Faux positifs et faux négatifs traqués

Faux positifs (une brique paraît couvrir le besoin, mais a une limite cachée) :

1. **`AudioQueue` (`lib/audio-queue.ts`)** décode des morceaux ENCODÉS via `decodeAudioData` ; elle
   ne lit pas un flux PCM brut 24 kHz avec vidage instantané sur `interrupted`. À écrire : un lecteur
   PCM planifié, réutilisant sa mécanique de déverrouillage/keep-alive iOS.
2. **Le worklet PCM** est bon, mais `VOICE_INPUT_CHUNK_SIZE = 4096` échantillons = 256 ms ; la Live
   API veut 20-40 ms. `buildPcmWorkletSource(chunkSize)` est déjà paramétré → `LIVE_INPUT_CHUNK_SAMPLES`.
3. **La mécanique « outils en direct » du téléphone** (`agents/telephony/live_tools.py`,
   runtime synthétique, projection vocale, budget, call-back) : conçue pour un agent vendeur borné à
   la lecture et à un webhook de 20 s. Elle ne sert PAS ici (retour 2) : le mode Live délègue au
   moteur, qui offre tout et se protège seul. Le téléphone n'est pas touché.
4. **`self_call_context.py`** (contexte riche du mandat téléphone) : utile là où l'agent ne peut rien
   demander ; ici la voix DEMANDE à LIA. Le mandat live porte l'identité, la personnalité, la langue
   et l'horloge — et la règle de déléguer tout le reste (arbitrage R3 sur un bloc de contexte).
5. **`get_proactive_messages_after`** n'injecte au tour suivant que des lignes `assistant` de type
   `proactive_*` (ADR-282, `PROACTIVE_MESSAGE_TYPE_PREFIX`). Les échanges purement vocaux ont DEUX
   rôles : la porte est élargie, pas dupliquée. Les tours délégués, eux, sont DÉJÀ dans le
   checkpoint du fil (ils ont tourné dans le graphe) : rien à injecter.
6. **ADR-245** : `kwargs_for` rend des kwargs LangChain ; la Live API veut `thinkingConfig.thinkingLevel`
   dans `setup`. Vocabulaire et profil réutilisés, un renderer de plus.
7. **`PlatformCapability.TELEPHONY` / `VoiceSettings`** ne couvrent pas une session live ; le garde
   de partition (`test_capability_coverage.py::EXPECTED_CAPABILITIES`) refuse une fonctionnalité
   sans interrupteur → capacité `LIVE`.
8. **Google Search intégré à la Live API** : un raccourci qui contournerait la capacité `WEB_SEARCH`,
   les connecteurs de recherche et le registre de consultation. Non activé : la recherche web est une
   demande déléguée comme une autre.

Faux négatifs (réinventer ce qui existe) :

1. La **porte du chat** pour exécuter, dessiner, confirmer, facturer et archiver un tour — c'est le
   cœur de la v2.
2. La **facture agrégée** : `get_token_summaries_by_run_ids` (motif `GET /telephony/calls`).
3. L'**activation par clé API** : `POST /connectors/api-key/activate` + vérificateur fonctionnel
   gratuit (`models.list` filtré sur `bidiGenerateContent` → `functionally_verified=True`).
4. Le **registre des décisions** hors graphe pour la SESSION elle-même (`out_of_turn_decision`,
   motif `infrastructure/proactive/tracking.py`) — les tours délégués ont chacun leur ligne par
   construction.
5. Les **familles Redis**, le **limiteur**, le **claim à jeton propriétaire** (`shared_flight`).
6. La **carte des capacités** (bijection `CAPABILITY_SECTION`), les **sections de réglages**, le
   **formulaire** téléphonie (clé → valider → choisir → activer), le **bandeau** d'appel.
7. Le **guide mobile** : micro déjà déclaré des deux côtés ; `CapacitorHttp` désactivé ne concerne pas
   `WebSocket`.

---

## 2. Périmètre cible et valeur

**Cible** : depuis le chat, la personne dont le connecteur « Live » est actif ouvre une session parlée
en duplex. Le modèle live est la VOIX de LIA (personnalité, langue, ton) ; **chaque demande qui
concerne les données, les actions ou les capacités de LIA est confiée au moteur du chat** par une
fonction unique, et le tour se déroule dans le fil comme un message tapé : planification ou boucle
ReAct selon le mode choisi dans le bandeau, outils, cartes, documents, images, brouillons à confirmer
(par un clic sur la carte OU par la voix), compteur de la bulle. La voix annonce l'attente, restitue
la réponse, relaie les questions de LIA. Les échanges purement vocaux sont ajoutés au fil dès qu'ils
sont finis. À la fin, une carte de session : durée, nombre de tours, **ce que LIA a dépensé** dans le
vocabulaire du compteur du chat. L'audio ne transite jamais par LIA ; les jetons du modèle live ne
sont ni comptés ni affichés.

**Hors programme** (chacun avec sa raison) : vidéo/caméra (2 min sans compression, budget à part) ;
GPT-Live-1 (l'abstraction est posée ; transport WebRTC + délégation = un lot daté plus tard) ; mot
d'éveil (le Live s'ouvre par un geste) ; clé d'instance (le connecteur est PERSONNEL par décision,
sinon la ligne de `cost_bearers` ment) ; migration du téléphone vers la délégation (possible un jour,
borné par le délai webhook du fournisseur — hors sujet).

**Valeur** : la latence perçue d'un tour tombe à celle d'un modèle duplex qui parle pendant que LIA
travaille ; l'interruption naturelle ; et rien de LIA n'est perdu — ni sa mémoire, ni ses gardes, ni
sa trace.

---

## 3. Arbitrages majeurs retenus

### A1 — Topologie : client → fournisseur, LIA ne porte pas l'audio

Le navigateur ouvre le WebSocket chez le fournisseur avec un **jeton éphémère que LIA frappe** sur la
clé du connecteur (jamais transmise au navigateur). Rejeté : un proxy média. Production = Raspberry
Pi 5, 4 workers uvicorn (ADR-283, ADR-271), tunnel Cloudflare : 48-96 ko/s par session, deux sockets
par session et un saut de plus par morceau audio seraient portés par la mauvaise machine ; Google
conçoit les jetons éphémères exactement pour ce cas. GPT-Live (SDP par le serveur, média pair-à-pair)
a la même forme.

### A2 — Une abstraction de SESSION et de DÉLÉGATION, pas de fil

Dorsal `domains/live/providers/` : `LiveProvider` (`verify_key`, `list_models`, `mint_credential
(mandate, delegation_tool, constraints)`, `capabilities(model)`) ; `GeminiLiveProvider` (SDK
`google-genai` 2.10.0 déjà verrouillé). Navigateur `lib/live/` : `LiveTransport` (`connect`,
`sendAudio`, `sendToolResponse`, `close` ; événements `audio`, `transcript`, `toolCall`,
`toolCallCancellation`, `interrupted`, `goAway`, `resumption`) et `transports/gemini-ws.ts` en
**WebSocket brut JSON** (protocole documenté et court ; `@google/genai` absent de `package.json`,
lourd dans le bundle chat, inutile pour OpenAI — à confirmer au lot 0 si le SDK apportait une reprise
qu'on ne veut pas réécrire). La délégation est le contrat commun : `DelegationRequest(request)` →
un tour du chat → `DelegationResult(text, pending_question)`.

### A3 — La délégation : la voix parle, LIA pense et agit dans son graphe

Le modèle live reçoit UNE fonction, `send_to_lia(request: string)`, `behavior: NON_BLOCKING`
(obligatoire sur Extended Thinking, défaut sur 3.8 Live), décrite ainsi (technique, en anglais,
ADR-256) : « Hand the person's request to LIA, in their own words, whenever it concerns their data,
their tools, an action, a document, or anything you cannot answer from the conversation alone. LIA
answers in the chat; you receive the answer as the result. One request at a time. Never claim LIA did
something before the result says so. When the result is a question from LIA, ask the person and send
their answer through the same function. »

Le navigateur (le bandeau) reçoit `toolCall(send_to_lia)` et **envoie la demande par la porte du chat
elle-même** (`useChat.sendMessage`, `POST /chat/stream`, cookie de session) avec une estampille
`live_session_id` (nouveau champ optionnel de `ChatRequest`, archivé par `archive_user_message_first`
dans les métadonnées de la ligne `user`). Le tour se dessine dans le fil comme un message tapé. Quand
le flux se termine (`done`) ou s'arrête sur une question (`hitl_interrupt_complete` — le seul chunk
émis, mesuré 2026-09-09), le bandeau renvoie `toolResponse` : la réponse aplatie par
`markdown_to_plain_text`, bornée par `LIVE_DELEGATION_RESULT_MAX_TOKENS` avec la coupe énoncée (le
fil garde la réponse entière), et `scheduling = LIVE_DELEGATION_SCHEDULING` (défaut `INTERRUPT` :
LIA a la réponse, la voix la donne).

Ce que cette forme donne **par construction** : le mode d'exécution du bandeau (pipeline/ReAct), le
catalogue entier lié par pertinence (ADR-293), le validateur, la gate d'effets et `mutation_policy`,
les brouillons un par un (ADR-288) et leurs cartes (ADR-289), les sous-agents, la génération de
documents et d'images (attachés à la bulle), les trois registres (une décision par tour, les
consultations des outils, les effets réclamés et réglés), les six extractions post-réponse, la
facture du tour sur sa bulle, l'archive des deux lignes. **Rien n'est réimplémenté hors graphe.**

**Deux intelligences, une couture — rien du modèle live n'est contourné.** Le modèle live possède la
CONVERSATION : il comprend, choisit le ton, gère les tours de parole et l'interruption (natifs),
parle pendant l'attente (« I'm checking your calendar » — c'est exactement ce que `NON_BLOCKING`
autorise, et ce que la fiche 3.8 Live nomme « background tool execution without interrupting the
conversation »), décide QUAND déléguer et comment restituer dans ses mots, pose ses propres
questions de clarification, tient la petite conversation sans rien demander à personne ; sur
Extended Thinking il raisonne en arrière-plan sur l'échange lui-même. Le moteur de LIA possède les
DONNÉES et les ACTIONS : ce que la personne a, ce que LIA sait d'elle, ce qui doit être fait — sous
ses gardes. La délégation est le seul point où l'un parle à l'autre. Faire répondre le moteur à
chaque énoncé (un « bonjour » compris) mettrait la latence d'un tour du chat sur chaque phrase et
tuerait le duplex, qui est l'intérêt du mode ; faire appeler les outils un à un par le modèle live
hors du graphe rejouerait hors graphe tout ce que le chat garantit (validation, brouillons,
registres, facture, extractions) — la seconde autorité d'exécution qu'ADR-263 refuse.

**Et pourtant tout est traité comme une discussion écrite.** Vu du fil, une session live est une
suite de tours ordinaires : ceux qui ont eu besoin de LIA sont des tours du chat au sens strict ;
ceux que la voix a tenus seule sont archivés comme des messages `user`/`assistant` visibles, entrent
dans le contexte du tour suivant, et passent par les mêmes extractions (R4). La réactivité perçue
tient à deux choses : la voix accuse réception à l'instant et parle pendant le travail, et le tour
délégué tourne dans le mode choisi par la personne (le pipeline pour une lecture, quelques appels de
modèle plus l'outil ; ReAct pour l'exploration). **Le lot 0 mesure la latence p50/p95 d'un tour
délégué** (lecture d'agenda, envoi d'un mail avec confirmation, question exploratoire) en pipeline et
en ReAct, avec la voix qui comble ; si la synthèse écrite domine le temps, une variante « résultats
projetés, restitution par la voix » sera étudiée comme optimisation SÉPARÉE (ADR-274 : le rendu
appartient au moteur, le sens au modèle), jamais comme un contournement du graphe.

Règles de la délégation :

- **Une à la fois.** Le chat n'exécute qu'un run actif par conversation (`chat:active_run`) ; le
  bandeau sérialise. Un second `send_to_lia` pendant un run reçoit immédiatement la ligne « LIA is
  still working on the previous request » (fichier de lignes), jamais un second run.
- **Une question de LIA est un résultat.** Le `toolResponse` porte la question (la carte HITL est
  dans le fil en même temps) ; la personne répond par la voix → `send_to_lia("yes")` → la même porte
  (un message pendant une question pendante la reprend) ; ou clique la carte → `hitl_decision`
  structurée. Deux gestes, une porte, un seul tour.
- **Une interruption du fournisseur ne tue jamais un run de LIA.** `toolCallCancellation` (la
  personne a coupé la voix pendant l'attente) → le bandeau abandonne la RÉPONSE d'outil (l'id est
  annulé) mais laisse le tour finir : sa réponse reste dans le fil, où la personne la lit. À mesurer
  au lot 0 : un résultat tardif peut-il être poussé dans la session comme un `clientContent` texte
  (« LIA's answer is ready: … ») sans dérouter le modèle — si oui, la voix le dit quand même. Seul
  le bouton Stop du bandeau (ou du fil) appelle `POST /runs/active/cancel`.
- **Un délai borné.** Après `LIVE_DELEGATION_TIMEOUT_SECONDS` sans fin de flux (un ReAct long), le
  bandeau renvoie « LIA is still working; the answer will appear in the chat » et le run détaché
  (ADR-117) continue ; sa réponse arrive dans le fil.
- **Une seule voix sur les faits de la personne.** Le mandat interdit au modèle live de répondre de
  lui-même sur les données, les actions et les capacités de LIA ; le taux de délégation est mesuré au
  lot 0 (§9).
- **Google Search de la Live API : non activé** (§1.5, point 8).

### A4 — Le mandat est rendu côté serveur et VERROUILLÉ dans le jeton

`prompts/v1/live_system_prompt.txt` + `live_lines.txt` (scaffolds `key|template`, ADR-284 : chaque
`{placeholder}` a un producteur, exemples en anglais), rendu par `domains/live/mandate.py` avec :
la langue nommée par `get_language_name` (normalise `zh`), le prénom, la personnalité (même porte
que le chat et le téléphone), l'horloge de la personne (`format_datetime_for_display`), la règle de
délégation, le comportement d'attente (annoncer brièvement, ne pas inventer, relayer une question).
Placé dans `live_connect_constraints.config.system_instruction` avec `tools` (la seule fonction) et
`model`, plus `lock_additional_fields`. **À mesurer au lot 0** : la doc montre `model`,
`sessionResumption`, `temperature`, `responseModalities` verrouillés et dit « you can also lock a
subset of fields » ; que `systemInstruction` et `tools` le soient est probable (`LiveConnectConstraints
.config` est un `LiveConnectConfig` entier) mais non prouvé. Repli : le serveur rend le mandat, le
navigateur le passe dans `setup` ; le seul « attaquant » serait la personne, sur sa propre clé et
son propre compte — et une demande falsifiée resterait un tour du chat sous toutes ses gardes.
Acceptable et écrit.

### A5 — Dépense, plafonds, concurrence, affichage en fin de session

- `COST_FAMILIES["live"] = CostFamily(USER, credential="ConnectorType.GEMINI_LIVE")`,
  `QUOTA_COLUMN_OF["live"] = None`. `usageMetadata` du fournisseur : **ignoré** (ni stocké, ni
  affiché, ni métrique en jetons).
- Ce que LIA dépense = les tours délégués, comptés par le chat sous le run id de chaque tour, sous les
  deux plafonds (ADR-272), affichés sur chaque bulle comme d'habitude. Un tour refusé par un plafond
  l'est par la porte du chat (message d'usage traduit) ; la voix le relaie comme un résultat.
- **En fin de session** (retour 1) : `POST /live/sessions/{id}/end` archive une ligne `assistant`
  de type `live_session_summary`, visible, dessinée dans le fil comme une petite carte : durée, tours
  délégués, échanges vocaux, et la facture de LIA agrégée par `get_token_summaries_by_run_ids` sur
  les run ids estampillés `live_session_id` (🟠 IN · 🟢 OUT · 🔵 CACHE · euros, le vocabulaire du
  compteur). Jamais une ligne « fournisseur ».
- **Concurrence** : une session live par compte (claim Redis `live:session:{user_id}` à jeton
  propriétaire, compare-and-delete, TTL = durée max) ; `LIVE_MAX_CONCURRENT_SESSIONS` par instance
  (borne la charge de tours délégués) ; frappe de jetons limitée (`RedisRateLimiter`,
  `live_mint:{user_id}`) ; les limites du fournisseur (sessions simultanées par projet) sont
  RAPPORTÉES (erreur nommée en six langues), pas modélisées.

### A6 — Cycle de vie de la session

Redis `live:session:{user_id}` → `{session_id, provider, model, started_at, delegations, outcome}`
(famille `USER_RUNTIME`), machine `minted → connected → ended | expired | failed | hidden`. Jeton :
`uses=1`, `new_session_expire_time = LIVE_CONNECT_WINDOW_SECONDS` (60), `expire_time =
LIVE_SESSION_MAX_MINUTES` (30). Client : compression de contexte (`LIVE_CONTEXT_TRIGGER_TOKENS`,
`LIVE_CONTEXT_TARGET_TOKENS`, lus via `GET /live/config`), reprise transparente toutes les ≈ 10 min
avec le dernier `newHandle` et le MÊME jeton, `goAway.timeLeft` honoré, `interrupted` → vidage du
lecteur, `LIVE_IDLE_TIMEOUT_SECONDS` de silence → fin, onglet caché > `LIVE_HIDDEN_GRACE_SECONDS` →
fin (iOS suspend l'`AudioContext`). Chaque fin est un `LiveOutcome` nommé et compté ; `end` clôt le
claim, écrit la décision de session, archive la carte de fin.

### A7 — Ce que le fil montre, et quand (retour 3)

- **Tour délégué** : les deux bulles du chat, EN DIRECT (SSE), avec tout ce qu'un tour dessine. La
  bulle `user` porte la demande dans les mots de la personne (l'argument `request`) et, en
  métadonnées, `live_session_id` et `spoken_text` (la transcription brute de l'énoncé) ; un glyphe
  « live » discret sur les deux bulles.
- **Échange purement vocal** (salutation, petite conversation, la restitution parlée d'une réponse) :
  à chaque `turnComplete`, le bandeau poste le tour (`POST /live/sessions/{id}/turns` : énoncé de la
  personne s'il n'a pas été délégué, réponse parlée de LIA, horodatages) ; le serveur archive des
  lignes `user`/`assistant` de type `live_turn` par `archive_message` avec `build_live_turn_metadata`
  (nouveau constructeur de `agents/api/archive_metadata.py`, garde AST), **visibles** (la personne a
  dit ces mots — l'argument du relais téléphone) ; le bandeau les ajoute au fil par `appendMessage`
  (le réducteur déduplique).
- **Règle d'unicité** : un énoncé qui déclenche une délégation est archivé UNE fois, comme bulle
  `user` du tour (la transcription brute reste dans ses métadonnées), jamais aussi en `live_turn`.
  La restitution parlée de LIA APRÈS un tour délégué est archivée en `live_turn assistant` : ce que la
  personne a entendu peut différer de ce qui est écrit, et la trace doit le montrer (arbitrage R2).
- **Continuité** : les tours délégués sont dans le checkpoint du fil (ils y ont tourné) ; les
  `live_turn` y entrent au tour suivant par la porte d'injection élargie à UN prédicat
  `OUT_OF_GRAPH_MESSAGE_TYPES` (`proactive_*` assistant-only + `live_turn` deux rôles, dans l'ordre).
- **Apprentissage** : les tours délégués lancent les six extractions par construction. Les échanges
  purement vocaux ne passent par aucun graphe : une passe d'extraction de fin de session sur leur
  transcription (sous les drapeaux de la personne, source `user`, dépense sous le run id de la
  session) est l'arbitrage R4 — recommandé en lot 6b.

### A8 — Registres

- Par tour délégué : décision, consultations, effets — par le chat, rien à faire.
- Par session : une ligne `agent_decisions` (`out_of_turn_decision(source="user")`,
  `route="live_session"`, `execution_mode="direct"`, `outcome` answered/interrupted selon la fin),
  pointant sur la carte de fin ; `CONSULTATION_RECORDERS["live_session"]` déclaré `NOT_A_READER`
  avec la raison (« la session n'ouvre aucune source ; chaque lecture est un tour du chat qui
  enregistre la sienne ») — le garde exige une réponse écrite.
- `direct_client_callers` : `domains/live/` n'importe aucun client de `connectors/clients` ; vérifié
  par le garde tout seul.

### A9 — Capacité, démonstrateur, carte

`PlatformCapability.LIVE` (`env_flag="live_enabled"`, `SystemSettingKey.CAPABILITY_LIVE_ENABLED`,
`family="media"`, `route_enforced=True` sur `/live`), ajoutée à `EXPECTED_CAPABILITIES`, aux quatre
`.env` du démonstrateur en **OFF** avec la raison (clé personnelle exigée ; connecteurs fermés sur la
démo) — donc ni Caddy ni `EXPECTED_EXPOSED_ROUTES`. Carte : nœud `live` interrupteur (pas de compte),
`CAPABILITY_SECTION.live = 'live-mode'` (nouvelle section Préférences › Voix & médias — la bijection
interdit `connectors`), anneau extérieur à côté de `telephony`.

### A10 — Le connecteur

`ConnectorType.GEMINI_LIVE = "gemini_live"` ; `CONNECTOR_FUNCTIONAL_CATEGORIES["live"]` (prêt pour
`OPENAI_LIVE`) ; `CATEGORY_DISPLAY_NAMES`, `CONNECTOR_DISPLAY_NAMES` ; clé personnelle (ni keyless,
ni clé globale ; parité `requiresKey` intacte) ; vérificateur fonctionnel gratuit (`models.list`) ;
`connector_metadata = {model, voice, thinking_level}` (jamais un secret ; réassigné, jamais muté).
Le modèle vient de la DÉCOUVERTE (`GET /live/models` : ceux de la clé qui supportent
`bidiGenerateContent`), présélection `GEMINI_LIVE_DEFAULT_MODEL` dans `core/constants.py` (un
défaut de constante ; jamais « le modèle utilisé » dans un écran ou une doc). Le niveau de réflexion
n'est offert QUE pour un modèle dont le profil le déclare (ADR-245 : famille
`gemini_live_extended_thinking` dans `core/reasoning_profiles.py`, échelle `low < medium < high`,
`can_disable=False`, `minimal` refusé), rendu par un renderer live (`thinkingConfig.thinkingLevel`),
vocabulaire `ReasoningIntent.level`.

### A10 bis — Ce que la personne règle, ce que LIA règle, ce que l'opérateur borne

Doctrine : le téléphone laisse « ce que l'agent a dans la voix » au portail ElevenLabs parce qu'un
portail existe et qu'un PATCH y est fusionné. Ici il n'y a pas de portail : le `setup` est envoyé
à chaque session, donc **le connecteur EST le portail de la personne**, sur sa clé. Trois
propriétaires, jamais deux autorités sur un même bouton.

| Réglage | Propriétaire / stockage | Champ fournisseur (Gemini) | Défaut |
|---|---|---|---|
| Fournisseur | connecteur (catégorie `live`, un actif) | — | — |
| Clé API | connecteur (`credentials_encrypted`) | jeton éphémère frappé côté serveur | — |
| Modèle | connecteur (`connector_metadata.model`), DÉCOUVERT par la clé (`bidiGenerateContent`) | `setup.model` | `GEMINI_LIVE_DEFAULT_MODEL` |
| Voix | connecteur (`connector_metadata.voice`), par `LiveProvider.list_voices()` — DÉCOUVERTE quand le fournisseur a un point de listage, sinon la liste PUBLIÉE par le fournisseur, embarquée et datée avec sa source, et la provenance AFFICHÉE dans le formulaire (Gemini : 30 voix, aucune API de listage vérifiée le 2026-09-18 ; un nom hors liste reste saisissable) ; le FOURNISSEUR est l'autorité : l'activation ouvre une session avec le modèle et la voix choisis (setup minimal, aucun audio, fermée sur `setupComplete`) et un refus du fournisseur est rapporté avec ses mots | `speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName` | première de la liste |
| Niveau de réflexion | connecteur (`connector_metadata.thinking_level`), offert SEULEMENT si le profil du modèle le déclare (ADR-245) | `thinkingConfig.thinkingLevel` ∈ low/medium/high | `low` |
| « LIA s'arrête quand je parle » | compte (`users.live_preferences.interruptions`) | `realtimeInputConfig.activityHandling` = `START_OF_ACTIVITY_INTERRUPTS` / `NO_INTERRUPTION` | oui |
| Prise de parole : automatique ou appuyer pour parler | compte (`…​.talk_mode`) + bascule par session dans le bandeau (bruit ambiant) | `automaticActivityDetection.disabled` + `activityStart`/`activityEnd` | automatique |
| Réactivité de fin de phrase (calme / normale / vive) | compte (`…​.end_of_speech`) | `endOfSpeechSensitivity` (LOW/défaut/HIGH) + `silenceDurationMs` (800 / 650 / 500 — la plage recommandée) | normale |
| Quand LIA obtient une réponse : l'annoncer tout de suite / attendre une pause | compte (`…​.result_delivery`) | `scheduling` de la réponse d'outil = `INTERRUPT` / `WHEN_IDLE` | tout de suite |
| Sous-titres affichés | APPAREIL (`localStorage`, comme la position du dock ADR-277) | — | affichés |
| Micro / haut-parleur | navigateur, par session dans le bandeau | — | par défaut du système |

`users.live_preferences` : UNE colonne JSONB nullable (migration d'une colonne, module de colonnes
extrait comme `phone_identity_columns.py`), validée par un modèle Pydantic à vocabulaires FERMÉS,
réassignée par un nouveau dict, lue par un lecteur tolérant (une valeur inconnue = le défaut, jamais
une erreur — le motif `settings_shortcuts`). Elle appartient au COMPTE et non au connecteur parce
qu'un changement de fournisseur ne doit pas rendre à la personne des réflexes qu'elle a réglés.

Délibérément PAS à la main de la personne, avec la raison : l'instruction système et la fonction
de délégation (c'est LIA) ; la personnalité (déjà un réglage de LIA, réutilisé) ; la température,
la compression de contexte, la reprise (technique, LIA) ; la transcription (c'est la trace, jamais
optionnelle) ; les plafonds de durée, d'inactivité et de sessions (l'opérateur, `.env`) ; Google
Search intégré (jamais) ; « proactive audio » (imposé par 3.8) et le dialogue affectif (retiré par
3.8) ; la langue (auto-détectée par les modèles audio natifs, « explicit language codes cannot be
set » ; le mandat nomme celle du profil) ; le mode d'exécution des tours délégués (le bandeau
Pipeline/ReAct existant) ; `turnCoverage` (technique). Un aperçu sonore d'une voix dépenserait la
clé de la personne pour une synthèse : arbitrage R9, non au lot 1.

### A11 — Surface web : un bandeau au-dessus du fil, jamais une feuille qui le cache (retour 3)

Un bouton « Live » à côté du `VoiceModeBadge` (centre de la barre du chat — rendu seulement quand la
capacité est ON et le connecteur ACTIF). Il ouvre un **bandeau** au-dessus du fil (le motif
`ActiveCallBanner` : une ligne d'état, hors de l'emplacement exclusif de `chat-surfaces`, qui ne
dispute rien à une carte HITL) : les yeux (le bandeau publie un `liveStore` dont `useEyesBehavior`
dérive `voiceState` — `recording` quand la personne parle, `speaking` quand LIA parle ; pendant un
tour délégué le `chatStatus` fait déjà « thinking/searching ») ; les sous-titres du dernier échange
(lignes qui grandissent pendant la parole croisée ; dépliables) ; micro coupé/rétabli ; état
(connexion, reprise, temps restant) ; Stop (annule le run en cours ET termine la session, avec
confirmation) ; Terminer. Le fil reste visible et reçoit les tours en direct ; le composeur est
désactivé pendant la session, sauf Stop (une seule voie d'entrée — arbitrage R5). Sous `lg` : bandeau
compact, sous-titres repliés, cibles ≥ 44 px. **Un seul propriétaire du micro** : ouvrir Live met le
mot d'éveil en pause et est refusé pendant une capture de réunion (`useMeetingIsCapturing`, ADR-258).
Accessibilité : `role="region"` nommé, `aria-live="polite"` sur les sous-titres, `aria-pressed` sur
le micro, tout au clavier, `motion-safe` sur la pulsation, états disabled traduits. Formulaire de
connecteur (`LiveConnectorForm`, forme de `TelephonyConnectorForm`) : clé → Valider → modèles + voix
→ Activer ; notice « facturé sur votre compte fournisseur ».

### A12 — CSP et coques natives

`buildConnectSrc` reçoit `LIVE_PROVIDER_CONNECT_SRC = ['wss://generativelanguage.googleapis.com']`
(motif `FIREBASE_MESSAGING_CONNECT_SRC`) ; OpenAI ajoutera `https://api.openai.com` (SDP). `task
mobile:probe:{android,ios}` (qui IMPORTE `csp.ts`) est relancé avec une sonde « WebSocket sortant vers
un hôte tiers + micro » sous la CSP/COEP de production. Un WebSocket n'a pas de CORS ; `CapacitorHttp`
désactivé ne touche pas `WebSocket` ; la règle « natif, pas `fetch` » vise le CORS d'un `fetch`, et il
n'y en a aucun ici (le jeton vient de LIA). À mesurer : micro + WebSocket simultanés dans WKWebView,
suspension à l'écran verrouillé (fin nommée, jamais une session zombie).

### A13 — Sécurité

Le jeton : usage unique, 60 s pour ouvrir, expiration = durée max, contraint au modèle/mandat/outil ;
la clé ne quitte jamais `credentials_encrypted`. La délégation passe par la porte du chat avec le
cookie de la personne : **aucune nouvelle route d'exécution**, donc aucune surface d'attaque nouvelle
sur les outils ; les gardes du chat (plafonds, HITL, gate d'effets, contenu externe enveloppé) sont
celles du mode écrit. Le risque propre à la voix — une réponse lue contenant « ignore your
instructions » — est borné parce que le modèle live n'exécute rien : il ne peut que déléguer, et une
délégation est un tour sous toutes ses gardes. Aucun secret ni contenu au niveau INFO.

### A14 — Ce que le mode Live n'introduit PAS

Pas de table SQL ; pas de route d'exécution d'outil ; pas de runtime synthétique ; pas de liste
d'outils ; pas de slot `llm_config_overrides` ; pas de métrique en jetons ; pas de clé plateforme ;
pas de synthèse de fin de session (le fil EST la trace).

---

## 4. Cartographie des impacts

### 4.1 Dorsal (`apps/api`)

| Zone | Fichiers | Nature |
|---|---|---|
| Connecteurs | `connectors/models.py` (type, catégorie, affichage), `api_key_verifiers.py` (`_verify_gemini_live`), `schemas.py` | ajout ; `models.py` probablement gelé (ratchet) → extraire les tables de catégories si le cap est atteint |
| Quotas | `usage_limits/cost_bearers.py` | entrée `live` USER |
| Capacités | `feature_switches/registry.py`, `system_settings/models.py`, `tests/…/test_capability_coverage.py` (`EXPECTED_CAPABILITIES`), `capabilities/service.py` (nœud interrupteur) | ajout |
| Config | `core/config/live.py` (+ MRO), `core/constants.py`, `.env.example`, `.env.prod.example`, `.env`, `.env.prod`, 4 × `.env.demo-instance*` (section `[97] LIVE MODE` AVANT `[99]`, même numéro dans les quatre) | ajout |
| Domaine | `domains/live/{router, service, schemas, errors, session_store, mandate, summary, providers/{protocol, gemini}}` | nouveau ; raisers dans le domaine (`core/exceptions.py` gelé) |
| Chat | `agents/api/schemas.py::ChatRequest` (+ `live_session_id`, `spoken_text` optionnels), `agents/api/archive_first.py` (estampille dans le constructeur), `agents/api/archive_metadata.py` (`build_live_turn_metadata`, `build_live_session_summary_metadata`), `conversations/repository.py` (prédicat élargi), `orchestration/service.py::_inject_proactive_messages` (deux rôles) | modification de portes existantes, à tester en régression |
| Prompts | `prompts/v1/live_system_prompt.txt`, `live_lines.txt`, `PromptName` | ajout ; garde des placeholders |
| Registres | `agents/effects/user_data_readers.py` (`NOT_A_READER["live_session"]` avec raison), décision de session dans `live/service.py`, `infrastructure/cache/key_families.py` | ajout |
| Raisonnement | `core/reasoning_profiles.py`, `llm/reasoning/translate.py` (renderer live) | une famille = une règle + un renderer |
| Routes | `api/v1/routes.py` (`if settings.live_enabled`) | ajout |
| i18n | `core/i18n_live.py` (fins de session, lignes de délégation, erreurs, carte de fin — six langues) | nouveau module de données |
| Observabilité | `observability/metrics_live.py` (`live_sessions_total{provider,outcome}`, `live_session_duration_seconds`, `live_delegations_total{outcome}`, `live_delegation_duration_seconds`, `live_mint_total{outcome}`), tableau de bord (11 voix ou `30-live.json`), alerte sur `failed` | ratchet de couverture |

### 4.2 Web (`apps/web`)

| Zone | Fichiers |
|---|---|
| Connecteur | `constants/connectors.ts`, `components/settings/connectors/constants.ts` (`LIVE_CONNECTOR_TYPES`), `UserConnectorsSection.tsx` (groupe « Live » — vérifier le ratchet), `connectors/LiveConnectorForm.tsx`, `hooks/useLiveConnector.ts` |
| Session | `lib/live/{transport.ts, transports/gemini-ws.ts, pcm-player.ts, session-machine.ts, delegation.ts}`, `stores/liveStore.ts`, `hooks/useLiveSession.ts` (orchestre transport ↔ `useChat.sendMessage` / `stopGeneration` / état `hitl`) |
| UI | `components/live/{LiveButton, LiveBanner, LiveCaptions, LiveSessionSummaryCard}.tsx`, `app/[lng]/dashboard/chat/page.tsx` (bouton + bandeau — fichier gelé : extraire le groupe central si le cap est atteint), `components/chat/ChatMessage.tsx` (glyphe live, carte de fin), `components/eyes/useEyesBehavior.ts` (`voiceState` dérivé du live) |
| Réglages | `lib/settings-sections.ts` (`live-mode`), `components/settings/LiveModeSettings.tsx`, `lib/capability-sections.ts`, `components/capabilities/constellation-layout.ts` |
| CSP | `lib/csp.ts` (`LIVE_PROVIDER_CONNECT_SRC`) |
| i18n | `locales/{en,fr,de,es,it,zh}/translation.json` — parité stricte |
| Audio | `lib/constants.ts` (`LIVE_INPUT_CHUNK_SAMPLES`, `LIVE_OUTPUT_SAMPLE_RATE`) |

À vérifier au lot 4 : `useChat.sendMessage` se résout-elle à la fin du flux (elle est `async`) ?
Sinon le pont observe `status` et `hitl` du hook.

### 4.3 Base de données

UNE migration : `users.live_preferences` (JSONB nullable, A10 bis) — les préférences de
conversation appartiennent au compte. Le reste : `connector_metadata` (modèle, voix, réflexion —
nouveau dict), état en Redis, trace dans `conversation_messages` (métadonnées) et les registres
existants. `task db:migrate:replay-check` au lot 1.

### 4.4 LLM et prompts

Un prompt système live (mandat) + un fichier de lignes. Le `setup` porte le mandat et UNE déclaration
de fonction : petit, donc le contexte refacturé à chaque tour reste celui de la conversation. La
réponse rendue à la voix est bornée (`LIVE_DELEGATION_RESULT_MAX_TOKENS`, `{result_budget}` publié
au prompt — ADR-184) parce qu'elle entre dans le contexte du fournisseur et y est refacturée à chaque
tour : le fil garde l'entier. Le taux de délégation et la propension du modèle live à répondre seul
sont mesurés au lot 0 ; le mandat se règle sur la mesure, pas sur une intuition.

### 4.5 Périmètres indirects et non-régression

- **Porte du chat** : un tour délégué est un tour ordinaire ; les seuls ajouts sont deux champs
  optionnels de `ChatRequest` et une estampille — tests de non-régression sur un tour sans eux.
- **Injection au tour suivant** : élargir le prédicat ne doit ni doubler ni réordonner les
  `proactive_*` (test sur un mélange des deux familles).
- **Voix existante** : `VoiceModeBadge` et `useVoiceMode` inchangés ; le mot d'éveil est mis en pause
  par le mécanisme de la réunion (sélecteur « micro pris »).
- **Yeux** : `voiceState` reste le seul signal ; sans session live, dérivation identique (les tests
  « once-sequences » d'ADR-264 sont sensibles à tout tirage supplémentaire).
- **Téléphone** : non touché.
- **Démo** : OFF ; `test_every_hidden_route_is_hidden_by_a_written_decision` reste vert.
- **Compteur du chat** : la carte de fin AGRÈGE ce que les bulles montrent déjà ; aucun second calcul.

---

## 5. Matrice des risques

| # | Risque | Prob. | Impact | Mitigation |
|---|---|---|---|---|
| R-1 | `systemInstruction`/`tools` non verrouillables dans le jeton | moyenne | mandat altérable par la personne (sur sa clé, sous les gardes du chat) | lot 0 mesure ; repli A4 écrit |
| R-2 | Le modèle live répond seul sur les faits de la personne au lieu de déléguer | moyenne | réponse inventée à la voix | mandat strict, description de la fonction, taux de délégation mesuré au lot 0, réglage `LIVE_DELEGATION_SCHEDULING` |
| R-3 | Latence d'un tour ReAct (dizaines de secondes) | haute | attente | `NON_BLOCKING` (la voix parle), délai borné puis « la réponse arrivera dans le fil » (ADR-117) |
| R-4 | Reconnexion à 10 min : refus du jeton (`uses:1`) ou perte de contexte | faible (documenté) | session coupée | lot 0 ; fin nommée `resumption_failed` |
| R-5 | iOS : `AudioContext` suspendu, micro + WebSocket, écran verrouillé | moyenne | session zombie | sonde mobile ; `visibilitychange` → fin `hidden` |
| R-6 | Double archive d'un énoncé délégué (transcription + bulle) | moyenne | trace fausse | règle d'unicité A7 + test |
| R-7 | Deux tours en même temps (le modèle rappelle avant le résultat) | moyenne | run refusé | sérialisation + ligne « still working » immédiate |
| R-8 | Interruption vocale pendant un tour → run tué | moyenne | action à moitié faite | jamais : la cancellation du fournisseur n'annule pas le run (A3) |
| R-9 | Ratchets de taille (`connectors/models.py`, `routes.py`, `registry.py`, `chat/page.tsx`, `UserConnectorsSection.tsx`, `ChatRequest`) | haute | build rouge | extraire, jamais relever |
| R-10 | Ordre des transcriptions (sortie asynchrone) → `live_turn` désordonnés | moyenne | archive fausse | n'archiver qu'au `turnComplete`, texte final, horodatages client + serveur |
| R-11 | Quatre workers, une session | certaine | aucun si l'état est en Redis | jamais d'état en mémoire de processus |
| R-12 | Deux onglets, deux sessions | moyenne | double facture chez le fournisseur | claim à jeton propriétaire |
| R-13 | Couverture front (seuils globaux et par glob) | haute | CI rouge | machine à états et transport testés avec faux WebSocket |
| R-14 | Métrique aveugle | haute | ratchet | chaque métrique câblée (`or vector(0)`) |
| R-15 | Le fournisseur retire un modèle | moyenne | connecteur cassé | découverte à l'activation et à l'ouverture, erreur nommée |
| R-16 | ADR-298 pris par le bac à sable | certaine | numérotation | ADR-299 ; `task release:sync-counts` |

---

## 6. Plan de test directeur (socle TDD)

### 6.1 Unitaire dorsal

- `domains/connectors/test_live_connector_type.py` : type, catégorie `live`, affichage, aucun conflit
  tant que seul, pas keyless, pas clé globale ; parité `requiresKey` intacte.
- `domains/connectors/test_live_key_verifier.py` : `models.list` (faux client) → vérifié / refusé /
  délai ; un modèle sans `bidiGenerateContent` n'est pas listé ; `list_voices()` rend la
  provenance (`discovered` / `published` avec date et source) ; la sonde d'activation ouvre et
  ferme une session sur la paire modèle + voix (faux transport) et rapporte un refus du
  fournisseur avec son message, jamais un refus décidé par la liste embarquée.
- `test_cost_bearers_guard.py` : `live` USER, hors de la somme ; `QUOTA_COLUMN_OF` complet.
- `test_capability_coverage.py` (+ `LIVE`), `test_demo_instance_capability_coherence.py`
  (`LIVE_ENABLED` dans les deux templates), `test_redis_key_family_guard.py`.
- `domains/live/test_session_store.py` : claim/relâche par jeton propriétaire, deux acteurs, TTL,
  reprise après expiration, claim d'un autre compte refusé, relâche avec mauvais jeton refusée.
- `domains/live/test_mint.py` : contraintes (modèle, instruction, fonction unique `NON_BLOCKING`,
  modalités, reprise, compression, transcriptions), expirations depuis les réglages, refus si
  connecteur inactif / capacité off / claim tenu / limiteur ; jamais la clé dans les logs.
- `domains/live/test_mandate.py` : placeholders produits, langue via `get_language_name` (dont `zh`),
  personnalité optionnelle, horloge de la personne ; grep anti-français / anti-noms propres.
- `agents/api/test_chat_request_live_stamp.py` : `live_session_id` et `spoken_text` archivés dans la
  ligne `user` par le constructeur ; absents → tour identique à aujourd'hui.
- `agents/api/test_archive_metadata_guard.py` : deux nouveaux constructeurs, aucun dict inline.
- `conversations/test_out_of_graph_injection.py` : deux rôles, ordre, mélange avec `proactive_*`,
  `visible_only`, limite ; un tour délégué n'est PAS injecté deux fois.
- `domains/live/test_end_and_summary.py` : agrégation par run ids estampillés (facture = somme des
  bulles), carte de fin archivée une fois, idempotence d'un double `end`, décision de session
  answered/interrupted.
- `core/test_reasoning_profiles.py` : famille live extended thinking ; renderer `thinkingConfig`.
- `test_i18n_live.py`, ratchet des métriques, placeholders, timezone, `except` vides, taille,
  `direct_client_callers`, `user_data_readers` (raison écrite) : verts par construction.

### 6.2 Intégration (PostgreSQL + Redis)

- Claim sous deux processus simulés ; tour délégué réel sur Docker dev avec estampille → ligne
  `user` porteuse ; `live_turn` archivés puis lus par la porte d'injection ; carte de fin agrégeant
  deux tours.

### 6.3 Sonde fournisseur (jamais un test qui se saute)

`scripts/live-probe/` + `task live:probe` (forme `mobile:probe` / `recurrence:corpus:measure`,
ADR-155) : frappe contrainte → WebSocket → tour audio synthétique → `send_to_lia` `NON_BLOCKING`
avec un résultat retardé (`INTERRUPT` vs `WHEN_IDLE`) → reprise à 10 min → `goAway` → fin ; et une
mesure du taux de délégation sur un corpus de demandes génériques en six langues.

### 6.4 Web (vitest)

- `transports/gemini-ws.test.ts` : faux `WebSocket` ; `setup` conforme ; `toolCall` → événement ;
  `toolCallCancellation` → réponse abandonnée, run conservé ; `interrupted` → `flush` ; `goAway` →
  reprise ; `sessionResumptionUpdate` mémorisé ; fermeture propre.
- `pcm-player.test.ts` : planification continue, vidage instantané, reprise iOS.
- `session-machine.test.ts` : états et fins nommées ; un seul propriétaire du micro.
- `delegation.test.ts` : sérialisation, « still working », délai borné, HITL par la voix (question →
  réponse → même porte), aplatissement borné avec coupe énoncée.
- `useLiveSession.test.ts` : frappe → transport → délégation → `appendMessage` des `live_turn` ;
  nettoyage au démontage (aucun socket vivant).
- `components/live/*.test.tsx` : rôles et noms accessibles, clavier, `aria-live`, disabled, six
  langues ; carte de fin (jamais une ligne fournisseur).
- `expression-engine.test.ts` : sans live, inchangé.
- `LiveConnectorForm.test.tsx` ; `csp.test.ts`.

### 6.5 E2E (Playwright 1.60, hermétique)

`page.routeWebSocket` (faux Gemini scripté) + API mockée : ouvrir Live, un `toolCall` → une bulle
`user` puis une réponse streamée dans le fil, la voix reçoit le résultat ; une question HITL → carte
dans le fil + réponse par la voix ; Terminer → carte de fin ; axe ; clavier ; viewport 360 ; refus
pendant une capture de réunion.

### 6.6 Scénarios limites

Perte du WebSocket en pleine phrase (reprise, sous-titres conservés) ; jeton expiré avant ouverture
(60 s) ; `goAway` pendant un tour délégué (le tour finit dans le fil, le résultat renvoyé après
reprise si l'id n'est pas annulé) ; fournisseur 429/403 (clé révoquée → connecteur `ERROR`, bannière
« reconnecter ») ; deux onglets ; onglet caché ; micro refusé ; changement de périphérique ; tour
refusé par un plafond (la voix relaie la phrase d'usage) ; ReAct de deux minutes (délai borné) ;
HITL à plusieurs brouillons (ADR-288 : un par un, à la voix) ; « stop » pendant un envoi de mail
(le run est annulé par Stop seulement) ; session > durée max ; silence prolongé ; langue `zh` ;
capacité coupée par l'administrateur PENDANT une session (la frappe suivante est refusée, la session
en cours finit) ; contenu lu contenant une injection (la voix ne peut que déléguer).

---

## 7. Plan d'actions séquencé (lots atomiques, TDD)

Plan d'exécution détaillé, tâche par tâche avec le code et les tests :
`docs/superpowers/plans/2026-09-18-live-mode.md` (32 tâches — lot 0 : Tasks 1-2 ; lot 1 : 3-12 ;
lot 2 : 13-16 ; lot 3 : 17-20 ; lot 4 : 21-22 ; lot 5 : 23-28 ; lot 6 : 29-32). La table ci-dessous
en est le résumé ; le plan fait foi.

| Lot | Contenu | Portes |
|---|---|---|
| **0 — Spike (jetable)** | Docker dev + clé de test : frappe contrainte (instruction + fonction verrouillées ?), connexion navigateur brute, tour audio, `send_to_lia` `NON_BLOCKING` avec résultat retardé (`INTERRUPT`/`WHEN_IDLE`), reprise à 10 min, `goAway`, ordre des transcriptions, taux de délégation sur un corpus générique, sonde mobile micro + WebSocket. Faits mesurés dans la spec ; R-1/R-2/R-3 tranchés. Rien n'est gardé. | rapport |
| **1 — Socle dorsal** | Connecteur (type, catégorie, vérificateur, affichage), `cost_bearers`, capacité + clé + `EXPECTED_CAPABILITIES`, `core/config/live.py` + constantes + 8 `.env`, `core/i18n_live.py`, familles Redis, `domains/live/` (schémas, erreurs, store, protocole + Gemini, frappe, `GET /live/models`, `GET /live/config`), mandat + prompts + famille de raisonnement, routes, métriques. | `lint`, `test:backend:unit:fast`, gardes |
| **2 — Trace dorsale** | `ChatRequest` (+2 champs), estampille dans `archive_first`, constructeurs `live_turn` / `live_session_summary`, `POST …/turns`, `POST …/end` (claim, décision, carte agrégée), injection élargie, `NOT_A_READER`. | idem + intégration PostgreSQL |
| **3 — Transport et audio web** | `LiveTransport`, `gemini-ws.ts`, lecteur PCM, worklet à petits morceaux, machine à états, `liveStore`, CSP. | `lint:frontend`, `test:frontend:coverage` |
| **4 — Pont de délégation** | `delegation.ts` + `useLiveSession` sur `useChat` (envoi estampillé, fin de flux, HITL par la voix, cancellation, délai borné, `live_turn` en direct). | idem |
| **5 — Surface web** | Bouton, bandeau, sous-titres, yeux, glyphe live, carte de fin, formulaire de connecteur, section de réglages, carte des capacités, i18n ×6, a11y ; e2e. | idem + `test:e2e` |
| **6 — Clôture** | (6b si R4 : extraction de fin de session sur les `live_turn`.) ADR-299, `docs/technical/LIVE_MODE.md`, `INDEX.md`, `ADR_INDEX.md`, `CONNECTORS_PATTERNS.md`, `VOICE_MODE.md` (renvoi), guides mobiles, `CLAUDE.md` + `task docs:sync-agents`, `task release:sync-counts`, ratchets relevés (≥ 2 pts), tableau de bord, `task ci:fast`, `task live:probe` rejouée. | `ci:fast` |

Chaque lot : tests d'abord ; preuve Docker dev pour tout ce qui touche la porte du chat ;
`git status --porcelain` avant tout déploiement ; aucun commit (le propriétaire commite).

---

## 8. Arbitrages résiduels (aucun ne bloque le lot 0)

| # | Question | Recommandation |
|---|---|---|
| R1 | Numéro d'ADR | 299 |
| R2 | La restitution PARLÉE d'une réponse déléguée est-elle archivée (ligne `live_turn assistant` après la bulle du chat) ? | oui : ce que la personne a entendu peut différer de l'écrit, et la trace le montre ; un glyphe distingue les deux |
| R3 | Un bloc de contexte dans le mandat (agenda du jour, rappels) pour éviter une délégation sur des questions triviales ? | non au lot 1 : déléguer coûte un tour du chat mais garantit l'exactitude ; à revisiter sur la mesure du lot 0 |
| R4 | Ce que LIA apprend des échanges purement vocaux (extraction de fin de session) | oui, lot 6b, sous les drapeaux de la personne, source `user` |
| R5 | Le composeur pendant une session : désactivé (sauf Stop) ou ouvert (un message tapé = une délégation de plus) | désactivé au lot 1 : une seule voie évite deux runs |
| R6 | Défauts : 30 min, 1 session/compte, 8/instance, délai de délégation 90 s, résultat rendu à la voix 600 jetons, `INTERRUPT` | ces valeurs, toutes en réglages |
| R7 | Vidéo, démonstrateur, voix | hors programme ; OFF ; choisie par la personne |
| R8 | WebSocket brut ou `@google/genai` dans le bundle | brut, sauf mesure contraire au lot 0 |
| R9 | Aperçu sonore d'une voix dans le formulaire (une synthèse sur la clé de la personne) | non au lot 1 ; la caractéristique publiée (« Firm », « Warm »…) est affichée à la place |

---

## 9. Ce que seul le lot 0 peut prouver — MESURÉ (2026-09-18, clé de dev, `gemini-3.8-live`)

Sonde : `apps/api/scripts/live/probe.py` (`task live:probe`, lit `LIVE_PROBE_API_KEY`, n'importe
rien de `src`). Chaque point du plan reçoit sa mesure et, quand elle contredit l'hypothèse, le
repli retenu.

1. **Verrouillage du mandat (R-1) — RÉFUTÉ.** Un jeton frappé avec `live_connect_constraints`
   (`system_instruction` + `tools`) a été accepté par une session ouverte avec une instruction
   DIFFÉRENTE : la contrainte verrouille le modèle, pas l'instruction. Repli A4 appliqué : le
   serveur rend le `setup` et le navigateur le rejoue verbatim (`LiveCredentialResponse.setup`).
2. **`scheduling` (R-2/R-3)** : un `send_to_lia` NON_BLOCKING est émis à t = 1,4 s ; le modèle
   termine son tour aussitôt (pas de comblement vocal dans une sonde textuelle) ; la réponse
   d'outil envoyée à t = 9,4 s est PARLÉE 0,5 s plus tard, en `INTERRUPT` comme en `WHEN_IDLE`
   (la voix était de toute façon au repos). Usage : 655 → 785 jetons pour la paire de tours.
3. **Délégation** : mesurée sur la sonde (un tour, une délégation) ; le taux sur corpus reste à
   mesurer en usage réel (`live_sessions_total` et le compteur `delegations` de la carte).
3b. **Résultat tardif** : un texte poussé en `clientContent` APRÈS l'appel d'outil (sans
   `toolResponse`) est parlé comme la réponse → `DelegationBridge.late` livre ainsi la réponse
   d'une délégation qui a dépassé son délai. Latence p50/p95 d'un tour délégué : à mesurer sur
   dev via `GET /admin/…/token_usage` (le tour délégué est un tour de chat ordinaire).
4. **Reprise (R-4) — RÉFUTÉ sur le jeton.** Le MÊME jeton `uses: 1` ne rouvre pas la session
   (1011 « Token has been used too many times ») ; un jeton FRAIS + le dernier `newHandle`
   reprend un tour complet. Repli : `POST /live/sessions/{id}/credential` refrappe un jeton
   pour la MÊME session (`LiveSessionRecord.setup_inputs`), le navigateur reconnecte avec le
   handle.
5. **WKWebView** : la sonde mobile mesure désormais `external_websocket` sous la CSP/COEP de
   production (`scripts/mobile-probe/page.html`, verdict `open`/`error` attendu, `blocked:*`
   refusé). À relancer sur les deux moteurs (`task mobile:probe:{android,ios}`) avant la
   première publication mobile du mode.
6. **Ordre des transcriptions** : les fragments `outputTranscription` arrivent PENDANT l'audio,
   puis `generationComplete`, puis `turnComplete` ~3 s plus tard ; aucune `inputTranscription`
   pour une tonalité synthétique (ce n'est pas de la parole). Le contrôleur ouvre une nouvelle
   ligne de sous-titre au fragment SUIVANT un `turnComplete`, jamais sur une ligne vide.
7. **`models.list`** : neuf modèles portent `bidiGenerateContent`, dont des modèles de
   transcription, de traduction et de robotique (non conversationnels) → exclusion par mot
   d'usage (`LIVE_NON_CONVERSATIONAL_MODEL_WORDS`) ; `thinking` vaut `true` sur
   `…-extended-thinking`, `null` sur le live simple. La sonde d'activation (setup + fermeture,
   sans audio) répond en 0,29 s ; un NOM DE VOIX INVALIDE est accepté au setup ET à la
   génération (repli silencieux du fournisseur, 537 vs 593 jetons pour trois mots) → la voix est
   validée contre la liste vendue, jamais par le fournisseur.
8. **Transport navigateur** : `BidiGenerateContent?access_token=…` refuse (1008) sur v1alpha et
   v1beta ; `BidiGenerateContentConstrained?access_token=…` répond `setupComplete` sur les deux ;
   `key=<jeton>` répond 1007. Le transport web ouvre la méthode Constrained en v1beta.
   `useChat.sendMessage` se résout bien à la fin du flux (`await chatSSEClient.streamChat`), une
   question HITL comprise : elle devient la dernière bulle assistante, que `readLastAnswer` rend
   comme la réponse quand `hitl.status` attend la personne.

---

## 10. Grille d'auto-évaluation

- **Complétude, robustesse, viabilité** : la v2 satisfait les trois retours par une seule forme —
  la délégation au moteur du chat — qui supprime toute réimplémentation hors graphe (outils, HITL,
  registres, facture, archive). Deux inconnues sont bornées par le lot 0 (verrouillage du mandat,
  comportement de délégation) avec leur repli écrit.
- **Hypothèses confrontées au code** : chaque réutilisation cite le fichier et sa limite (§1.3,
  §1.5) ; la porte du chat, ses champs, l'annulation, l'agrégation de facture et l'aplatissement ont
  été localisés ; ce qui n'est pas prouvable sans session réelle est en §9.
- **Jetons/coûts, registres, mobile** : cadrés (A5, A7, A8, A12) ; la facture de LIA est celle que
  les bulles montrent déjà, agrégée une fois, affichée en fin de session ; celle du fournisseur
  n'existe nulle part dans l'application.
- **Plan de tests et d'actions** : prêts ; les gardes qui rougiront sont nommés d'avance.
