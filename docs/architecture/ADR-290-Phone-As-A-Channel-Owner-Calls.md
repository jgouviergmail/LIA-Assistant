# ADR-290 — Le téléphone est un canal : LIA appelle la personne sur un numéro VÉRIFIÉ, sans carte de confirmation, et ce qu'elle dit au téléphone devient son propre tour

- **Statut** : Accepté
- **Date** : 2026-09-16
- **Amende** : ADR-127 (un seul agent vocal, mais TROIS mandats — le mandat
  tiers y reste ce qu'il était, l'appel du titulaire et l'appel de
  vérification lui sont ajoutés par un override PAR APPEL ; le mot d'ordre
  « chaque appel est confirmé par une carte » ne vaut plus pour l'appel de la
  personne elle-même), ADR-263 (une politique `reversible` avec sa raison
  écrite est ce qui laisse `call_me` tourner sans personne devant l'écran —
  une routine « appelle-moi à huit heures » — et ce qui fait de la lecture
  d'un appel une consultation enregistrée sur la surface `phone_call`),
  ADR-276 (un run hors tour peut être PARLÉ par la personne : le tour relayé
  n'est ni une routine ni un ticket), ADR-179 (la synthèse de relais passe par
  le point d'étranglement structuré), ADR-184 (les bornes qu'un outil en
  direct impose sont publiées au modèle vocal), ADR-284 (chaque ligne que
  l'agent vocal lit vit dans un fichier de lignes, avec ses producteurs)
- **Périmètre** : `domains/telephony/{phone_numbers,identity,verification,
  errors,mandates,payload,synthesis_usage,budget,self_call_context,
  self_call_relay,owner_call,live_tools}.py` (nouveaux),
  `domains/telephony/{client,agent_prompt,availability,service,models,
  repository,reapers,router,schemas,return_synthesis}.py`,
  `infrastructure/scheduler/phone_relay_runner.py` (nouveau),
  `infrastructure/scheduler/out_of_turn_run.py` (`spoken_by_person`),
  `domains/agents/api/run_origin.py` (une origine VISIBLE),
  `domains/agents/tools/telephony_self_tools.py` (nouveau, `call_me`),
  `domains/agents/telephony/{live_tools,live_tools_router}.py` (nouveaux),
  `domains/users/models.py` (le numéro chiffré, sa date de vérification, le
  commutateur de contexte), trois migrations, quatre prompts et trois fichiers
  de lignes, `core/i18n_telephony.py`, `core/i18n_api_messages.py`, la section
  de réglages `TelephonyIdentitySection` et les surfaces du chat côté front
- **Spécification** :
  `docs/superpowers/specs/2026-09-16-phone-self-call-channel-design.md`

## Contexte

Le propriétaire a demandé deux choses que la téléphonie d'ADR-127 ne savait
pas faire, et une troisième qui en découle :

1. **Quand LIA appelle la personne ELLE-MÊME, aucune carte de confirmation.**
   La carte existe pour protéger un tiers qui n'a rien demandé ; la personne
   qui décroche est celle qui aurait cliqué « Valider ». Mais l'exception ne
   vaut que si le numéro est PROUVÉ être le sien : un nom du carnet ne prouve
   rien (deux fiches « Alex », un contact mal saisi), et un appel sans carte
   vers un inconnu porterait le contexte du titulaire à un étranger.
2. **Ce qui se dit au téléphone est un message de la personne.** Jusque-là un
   appel revenait dans le chat comme un compte rendu : une notification, des
   brouillons éventuels, rien d'autre. Aucune extraction de mémoire, aucune
   boucle ouverte, aucun journal — l'engin hors tour (`stream_instruction`)
   fixe `is_automated_source=True`, ce qui SAUTE toutes les extractions, et la
   politique `draft` est refusée hors présence, ce qui refuse le brouillon
   d'e-mail qu'on vient de dicter. Mesuré sur le code avant toute ligne.
3. **Le téléphone est alors un canal**, au même titre que le chat ou Telegram :
   la valeur propre en est l'initiative (une routine « appelle-moi le matin
   avec mon agenda ») et l'absence d'application ; le mode vocal in-app
   couvrait déjà « parler au lieu de taper ».

Trois décisions du propriétaire ont fixé le cadre : l'identité est un numéro
DÉCLARÉ dans une section de réglages puis VÉRIFIÉ par un appel qui lit un code
(jamais une reconnaissance par nom) ; sortant uniquement (la personne n'appelle
jamais LIA) ; les brouillons produits par le tour relayé se confirment dans le
CHAT. Deux précisions : réutiliser le MÊME agent ElevenLabs (la voix et le
modèle restent réglés en un lieu), et donner à l'appel du titulaire le contexte
riche du chat, avec des outils en direct si c'est faisable.

Le lot 0 a mesuré le fournisseur sur l'espace de travail de production (agent
et outil JETABLES, jamais l'agent réel) : la forme de la permission d'override
par appel (`platform_settings.overrides.conversation_config_override`), un
PATCH qui remplace par `false` tout booléen omis, la création d'un webhook tool
et son rattachement par `tool_ids`, et un DELETE d'outil qui exige
`?force=true` tant qu'un agent — même supprimé — le référence.

## Décision

1. **L'identité est un numéro déclaré, chiffré, puis vérifié par un appel.**
   `users.phone_number_encrypted`, `phone_number_verified_at` et
   `phone_rich_context_enabled` (une colonne par chose, classées dans la carte
   des données : deux SCRUBBED, une PREFERENCE, purgées à la suppression du
   compte). Le numéro est normalisé en E.164 par UN module
   (`telephony/phone_numbers.py`) et affiché ENTIER dans la section — un
   numéro masqué ne laisse pas voir la faute de frappe qui enverrait le
   contexte à un inconnu. Changer de numéro perd la vérification ; le
   re-déclarer à l'identique la garde. La vérification place un appel sous le
   mandat `VERIFICATION` qui lit un code à voix haute (`secrets`, TTL et
   compteur d'essais en Redis, famille `USER_RUNTIME`, comparaison en temps
   constant, verrou 429 après trop d'essais) ; la personne tape le code dans la
   section. Le code est LIÉ au numéro sur lequel il a été lu (la valeur Redis
   porte le numéro) : déclarer A, entendre le code sur A, passer à B, taper le
   code ne vérifie pas B — le code est annulé, et la sonde « en attente » le
   dit à la page. Un appel de vérification compte dans le même plafond
   horaire que tout appel payant (`TELEPHONY_RATE_LIMIT_PER_HOUR`) : une
   session volée ne fait pas sonner un numéro arbitraire à volonté. Une
   identité n'est jamais déduite d'un nom : le troisième outil
   (`place_phone_call`) REFUSE désormais de composer le numéro vérifié du
   titulaire (`callee_is_the_user`), pour que l'appel « à soi-même » ne passe
   jamais par la carte du tiers.
2. **Un agent, trois mandats, rendus côté serveur.** `mandates.py` déclare par
   `CallKind` (`THIRD_PARTY`, `SELF`, `VERIFICATION`) ce qu'un appel dit et
   sait ; un kind sans mandat refuse le boot (ADR-085). Les deux nouveaux
   mandats voyagent dans `conversation_config_override` (prompt et premier
   message — rien d'autre depuis la seconde mesure réelle, voir plus bas) —
   l'agent provisionné garde le mandat
   tiers CUIT, et la permission d'override entre dans l'empreinte de
   configuration, si bien qu'un connecteur activé avant ce lot est re-synchronisé
   AVANT que le titulaire soit composé ; pour un override la synchronisation
   est OBLIGATOIRE (`agent_sync_failed`), parce que composer quand même
   servirait au titulaire les règles de l'étranger. Le prompt est rendu par
   `str.format` ici, jamais laissé à la substitution `{{…}}` du fournisseur :
   le garde des placeholders prouve chaque clé, et un `{{x}}` dans un objet
   d'e-mail est neutralisé avant d'entrer.
3. **`call_me` est un outil `reversible` avec sa raison, et il n'est offert
   qu'à un numéro vérifié.** Aucune carte, PAR CONSTRUCTION : la personne qui
   confirmerait est celle qui décroche, et raccrocher défait l'acte. La même
   politique est ce qui laisse une routine le planifier sans personne devant
   l'écran (ADR-276). Le contexte de l'appel est construit par
   `self_call_context.py` sous un budget de tokens, section par section dans un
   ordre déclaré (mémoires, agenda, rappels, boucles ouvertes, derniers
   échanges — le constructeur de mémoire est PASSÉ par l'outil, parce qu'il
   vit dans `agents` que `telephony` n'importe pas), la coupe dite, chaque
   lecture enregistrée sur la surface `phone_call` ; la personne le coupe d'un
   commutateur. `availability.py`, qui ouvre le CALENDRIER depuis le chemin de
   composition, a été reclassé : il était déclaré « pas une lecture ».
4. **Le transcript d'un appel du titulaire est relayé comme SON tour.** La
   synthèse de relais (chokepoint structuré, road `CALLER`, comptable
   `synthesis_usage.py`) rend `owner_confirmed`, `relay_message` et un résumé
   ; si la personne n'a pas confirmé être elle-même, rien n'est relayé. Le
   runner (`phone_relay_runner.py`, dans `infrastructure/scheduler` pour ne pas
   fermer le cycle `agents ↔ telephony`) exécute `stream_instruction` en mode
   `spoken_by_person` : source NON automatisée, extractions de mémoire,
   journaux et psyché selon les préférences, origine `phone_call` VISIBLE
   (`RunOrigin.hidden=False` — un message archivé porte le tampon d'origine
   sans le tampon caché, et le chat dessine le badge « dit au téléphone »).
   Exactement-une-fois et sûreté au crash : la ligne d'outbox passe en
   `RELAYING` AVANT le tour, se règle par mise à jour conditionnelle
   (`mark_relay_delivered` / `mark_relay_fallback`), et le faucheur de
   notifications rend à `PENDING` toute ligne `RELAYING` plus vieille que
   `TELEPHONY_RELAY_MAX_AGE_MINUTES`. Une conversation occupée est réessayée
   puis notifiée ; une question HITL pendante, un quota bloqué ou un échec
   deviennent une notification qui DIT pourquoi (`RelayOutcome`, dix valeurs
   depuis la seconde mesure réelle,
   comptées, stockées dans `notification_payload.relay_outcome`, dessinées
   sur la liste des appels). Un tour qui a tourné envoie un push, et rien
   qu'un push (ses lignes sont déjà dans le chat) : la personne qui vient de
   raccrocher ne regarde pas forcément l'application. Les brouillons que le
   tour produit attendent dans le chat (`waiting`), où la personne les
   confirme — dessinés en `lia-card` comme ceux du chat, parce que
   `card_surface()` lit la VISIBILITÉ de l'origine (un ticket est caché, un
   tour relayé ne l'est pas), non sa seule présence.
5. **Des outils en direct pendant l'appel, derrière un drapeau, en lecture
   seule, sur un appel du titulaire ACTIF** (`TELEPHONY_LIVE_TOOLS_ENABLED`,
   off par défaut). L'allowlist est UNE déclaration
   (`agents/telephony/live_tools.py` : nom de registre, section de la surface
   `phone_call`, paramètres exposés) vérifiée au boot — un outil `search` ou
   à politique `read` explicite, jamais le repli `readonly` où siège le bac à
   sable ; chaque paramètre exposé existe sur le manifeste ; chaque outil a sa
   ligne de description. Les webhook tools sont créés dans l'espace du
   fournisseur une fois par connecteur, remplacés à toute dérive de leur
   empreinte (libellé, hôte, secret tourné), supprimés à la désactivation
   après l'agent qui les référençait, et rattachés À L'AGENT le temps de
   l'appel du titulaire (la seconde mesure réelle a réfuté le rattachement
   par appel, voir plus bas) : rattachés avant que le titulaire soit composé,
   détachés quand son appel se termine, et détachés encore par le chemin de
   composition avant tout appel tiers ou de vérification si un webhook n'est
   jamais venu — le connecteur se souvient de l'état de l'agent
   (`live_tools_attached`), et le prompt du tiers nomme tout outil de
   recherche rattaché comme REFUSÉ sur son appel. Le
   rappel `POST /telephony/tools/{name}` n'a pas de session : il n'ouvre que
   pour un appel `SELF` en ligne et plus jeune que le délai de péremption des
   appels (le plafond de durée est celui du portail, l'application ne peut
   pas le lire), avec
   un jeton DÉRIVÉ du secret de webhook du connecteur (HMAC, jamais le secret
   lui-même), pour un outil allowlisté ET offert par les capacités, dans le
   budget de recherches de l'appel ; tout refus sauf un mauvais secret sur un
   appel connu se lit « introuvable ». L'outil tourne sur un runtime
   synthétique pour la personne, ses arguments validés par SON schéma d'appel,
   borné SOUS le délai du fournisseur pour que l'agent entende une phrase et
   non un timeout, son résultat projeté comme la boucle ReAct le projette
   (ADR-286, la coupe dite), sa consultation collectée sous un collecteur que
   la route ouvre elle-même — un rappel ne tourne dans aucun tour.

## Conséquences

- Un appel de LIA à la personne n'a plus de carte, et la garantie tient à une
  seule couture : `TelephonyIdentityService.verified_number`. Tout ce qui est
  moins qu'un numéro vérifié est un refus localisé qui pointe la section.
- La voix, le modèle et le format audio restent réglés en un lieu (un agent) ;
  rien du contexte du titulaire n'est jamais cuit dans un agent qui appelle
  aussi des étrangers.
- Le chat garde une trace fidèle : le message relayé porte le badge
  téléphone, la liste des appels dit le mandat et le verdict du relais, le
  bandeau d'appel dit « LIA vous appelle ».
- Quinze réglages nouveaux, tous dans `core/constants.py`, `core/config/
  telephony.py` et les quatre `.env` applicatifs ; les quatre `.env` du
  démonstrateur gardent leur seul commutateur `TELEPHONY_ENABLED=false`, comme
  pour les vingt-trois réglages de téléphonie qui les précèdent.
- Trois métriques et quatre panneaux de plus sur le tableau 24
  (`telephony_relay_total`, `telephony_live_tool_calls_total`,
  `telephony_live_tool_duration_seconds`).

## Revue à froid (2026-09-16)

Six défauts trouvés en relisant l'ensemble livré, chacun corrigé avec son test :

1. un code lu sur A vérifiait B (le code n'était lié à aucun numéro) ;
2. un chiffre non ASCII tapé (clavier arabe) faisait lever `compare_digest`
   en 500 au lieu d'un refus ;
3. un second « Rappeler » pendant que le premier appel sonne effaçait le code
   en cours de lecture ;
4. une carte de brouillon issue du tour relayé se dessinait en Markdown dans
   le chat (`card_surface()` lisait la présence d'une origine, non sa
   visibilité) ;
5. un tour relayé qui avait répondu n'envoyait aucun push — la personne au
   téléphone ne l'apprenait qu'en ouvrant l'application ;
6. les derniers échanges arrivaient au modèle vocal avec leur balisage
   (`lia-card`, Markdown) ; ils sont aplatis par le module qui aplatit déjà
   les commentaires de ticket, passé en argument comme le lecteur de mémoire.

Et trois écarts sans défaut visible : aucune borne sur les départs d'appel de
vérification (plafond horaire ajouté), une section « agenda » comptée comme
ouverte quand la personne n'a pas de calendrier (plus rien n'est consigné),
et « appelle-moi dans une heure » routé vers un appel immédiat (le prompt et
le manifeste renvoient désormais à un rappel ou une routine).

## Première mesure réelle (2026-09-16, production) — le modèle vocal est celui du portail

Le premier appel de vérification réel a été REFUSÉ (`agent_sync_failed`) : la
synchronisation obligatoire de l'agent (la permission d'override entre dans
l'empreinte) envoyait le `llm` qu'un réglage épinglait, et le fournisseur
FUSIONNE un PATCH avec ce que l'agent stocke déjà — ici `gemini-3.6-flash` +
`reasoning_effort: minimal`, choisis sur le portail ElevenLabs — puis valide la
paire : « Not supported reasoning effort ». Le mandat tiers n'en souffrait pas
(sa synchronisation est best-effort et l'appel partait sur l'ancienne
configuration), les deux mandats à override en mouraient. Reproduit sur un
agent jetable. **Décision du propriétaire : le modèle du voix-agent est celui
configuré sur le portail, pour l'agent.** `TELEPHONY_AGENT_LLM_MODEL` est
SUPPRIMÉ (réglage, constante, quatre `.env`), LIA n'envoie ni `llm` ni
`reasoning_effort`, à la création comme à la synchronisation, et l'empreinte ne
les connaît plus ; un agent neuf démarre sur le modèle par défaut du fournisseur
jusqu'à ce que la personne le choisisse sur le portail (runbook). Ce qui reste
mesuré et vaut pour tout bouton du fournisseur : un PATCH partiel hérite de ce
que le portail a stocké, et la paire est validée — n'épingler un bouton que
si l'on épingle ses voisins.

## Seconde mesure réelle (2026-09-16, production) — le périmètre de LIA, et l'appel qui mourait au décroché

Une fois le modèle rendu au portail, l'appel de vérification réel a RÉUSSI
(19 s, le code lu deux fois). Les deux appels réels du titulaire qui ont suivi
sont MORTS AU DÉCROCHÉ (0 à 1 s) : le fournisseur a terminé la conversation
sur « Tool IDs not attached to this agent » — `tool_ids` est accepté dans la
PERMISSION d'override (mesuré sur agent jetable, lot 0) et REFUSÉ dans
l'override d'un appel réel. Et la personne a lu « Quelqu'un d'autre a répondu
à mon appel » : le statut `FAILED` d'un appel tombait dans `NOT_OWNER`, le
seul verdict prévu pour un appel sans parole.

Trois décisions, la première du propriétaire :

1. **Ce que l'agent vocal a dans la voix appartient au portail** (amende la
   première mesure) : la langue, la voix, le format audio et le plafond de
   durée rejoignent le modèle — administrés sur le portail ElevenLabs, sans
   relancer l'application. Six réglages supprimés (réglage, constante, quatre
   `.env`) : `TELEPHONY_AGENT_TTS_MODEL_ID`, `TELEPHONY_AGENT_VOICE_ID`,
   `TELEPHONY_AGENT_AUDIO_FORMAT`, `TELEPHONY_MAX_CALL_DURATION_SECONDS`,
   `TELEPHONY_SELF_CALL_MAX_DURATION_SECONDS`,
   `TELEPHONY_VERIFICATION_CALL_MAX_DURATION_SECONDS`. **L'application ne
   passe que ce qui lui est propre** : le nom, le prompt, le premier message,
   les outils système, le contrat `data_collection`, la permission d'override
   pour les deux champs qu'un mandat rend par appel — et l'empreinte ne couvre
   que cela, si bien qu'un changement sur le portail ne déclenche jamais de
   synchronisation et qu'une synchronisation n'écrase jamais le portail. Le
   prompt du titulaire ne cite plus de plafond en minutes ; là où le code
   lisait le plafond du mandat (l'âge d'un appel vivant pour le rappel d'outil,
   la vie du budget de recherches), il lit le délai de péremption des appels
   (`TELEPHONY_STALE_CALL_TIMEOUT_MINUTES`).
2. **Les outils en direct sont rattachés à l'AGENT, le temps de l'appel du
   titulaire** (`set_agent_tool_ids`, un PATCH du seul `tool_ids` du prompt,
   fusionné par le fournisseur). Rattachés avant de composer le titulaire,
   détachés à la fin de son appel par le chemin de retour (best-effort), et
   détachés encore par `_arm_live_tools` avant tout appel tiers ou de
   vérification si le connecteur dit qu'ils y sont toujours
   (`live_tools_attached`, un dict neuf, commité avant la ligne de
   composition). Un rattachement refusé par le fournisseur laisse partir
   l'appel SANS outils, le prompt disant « aucune recherche en direct » — un
   appel sans recherche vaut mieux qu'un prompt qui promet une recherche que
   l'agent ne peut pas faire. Et le prompt du tiers nomme tout outil de
   recherche qu'il trouverait rattaché comme réservé aux appels du titulaire
   et refusé sur le sien : la défense de fond reste le rappel lui-même, qui
   n'ouvre que pour un appel `SELF` vivant.
3. **« Personne n'a répondu » n'est pas « quelqu'un d'autre a répondu ».**
   `RelayOutcome` gagne `UNANSWERED` (pas de réponse, messagerie) et
   `CALL_FAILED` (la ligne a échoué) — dix valeurs, chacune avec sa phrase en
   six langues, son libellé sur la liste des appels et sa tonalité (une ligne
   qui échoue est destructive, une absence de réponse est une fin normale).

## Troisième mesure réelle (2026-09-16, production) — l'appel qui a marché, et ce qu'il n'a pas su

Le troisième appel du titulaire a tourné de bout en bout : 179 s, quatre
recherches en direct (agenda ×3, tâches ×1, 478 à 783 ms), outils détachés au
webhook, transcript relayé en tour de la personne (38 s), `answered`. Deux
manques, lus dans la conversation chez le fournisseur (arguments et tailles
seulement) : **aucune porte vers les e-mails ni la mémoire** — l'allowlist
tenait trois outils — et **le rendez-vous de dimanche oublié** : la recherche
« ce week-end » avait renvoyé QUATRE événements et l'agent vocal n'en a vu
qu'un (« Only 1 of 4 items are shown »), le JSON brut d'un événement Google
(id, lien, participants, rappels, couleur) mangeant le budget de 800 jetons
à lui seul.

## Lot 8 — le téléphone lit tout ce que le chat lit (décision du propriétaire, 2026-09-16)

« Pas d'action mutable par téléphone, pour l'instant. Mais que l'assistant
puisse contextualiser avec ma mémoire, mes mails, mon agenda, mes tâches, mes
rappels, la météo, mes contacts, mes fichiers, les lieux… tous les services,
avec leurs outils non mutables. Comptabiliser, à la restitution, la
consommation cumulée. Et que je puisse activer ou désactiver les domaines pour
mes appels personnels. »

1. **L'allowlist devient une RÈGLE sur le catalogue** (`derive_live_tool_specs`) :
   tout outil qui ne fait que lire (catégorie `search` ou politique `read`
   explicite — jamais le repli `readonly` où siège le bac à sable), qui n'est
   pas un outil `system` (ceux-là répondent dans un tour), qui tourne hors de
   l'exécuteur du pipeline, dont le domaine est offert par le téléphone
   (`domains/shared/phone_domains.PHONE_DOMAINS`, le vocabulaire du registre,
   partagé par les deux moitiés qui ne peuvent s'importer) et dont les
   paramètres obligatoires se disent à la voix (un identifiant — par
   `semantic_type` ou par nom — cache son paramètre ; un outil dont le
   paramètre obligatoire est un id reste dehors). Mesuré sur le vrai
   catalogue : 55 outils sur 22 domaines. La mémoire n'a pas d'outil dans le
   chat (il l'injecte lui-même) : le téléphone gagne une recherche NATIVE,
   `recall_memories`, qui lit par le constructeur de profil du chat. La
   description fournisseur est la ligne vocale du fichier quand elle existe,
   sinon les propres mots du manifeste. Mesuré chez le fournisseur (agent
   jetable) : soixante outils créés et rattachés d'un PATCH sans plafond ;
   un paramètre `array` exige des `items` portant leur description ; la
   création est concurrente sous une borne, parce que soixante créations
   séquentielles retiendraient la composition une minute.
2. **Une projection pour la voix** (`agents/telephony/voice_projection.py`,
   branchée par un crochet `reshape` sur le bloc ADR-286) : identifiants,
   liens et détails de câblage retirés, une valeur imbriquée dite par sa
   forme parlée (`formatted`, `name`…), une liste d'enregistrements comptée,
   un texte long coupé — PUIS la pagination par item. Quatre événements
   tiennent là où un seul passait ; le budget par défaut monte à 2 000 jetons
   dépensés en mots, et le nombre de recherches par appel à 40.
3. **Une dépense par appel** (`telephony/spend.phone_call_run_id`) : les
   recherches pendant l'appel (un `TrackingContext` ouvert autour de chacune,
   son callback sur la config du runtime synthétique — la leçon d'ADR-287 —,
   le tracker ambiant pour les clients Maps et embeddings), la synthèse après
   l'appel et le tour relayé dépensent sous UN run id dérivé de l'appel. La
   ligne `message_token_summary` que le compteur du chat lit déjà (unique par
   run id, cumulée par arithmétique de colonne) devient la facture de l'appel
   par construction : la bulle de la réponse relayée l'affiche, la liste des
   appels la porte (`usage`). Aucune colonne neuve : la clé de corrélation
   est le design. **C'est la facture de ce que LIA paie, et rien d'autre —
   par décision** (règle du propriétaire, 2026-09-16, `cost_bearers`) : le
   LLM vocal, la synthèse vocale, la reconnaissance et la ligne tournent sur
   la clé ElevenLabs de la personne et ne sont jamais comptés ni affichés.
   Mesuré sur un appel de 198 s à huit recherches : LIA 28 k jetons /
   0,0065 € ; le fournisseur 409 k jetons de LLM vocal, 2 079 crédits ≈
   0,41 $ sur le compte de la personne — vingt fois plus, et pas à nous de
   le compter.
4. **Les domaines à la main de la personne** : `users.phone_disabled_domains`
   (l'ensemble DÉSACTIVÉ, en JSONB, pour qu'un domaine offert plus tard soit
   actif par défaut — la parité est la règle, l'interrupteur l'exception),
   validé contre le vocabulaire partagé, publié avec l'identité
   (`disabled_domains`, `available_domains`), écrit par `PATCH
   /telephony/identity`, dessiné en un interrupteur par domaine dans
   *Téléphonie · Mon identité* (la mémoire porte son propre nom). Le chemin de
   composition ne rattache que ce que la personne a laissé, et le rappel
   relit ses interrupteurs sur SA ligne à chaque appel : un outil encore
   rattaché par un PATCH périmé répond « introuvable » sur un domaine coupé
   depuis. Tout est en lecture seule par construction ; le prompt du
   titulaire nomme les DOMAINES qu'il peut consulter, en mots, jamais
   cinquante noms d'outils.

## Lot 9 — la personnalité de l'assistant parle aussi au téléphone (question du propriétaire, 2026-09-16)

« Tu passes la personnalité de l'assistant dans le prompt de l'agent
téléphonique ? » Non, jusqu'ici : le prompt du titulaire portait une identité
fixe (« warm, efficient »), celui du tiers la sienne, alors que le chat et le
flux vocal chargent `PersonalityService.get_prompt_instruction_for_user` et le
tissent dans un bloc `<personality_profile>`. Désormais la composition lit
cette même instruction UNE fois, en best-effort (une voix au ton par défaut
vaut mieux qu'aucun appel), et la sert aux deux mandats : rendue côté serveur
dans le prompt du titulaire (`{personality_block}`, neutralisée comme toute
valeur, un scaffold « aucune personnalité configurée » sinon) et passée à
l'agent tiers en VARIABLE dynamique (`{{personality_profile}}`) — jamais cuite
dans l'agent, pour qu'un changement de personnalité ne demande ni
synchronisation ni re-provisionnement. Les deux prompts disent comment elle
s'applique : elle colore la manière de parler, jamais ce que l'agent peut
partager ou faire.

## Ce qui n'a PAS été mesuré

- **Un appel réel du titulaire sous la liste dérivée** (une recherche
  d'e-mail, un rappel de mémoire, la facture cumulée sur la bulle). Le
  rattachement au niveau de l'agent, soixante outils sur un agent et la
  projection pour la voix sont mesurés ; l'appel vivant qui les enchaîne ne
  l'est pas encore. Le lot 7 reste off par défaut pour cette raison.
- Le comportement du fournisseur face au champ `data_collection`
  `owner_confirmed` sur un appel tiers (attendu : vide) n'a pas été observé.

## Ce que ce n'est pas

- Pas d'appel entrant : la personne n'appelle jamais LIA.
- Pas de reconnaissance par nom : un contact « moi » ne vérifie rien.
- Pas de second agent vocal.
- Un outil qui dépense des jetons de modèle n'est pas admis dans l'allowlist
  tant que ce chemin ne publie pas de tracker ; les trois admis n'appellent
  aucun modèle.
