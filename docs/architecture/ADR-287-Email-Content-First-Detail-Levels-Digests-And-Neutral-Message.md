# ADR-287 — Le contenu d'un e-mail arrive propre, à trois niveaux de détail, condensé une fois par message, dans un vocabulaire neutre

- **Statut** : Accepté
- **Date** : 2026-09-15
- **Amende** : ADR-286 (la projection par item borne le VOLUME d'un résultat ;
  cette décision borne ce qu'un e-mail CONTIENT et choisit ce qui est servi),
  ADR-184 (une borne imposée est publiée — l'outil publie `detail`, `part`,
  `page_token`, et le manifeste dit ce que chaque niveau coûte), ADR-185 (un
  compte est exact ou n'existe pas — `result_size_estimate` est nommé ESTIMATION
  et `count` compte la page), ADR-260 (une clé Redis nommée par un `user_id`
  déclare sa famille — `email:digest` est un `USER_CACHE`), ADR-272 (tout jeton
  payé par la plateforme répond aux deux plafonds — le condensé est refusé par
  `spend_blocked` et sa dépense voyage sur le `RunnableConfig` du tour),
  ADR-275 (une sortie structurée tronquée est un refus — un condensé raté laisse
  le corps, jamais un condensé inventé), ADR-256 (les messages d'outil sont en
  anglais technique)
- **Périmètre** : `domains/connectors/clients/normalizers/{email_message,
  html_text, reply_trimming}.py`, les trois normaliseurs (`google_gmail_client.
  _normalize_message_fields`, `microsoft_email_normalizer`, `email_normalizer`),
  les trois clients (`search_emails(page_token, headers_only)`),
  `domains/connectors/clients/protocols.py`, `domains/agents/emails/
  {detail_levels, digest, get_emails_manifest}.py`,
  `domains/agents/tools/emails_tools.py` (`get_emails_tool`, les deux outils
  hérités supprimés), `domains/agents/tools/formatters.py`,
  `domains/agents/display/components/email_card.py`, `core/i18n_v3.py`,
  `prompts/v1/{email_digest_prompt, emails_agent_prompt, smart_planner_prompt}.txt`,
  `domains/llm_config/constants.py` (slot `email_digest`), `infrastructure/llm/
  factory.py`, `infrastructure/database/seeds/llm_config_seed.sql`,
  `infrastructure/cache/key_families.py`, `infrastructure/llm/spend_roads.py`,
  `observability/metrics_extractions.py`, dashboard Grafana 10, `core/constants.py`,
  `core/config/connectors.py`, les trois `.env`, les six locales web,
  `scripts/emails/measure_reply_trimming.py`, `Taskfile.yml`

## Contexte

ADR-286 a réparé la coupe au caractère : le modèle lit désormais des e-mails
entiers. Restait ce qu'il lisait. Le propriétaire a précisé l'usage réel, qui
n'est pas celui d'un client de messagerie où l'on clique sur un message :
« résume mes e-mails non lus », « fais-moi un résumé des e-mails reçus cette
semaine », « une synthèse des newsletters », les notifications proactives et
les routines qui raisonnent sur le CONTENU de dix ou vingt messages. Un
modèle « liste puis clique » ne sert pas ces cas.

Mesuré sur le code au 2026-09-15 :

- Trois « formats unifiés » qui étaient le format Gmail : les normaliseurs
  Graph et IMAP FABRIQUAIENT un `payload.headers`, un `labelIds`, un
  `internalDate`, pour que les lecteurs écrits pour Gmail ne s'en aperçoivent
  pas ; le corps Graph restait du HTML brut converti tard, dans le formateur
  d'agent ; le corps IMAP était aplati par une regex qui perdait paragraphes et
  liens ; deux conversions HTML → texte vivaient dans deux fichiers.
- Chaque réponse d'un fil citait tout l'historique : un fil de huit réponses
  atteignait le modèle huit fois, signatures comprises. Rien ne le retirait.
- `get_emails_tool` n'avait qu'un niveau : la recherche en `format=metadata`
  suivie d'un re-fetch `full` de chaque message, corps borné à 1 500 caractères
  par `EMAILS_BODY_MAX_LENGTH` — trop pour lister, trop peu pour lire, et
  aucun moyen de raisonner sur vingt messages sans les charger tous.
- Deux outils hérités (`search_emails_tool`, `get_email_details_tool`,
  ~790 lignes) n'étaient plus offerts à aucun catalogue.
- `resultSizeEstimate` de Gmail était traité comme un compte ; aucune
  pagination n'existait ; la réparation Apple des réponses (`In-Reply-To`)
  n'avait jamais fonctionné, les en-têtes fabriqués ne portant pas de
  `Message-ID`.

Les pratiques établies pour un assistant qui lit du courrier : nettoyer le
contenu avant le modèle (texte, jamais de balisage ; citations et signatures
retirées), condenser chaque message UNE fois par un petit modèle et mettre le
condensé en cache, raisonner en map-reduce sur les condensés, laisser la
question choisir le niveau de détail avec son coût annoncé, ne jamais borner en
silence, et servir un modèle neutre depuis un normaliseur par fournisseur.

## Décision

1. **Un vocabulaire neutre à la frontière du client.** `EmailMessage`
   (`normalizers/email_message.py`) est ce que les trois normaliseurs
   produisent : `id`, `threadId`, `labelIds`, `snippet`, `subject`, `from`,
   `to`, `cc`, `date`, `rfc_message_id`, `internalDate`, `body` (texte propre,
   jamais HTML ni base64), `attachments`, `_provider`. Graph et IMAP ne
   fabriquent plus d'arbre Gmail ; Gmail garde son arbre natif jusqu'au builder
   qui le retire (ADR-286). Une seule conversion HTML → texte (`html_text.py`,
   liens conservés sous une étiquette technique), une seule ligne d'aperçu
   (`strip_html_to_line`). La signature de `search_emails` est celle du
   protocole pour les trois clients (garde de parité).
2. **La citation et la signature quittent le corps au bord du client.**
   `reply_trimming.trim_quoted_reply` coupe au premier marqueur — « a écrit : »
   en six langues (deux lignes jointes quand le client de messagerie a replié
   la ligne), bannière « Original Message » en six langues, bloc d'en-têtes
   Outlook (`From:` suivi de `Subject:` dans les cinq lignes), suite finale de
   lignes `>`, séparateur `-- `, « Envoyé de mon … » en six langues — et rend le
   corps intact quand il resterait moins de 20 caractères (un « Merci ! » nu :
   la citation est ce que le lecteur attend) ou quand les réponses sont
   entrelacées dans la citation — ou quand le message est un TRANSFERT
   (préfixe de sujet `Fwd`/`TR`/`WG`/`RV`/`I`/`转发`, ou bannière « Message
   transféré » dans le corps) : le texte sous le bloc d'en-têtes EST le
   message, le couper rendrait « voici la demande de Marc » et rien d'autre
   (revue à froid, 12 cas au corpus). Un seul point d'appel, `clean_reply_body`,
   sous `EMAILS_TRIM_QUOTED_REPLIES` (défaut vrai). Le retrait vaut pour tout
   lecteur du corps normalisé — registre, condensé, heartbeat, espace RAG qui
   suit un libellé (chaque message y porte ses propres mots ; l'historique vit
   dans les messages qui le portent) ; la réponse et le transfert, qui citent
   l'original, lisent l'arbre natif et ne sont pas touchés.
3. **Trois niveaux de détail, choisis par la question, au coût annoncé.**
   `get_emails_tool(detail=metadata|summary|full, part, page_token)` :
   `metadata` liste sans corps (recherche `headers_only` sur IMAP, aucun
   re-fetch) ; `full` (défaut) sert le corps propre paginé au paragraphe
   (`EMAILS_BODY_PART_TOKENS`, `body_part`/`body_parts`, une note
   `[continued: part n/total; pass part=n+1 …]`), jamais coupé en milieu de
   phrase ; `summary` sert `gist`, `key_points`, `actions`, `category`,
   `importance` à la place du corps. Un niveau inconnu est réparé en `full`
   et journalisé (le validateur sémantique n'impose pas les enums). La
   pagination est opaque (`page_token` : `pageToken` Gmail, URL `@odata.nextLink`
   Graph — refusée hors de `api_base_url` —, décalage décimal IMAP), et
   `result_size_estimate` est l'estimation du FOURNISSEUR ou rien — Gmail la
   donne, Graph seulement quand `@odata.count` est demandé, IMAP jamais ; la
   taille de la page n'est ni une estimation ni un compte et n'est plus
   publiée comme telle (ADR-185) — `count` compte la page.
   Le manifeste (`get_emails_manifest.py`, v3.0.0) dit ce que chaque niveau
   porte et coûte ; le prompt de l'agent et le planificateur le répètent avec les
   mêmes mots — et depuis la mesure du 2026-09-15 la PORTÉE et le NOMBRE aussi :
   le courrier récent sans autre précision est la boîte de réception
   (`in:inbox`, ce qu'une personne appelle « mes e-mails ») et un message précis
   (de X, à propos de Y) ajoute `in:anywhere` pour retrouver un archivé ;
   `max_results` est le nombre demandé (« mes 6 derniers » → 6), jamais vingt
   pour en choisir six sous `summary` où chaque message est un appel payé.
   `test_get_emails_contract_surfaces.py` tient les trois surfaces égales, et
   le réparateur côté code dit la même chose (ADR-284) : `normalize_gmail_query`
   fait d'une requête vide, de « inbox » ou de « received » un listing de la
   boîte de réception (`label:inbox`), et d'une recherche sans portée
   (« from:john ») une recherche hors envoyés et brouillons, archives
   comprises — il faisait de tout cela « tout sauf envoyés ».
4. **Un condensé par message, calculé une fois, mis en cache.** `EmailDigest`
   (`emails/digest.py`) est produit par le slot `email_digest`
   (`CATEGORY_SPECIALIZED`, `structured_output` requis, `POWER_TIER_LOW`,
   raisonnement `none` par `short_answer_config`, le plafond de sortie étant
   celui du SLOT — `max_tokens` de `llm_config_overrides`, édité par
   l'administrateur, semé à 1 000 par `EMAIL_DIGEST_MAX_OUTPUT_TOKENS` (600
   jusqu'au 2026-09-15 : une newsletter dense en produit 550 à 600, un condensé
   sur vingt fut coupé — un refus payé plein) ; le code n'impose plus de
   plafond propre, qui écrasait en silence ce que l'administrateur saisissait
   (ADR-244 : la configuration d'un slot vit en base, jamais dans une constante
   ni une clé `.env`) —, entrée
   bornée à `EMAILS_DIGEST_INPUT_MAX_TOKENS` au paragraphe avec « [the message
   continues] »), sur le prompt versionné `email_digest_prompt.txt` dont les
   cinq `{placeholders}` ont un producteur. Clé Redis
   `email:digest:{user}:{provider}:{message}:{langue normalisée}:{version de
   schéma}`, famille `USER_CACHE`, TTL `EMAILS_DIGEST_CACHE_TTL_SECONDS`
   (30 jours, écrite avec `ex=`). Ordre : cache, puis `spend_blocked` (tout
   manquant devient `skipped_quota` et garde son corps), puis calcul sous un
   sémaphore (`EMAILS_DIGEST_CONCURRENCY`) et `run_single_flight` par clé. Un
   échec — `StructuredOutputError`, troncature comprise (ADR-275) — laisse le
   corps et vaut `failed` ; un plafond fermé entre la porte du lot et un
   appel vaut `skipped_quota`, jamais `failed` (ADR-272) ; le cache est un
   accélérateur, jamais une porte : Redis injoignable, chaque message est
   condensé et rien n'est écrit (un tour plus lent, pas un outil en échec),
   et les lectures tiennent en un seul `mget` ; `email_digest_cache_total{result}` compte chaque
   issue (ligne « Email digests (ADR-287) » du dashboard 10). Le condensé
   voyage sur le **`RunnableConfig` du tour** (`runtime.config`), comme la
   génération de contenu d'e-mail : c'est lui qui porte le rappel de suivi des
   jetons, et un appel de modèle auquel on ne le tend pas est un euro qu'aucun
   registre ne voit (mesuré, § Mesures).
5. **La carte montre le condensé.** `email_card` dessine « L'essentiel », les
   « Points clés » et « À faire » (six langues, `core/i18n_v3.py`) entre
   l'aperçu et le corps, et ne dessine plus l'aperçu deux fois ; le
   sérialiseur de réponse lit `gist`/`key_points`/`actions` (il saute un champ
   nommé `summary` trop court, d'où ces noms).
6. **Les outils hérités sont supprimés**, `EMAIL_TRUNCATION_RATIO` et
   `_extract_body_truncated` avec eux ; `EMAILS_BODY_MAX_LENGTH` ne borne plus
   ce que le modèle lit (le budget ADR-286 et `EMAILS_BODY_PART_TOKENS` le
   font), sa valeur d'exploitation est laissée telle quelle.
7. **La bibliothèque tierce reste au dehors, sur mesure.** `mail-parser-reply`
   1.36 (55 KiB, aucune dépendance, import 5 ms — sous le plafond de 5 Mio)
   fait **22 sur 48** corps et **1 gardien sur 2** sur le corpus, par sa porte
   la plus favorable (`read(...).replies[0].body`, quotes retirées) : elle ne
   retire pas une suite finale de lignes `>` sans en-tête, ne reconnaît qu'une
   bannière « Original Message » sur six, ni les « Envoyé de mon » fr/de/zh,
   et coupe une formule de politesse (« Bonne journée,\nClaire ») comme une
   signature — les propres mots de la personne. Le trimmer maison fait 48/48
   et 2/2. `task emails:corpus:measure` rejoue le corpus et note la candidate
   quand l'interpréteur qui l'exécute la porte ; la règle d'adoption reste
   48/48 ET un import sous 5 Mio.

## Conséquences

- Six clés nouvelles dans la section `[34]` des trois `.env`
  (`EMAILS_BODY_PART_TOKENS`, `EMAILS_DIGEST_*` ×4, `EMAILS_TRIM_QUOTED_REPLIES`),
  aucune dans les `.env` du démonstrateur, qui ne portent pas le bloc e-mails.
- Un slot LLM de plus (`email_digest`) : registre, défauts, `LLMType`, seed
  SQL, six locales — la garde de vocabulaire tient les quatre égaux. Le seed
  nomme le même fournisseur et le même modèle que les six autres lignes
  DeepSeek du seed ; le défaut de code nomme un modèle admis par la matrice
  de conformité des défauts. Ni l'un ni l'autre n'est « le modèle utilisé » :
  la configuration réelle vit en base (`llm_config_overrides`).
- Le cache Redis des messages Gmail (`gmail:message`, ≤ 5 min) peut servir un
  corps HTML Graph ou un corps cité normalisé avant cette décision pendant
  cette fenêtre, puis expire.
- La résolution des libellés dans une requête (`resolve_label_names_in_query`)
  n'est pas appelée par `get_emails_tool` — antérieur, constaté, non traité.
- La réponse Apple porte `In-Reply-To`/`References` (le `rfc_message_id`
  normalisé), ce que les en-têtes fabriqués n'avaient jamais permis.
- `short_answer_config(max_tokens=None)` garde le budget du slot : un
  appelant qui EMPRUNTE un slot partagé (le rappel sur `response`) dimensionne
  le sien, un appelant qui a le sien n'impose rien.
- Les règles de profil de raisonnement (`ReasoningProfile`,
  `resolve_reasoning_profile`, `DEEPSEEK_THINKING_PREFIXES`) vivent dans
  `core/reasoning_profiles.py` : `core/llm_config_helper.py` les importait
  depuis `infrastructure/llm/reasoning/profiles.py`, une inversion de couche
  qui fermait un cycle (`infrastructure.llm.__init__` → pipeline d'évaluation
  → le helper) et faisait échouer un import à froid du helper. Le chemin
  d'infrastructure reste, en simple réexport, pour ses lecteurs.

## Mesures

Docker dev, vraie boîte du compte, 2026-09-15, mode ReAct, exécution par le
propriétaire dans l'interface :

- « recherche mes 5 derniers emails recus » : le modèle choisit
  `get_emails_tool(query="in:inbox", max_results=5, detail="metadata")` ;
  outil en 219 ms ; **2 itérations** (11 avant ADR-286) ; second appel du
  modèle 2 216 tokens neufs + 29 568 en cache, 614 en sortie ; réponse de
  1 942 caractères listant les cinq messages ; tour complet 15,5 s.
- « fais un résumé de mes 6 derniers emails recus » : `detail="summary"`,
  `max_results=6` ; **6 condensés calculés, 0 échec**, 3,5 s d'outil ;
  `ToolMessage` de 11 327 caractères / 3 934 tokens, JSON valide, aucune note
  de budget, `result_size_estimate: 201`, `next_page_token` présent ; 2
  itérations ; second appel 4 279 tokens neufs + 30 848 en cache, 1 253 en
  sortie ; `email_digest_cache_total{result="computed"} = 6` ; tour 23,5 s.
- Ce que la mesure a trouvé : six `native_structured_output_success` pour
  `EmailDigest` et **zéro `token_usage_recorded` pour `email_digest`** —
  `callbacks_before_filter: 0`. La porte structurée construit un config neuf
  quand on ne lui en tend aucun, et le tracker du tour est un rappel PORTÉ par
  le `RunnableConfig`, pas un contexte ambiant : le condensé reçoit désormais
  `runtime.config` (tests `TestTheSpendIsAccounted`,
  `TestSummaryIsAccountedToTheTurn`). La déclaration `TURN` du registre des
  routes de dépense était vraie sur le papier et fausse dans le journal.
  Vérifié ensuite dans le conteneur, par une sonde tendant un
  `TokenTrackingCallback` réel sur un message synthétique : la porte voit le
  rappel (`callbacks_before_filter: 1`) et le tracker enregistre
  `('email_digest', <modèle configuré en base>, 477 tokens d'entrée, 189 de
  sortie, 256 en cache)` pour un condensé exact (gist et action de la
  demande). La même sonde sans la configuration en base retombe sur le défaut
  de code, dont cette instance n'a pas la clé : le condensé vaut `failed`, le
  corps reste, et le tracker garde la trace de l'appel refusé — la
  dégradation prévue.
- Six tours rejoués par le propriétaire après la livraison (21:19–21:26 UTC),
  trois en ReAct, trois en pipeline, relus dans le journal et les registres :
  chaque `get_emails_tool` a sa ligne dans `agent_treatments` (scellée), chaque
  tour sa ligne dans `agent_decisions`, aucun `agent_effects` — aucune action,
  que des lectures ; 34 lignes `email_digest` dans `token_usage_logs` (8 + 5 + 16
  + sonde), reprises dans le `node_breakdown` du tour et dans le résumé agrégé
  envoyé au flux SSE au token près (l'écart avec la somme des lignes est
  l'extraction des boucles ouvertes, filée sous son propre run — par
  conception). Deux défauts de CONTRAT trouvés par la même lecture : la même
  demande listait la boîte de réception en ReAct (`in:inbox`) et « tout sauf
  envoyés et brouillons » en pipeline (`-in:sent -in:draft`, la ligne du
  manifeste, tandis que le prompt de l'agent faisait de `in:anywhere` le
  défaut) ; et « résumé des 6 derniers de TLDR AI » en pipeline a demandé
  `max_results=20` sous `summary` — quinze condensés calculés pour six messages
  voulus, dont un refusé pour dépassement des 600 tokens de sortie. D'où la
  règle de portée et la règle de nombre sur les trois surfaces, et le plafond
  à 1 000 avec une consigne de brièveté (version de schéma 2 : les condensés
  en cache sous l'ancien prompt sont recalculés à la demande suivante).
- Corpus de citations : 48/48 et 2/2 (maison) contre 22/48 et 1/2
  (`mail-parser-reply` 1.36), voir la décision 7.
- Tailles (SLOC logiques) : `emails_tools.py` 1 634 → 1 228,
  `emails/catalogue_manifests.py` 753 → 595 (+ `get_emails_manifest.py` 215),
  `google_gmail_client.py` 985 → 910, `mixins.py` 673 → 670 ; les plafonds
  gelés baissent d'autant.

## Preuves

- `tests/unit/domains/connectors/clients/normalizers/test_email_message_contract.py`
  (les trois normaliseurs sur des charges réelles, corps texte, liens, la
  citation retirée à la frontière et l'interrupteur qui la laisse),
  `test_reply_trimming.py` + `reply_trimming_corpus.json` (48 corps, 2
  gardiens), `test_email_search_pagination.py` (jetons de page des trois
  clients, `headers_only`, garde SSRF Graph),
  `tests/unit/domains/agents/emails/{test_detail_levels, test_get_emails_tool_detail,
  test_digest}.py`, `tests/unit/domains/agents/display/test_email_card_digest.py`,
  `test_apple_email_client.py` (réponse construite depuis le producteur, fil
  `In-Reply-To`), les gardes de vocabulaire LLM, de famille de clés, de
  couverture des métriques, de placeholders de prompt, de parité des
  fournisseurs, de routes de dépense, de taille de fichier.
- `task emails:corpus:measure` (scores ci-dessus, datés).

## Non traité

- Le condensé calculé à l'arrivée du message (réveil push ADR-261) : une
  suite possible, non engagée.
- Le condensé de FIL (plusieurs messages en un) : le niveau `summary` condense
  par message ; la synthèse d'un fil reste au modèle du tour.

## Amendement 2026-09-30 — le niveau décide de ce que lit le MODÈLE, jamais de ce que dessine la carte

**Constat, reproduit dans le conteneur `lia-api-dev`.** Une liste demandée en
`detail=metadata`, ce que le manifeste, le planificateur et le prompt de
l'agent prescrivent pour « mes derniers e-mails », dessinait des cartes vides.
Leur « Voir plus » ne portait que les destinataires, sans corps, et aucune
pastille de pièce jointe. Deux causes :

1. **Le modèle et la carte lisaient la même charge.** Retirer le corps au
   modèle le retirait aussi de la carte.
2. **La recherche Gmail lisait chaque résultat en `format=metadata`**, sans
   parties MIME. `headers_only` était « accepté pour la parité » et ignoré.
   Les pièces jointes ne pouvaient pas être extraites, alors que le manifeste
   promettait `attachments` à ce niveau.

**Décision.**

- **Chaque niveau lit les messages en entier.** `search_emails` de Gmail
  respecte `headers_only` comme IMAP : sans lui, chaque résultat est lu en
  `format=full`, avec toujours une requête par résultat. La clé de cache de la
  recherche nomme ce format, et `use_cache=False` atteint aussi la lecture de
  chaque résultat. Un client DÉCLARE si ses résultats sont déjà des messages
  complets (`EmailClientProtocol.SEARCH_HITS_ARE_WHOLE` : Gmail et IMAP oui,
  Graph non, car sa liste sélectionne `bodyPreview` et n'étend pas les pièces
  jointes). `get_emails_tool` ne relit jamais un message complet : N+1
  requêtes Gmail à tous les niveaux, contre 2N+1 auparavant en `full`. La
  garde de parité exige que chaque `ClassVar` d'un protocole soit posé par
  chaque client.
- **Un corps retenu voyage hors de la charge.** Le niveau le range sous
  `FIELD_DISPLAY_ONLY`. `create_registry_item` le déplace dans
  `RegistryItemMeta.display` AVANT toute copie de la charge (données
  structurées, magasin de contexte, `$steps`). Aucune projection vers le
  modèle ne lit `meta`, le recensement l'a vérifié chemin par chemin : boucle
  ReAct, téléphone, outils de contexte, références du pipeline, résumé de
  réponse. Les rendus de cartes lisent l'item par `card_payload`
  (`data_registry/card_payload.py`), qui fusionne ces champs sur la charge.
  La carte est inchangée : elle lit `body`. En `full`, le corps servi suffit
  et rien n'est dupliqué.
- Même règle en `summary` : une carte condensée dessine le condensé ET le
  message sous « Voir plus ».
- **L'invariant est central.** Un validateur de `RegistryItem` sort
  `FIELD_DISPLAY_ONLY` de TOUTE charge, quel que soit le constructeur :
  fabrique de formateurs, candidats réhydratés d'une référence. Il ne mute
  jamais le dictionnaire reçu. `create_registry_item` retire en plus la clé du
  dictionnaire SOURCE, parce que les données structurées en copient les items.
- **Une référence résolue (« ouvre le deuxième ») garde la carte entière.** Le
  chemin normal réassocie la référence à l'élément du registre, `display`
  compris. La revue à froid a trouvé les deux replis, qui dessinent depuis les
  éléments résolus eux-mêmes : ils portent désormais leurs champs d'affichage
  sous `FIELD_DISPLAY_ONLY` (`context_resolution_service._resolved_payload`),
  une clé que le résumé pour le modèle et `to_llm_context` ignorent (préfixe
  `_`). `generate_html_for_resolved_context` et `_registry_from_resolved_context`
  les restituent à la carte.

**Effet de bord accepté (arbitrage du propriétaire).** Le briefing, le
heartbeat et la fiche Relations reçoivent eux aussi les messages Gmail
complets : plus d'octets, aucune requête en plus. Aucun ne lit le corps, et la
radio demande déjà `headers_only`.

**Non traité, dit.** La carte, texte du corps compris (tronqué à
`EMAILS_BODY_MAX_LENGTH`), fait partie de la réponse enregistrée. L'historique
ReAct la relit brute au tour suivant, comme toute carte et comme en `full`
depuis toujours. La retirer serait retirer du contexte au modèle, ce qui est
une décision à part.

**Preuves.** `tests/unit/domains/agents/emails/test_withheld_body_reaches_the_card.py`
(aucune charge ni projection ReAct ne porte le corps ; la carte le dessine,
après un aller-retour de checkpoint, dans un groupe corrélé, pour une
référence résolue et ses deux replis ; les trois vrais normaliseurs Gmail,
Graph et IMAP, de la recherche à la carte),
`test_get_emails_tool_detail.py` (une seule lecture pour les trois niveaux),
`test_detail_levels.py`, `tests/unit/connectors/test_google_gmail_client.py::TestSearchHitFormat`,
`test_provider_parity_contract.py::test_client_sets_every_declared_class_attribute`.

## Amendement 2026-10-13 — une requête que Graph accepte, et l'identifiant IMAP porte son dossier

**Constats.**

1. **Outlook abandonnait la recherche.** La traduction produisait un `$search`
   (expéditeur, objet, mots) ET un `$filter` (dates, lu/non lu, pièce jointe).
   Graph refuse de les combiner sur `/messages`, et le client supprimait le
   `$search` — le critère même qui nomme le message. Mesuré en production
   (lecture seule, sept jours, le 2026-10-13) : 5 recherches tronquées ainsi
   sur 626 recherches Outlook réussies. « Les mails non lus de Marie »
   listaient tous les mails non lus ; la fiche Relations, qui interroge
   `from:<adresse> after:<date>`, listait tous les mails reçus depuis la date
   comme échangés avec la personne.
2. **Un `$filter` accompagné d'un `$orderby` doit être MENÉ par la propriété
   de tri** (règle documentée, `InefficientFilter` sinon). La production a
   toléré `isRead eq false` seul (aucune erreur sur 626 recherches) ; la
   traduction suit désormais le contrat documenté plutôt que cette tolérance.
3. **Un UID IMAP ne nomme un message que dans UN dossier** (RFC 3501).
   L'identifiant Apple était l'UID nu, et chaque lecture commençait par
   l'INBOX : lire, mettre à la corbeille ou télécharger une pièce jointe d'un
   message listé hors de l'INBOX pouvait atteindre le message de l'INBOX
   portant le même numéro, et le transfert lisait l'INBOX seule.

**Décision.**

- **Une seule requête, celle que Graph accepte**
  (`normalizers/graph_mail_query.py`) :
  - rien à chercher → un `$filter` mené par la date de tri
    (`receivedDateTime ge 1900-01-01T00:00:00Z` quand aucune date n'est
    demandée) ;
  - seule une adresse d'expéditeur exacte à chercher, à côté d'une
    condition → le même `$filter` (`from/emailAddress/address eq`, forme
    documentée) : l'expéditeur, les dates et l'état de lecture sont tous
    appliqués par le serveur ;
  - sinon → un `$search` portant tout ce que KQL documente
    (`from`/`to`/`cc`/`subject`, les mots, `hasAttachments:true`).
- **Ce que la requête ne peut pas porter est vérifié sur chaque message de la
  page** : à côté d'une recherche, les dates (KQL ne documente aucun
  intervalle) et l'état de lecture (KQL n'en a pas) ; l'étoile — le drapeau
  d'Outlook — dans tous les cas, faute de forme documentée.
- **Une page amincie le DIT.** `set_aside_on_page` (champ partagé
  `FIELD_SET_ASIDE_ON_PAGE`, écrit par le client, lu par les outils) compte
  les messages écartés. `get_emails_tool` et `list_mailbox_drafts_tool` le
  publient au modèle, même sur une page vide, et leurs manifestes l'annoncent :
  `next_page_token` peut en tenir d'autres. Une continuation relit ses
  conditions dans la requête qu'on lui redonne, comme Gmail relit son `q`.
- **Les dates sont celles de la propriété de tri.** La liste des brouillons
  trie, filtre et affiche la dernière sauvegarde. `before:` exclut le jour
  nommé, comme Gmail et `BEFORE` d'IMAP. Une date illisible est refusée
  plutôt que d'élargir la recherche en silence ; une date ISO est lue comme
  son jour, des secondes Unix comme un instant (forme documentée par Gmail).
- **L'identifiant d'un message IMAP porte son dossier**
  (`normalizers/imap_handles.py`) : l'UID, et, hors de l'INBOX, une empreinte
  du nom du dossier — jamais le nom lui-même, qui est une étiquette de la
  personne alors qu'un identifiant passe dans les journaux (ADR-317). La
  lecture sélectionne le dossier dont le nom porte cette empreinte
  (`apple_imap.select_message_folder`) : lecture, corbeille, pièce jointe et
  transfert ne devinent plus le dossier. Un UID nu reste l'INBOX, ce que
  signifiaient les identifiants déjà émis. La poignée d'un brouillon
  (`mailbox_draft_id`, ADR-344) reste l'UID que connaît le dossier des
  brouillons, et son cache est oublié sous l'identifiant du message, plus sous
  celui du message de l'INBOX de même numéro.

**Non mesuré.** Le connecteur Outlook de dev est en erreur depuis le
2026-08-01 (sa reconnexion appartient au propriétaire) et aucun compte iCloud
n'est configuré. La traduction suit le contrat documenté de Graph, l'identifiant
IMAP la RFC 3501, prouvés par des tests contre un faux Graph et un faux serveur
IMAP à UID par dossier (`tests/unit/domains/connectors/clients/imap_fakes.py`).

**Non traité, dit.** Les opérateurs niés restent retirés de la requête (Graph
n'a pas de NOT utilisable). Un dossier personnel nommé par `label:` n'est pas
résolu en identifiant de dossier sur Outlook : la boîte de réception est lue.
La recherche `in:trash` d'iCloud vise un dossier nommé « Trash » : la corbeille
réelle est trouvée par son rôle pour l'ACTION, pas encore pour la RECHERCHE.
Traités le 2026-10-14 (amendement suivant).

**Preuves.** `tests/unit/domains/connectors/clients/normalizers/test_graph_mail_query.py`,
`test_microsoft_outlook_client.py::TestSearchEmails`,
`test_email_search_pagination.py::TestGraphPagination::test_a_continuation_checks_its_page_like_the_first`,
`test_outlook_drafts.py::TestRead`, `test_apple_message_handles.py`,
`tests/unit/domains/agents/emails/test_get_emails_tool_detail.py::TestAThinPageSaysSo`,
`test_list_mailbox_drafts_tool.py`.

## Amendement 2026-10-14 — le dossier nommé et la négation tiennent

**Constats.** Les trois restes du 2026-10-13 sont une même famille : une
recherche lue ailleurs, ou plus largement, que ce que disait la requête.

1. **Outlook lisait la boîte de réception** pour `label:<un dossier de la
   personne>` : la traduction ne connaissait que les dossiers bien connus.
2. **iCloud cherchait `in:trash` dans un dossier nommé « Trash »**, alors
   qu'iCloud garde sa corbeille dans « Deleted Messages ». Un nom qu'iCloud
   n'avait pas, ou écrit dans une autre casse, échouait en erreur interne, et
   `label:starred` sélectionnait un dossier « starred ».
3. **Les opérateurs niés étaient retirés** : « mes mails, pas la newsletter »
   listait la newsletter.

**Décision.**

- **Un dossier système est trouvé par son RÔLE, un dossier de la personne par
  son nom, sinon il est refusé** (`clients/mail_folders.py`, une seule
  résolution pour les deux fournisseurs). Le dossier de la personne est
  cherché par son chemin, sinon par son propre nom, sans tenir compte de la
  casse.
  - Deux dossiers du même nom : refus avec leurs chemins
    (`DISAMBIGUATION_REQUIRED`).
  - Un nom que rien ne porte : refus avec les dossiers qui existent
    (`NOT_FOUND`), en disant si la liste lue était complète.
  - Jamais la boîte de réception à la place : une recherche lue ailleurs
    répond à une autre question, et une recherche vide dit « rien » d'un
    dossier que personne n'a lu.
  - Le nom reste un attribut de l'exception, jamais son texte : c'est une
    étiquette de la personne, et le texte d'une exception atteint les journaux
    (ADR-317).
- **Outlook parcourt l'arborescence niveau par niveau** (`childFolders`).
  - Il lit des pages de la taille du fournisseur
    (`MICROSOFT_MAIL_FOLDERS_PAGE_SIZE`) et suit `@odata.nextLink`.
  - Il s'arrête à `OUTLOOK_MAIL_FOLDERS_WALK_MAX` dossiers (réglage, 500).
    C'est une lecture interne : jamais le plafond d'éléments que reçoit
    l'agent (`API_MAX_ITEMS_PER_REQUEST`), dont l'usage pour une pagination
    interne a déjà rendu un flux 40 fois plus bavard.
  - Un dossier bien connu n'appelle aucune liste.
- **iCloud résout le dossier dans sa session** (`apple_imap.search_folder`).
  - La corbeille, les envoyés, les brouillons, les indésirables et les
    archives sont trouvés par leur rôle RFC 6154 (`\Trash`, `\Sent`,
    `\Drafts`, `\Junk`, `\Archive`), avec les noms connus en repli.
  - Un dossier système que le serveur n'a pas est refusé
    (`MailboxFolderUnavailableError`).
  - `label:starred` est le drapeau, comme sur Graph.
- **Une négation tient.**
  - Un état devient sa clause contraire : `-is:unread` lit les messages lus,
    `-has:attachment` devient `hasAttachments eq false`.
  - Une date devient l'autre côté de son jour : `-after:X` équivaut à
    `before:X`.
  - L'étoile niée est le drapeau absent.
  - Une personne ou un objet nié est écarté sur la page sur Outlook, car KQL
    ne documente pas de NOT ; le compte écarté est publié
    (`set_aside_on_page`). Sur IMAP, il devient `NOT (…)`.
  - Un dossier nié est exclu en en lisant un autre.
  - Exclure le dossier même que la requête lit (`-in:inbox`) est refusé avant
    toute lecture. Gmail l'entend comme « partout sauf là » ; une recherche
    qui lit UN dossier ne peut pas le servir, et lire ce dossier répondait
    l'inverse de la question.
  - Un trait d'union à l'intérieur d'un mot n'est jamais une négation :
    `reply-to:` est un terme.
- **Le refus atteint le modèle sous un code typé.** `get_emails_tool` traduit
  en refus nommés (`MAIL_SEARCH_REFUSALS`, `refusal_for`), jamais en « erreur
  interne » :
  - un dossier introuvable ou ambigu ;
  - un dossier système absent ;
  - un refus de la requête (`ValueError` : date illisible, ou dossier à la
    fois lu et exclu).

**Non mesuré.** Comme le 2026-10-13, le connecteur Outlook de dev est en
erreur et aucun compte iCloud n'est configuré. Les preuves passent par un faux
Graph (parcours, pagination, borne) et un faux serveur IMAP (rôles, dossiers
sans drapeau, drapeau `\Flagged`).

**Non traité, dit.**
- IMAP n'a toujours pas de critère pour `has:attachment`, ni sous sa forme
  positive ni niée.
- Gmail répond vide à un libellé inconnu : sa recherche est native et ne
  refuse rien.
- `resolve_label_names_in_query`, qui devait résoudre les libellés imbriqués
  de Gmail, n'a aucun appelant sur les trois clients.

**Preuves.** `tests/unit/domains/connectors/clients/test_mail_folders.py`,
`normalizers/test_graph_mail_query.py::TestANegation`,
`normalizers/test_email_normalizer.py::TestANegation`,
`tests/unit/domains/agents/emails/test_get_emails_tool_detail.py::TestAFolderTheMailboxCannotResolveIsSaid`.

## Amendement 2026-10-22 — l'aperçu de Gmail est décodé au bord du client

**Constat.** Le vocabulaire `EmailMessage` promet un `snippet` en texte, sur une
ligne. Graph et IMAP le tenaient ; Gmail livre son aperçu échappé en HTML
(« J&#39;ai »), et les infolettres le rembourrent de caractères qui ne dessinent
rien. Mesuré le 2026-10-22 sur des aperçus Gmail réels : 4 sur 20 portaient des
entités ; sur quarante, 187 ZERO WIDTH NON-JOINER, 84 COMBINING GRAPHEME JOINER
et un BYTE ORDER MARK. La fiche Relations montrait les entités telles quelles,
et les cartes e-mail du chat les échappaient une seconde fois. Le seul lecteur
qui décodait, `GmailFormatter._extract_snippet`, n'avait plus d'appelant depuis
ADR-194.

**Décision.**

- L'aperçu de Gmail passe par `strip_html_to_line`, la seule ligne d'aperçu,
  déjà celle de Graph et d'IMAP. Il y passe une fois, au premier passage dans
  `GoogleGmailClient._normalize_message_fields`.
- Un message déjà marqué `_provider` (relu du cache) n'est jamais décodé une
  seconde fois : ce serait changer un « &amp; » que l'expéditeur a écrit en un
  caractère qu'il n'a pas écrit. Aucun lecteur ne décode plus l'aperçu ; les
  rendus l'échappent une fois.
- `strip_html_to_line` écarte une suite faite seulement de rembourrage
  invisible. Un mot qui en porte un à l'intérieur (un non-joiner persan) reste
  tel qu'il est écrit, et le ZERO WIDTH JOINER, qui tient les séquences
  d'emoji, n'en fait pas partie.
- `GmailFormatter._extract_snippet` est supprimé : du code mort qui décrivait
  un décodage que plus rien n'appelait.
- La longueur reste celle du fournisseur (décision du propriétaire : le
  plafond de la fiche Relations ne change pas). La fiche montre l'aperçu sur
  quatre lignes au lieu de deux.

**Transition.** Une entrée du cache Gmail écrite avant ce changement porte déjà
`_provider` : son aperçu reste échappé jusqu'à son expiration.

**Preuves.** `tests/unit/domains/connectors/clients/normalizers/test_email_message_contract.py`
(`TestTheSnippetIsPlainTextOnEveryProvider`, le rembourrage, le non-joiner
persan).
