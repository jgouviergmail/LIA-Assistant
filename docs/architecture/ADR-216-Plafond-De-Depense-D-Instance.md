# ADR-216 : une limite par utilisateur ne borne pas une instance

**Statut**: ✅ IMPLEMENTED (2026-08-06)
**Date**: 2026-08-06
**Contexte programme**: démonstrateur public libre (lot 1/8)

## Contexte

LIA dispose depuis 2026-03 de limites d'usage **par utilisateur** riches
(tokens, messages et coût, par cycle et absolus, plus un blocage manuel) :
`domains/usage_limits/`. Elles répondent à la question « combien ce compte
peut-il consommer ».

Le programme de démonstrateur public pose une question différente : **combien
cette instance peut-elle dépenser**. Aucune des limites existantes n'y répond,
et la vérification menée le 2026-08-06 sur toute la base de code n'a trouvé
aucun plafond global (`global`, `instance_wide`, `daily_total` : zéro
occurrence). C'est structurel, pas un oubli d'implémentation : N comptes × leur
quota est une dépense non bornée, et un démonstrateur donne un compte à chaque
visiteur. Un script qui ouvre des comptes draine le budget sans franchir la
moindre limite.

Le propriétaire a fixé le besoin en une phrase : **1 € par jour maximum**,
premier arrivé premier servi, puis « revenez demain ».

## Décision

Un **registre journalier d'instance** (`instance_daily_budget`, une ligne par
jour UTC) et un plafond composé de deux bornes.

### 1. L'autorité est PostgreSQL, l'écriture est un UPSERT atomique

`InstanceBudgetService.record_spend` fait un seul
`INSERT ... ON CONFLICT DO UPDATE` avec arithmétique de colonne, en imitant
`ChatRepository.create_or_update_token_summary`. Aucun SELECT → incrément en
Python → flush : sous concurrence, ce motif perd des écritures, et perdre des
écritures sur un compteur de dépense revient à ne pas avoir de plafond.

Mesuré en conteneur : trois runs concurrents de 0,30 € donnent exactement
`0.900000 €` et `run_count = 3`.

### 2. L'enregistrement est inconditionnel, la lecture est exacte

Le coût rejoint le registre **dans la transaction** qui persiste le résumé de
tokens (`TrackingContext._do_persist` → `record_run_summary`) : les deux
atterrissent ensemble ou pas du tout, donc le plafond ne voit jamais une vue
partielle. L'insertion passe par un **SAVEPOINT** : avaler une instruction en
échec sans savepoint empoisonne la transaction et emporte le commit de
l'appelant — on perdrait la comptabilité qu'on venait écrire.

L'enregistrement n'est **pas** conditionné à l'existence d'un plafond. Le
conditionner laisserait une fenêtre où un administrateur pose un plafond alors
que le compteur est muet : le plafond ne se déclencherait jamais. C'est
exactement le piège « réglage défini mais lu nulle part » (ADR-183). Le coût
est un UPSERT sur une ligne indexée par run, à côté des dizaines d'insertions
de logs de tokens déjà faites au même endroit.

La **dépense** est lue sans cache. Le **plafond** peut venir du cache (il
change rarement). Un budget approximatif n'est pas un budget.

### 3. La configuration ne peut que RESSERRER

Deux bornes, et la plus petite s'applique :

| Borne | Origine | Rôle |
|---|---|---|
| Déploiement | `INSTANCE_DAILY_BUDGET_EUR` (env) | ce que l'exploitant autorise |
| Opérateur | réglage d'administration (base) | ce que l'administrateur choisit à l'intérieur |

`resolve_ceiling` retourne le minimum des valeurs configurées, ou `None` quand
rien n'est configuré — auquel cas le registre n'est **pas** interrogé et une
instance qui n'utilise pas la fonctionnalité ne paie rien par message. Un
opérateur peut abaisser une borne de déploiement, jamais la relever ; la valeur
saisie est stockée telle quelle, et l'interface affiche **ce qui s'applique**
à côté, parce qu'un plafond affiché qui ne s'applique pas est une fiction.

### 4. Un seul point d'étranglement, pas trois copies

La vérification est composée **dans `UsageLimitService.check_user_allowed`**,
la porte unique que franchissent déjà le routeur de chat, la barrière SSE, le
WebSocket vocal et tous les jobs planifiés (`is_user_blocked_for_llm`). La
couverture est donc obtenue par construction plutôt qu'en recopiant le contrôle
dans chaque appelant — et en oubliant le suivant.

Deux propriétés en découlent, toutes deux testées :

- Le verdict d'instance est calculé **avant et en dehors** du cache par
  utilisateur. Un « autorisé » en cache continuerait de dépenser pendant tout
  le TTL après l'épuisement ; un « bloqué » en cache suivrait un utilisateur
  dans le jour suivant.
- Il est **indépendant de `usage_limits_enabled`**. Borner un compte et borner
  une instance sont deux protections distinctes ; les coupler désarmerait
  silencieusement celle-ci.

### 5. Le sens de l'argent : fail-closed, et diagnosticable

Les limites par utilisateur échouent **ouvertes** (base injoignable → on
laisse passer : au pire un message de trop). Une dépense d'instance inconnue
échoue **fermée** : au pire, c'est tout le budget. La différence de doctrine
est délibérée et documentée dans le code.

Un fail-closed muet étant indéfendable en exploitation, le log porte le **type**
de l'erreur — jamais son message, qui peut contenir du SQL et des valeurs.

### 6. Un refus d'instance n'est pas un quota personnel

« Vous avez atteint votre limite, contactez votre administrateur » est faux
deux fois quand c'est le déploiement qui est en pause. Un code d'erreur dédié
(`instance_budget_exhausted`) traverse les deux chemins — l'événement SSE et le
429 de couche 0 — et le frontend le localise dans les 6 langues. Le 429 porte
en plus un `Retry-After` calculé jusqu'au prochain minuit UTC : « revenez
demain » est un instant calculable, pas un espoir vague.

Le backend n'expédie jamais la phrase vue par le visiteur (règle systémique
i18n) ; il expédie un code stable.

### 7. Le magasin de réglages ne connaît pas ses clients

Le plafond opérateur est rangé dans `system_settings`, mais son administration
vit dans `domains/usage_limits/instance_budget_admin.py`. Placer ce service du
côté du magasin faisait importer le domaine budget par le magasin, ce qui
fermait un cycle d'imports (F009, détecté par le ratchet). La dépendance pointe
`usage_limits → system_settings` et jamais l'inverse.

Au passage, `system_settings` devient un **magasin générique typé** : chaque
clé est déclarée une fois (codec, valeur par défaut, cache) dans
`registry.py`, avec un assert de complétude au boot (doctrine ADR-085 — une
clé sans déclaration refuse de démarrer). Les deux clés existantes du panneau
de debug produisaient ~250 lignes de code dupliqué chacune ; le lot des
capacités administrables (STT, TTS, images, documents…) en aurait ajouté une
douzaine.

## Conséquences

**Positives**

- Une mauvaise journée coûte un montant connu, sur une instance publique
  comme sur une instance privée.
- Le registre répond aussi à « combien cette instance dépense-t-elle par
  jour », que quelqu'un la borne ou non.
- Le magasin de réglages typé rend l'ajout d'un réglage administrable trivial
  et impossible à oublier (assert de boot).

**Coûts assumés**

- Une lecture Redis du plafond opérateur par message (le réglage pourrait
  exister sans variable d'environnement : ne pas le lire ressusciterait le
  piège du réglage inerte).
- Une requête SQL de dépense par message **uniquement** quand un plafond est
  configuré.
- Un UPSERT par run.

**Non couvert (volontairement)**

- Aucune réservation avant appel : le plafond est constaté après coup, donc un
  run en vol peut franchir la borne de son propre coût. À 1 €/jour et ~1,5 ¢
  par session, le dépassement maximal est d'un run. Une réservation exigerait
  d'estimer le coût avant l'appel, donc d'inventer un chiffre.

## Preuves

- 22 tests du service (`test_instance_budget.py`), 9 du câblage
  (`test_instance_budget_enforcement.py`), 12 de l'administration
  (`test_instance_budget_admin.py`), 25 du registre typé
  (`test_registry.py`), 30 du magasin (`test_settings_store_service.py`),
  5 de la persistance (`test_tracking_context_instance_budget.py`), 4 de la
  barrière SSE, 6 du contrat 429.
- Frontend : 6 tests de la carte d'administration, 10 de la validation pure,
  4 du handler SSE, 3 du client 429.
- Runtime (conteneur dev, PostgreSQL réel) : sans plafond → autorisé sans
  requête ; 3 runs concurrents → 0,900000 € / 3 runs ; plafond 1 € à 0,90 € →
  autorisé (reste 0,10 €) ; à 1,10 € → bloqué (reste 0) ; point d'étranglement
  → `blocked_instance_budget` / `instance_daily_budget`.
- Migration `b665290a2fb4` appliquée, `alembic heads` à une seule tête.
- Gates : `task lint` vert (ratchets CC, cycles, taille de fichier, i18n),
  MyPy strict sur 1136 fichiers, 16824 tests backend, 5303 tests frontend.

## Alternatives écartées

- **Un plafond en mémoire par processus** : deux workers = deux budgets, et un
  redémarrage remet le compteur à zéro.
- **Un compteur Redis** : rapide, mais une éviction ou un `FLUSHDB` efface la
  dépense du jour sans trace ; l'argent mérite le magasin durable.
- **Réserver avant l'appel** (ce que faisait l'ancien process `public_demo`) :
  correct en théorie, mais suppose d'estimer un coût inconnu avant l'appel.
  Le constat après coup, avec un dépassement borné à un run, est plus honnête.
