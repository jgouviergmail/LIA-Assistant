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
