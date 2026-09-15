# ADR-285 — Une réponse courte se demande sans raisonnement, et une famille de modèles se déclare une fois

- **Statut** : Accepté
- **Date** : 2026-09-12
- **Amende** : ADR-245 (le profil de raisonnement est dérivé — ici trois
  lecteurs le dérivaient chacun de leur côté), ADR-267 (« douze tokens
  demandés, douze tokens de réflexion, une réponse vide » — le même défaut,
  chez un autre fournisseur), ADR-244 (le catalogue est l'autorité sur ce
  qu'un modèle peut faire — le plafond de sortie DeepSeek le lisait dans un
  littéral), ADR-275 (une troncature est un refus, jamais un secours — le
  rappel l'envoyait telle quelle), ADR-272 (un seul lecteur de l'usage
  fournisseur — une neuvième copie facturait chaque rappel à un modèle sans
  nom), ADR-223 (tarif par plages UTC — `deepseek-flash` tarifé dans la
  graine ET par migration)
- **Périmètre** : `infrastructure/llm/reasoning/profiles.py`
  (`DEEPSEEK_THINKING_PREFIXES`, `is_deepseek_thinking_model`, échelle
  `none/low/high/max`), `providers/adapter.py` + `providers/deepseek_limits.py`
  (nouveau), `llm/structured_output.py`, `llm/usage_metadata.py`
  (`model_name_of_response`, `reasoning_tokens_of`), `core/llm_config_helper.py`
  (`short_answer_config`), `scheduler/reminder_notification.py`,
  `core/config/llm.py`, `core/constants.py` (`REMINDER_MESSAGE_MAX_TOKENS`,
  `FALLBACK_MODELS_DEFAULT`), migration `e9b5d7f3a2c4`, les deux graines de
  référence, les quatre `.env` du démonstrateur, `reasoningDocText.ts`

## Contexte

Le 2026-09-11 au soir, le slot `response` de production est passé sur
`deepseek-flash`, le nom que l'API DeepSeek donne désormais à son modèle
phare (DeepSeek-V4.1-Flash ; `deepseek-v4-flash` est un alias retiré qu'elle
accepte encore). Le lendemain, chaque rappel arrivait sous la forme « 🔔 » et
rien d'autre. Mesuré en production, trois fois sur trois, par le vrai chemin
de code sur la vraie configuration :

| Ce que le rappel demandait | Ce que le modèle rendait |
|---|---|
| `max_tokens=150` sur le slot tel que configuré | `output_token_details.reasoning = 150`, `content = ""`, `finish_reason = "length"` |
| le même appel à 2 000 tokens | 965 tokens de réflexion, puis 101 caractères de réponse |
| le même appel avec `thinking: disabled` | 42 tokens, réponse complète |

Le fournisseur active la réflexion **par défaut** (effort `high`) et la
compte **dans** `max_tokens` : un plafond de 150 tokens achète 150 tokens de
chaîne de pensée cachée et aucune réponse. Ce n'est pas propre à DeepSeek —
OpenAI, Anthropic et Gemini comptent aussi la réflexion dans le plafond — et
le rappel n'avait fonctionné jusque-là que parce que `response` était sur un
modèle qui ne réfléchit pas.

Derrière ce symptôme, quatre défauts, trouvés dans l'ordre :

1. **Un littéral qui dimensionne un budget qu'il ne peut pas connaître.**
   `{"temperature": 0.7, "max_tokens": 150}` dans le générateur du rappel
   depuis la v1.0.0, seul appelant du code à écraser `max_tokens` aussi bas.
2. **Une famille reconnue par trois copies privées d'un préfixe.** La règle de
   profil (`("deepseek-v4",)`), la branche V4 de l'adaptateur
   (`startswith("deepseek-v4-")`) et le détour `tool_choice` de la sortie
   structurée ne connaissaient pas `deepseek-flash` : aucune échelle publiée
   à l'administration (ce qui avait étonné le propriétaire en créant la
   ligne), un `none` explicite qui n'envoyait pas `thinking: disabled`, le
   plafond V3 de 8 192 appliqué à un modèle qui sort 384 K (mesuré sur
   `heartbeat_message` : 10 000 → 8 192 en silence).
3. **Aucune garde d'honnêteté.** La phrase de repli écrite n'existait que pour
   une exception ; un succès vide partait tel quel, et un succès coupé au
   plafond aussi.
4. **Une neuvième copie de la lecture des métadonnées d'usage.** Elle lisait
   `response_metadata["model"]` (clé que LangChain ne pose jamais) et
   `cached_tokens` (la clé brute, pas la forme normalisée) : chaque rappel
   était facturé à un modèle sans nom, au prix zéro, sans crédit de cache,
   et la ligne `token_usage_logs` de l'article 12 ne nommait aucun modèle.

## Décision

1. **Une réponse courte se demande sans raisonnement.** `short_answer_config`
   (`core/llm_config_helper.py`) prend la configuration du slot, résout son
   profil de raisonnement par la couture ADR-245 et, **là où le modèle peut
   s'arrêter de réfléchir** (`can_disable`, famille connue), déclare
   `ReasoningIntent(level="none")` et applique le budget de réponse
   (`REMINDER_MESSAGE_MAX_TOKENS`, une constante nommée). Là où le raisonnement
   est obligatoire ou la famille inconnue, le budget du slot reste : un plafond
   qui inclut la réflexion n'est pas un plafond sur la réponse. Mesuré sur
   Docker dev avec le modèle réel : 35 à 48 tokens de sortie, trois messages
   sur trois.
2. **Une réponse vide ou coupée est un refus, jamais un rappel.** Le générateur
   consulte `is_output_truncated` (ADR-275) et le texte : dans les deux cas la
   phrase de repli part, un avertissement `reminder_message_empty` nomme le
   modèle, la troncature et le compte de tokens de réflexion, et **la dépense
   qui a eu lieu est conservée** — un texte de repli ne dé-dépense rien.
3. **La famille DeepSeek à bascule se déclare une fois.**
   `DEEPSEEK_THINKING_PREFIXES = ("deepseek-flash", "deepseek-v4")` dans
   `reasoning/profiles.py`, lue par la règle de profil et exposée par
   `is_deepseek_thinking_model` à l'adaptateur et au détour de sortie
   structurée ; un garde refuse toute recopie du test de préfixe ailleurs dans
   `src/`. Ce que les trois noms partagent est la **forme de l'API** — bascule
   `thinking`, échelle d'effort — qui est ce qu'une famille décrit, pas une
   version : `deepseek-flash` est un autre modèle que `deepseek-v4-flash`, et
   les deux lignes de catalogue restent distinctes. L'échelle devient celle
   que le vendeur documente, `none/low/high/max` (`low` manquait ; l'API
   répond aussi 200 à `medium` et `minimal`, mais un silence n'est pas une
   déclaration — leçon ADR-278).
4. **Le plafond de sortie de la famille est la ligne de catalogue**
   (`providers/deepseek_limits.py`) : `max_output_tokens` quand la ligne est
   connue, 64 000 en repli pour un modèle que personne n'a semé.
5. **Le nom courant voyage par migration ET par graine.** La production ne
   rejoue jamais la graine de référence, donc `e9b5d7f3a2c4` insère la ligne
   `deepseek-flash` (`ON CONFLICT DO NOTHING` — une ligne curée reste), son
   tarif seulement là où aucun tarif administré n'est actif (le vôtre reste
   l'autorité), ses fenêtres UTC, et apprend `low` aux échelles déclarées de
   la famille — uniquement à une ligne qui déclarait exactement l'ancienne
   échelle complète. La graine porte la même ligne, le même tarif et le même
   `effective_from`, et un garde tient les deux sources égales. La provenance
   est `verified` : curée par une personne depuis la table du vendeur, comme
   la ligne de production — ni `declared` (défauts de colonne que la fenêtre
   de contexte refuse de croire), ni `imported` (la photo vendue des
   registres ne porte pas encore ce nom ; la rafraîchir est un acte de sync
   à part, à revoir avec `task llm:catalogue:preflight`).
6. **Une seule lecture des métadonnées de réponse.** `model_name_of_response`
   et `reasoning_tokens_of` rejoignent `usage_metadata.py` ; le rappel et
   `business_metrics` lisent là.

## Conséquences

- Un rappel sur un modèle qui réfléchit par défaut coûte ~40 tokens de sortie
  au lieu de 150 de réflexion perdue, et arrive avec son texte.
- `deepseek-flash` se configure depuis l'administration avec son échelle, son
  interrupteur, son plafond (384 K) et son tarif par plages ; les quatre `.env`
  du démonstrateur et les slots de la graine de configuration le nomment.
- `deepseek-v4-flash` reste dans le catalogue et fonctionne (alias accepté).
  Le défaut de repli `FALLBACK_MODELS` le garde encore : un garde refuse un
  modèle de repli qu'aucun registre vendu ne connaît, et la photo des registres
  ne porte le nom courant qu'après un rafraîchissement revu (voir « Non
  traité »).
- Le tableau des slots de `GETTING_STARTED.md` reste une extraction datée :
  il nomme l'alias retiré et le dit.

## Preuves

Sondes exécutées dans le conteneur de production (clé lue par le
déchiffrement de l'application, prompt synthétique) puis sur Docker dev par
le vrai chemin de code ; `task db:migrate:replay-check` vert ; cycle
downgrade/upgrade de la migration sur la base dev : 0/1 puis 1/1 tarif actif.

## Non traité

- Le rafraîchissement de la photo vendue des registres
  (`task llm:catalogue:fetch`) : il change des faits que trois tests pincent
  (un modèle OpenAI que les deux registres retirent désormais, une colonne
  `supports_vision` corrigée) et se revoit avec `preflight` contre chaque
  instance.
- Le tarif de l'alias retiré `deepseek-v4-flash` : le vendeur le sert au tarif
  de `deepseek-flash`, la graine garde l'ancien.
