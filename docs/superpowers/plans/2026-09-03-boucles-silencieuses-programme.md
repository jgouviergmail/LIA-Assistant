# Programme « Trois boucles silencieuses » — plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task, INLINE (the owner forbids subagents on this programme). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que le push Google, l'apprentissage des habitudes et l'inbox de propositions produisent enfin un effet observable en production, sans baisser un seul seuil calibré et sans qu'aucune notification ne soit jamais comptée comme une activité humaine.

**Architecture:** Une cause commune (le reset de conversation efface toute clé Redis nommée par l'identifiant utilisateur) est traitée en premier par un registre de familles de clés à portée déclarée. La source « tour humain » devient `product_outcomes.channel = 'web'` (durable, colonne explicite) pour le rythme comme pour le seed du ledger. La présence en lecture (ouverture de l'application, pouce sur une notification) devient une quatrième source de rythme, opt-in. Le push cesse d'être une simple invalidation de cache : il réveille le heartbeat pour l'utilisateur concerné, sous l'éligibilité complète, et réindexe les dossiers Drive liés ; une source « Mail » opt-in par libellé Gmail rejoint les espaces RAG en miroir de la source Drive.

**Tech Stack:** FastAPI 0.135+, SQLAlchemy 2 async, Alembic, Redis 7 (redis.asyncio), APScheduler, LangGraph 1.x (inchangé), Next.js 16 / React 19, vitest, Playwright.

**Spec:** ce document est la spécification. Preuves et mesures : artefact « Trois boucles silencieuses » (2026-09-03) et mémoire de session `project_silent_loops_audit_2026_09_03.md`. Rien de ce qui suit ne re-dérive une mesure.

## État au 2026-09-03 (fin de session, RIEN N'EST COMMITÉ)

Les six lots sont **implémentés et verts en local**. Ce qui reste est
explicitement listé plus bas ; rien d'autre n'a été laissé de côté.

| Lot | État | Preuve locale |
|---|---|---|
| 0 — familles de clés Redis (ADR-260) | livré | registre + garde de complétude au boot + purge par famille ; `test_key_families`, `test_redis_key_family_guard`, `test_reset_purge`, `test_account_deletion_redis` |
| 1 — un seul tour humain durable | livré | `habits/human_turns.py` partagé par le rythme, les bornes et le seed ; garde d'asymétrie sur la récurrence |
| 3 — présence en lecture (flag OFF) | livré | `habits/presence.py`, endpoint 204/429, `PresencePing.tsx`, porte d'inactivité, intégration PostgreSQL deux workers |
| 4 — exploitation du push (ADR-261) | livré | file de réveil, pré-filtre publié, balayage élu leader sous éligibilité complète, `trigger=push` persisté et affiché, Drive → réindexation ciblée |
| 6 — source « libellé Gmail » (ADR-262, flag OFF) | livré | `mail_render` / `mail_sync` / `mail_source_service`, endpoints, reaper, UI et picker accessibles, 6 locales |
| 5 — honnêteté visible et clôture | livré | panneaux Grafana 09/13/18, amendements ADR-214 et ADR-238, ADR-260/261/262, `CLAUDE.md` + `AGENTS.md` |

**Portes passées en local (2026-09-03)** : `task lint:backend` (ruff, black,
mypy strict — 1355 fichiers), `task lint:frontend` (eslint + trois ratchets +
tsc non incrémental), `task lint:i18n` (parité 6 langues), `task lint:hygiene`,
`task lint:docs:preview` (0 lien mort, 0 chemin périmé, 0 orphelin, 0 fait
dérivé), `task test:frontend` (562 fichiers, 7005 tests),
`task test:backend:unit:fast`, ratchets métriques / taille / complexité (la
complexité a été ABAISSÉE : 331 → 330 fonctions ≥ CC 15, baseline reverrouillée).

**Chiffres des portes (2026-09-03, après la revue à froid)** :
`test:backend:unit:fast` **21 097 verts / 1 rouge** — l'unique rouge est `test_doc_audit_adr_link_guard`,
qui décide l'existence depuis l'**index git** : les fichiers créés dans cette
session ne sont pas stagés, et `task lint:docs:preview` (suivi + `git add -A`)
donne **0 chemin périmé**. C'est le comportement documenté : on stage, on ne
« corrige » pas. `tests/agents/` : **1 127 verts** (les 3 rouges d'alors n'étaient que
l'absence de Redis ; ils passent, 12 verts, une fois Docker rétabli).
`task test:frontend` : **7 015 verts / 563 fichiers**. `task test:markers` :
22 981 tests collectés, aucun orphelin. Couverture backend **71,37 %** pour un
plancher de 69 : la marge de 2 points imposée par la doctrine interdit de
relever le plancher, il reste donc à 69.

**Sept défauts trouvés par les portes, corrigés à leur source** :

1. `d9e0f1a2b3c4` était déjà l'identifiant d'une migration du 2026-08-08.
   Alembic levait `CycleDetected` — et la garde d'hygiène, qui indexait les
   révisions par identifiant, voyait « aucune révision » et PASSAIT. Migration
   renumérotée `a7c3e9b1d5f2`, garde durcie (doublon = échec, zéro tête =
   échec) et couverte par `test_check_code_hygiene_alembic_guard.py`.
2. `list_events(updated_min=…)` cassait le contrat de parité des fournisseurs
   (les autres calendriers ne savent pas filtrer sur « modifié depuis »). Le
   delta du réveil passe désormais par une méthode Google dédiée,
   `list_updated_events`, et la signature partagée est intacte.
3. `reindex_from_push` répondait `no_linked_folder` quand une source avait
   échoué : un verdict faux dans une métrique. Il répond `error`.
4. `rag_mail_sources` n'était pas classée dans `user_data_map.TABLE_RULES` —
   la garde de complétude l'a vu : une table non classée n'a **ni décision
   d'export ni décision de purge** au moment d'une suppression de compte. Elle
   est désormais `USER_CASCADE` / `ExportPolicy.FULL` avec sa raison écrite.
7. Le **compilateur React** a refusé la mémoïsation manuelle du sélecteur de
   libellé (une valeur dérivée d'une liste), le **ratchet a11y** a refusé
   l'association implicite `<label>` → radio, et le **ratchet de complexité**
   a refusé la page « espace » passée à CC 18. Les trois sont corrigés à la
   source, et le dernier a produit la factorisation qui manquait :
   `useSourceActions` (lier / délier / synchroniser + toasts, une fois pour
   Drive et pour Mail) et `useSpaceSources` (les deux listes, la porte
   d'instance, le sondage pendant une synchro). La page pose une question et
   rend ; les règles sont dans des hooks testables.
6. Le fixture du test de la page « espace » n'avait pas `mail_sources` : le
   **typecheck non incrémental** l'a vu (le champ est requis par
   `RAGSpaceDetail`). Complété, et le test couvre désormais la porte
   d'instance — la section n'existe que si le serveur déclare le drapeau.
5. La migration `f1a2b3c4d5e6` ne posait pas les **commentaires de colonnes**
   que les modèles déclarent (`last_history_id`, `mail_last_message_at`) : la
   comparaison structurelle modèles↔schéma du rejeu (F042) l'a vu. Les
   commentaires sont désormais dans la migration, et le schéma migré reste la
   source de vérité honnête.

### Revue adversariale à froid (2026-09-03, après les portes)

Relecture complète du code livré, fichier par fichier, contre les règles de
`CLAUDE.md` (back et front) — pas un simple déroulé de tests. Huit défauts de
plus, tous corrigés à leur source, tous couverts par un test :

| # | Défaut | Correction |
|---|---|---|
| 8 | La métrique des familles inconnues pouvait publier un identifiant en LABEL (seuls l'utilisateur et la conversation étaient neutralisés) — cardinalité non bornée **par construction** | tout segment de tête en forme d'identifiant devient `id_prefixed` ; test dédié |
| 9 | **Un compte qui ne vit que par la lecture** (pings + pouces) sortait en `skipped_no_activity` : les bornes d'activité ignoraient les pouces, et la présence n'a pas d'horodatage propre. C'était EXACTEMENT le profil que l'amendement ADR-214 visait | les pouces entrent dans les bornes ; la sortie précoce interroge le rollup durable ; 2 tests de service + contrat SQL |
| 10 | La phrase FRESH du prompt de décision était écrite **en dur dans un `.py`** (interdit par CLAUDE.md) | `prompts/v1/heartbeat_wake_fresh_prompt.txt` + `load_prompt_with_fallback` ; le module ne garde que l'événement, le test pinne le contrat |
| 11 | Le nom d'un document devient, avec la source Mail, un **sujet écrit par un tiers** — et il part dans un `Content-Disposition`. Ni le nom stocké ni l'en-tête n'étaient assainis (CRLF, guillemet, antislash, séparateurs) | assainissement aux deux bouts (l'en-tête profite aussi aux imports et aux réunions) ; 7 tests dont un sujet hostile |
| 12 | La carte de source révélait ses actions **au survol** (`opacity-0 group-hover`) : un focus clavier atterrissait sur un contrôle invisible — interdit par ADR-208 | la carte partagée passe sur `RowActions` (corrige Drive du même coup) ; 8 tests |
| 13 | Icône de titre de section en gris (règle propriétaire : une icône de titre porte la couleur du thème) | `text-primary` sur les deux sections |
| 14 | Le « ⋮ » du mobile ne nommait pas sa ligne (toutes les lignes se lisaient pareil au lecteur d'écran) | `common.actions_for` avec le nom de la source |
| 15 | Le plan demandait T3/T4 et T15/T17 **contre un vrai Redis** ; seuls des tests unitaires existaient | 6 tests d'intégration écrits : le reset garde l'apprentissage et enlève la conversation, une famille inconnue survit, la suppression de compte ne laisse rien, une tempête = un réveil daté du premier, deux balayages concurrents se partagent la file sans jamais servir le même utilisateur, le cooldown n'admet qu'un gagnant |

Deux vérifications ont conclu à un **faux positif** et sont consignées pour ne
pas être refaites : `except A, B, C:` sans parenthèses est valide en Python
3.14 (PEP 758), et l'avancement de l'ancre Gmail à la LECTURE (et non à la
décision) est exactement ce que fait déjà le tick — la symétrie est voulue.

Un point **hors périmètre, non corrigé** : `apps/web/src/components/spaces/SpaceCard.tsx`
porte la même violation `opacity-0 sm:group-hover` qu'ADR-208 interdit. Le
fichier n'appartient à aucun lot de ce programme ; à traiter à part.

**Reste à faire (dans cet ordre)**

- [x] `task db:migrate:replay-check` : **vert** une fois Docker remis d'aplomb
      par le propriétaire — chaîne rejouée depuis une base vide, cycle
      downgrade/upgrade de la dernière révision, équivalence structurelle
      modèles↔schéma et `alembic check` (F007 + F042).
- [x] `tests/agents/integration/test_hitl_streaming_e2e.py` : **12 verts** (les
      trois rouges précédents n'étaient que l'absence de Redis).
- [x] `task test:backend:integration` : **708 verts** (PostgreSQL + Redis),
      dont les 6 tests écrits par la revue à froid (reset réel, file de réveil).
- [ ] `task ci:fast` complet avant tout push.
- [ ] La suite `tests/agents/` explicitement (piège documenté : hors du hook
      et de `ci:fast`).
- [ ] Opération production du lot 1 : purger les 16 clés de ledger polluées
      puis recalculer le profil (avec le propriétaire, après déploiement).
- [ ] Retirer la branche `NOT EXISTS` datée de `_DAY_ACTIVITY_SQL` après le
      2026-09-30.
- [ ] Preuve runtime (T26) après déploiement, flags allumés un par un :
      `HABITS_PRESENCE_ENABLED`, `PUSH_WAKE_ENABLED`,
      `RAG_SPACES_MAIL_SYNC_ENABLED`.

---

## Global Constraints

- Aucun seuil calibré n'est modifié : `HABITS_*` et `RECURRENCE_*` restent aux valeurs de `core/constants.py`.
- **Une notification n'est jamais une activité** : ni son envoi, ni sa lecture implicite. Seuls comptent un message humain, un run humain (`channel='web'`), un reset, une ouverture de l'application (ping de visibilité) et un pouce haut/bas (décision propriétaire 2026-09-03).
- Toute nouvelle clé Redis nommée par un identifiant utilisateur déclare sa portée dans le registre du lot 0 ; une famille non déclarée n'est jamais purgée par le reset et fait échouer le test de complétude.
- Chaque nouvelle métrique atteint un panneau Grafana dans le même lot (`task ratchet:metrics` ne fait que retirer).
- Fichiers gelés par le ratchet de taille (`context_aggregator.py`, `conversations/service.py`, `drive_sync.py`, `proactive_task.py`) : on y ajoute au plus quelques lignes d'appel ; la logique va dans de nouveaux modules.
- i18n : toute chaîne visible existe dans les 6 locales (`zh` côté front, `zh-CN` côté back), parité stricte.
- Tests inconditionnels (ADR-155), seuils lus dans `settings`, coroutines toujours attendues ou fermées.
- Portes minimales par lot : `task lint`, `task test:backend:unit:fast`, la suite `tests/agents/` explicitement (hors hook, piège documenté), `task test:frontend` si le front bouge ; avant push : `task ci:fast` ; migrations : `task db:migrate:replay-check`.
- Commits par tâche, Conventional Commits, jamais de push sans demande du propriétaire.

---

## 0. Ce que le plan corrige (rappel des preuves)

| Symptôme | Cause prouvée | Lot |
|---|---|---|
| 0 habitude récurrente, 0 proposition, jamais | `reset_conversation` efface `recurrence:{uid}:*` (161 resets / 56 j) | 0 |
| Ledger reseedé avec les routines de LIA (email 27 j, event 26, weather 26, web_search 27 pour 5 tours humains) | liste blanche « pas de résumé de tokens = humain » ; les résumés sont supprimés au reset, les run_id proactifs ne correspondent jamais | 1 |
| Un run programmé peut évaluer/promouvoir une récurrence | `_resolve_recurrence_suggestion` sans garde `is_automated_source` | 2 |
| Rythme `none` malgré 44 jours actifs / 56 | honnête (meilleur bin 0,39 < 0,55) ; mais la présence = frappe seule, sources détruites par le reset | 1, 3 |
| Heartbeat muet pour les comptes qui lisent sans écrire | porte d'inactivité sur `last_login` | 3 |
| Push vivant (802 notifications / 15 j) sans effet | unique consommateur = invalidation de cache ; `page_token` Drive jamais lu | 4 |
| Pas d'historisation utile du courrier | pas de source Mail ; RAG boîte entière refusé (redondance, PII, doctrine) | 6 |

---

## 1. Carte des fichiers

### Backend — créés
- `apps/api/src/infrastructure/cache/key_families.py` — registre des familles de clés Redis et de leur portée ; prédicat `is_reset_purgeable(key)`.
- `apps/api/src/domains/conversations/reset_purge.py` — purge Redis du reset, extraite de `conversations/service.py` (fichier gelé), lit le registre.
- `apps/api/src/domains/habits/human_turns.py` — UN prédicat SQL « tour humain » partagé par le dépôt habitudes et le seed.
- `apps/api/src/domains/habits/presence.py` — service de présence : ping de visibilité, pouce, `last_presence_at`, écriture rollup.
- `apps/api/src/domains/push_channels/wake.py` — file de réveil (Redis) : `enqueue_wake`, `pop_wakes`, charge utile.
- `apps/api/src/domains/push_channels/wake_filter.py` — pré-filtre déterministe mail/agenda (pur, testé).
- `apps/api/src/domains/heartbeat/wake_context.py` — bloc « FRESH » injecté dans le contexte heartbeat depuis la charge de réveil.
- `apps/api/src/infrastructure/scheduler/heartbeat_wake_sweep.py` — job de balayage court.
- `apps/api/src/domains/rag_spaces/drive_ingest.py` — ingestion par fichier extraite de `drive_sync.py` ; `sync_changed_files`.
- `apps/api/src/domains/rag_spaces/mail_sync.py` — source Mail : liste des fils d'un libellé, rendu Markdown, ingestion, suppression.
- `apps/api/src/infrastructure/observability/metrics_presence.py` — métriques présence + reset.
- `apps/api/alembic/versions/2026_09_03_2100-a7c3e9b1d5f2_feedback_at_and_trigger.py` — colonnes `feedback_at`, `trigger`.
- `apps/api/alembic/versions/2026_09_0X_XXXX-e0f1a2b3c4d5_rag_mail_sources.py` — table `rag_mail_sources` + colonnes `rag_documents`.
- Tests : miroir exact sous `apps/api/tests/unit/...` (listés par tâche).

### Backend — modifiés
- `domains/conversations/service.py:455-535` → remplace le bloc de scan par un appel à `reset_purge.purge_conversation_keys(...)`.
- `domains/users/account_deletion_service.py:479-530` → purge totale par familles déclarées (registre), plus de motifs à la main.
- `domains/habits/repository.py` → `_RUN_ACTIVITY_SQL` sur `product_outcomes` ; `_DAY_ACTIVITY_SQL` sans jointure MTS ; bornes.
- `domains/habits/ledger_seed.py` → même prédicat ; `origin: "seed"` dans la charge.
- `domains/habits/candidates.py`, `schemas.py`, `router.py` → `origin` publié ; « Tout oublier » supprime le ledger et la présence.
- `domains/habits/service.py` → rien de structurel (le rollup absorbe la présence par construction).
- `domains/agents/nodes/initiative_recurrence.py` → garde automatisée.
- `domains/heartbeat/router.py:296-345` et `domains/interests/router.py:663` → présence sur pouce + `feedback_at`.
- `domains/heartbeat/repository.py:322-347` → `feedback_at`.
- `domains/heartbeat/models.py`, `domains/interests/models.py` → colonnes.
- `domains/heartbeat/proactive_task.py:101-135` → porte d'inactivité sur `max(last_login, présence)` ; `wake` transmis à l'agrégateur ; `trigger` persisté.
- `domains/heartbeat/context_aggregator.py` → 3 lignes : accepte `wake`, l'applique dans `_fetch_emails` / `_fetch_calendar` via `wake_context`.
- `domains/heartbeat/schemas.py` → champ `wake_trigger`, section prompt « FRESH ».
- `domains/heartbeat/gmail_delta.py` → clé d'ancre déclarée `user_learning` (aucun changement de format).
- `domains/push_channels/service.py` → `enqueue_wake` après invalidation ; `page_token` mis à jour.
- `domains/push_channels/models.py` → rien (colonnes existantes suffisent).
- `domains/connectors/clients/google_drive_client.py` → `list_changes`.
- `domains/connectors/clients/google_gmail_client.py:574-596` → `history_types` paramétrable.
- `infrastructure/proactive/runner.py:54-98, 300-320` → `user_ids` optionnel.
- `infrastructure/startup/schedulers.py` → job de balayage.
- `core/config/habits.py`, `core/config/push.py`, `core/config/rag_spaces.py`, `core/constants.py` → réglages et défauts.
- `.env.example`, `.env.prod.example` → nouvelles variables.
- `infrastructure/observability/grafana/dashboards/13-proactive-heartbeat.json`, `18-rag-spaces.json`, `09-conversations-users.json` → panneaux.
- Docs : `docs/technical/GOOGLE_PUSH_CHANNELS.md`, `HEARTBEAT_AUTONOME.md`, `DATABASE_SCHEMA.md`, `HYBRID_SEARCH.md`, `docs/architecture/ADR-214…md` (amendement), `ADR-238…md` (attente honnête), `ADR-260`, `ADR-261`, `ADR-262`, `ADR_INDEX.md`, `docs/INDEX.md`, guides how/why ×6 (une phrase chacun), CHANGELOG à la release.

### Frontend — créés / modifiés
- `apps/web/src/components/telemetry/PresencePing.tsx` (créé) — ping authentifié sur visibilité, throttlé.
- `apps/web/src/app/[lng]/layout.tsx` — monte `PresencePing` à côté de `TelemetryBootstrap`.
- `apps/web/src/hooks/useHabits.ts`, `components/settings/HabitsSettings.tsx` — `origin` des candidats, texte d'aide présence.
- `apps/web/src/hooks/useMailSources.ts` (créé), `components/spaces/MailLabelPickerDialog.tsx` (créé), page détail d'espace — section « Sources e-mail ».
- `apps/web/src/components/notifications/*` — badge « en réaction à un e-mail / une invitation » (`trigger === 'push'`).
- `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` — clés listées par tâche.

---

## 2. Lot 0 — Le reset ne détruit plus l'apprentissage (ADR-260)

### Task 0.1 : registre des familles de clés Redis

**Files:**
- Create: `apps/api/src/infrastructure/cache/key_families.py`
- Test: `apps/api/tests/unit/infrastructure/cache/test_key_families.py`

**Interfaces:**
- Produces: `class KeyScope(str, Enum)` = `CONVERSATION | USER_CACHE | USER_LEARNING | USER_RUNTIME | GLOBAL` ; `KEY_FAMILIES: dict[str, KeyScope]` (clé = préfixe jusqu'au premier segment variable) ; `family_of(key: str) -> str | None` ; `is_reset_purgeable(key: str) -> bool` ; `is_user_scoped(key: str) -> bool` ; `assert_key_families_complete() -> None`.

- [ ] **Step 1 : écrire les tests qui échouent**

```python
"""Redis key families declare their scope (ADR-260).

The conversation reset used to delete every key matching *:{user_id}* —
which is how the recurrence ledger, the Gmail delta anchor and the adaptive
thresholds were wiped 161 times in 56 days on the primary account. A family
now declares what it is; an undeclared family is never purged by a reset.
"""
from __future__ import annotations

import pytest

from src.infrastructure.cache.key_families import (
    KEY_FAMILIES,
    KeyScope,
    assert_key_families_complete,
    family_of,
    is_reset_purgeable,
)

pytestmark = pytest.mark.unit

UID = "08dfb351-5336-42c8-92a9-ee46c6e7f0d0"


@pytest.mark.parametrize(
    "key",
    [
        f"recurrence:{UID}:email",
        f"gmail_history_anchor:{UID}",
        f"adaptive:thr:journal_injection:{UID}",
        f"briefing:v2:lastgood:{UID}:mails",
        f"presence:{UID}:2026-09-03:14",
        f"sse:connection:{UID}",
        f"user:{UID}:sessions",
        f"user:{UID}:contacts_search",
    ],
)
def test_learning_and_runtime_keys_survive_a_reset(key: str) -> None:
    assert is_reset_purgeable(key) is False


@pytest.mark.parametrize(
    "key",
    [
        f"hitl_pending:{UID}",
        f"contacts_search:{UID}:jean",
        f"gmail:search:{UID}:abc",
        f"briefing:v2:{UID}:mails",
        f"chat:active_run:{UID}",
    ],
)
def test_conversation_and_cache_keys_are_purged(key: str) -> None:
    assert is_reset_purgeable(key) is True


def test_undeclared_family_is_never_purged() -> None:
    assert family_of(f"brand_new_family:{UID}") is None
    assert is_reset_purgeable(f"brand_new_family:{UID}") is False


def test_lastgood_is_distinct_from_the_briefing_cache() -> None:
    assert KEY_FAMILIES["briefing:v2:lastgood"] is KeyScope.USER_LEARNING
    assert KEY_FAMILIES["briefing:v2"] is KeyScope.USER_CACHE


def test_registry_is_complete() -> None:
    assert_key_families_complete()
```

- [ ] **Step 2 : lancer, vérifier l'échec** — `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/cache/test_key_families.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3 : implémenter**

```python
"""Redis key families and their scope (ADR-260).

Every key family LIA writes is listed here with the scope that decides who
may delete it:

- CONVERSATION: state of the running conversation (HITL, active run, tool
  contexts) — purged by a conversation reset.
- USER_CACHE: per-user caches with a TTL — purged by a reset (privacy and
  freshness), harmless to lose.
- USER_LEARNING: what LIA learned about the user — NEVER purged by a reset;
  purged by account deletion and by the explicit "forget" surfaces.
- USER_RUNTIME: sessions, rate limits, SSE registries — never purged by a
  reset (deleting a rate-limit key at reset was a bypass).
- GLOBAL: not user-scoped.

The match is longest-prefix on ':'-separated segments, so
``briefing:v2:lastgood`` wins over ``briefing:v2``. An UNDECLARED family is
never purged: silent deletion is how learning died invisibly, so the safe
default is to keep and to count (``reset_undeclared_family_total``).
"""

from __future__ import annotations

from enum import Enum


class KeyScope(str, Enum):
    CONVERSATION = "conversation"
    USER_CACHE = "user_cache"
    USER_LEARNING = "user_learning"
    USER_RUNTIME = "user_runtime"
    GLOBAL = "global"


KEY_FAMILIES: dict[str, KeyScope] = {
    # conversation
    "hitl_pending": KeyScope.CONVERSATION,
    "hitl:request_ts": KeyScope.CONVERSATION,
    "chat:run": KeyScope.CONVERSATION,
    "chat:active_run": KeyScope.CONVERSATION,
    "chat:listeners": KeyScope.CONVERSATION,
    "chat:cancel": KeyScope.CONVERSATION,
    "browser:session": KeyScope.CONVERSATION,
    # user caches
    "contacts_list": KeyScope.USER_CACHE,
    "contacts_search": KeyScope.USER_CACHE,
    "contacts_details": KeyScope.USER_CACHE,
    "places_search": KeyScope.USER_CACHE,
    "places_nearby": KeyScope.USER_CACHE,
    "gmail:message": KeyScope.USER_CACHE,
    "gmail:search": KeyScope.USER_CACHE,
    "gmail:labels": KeyScope.USER_CACHE,
    "relations:context:v2": KeyScope.USER_CACHE,
    "briefing:v2": KeyScope.USER_CACHE,
    "heartbeat:birthdays": KeyScope.USER_CACHE,
    "heartbeat:departure": KeyScope.USER_CACHE,
    "user_connectors": KeyScope.USER_CACHE,
    "interest_analysis": KeyScope.USER_CACHE,
    "usage_limit": KeyScope.USER_CACHE,
    "conv:user": KeyScope.USER_CACHE,
    "meetings:start": KeyScope.USER_CACHE,
    "skills:url_import": KeyScope.USER_CACHE,
    # learning — never purged by a reset
    "recurrence": KeyScope.USER_LEARNING,
    "gmail_history_anchor": KeyScope.USER_LEARNING,
    "adaptive": KeyScope.USER_LEARNING,
    "briefing:v2:lastgood": KeyScope.USER_LEARNING,
    "presence": KeyScope.USER_LEARNING,
    "heartbeat:wake": KeyScope.USER_LEARNING,
    # runtime — never purged by a reset
    "session": KeyScope.USER_RUNTIME,
    "user": KeyScope.USER_RUNTIME,
    "sse:connection": KeyScope.USER_RUNTIME,
    "sse:streams": KeyScope.USER_RUNTIME,
    "oauth_lock": KeyScope.USER_RUNTIME,
    "oauth:health:notified": KeyScope.USER_RUNTIME,
    "apikey:user": KeyScope.USER_RUNTIME,
    "ws:audio": KeyScope.USER_RUNTIME,
    "webauthn:reg": KeyScope.USER_RUNTIME,
    "webauthn:stepup": KeyScope.USER_RUNTIME,
    # global
    "llm_cache": KeyScope.GLOBAL,
    "web_search": KeyScope.GLOBAL,
    "web_fetch": KeyScope.GLOBAL,
    "push:debounce": KeyScope.GLOBAL,
    "scheduler": KeyScope.GLOBAL,
    "scheduler_lock": KeyScope.GLOBAL,
    "diagnostics": KeyScope.GLOBAL,
    "system": KeyScope.GLOBAL,
    "http": KeyScope.GLOBAL,
    "ratelimit": KeyScope.GLOBAL,
    "product": KeyScope.GLOBAL,
    "pricing": KeyScope.GLOBAL,
    "plan:patterns": KeyScope.GLOBAL,
    "heartbeat:geocode": KeyScope.GLOBAL,
    "rag": KeyScope.GLOBAL,
}

_RESET_PURGED: frozenset[KeyScope] = frozenset({KeyScope.CONVERSATION, KeyScope.USER_CACHE})
_USER_SCOPED: frozenset[KeyScope] = frozenset(
    {KeyScope.CONVERSATION, KeyScope.USER_CACHE, KeyScope.USER_LEARNING, KeyScope.USER_RUNTIME}
)


def family_of(key: str | bytes) -> str | None:
    """Longest declared prefix of ``key`` on ':' boundaries, or None."""
    name = key.decode() if isinstance(key, bytes) else key
    parts = name.split(":")
    for length in range(len(parts), 0, -1):
        candidate = ":".join(parts[:length])
        if candidate in KEY_FAMILIES:
            return candidate
    return None


def scope_of(key: str | bytes) -> KeyScope | None:
    family = family_of(key)
    return KEY_FAMILIES[family] if family is not None else None


def is_reset_purgeable(key: str | bytes) -> bool:
    """A conversation reset may delete this key (declared conversation/cache)."""
    return scope_of(key) in _RESET_PURGED


def is_user_scoped(key: str | bytes) -> bool:
    """Account deletion must delete this key (any user-scoped family)."""
    return scope_of(key) in _USER_SCOPED


def assert_key_families_complete() -> None:
    """Boot-time guard (ADR-085): no family may be declared twice under a
    shadowing prefix with a contradictory scope, and every constant prefix in
    ``core.constants`` that names a Redis key family must be declared."""
    from src.core import constants as c

    declared_prefixes = [
        getattr(c, name).rstrip(":").rstrip("_")
        for name in dir(c)
        if name.startswith("REDIS_KEY_") and name.endswith("_PREFIX")
    ]
    missing = sorted(p for p in declared_prefixes if family_of(p + ":x") is None)
    if missing:
        raise RuntimeError(f"Redis key families without a declared scope: {missing}")
```

Ajouter l'appel `assert_key_families_complete()` dans `infrastructure/startup/registries.py` juste après `assert_category_vocabulary_completeness` (ligne 62, même étape ADR-085), et un test qui l'appelle.

Garde complémentaire, parce que l'assert de boot ne voit que les constantes `REDIS_KEY_*_PREFIX` et qu'une clé construite par f-string littérale lui échappe (piège mesuré : `heartbeat:birthdays:{uid}`, `meetings:start:{uid}`, `relations:context:v2:{uid}`) : `tests/unit/test_redis_key_family_guard.py` parcourt `apps/api/src` avec le motif `r'f"([a-z_:]+):\{(user_id|uid|user\.id)'` et exige `family_of(prefix + ":x") is not None` pour chaque préfixe trouvé ; liste d'exclusion shrink-only vide au départ.

Deux limites connues et acceptées de la source `product_outcomes` (vérifiées 2026-09-03) : un outcome n'est écrit que lorsqu'un message assistant a été archivé (`schedule_outcome_recording` no-op sinon) — un tour interrompu par un HITL sans réponse archivée ne compte pas dans cette source (il reste compté par les messages vivants jusqu'au reset, et par la présence du lot 3) ; et la source dépend de `PRODUCT_ANALYTICS_ENABLED` (vrai en prod ; documenter la dépendance dans `.env.example` à côté de `HABITS_ENABLED`). Telegram passe par `stream_chat_response` → même écriture, donc compte. Test de caractérisation à ajouter au lot 1 : `test_hitl_interrupted_turn_writes_no_outcome` (fige le comportement, ne le change pas).

- [ ] **Step 4 : vérifier vert**, puis mypy strict sur le module.

- [ ] **Step 5 : commit** — `feat(cache): declare the scope of every Redis key family (ADR-260)`

### Task 0.2 : la purge du reset lit le registre

**Files:**
- Create: `apps/api/src/domains/conversations/reset_purge.py`
- Modify: `apps/api/src/domains/conversations/service.py:455-535` (remplacer le bloc par un appel)
- Create: `apps/api/src/infrastructure/observability/metrics_presence.py` (`conversation_reset_keys_deleted_total{family}`, `conversation_reset_keys_kept_total{scope}`, `reset_undeclared_family_total{family}`)
- Test: `apps/api/tests/unit/domains/conversations/test_reset_purge.py`

**Interfaces:**
- Produces: `async def purge_conversation_keys(redis, *, user_id: str, conversation_id: str) -> dict[str, int]` (compte par famille).

- [ ] **Step 1 : tests qui échouent** — un double Redis en mémoire (copier `_FakeRedis` de `test_ledger_seed.py` et lui ajouter `scan(cursor, match, count)` + `delete(*keys)`), semé avec les clés du tableau de l'audit ; asserts : après purge, `recurrence:*`, `gmail_history_anchor:*`, `adaptive:*`, `briefing:v2:lastgood:*`, `sse:*`, `user:{uid}:contacts_search` **existent encore** ; `hitl_pending:*`, `contacts_search:*`, `gmail:search:*`, `briefing:v2:{uid}:mails` **n'existent plus** ; une clé `brand_new:{uid}` existe encore et le compteur `reset_undeclared_family_total{family="brand_new"}` vaut 1 ; retour `{"contacts_search": 1, ...}`.

- [ ] **Step 2 : implémenter** — même six motifs de SCAN qu'aujourd'hui (aucune clé n'échappe au balayage), mais chaque clé passe par `is_reset_purgeable` ; les autres sont comptées par scope ; log `redis_purged_for_reset` conservé avec `deleted_by_family` et `kept_by_scope`. Dans `service.py`, le bloc 455-535 devient :

```python
        # ADR-260: the purge deletes only families declared conversation/cache;
        # learning and runtime families survive (they are not the conversation).
        with suppress(Exception):
            from src.domains.conversations.reset_purge import purge_conversation_keys
            from src.infrastructure.cache.redis import get_redis_cache

            await purge_conversation_keys(
                await get_redis_cache(),
                user_id=str(user_id),
                conversation_id=str(conversation.id),
            )
```

(Le `except Exception as redis_error` existant devient inutile ; la ligne de commentaire ci-dessus est la justification exigée par la doctrine `suppress`.)

- [ ] **Step 3 : vert + mesure de taille** — `python scripts/audit/measure_sloc.py apps/api/src/domains/conversations/service.py` doit **baisser** (le bloc extrait est plus long que l'appel).

- [ ] **Step 4 : suite `tests/agents/test_context_cleanup_on_reset.py`** — `cd apps/api && .venv/Scripts/pytest tests/agents/test_context_cleanup_on_reset.py -v` (PostgreSQL + Redis dev requis).

- [ ] **Step 5 : commit** — `fix(conversations): a reset no longer wipes learning and runtime Redis keys (ADR-260)`

### Task 0.3 : la suppression de compte et « Tout oublier » utilisent le registre

**Files:**
- Modify: `apps/api/src/domains/users/account_deletion_service.py:479-530` — remplacer les motifs à la main par un SCAN des six motifs utilisateur + `is_user_scoped(key)` (toutes les familles utilisateur, y compris learning et runtime) ; garder les `explicit_keys`.
- Modify: `apps/api/src/domains/habits/router.py:279-292` (`delete_all_habits`) — après `delete_activity_rollup`, supprimer `recurrence:{uid}:*` via une nouvelle fonction `recurrence_store.delete_user_ledger(redis, user_id) -> int` et les clés `presence:{uid}:*` via `presence.forget_user(redis, user_id)` (tâche 3.1).
- Modify: `apps/api/src/infrastructure/cache/recurrence_store.py` — `delete_user_ledger`.
- Tests: `tests/unit/domains/users/test_account_deletion_redis.py` (toutes les familles utilisateur supprimées, les globales conservées) ; `tests/unit/domains/habits/test_habits_router.py` (nouveau cas : « Tout oublier » supprime le ledger).

- [ ] Steps : test rouge → implémentation → vert → commit `feat(habits): forget-all also drops the recurrence ledger; account deletion purges by declared scope`.

### Task 0.4 : panneau et documentation du lot 0

- Modify: `infrastructure/observability/grafana/dashboards/09-conversations-users.json` — panneau « Reset : clés supprimées / conservées par famille » avec `sum by (family) (increase(conversation_reset_keys_deleted_total[24h])) or vector(0)` et `"noValue": "0"`.
- Create: `docs/architecture/ADR-260-Redis-Key-Families-Scope-And-Reset-Purge.md` (contexte : les mesures de l'audit ; décision ; alternatives : deny-list rejetée parce qu'une nouvelle famille y serait purgée par défaut).
- Modify: `docs/architecture/ADR_INDEX.md`, `docs/INDEX.md`, `CLAUDE.md` § Systemic Rules › Persistence (une règle : « toute clé Redis nommée par un identifiant utilisateur déclare sa portée dans `key_families.py` »), puis `task docs:sync-agents`.
- Gates : `task ratchet:metrics` (retire les nouvelles métriques de la baseline si elles y étaient ajoutées par erreur — elles ne doivent pas y entrer), `task lint:docs:preview`.
- Commit `docs(adr): ADR-260 Redis key families`.

---

## 3. Lot 1 — Une seule définition durable du tour humain

### Task 1.1 : le prédicat partagé

**Files:**
- Create: `apps/api/src/domains/habits/human_turns.py`
- Test: `apps/api/tests/unit/domains/habits/test_human_turns.py`

**Interfaces:**
- Produces: `HUMAN_OUTCOME_PREDICATE_SQL: str` = `"po.channel = 'web' AND po.result_type IN ('answer', 'action')"` ; `HUMAN_OUTCOME_CHANNELS: frozenset[str] = {"web"}` ; test de contrat avec `domains/product/constants.py::CHANNELS` et `RESULT_TYPES` (le vocabulaire vient de là, jamais redéclaré : le test compare).

- [ ] Test : le prédicat n'accepte que des valeurs de `CHANNELS`/`RESULT_TYPES` ; `scheduler`, `web_showroom`, `unknown` exclus ; `automation_run` exclu. Implémentation triviale. Commit `feat(habits): one SQL predicate for a human turn`.

### Task 1.2 : le dépôt habitudes lit `product_outcomes`

**Files:**
- Modify: `apps/api/src/domains/habits/repository.py:38-130`
- Test: `apps/api/tests/unit/domains/habits/test_habits_repository.py` (réécrire `TestMessageSourceAntiAutomation`, ajouter `TestOutcomeSource`, adapter `TestActivityBounds`)
- Test intégration : `apps/api/tests/integration/domains/habits/test_activity_sources_pg.py` (nouveau, marqueur `integration`)

- [ ] **Step 1 : tests rouges**

```python
class TestOutcomeSource:
    """The durable human-turn source is product_outcomes (one row per run,
    never deleted by a conversation reset — token summaries ARE)."""

    def test_sql_reads_outcomes_with_the_shared_predicate(self) -> None:
        sql = str(_RUN_ACTIVITY_SQL)
        assert "product_outcomes" in sql
        assert HUMAN_OUTCOME_PREDICATE_SQL in sql
        assert "message_token_summary" not in sql

    def test_message_source_keeps_marker_and_historical_whitelist(self) -> None:
        # Lot 1 keeps the historical NOT EXISTS clause (see the note above);
        # lot 5 removes it after 2026-09-30 and flips this assertion.
        sql = str(_DAY_ACTIVITY_SQL)
        assert "is_automated_source" in sql
        assert "NOT EXISTS" in sql


class TestActivityBounds:
    def test_bounds_union_spans_messages_outcomes_and_resets(self) -> None:
        sql = str(_ACTIVITY_BOUNDS_SQL)
        assert "conversation_messages" in sql
        assert "product_outcomes" in sql
        assert "conversation_audit_log" in sql
        assert "message_token_summary" not in sql
        assert sql.count("UNION ALL") == 2
```

Test d'intégration (PostgreSQL réel) : insérer pour un utilisateur 3 outcomes `web/answer` à 9 h, 1 `scheduler/automation_run` à 7 h, 1 `web_showroom/answer` à 10 h ; `fetch_run_activity` rend `{jour: {9: 3}}` exactement.

- [ ] **Step 2 : implémenter**

```python
_RUN_ACTIVITY_SQL = text(f"""
    SELECT (po.produced_at AT TIME ZONE :tz)::date AS local_date,
           EXTRACT(HOUR FROM po.produced_at AT TIME ZONE :tz)::int AS local_hour,
           COUNT(*) AS n
    FROM product_outcomes po
    WHERE po.user_id = :user_id
      AND po.produced_at >= :since
      AND {HUMAN_OUTCOME_PREDICATE_SQL}
    GROUP BY 1, 2
    """)
```

`_DAY_ACTIVITY_SQL` : **conserver** la clause NOT EXISTS sur `message_token_summary` (lignes 55-60) jusqu'au 2026-09-30 — le marqueur `is_automated_source` n'existe que depuis le 2026-08-05 et un message automatisé antérieur non marqué reste dans la fenêtre de 56 jours jusqu'à cette date ; la clause est inoffensive (elle n'exclut que ce qu'un résumé non humain désigne) et sa suppression est une tâche datée du lot 5. Le test `test_message_source_keeps_only_the_metadata_marker` ci-dessous ne s'écrit donc qu'au lot 5 ; au lot 1 on garde l'assert existant. `_ACTIVITY_BOUNDS_SQL` : branche 2 sur `product_outcomes`. Supprimer le paramètre `uuid_regex` des trois appels. `HUMAN_CHAT_SESSION_PREFIXES` / `HUMAN_CHAT_SESSION_UUID_REGEX` (`core/constants.py:682-683`) n'ont que trois lecteurs (vérifié 2026-09-03 : `habits/repository.py`, `habits/ledger_seed.py`, `tests/unit/domains/habits/test_habits_repository.py`) : les supprimer dans cette tâche et la suivante, avec leur import dans le test.

- [ ] **Step 3 : vert unitaire + intégration** — `task test:backend:integration` (filtrer `-k activity_sources`).

- [ ] **Step 4 : commit** — `fix(habits): the durable human-turn source is product_outcomes, not token summaries`

### Task 1.3 : le seed lit le même prédicat et marque sa provenance

**Files:**
- Modify: `apps/api/src/domains/habits/ledger_seed.py:47-63, 118-125`
- Modify: `apps/api/src/infrastructure/cache/recurrence_store.py` — `load()` pose `data.setdefault("origin", "live")`.
- Modify: `apps/api/src/domains/habits/candidates.py`, `schemas.py` (`RecurrenceCandidate.origin: Literal["live","seed"]`), `router.py` (publie).
- Test: `tests/unit/domains/habits/test_ledger_seed.py` (`test_sql_carries_the_human_whitelist_and_domain_filter` → `test_sql_uses_the_shared_human_predicate` : `HUMAN_OUTCOME_PREDICATE_SQL in sql`, `"message_token_summary" not in sql`) ; `test_candidates.py` (origin publié, un candidat `seed` garde ses jours tels quels — la provenance est affichée, jamais un seuil différent).
- Simulation (fixture) : `tests/unit/domains/habits/fixtures/prod_like_outcomes.json` — jeu anonymisé reconstruit depuis les comptages de l'audit (183 outcomes `scheduler` entre 1 h et 4 h, 5 `web`), test `test_seed_never_learns_lia_s_own_routines` : après seed, aucune signature n'a plus de jours que d'outcomes `web`, et `evaluate_locks` sur chaque clé rend `None`.

- [ ] Steps : rouge → vert → commit `fix(habits): the ledger seed keeps LIA's own routines out and states its origin`.

### Task 1.4 : garde d'asymétrie sur l'évaluation de récurrence (ex-lot 2)

**Files:**
- Modify: `apps/api/src/domains/agents/nodes/initiative_recurrence.py:32-45`
- Modify: `apps/api/src/infrastructure/observability/metrics_agents.py` — `recurrence_evaluation_skipped_total{reason}` (`automated_source`, `flag_off`, `not_actionable`, `no_user`).
- Test: `tests/unit/domains/agents/nodes/test_recurrence_suggestion_wiring.py` — `test_automated_run_never_evaluates_nor_promotes` (patch `runtime_context_if_running` → contexte avec `is_automated_source=True`, ledger verrouillé → `evaluate_suggestion` jamais appelé) ; `test_human_run_with_same_ledger_fires`.

```python
    from src.domains.agents.context.runtime_context import runtime_context_if_running

    ctx = runtime_context_if_running()
    if ctx is not None and ctx.is_automated_source:
        # Symmetry with post_response_extractions: a scheduled run must neither
        # record nor evaluate — otherwise LIA proposes to automate her own
        # automation and promotes it as the user's habit.
        recurrence_evaluation_skipped_total.labels(reason="automated_source").inc()
        return None
```

- [ ] Commit `fix(agents): recurrence evaluation is guarded like recurrence recording`.

### Task 1.5 : opération prod (avec le propriétaire, après déploiement)

- [ ] Supprimer les 16 clés seedées polluées du compte principal : `python` dans `lia-api-prod` via `get_redis_cache()` → `delete` des clés `recurrence:{uid}:*` dont `origin` est absent (pré-lot) ; journaliser le nombre.
- [ ] `POST /habits/recompute` (bouton « Recalculer ») → vérifier `recurrence_ledger_seeded` et, en Redis, qu'aucune signature ne dépasse ses jours `web`.
- [ ] Preuve : faire un reset de conversation, relire `recurrence:{uid}:*` → présentes.

---

## 4. Lot 3 — La présence en lecture (flag OFF par défaut)

### Task 3.1 : service de présence et rollup

**Files:**
- Create: `apps/api/src/domains/habits/presence.py`
- Modify: `apps/api/src/core/config/habits.py` — `habits_presence_enabled: bool = False`, `habits_presence_client_throttle_minutes: int = 15`, `habits_presence_last_ttl_days: int = 30`.
- Modify: `apps/api/src/core/constants.py` — `HABITS_PRESENCE_CLIENT_THROTTLE_MINUTES_DEFAULT = 15`, `HABITS_PRESENCE_LAST_TTL_DAYS_DEFAULT = 30`, `REDIS_KEY_PRESENCE_PREFIX = "presence:"`.
- Modify: `apps/api/src/domains/habits/repository.py` — `async def bump_activity_hour(user_id, local_date, hour) -> None` (UPSERT atomique côté serveur : `INSERT ... ON CONFLICT (user_id, local_date) DO UPDATE SET hour_counts = jsonb_set(coalesce(hour_counts,'{}'), ARRAY[:h], to_jsonb(GREATEST(coalesce((hour_counts->>:h)::int,0),1)))` — jamais SELECT → incrément Python).
- Test: `tests/unit/domains/habits/test_presence.py`, `tests/integration/domains/habits/test_presence_pg.py`.

**Interfaces:**
- Produces: `async def record_presence(db, redis, user, *, kind: Literal["visibility","feedback"], at: datetime | None = None) -> bool` (True si une heure a été bankée) ; `async def last_presence_at(redis, user_id) -> datetime | None` ; `async def forget_user(redis, user_id) -> int`.

Comportement : refuse si `settings.habits_enabled` faux ou `user.habits_enabled` faux ou `settings.habits_presence_enabled` faux (`kind="feedback"` passe même si `habits_presence_enabled` est faux : le pouce est une décision explicite, acceptée par le propriétaire) ; `now_local = at.astimezone(resolve_user_timezone(user))` ; `SET presence:{uid}:{date}:{hour} 1 NX EX 7200` → si acquis, `bump_activity_hour` ; toujours `SET presence:last:{uid} <iso> EX ttl` ; métrique `habits_presence_recorded_total{kind, outcome}` (`banked`, `throttled`, `disabled`). Redis absent → `False`, jamais d'exception (fail-open).

- [ ] Tests : throttle par heure locale (deux pings à 14:05 et 14:50 → une seule écriture) ; changement de fuseau Asia → Paris date le bon jour local ; DST (2026-10-25 02:30 Paris) ; `feedback` accepté avec présence désactivée ; `visibility` refusé avec présence désactivée ; deux workers (deux appels concurrents, NX) → un seul bump (intégration) ; `forget_user` supprime toutes les clés. Commit `feat(habits): reading presence as a rhythm source (ADR-214 amendment)`.

### Task 3.2 : endpoint et pouces

**Files:**
- Modify: `apps/api/src/domains/habits/router.py` — `POST /habits/presence` (204, `Depends(get_current_active_session)`, rate limit 6/min par utilisateur via le limiteur existant, corps vide).
- Modify: `apps/api/src/domains/heartbeat/router.py:296-345` et `domains/interests/router.py:663+` — après `update_feedback`, `record_presence(kind="feedback")` dans la même transaction.
- Modify: `apps/api/src/domains/heartbeat/repository.py:322-347` et l'équivalent intérêts — `.values(user_feedback=feedback, feedback_at=func.now())`.
- Modify: modèles + migration `a7c3e9b1d5f2` (down `e0f1a2b3c4d5` — `d9e0f1a2b3c4` was already taken by a 2026-08-08 migration, measured 2026-09-03) : `heartbeat_notifications.feedback_at timestamptz NULL`, `heartbeat_notifications.trigger varchar(16) NOT NULL server_default 'tick'`, `interest_notifications.feedback_at timestamptz NULL`. Downgrade symétrique. Pas de backfill (aucun horodatage historique).
- Modify: `apps/api/src/domains/habits/repository.py` — quatrième source de recalcul `_FEEDBACK_ACTIVITY_SQL` (UNION des deux tables sur `feedback_at`), fusionnée par MAX dans `service.recompute_user_profile` — ainsi « Recalculer » reconstruit la présence des pouces même après « Tout oublier » ? **Non** : « Tout oublier » signifie oublier ; la source pouces est lue au recalcul mais le bouton « Tout oublier » pose `users.habits_forgotten_at` ? Trop lourd. Décision : la source `_FEEDBACK_ACTIVITY_SQL` est lue avec `feedback_at >= since` comme les autres ; « Tout oublier » supprime le rollup ET la profil ; au prochain recalcul les pouces des 56 derniers jours reviennent (comme les messages et les resets reviennent aujourd'hui). Documenté dans l'aide de l'écran (clé i18n `forget_all_description` amendée ×6).
- Tests : `test_habits_router.py` (presence 204, 404 si feature OFF, rate limit), `test_offers_endpoint.py` / `tests/unit/domains/heartbeat/test_feedback_presence.py` (pouce → `record_presence(kind="feedback")` appelé, `feedback_at` posé), `test_habits_repository.py` (SQL feedback), migration : `task db:migrate:replay-check`.
- [ ] Commit `feat(habits): thumbs on a notification count as presence; feedback_at persisted`.

### Task 3.3 : porte d'inactivité du heartbeat

**Files:**
- Modify: `apps/api/src/domains/heartbeat/proactive_task.py:120-135` — `last_seen = max(filter(None, [user.last_login, await last_presence_at(redis, user_id)]))`.
- Test: `tests/unit/domains/heartbeat/test_proactive_task_inactivity.py` — login il y a 20 j + présence il y a 2 j → non ignoré ; login 20 j, pas de présence → ignoré ; Redis KO → comportement `last_login` seul.
- [ ] Commit `fix(heartbeat): inactivity gate reads presence, not only last_login`.

### Task 3.4 : ping client

**Files:**
- Create: `apps/web/src/components/telemetry/PresencePing.tsx`
- Modify: `apps/web/src/app/[lng]/layout.tsx:14+` — `<PresencePing />` à côté de `<TelemetryBootstrap />`.
- Test: `apps/web/src/components/telemetry/__tests__/PresencePing.test.tsx`.

```tsx
'use client';

/**
 * Reading presence (ADR-214 amendment): tells the API "the user has LIA in
 * front of them" — on mount, on visibilitychange→visible and on focus,
 * throttled client-side. NEVER from a background poll: an open tab on a
 * second screen is not a presence. Silent on any failure.
 */

import { useEffect, useRef } from 'react';

import apiClient from '@/lib/api-client';
import { useAuth } from '@/hooks/useAuth';

const THROTTLE_MS = Number(process.env.NEXT_PUBLIC_PRESENCE_THROTTLE_MINUTES ?? '15') * 60_000;

export function PresencePing(): null {
  const { isAuthenticated } = useAuth();
  const lastSent = useRef(0);

  useEffect(() => {
    if (!isAuthenticated) return undefined;
    const send = () => {
      if (document.visibilityState !== 'visible') return;
      const now = Date.now();
      if (now - lastSent.current < THROTTLE_MS) return;
      lastSent.current = now;
      void apiClient.post('/habits/presence').catch(() => undefined);
    };
    send();
    document.addEventListener('visibilitychange', send);
    window.addEventListener('focus', send);
    return () => {
      document.removeEventListener('visibilitychange', send);
      window.removeEventListener('focus', send);
    };
  }, [isAuthenticated]);

  return null;
}
```

(Vérifier le nom réel du hook d'authentification dans `apps/web/src/hooks` avant d'écrire ; `useAuth` est le nom présumé.)

- Tests vitest : monté authentifié → un POST ; second `focus` dans la fenêtre de throttle → aucun ; `visibilityState = 'hidden'` → aucun ; non authentifié → aucun ; échec réseau → pas d'erreur non gérée.
- i18n : `settings.habits.enabled_hint` amendé ×6 (« Les ouvertures de l'application et vos pouces comptent ; les notifications reçues, jamais. »), `settings.habits.candidate_origin_seed` ×6 (« reconstruit depuis l'historique »).
- `.env.example` / `.env.prod.example` : `HABITS_PRESENCE_ENABLED=false`, `HABITS_PRESENCE_CLIENT_THROTTLE_MINUTES=15`, `HABITS_PRESENCE_LAST_TTL_DAYS=30`, `NEXT_PUBLIC_PRESENCE_THROTTLE_MINUTES=15`.
- [ ] Commit `feat(web): reading-presence ping on visibility and focus`.

### Task 3.5 : simulation de calibration (preuve, pas de code livré)

- [ ] Script scratchpad : rejouer `compute_rhythm_profile_with_diagnostics` sur le rollup prod exporté + présence simulée « ouverture 8-9 h, 30 jours » → attendu : fenêtre matin claimée en semaine ; présence uniforme 24 h → aucune fenêtre. Consigner les sorties dans l'amendement ADR-214 (§ « Présence en lecture »).

---

## 5. Lot 4 — Exploitation du push (ADR-261)

### Décision d'ancre (correction de l'analyse initiale)
Les deux ancres Gmail ont deux sens : `webhook_channels.last_history_id` = dernier événement vu (avance à chaque push, même non consommé) ; `gmail_history_anchor:{uid}` = dernier point consommé par le heartbeat. Les fusionner ferait perdre au heartbeat tout message arrivé entre son dernier tick et un push ultérieur. Elles restent deux, mais l'ancre du heartbeat est désormais `USER_LEARNING` (lot 0) : plus jamais effacée par un reset. Documenté dans ADR-261.

### Task 4.1 : file de réveil

**Files:**
- Create: `apps/api/src/domains/push_channels/wake.py`
- Modify: `apps/api/src/core/config/push.py` — `push_wake_enabled: bool = False`, `push_wake_sweep_interval_seconds: int = 120`, `push_wake_cooldown_minutes: int = 20`, `push_wake_max_users_per_sweep: int = 10`, `push_wake_payload_ttl_seconds: int = 3600`.
- Modify: `apps/api/src/core/constants.py` — défauts + `REDIS_KEY_WAKE_PENDING = "heartbeat:wake:pending"`, `REDIS_KEY_WAKE_PAYLOAD_PREFIX = "heartbeat:wake:payload:"`, `REDIS_KEY_WAKE_COOLDOWN_PREFIX = "heartbeat:wake:cooldown:"`, `SCHEDULER_JOB_HEARTBEAT_WAKE_SWEEP = "heartbeat_wake_sweep"`.
- Modify: `apps/api/src/domains/push_channels/service.py` — dans `handle_channel_notification` et `handle_gmail_push`, après `invalidate_for_provider` : `await enqueue_wake(redis, channel.user_id, channel.provider, previous_history_id=previous)` (pour Gmail, `previous = channel.last_history_id` lu AVANT l'affectation ; pour Drive, `page_token=channel.page_token`).
- Test: `tests/unit/domains/push_channels/test_wake.py`, `test_service_notifications.py` (nouveaux cas : un `processed` enfile un réveil ; `debounced`/`ignored_*` n'enfilent rien ; flag OFF n'enfile rien).

**Interfaces:**
- Produces: `@dataclass(frozen=True) class WakePayload(user_id: UUID, provider: str, previous_history_id: int | None, page_token: str | None, enqueued_at: datetime)` ; `async def enqueue_wake(redis, user_id, provider, *, previous_history_id=None, page_token=None) -> bool` (SADD + SET payload EX ttl ; une charge par (user, provider), la plus ancienne gagne : `NX`) ; `async def pop_wakes(redis, limit) -> list[WakePayload]` (`SPOP` par lots, charge lue puis supprimée) ; `async def try_acquire_wake_cooldown(redis, user_id, minutes) -> bool`.

- [ ] Commit `feat(push): a processed notification enqueues a heartbeat wake`.

### Task 4.2 : pré-filtre déterministe

**Files:**
- Create: `apps/api/src/domains/push_channels/wake_filter.py` (pur, sans I/O)
- Modify: `apps/api/src/domains/connectors/clients/google_gmail_client.py:574-596` — paramètre `history_types: tuple[str, ...] = ("messageAdded",)`.
- Test: `tests/unit/domains/push_channels/test_wake_filter.py`

**Interfaces:**
- Produces: `def mail_passes(message_meta: dict, *, favorites: frozenset[str], rules: MailWakeRules) -> WakeVerdict` ; `def calendar_passes(event: dict, *, user_email: str, now: datetime, rules: CalendarWakeRules) -> WakeVerdict` ; `WakeVerdict(passes: bool, reason: str)` avec `reason` borné (`important_label`, `favorite_sender`, `promo_excluded`, `own_event`, `needs_action_soon`, `no_signal`).
- Règles publiées (`core/config/push.py`, préfixe `PUSH_WAKE_`) : `mail_require_labels=["IMPORTANT"]`, `mail_exclude_labels=["CATEGORY_PROMOTIONS","CATEGORY_SOCIAL","CATEGORY_FORUMS"]`, `mail_exclude_list_mail=True` (en-tête `List-Unsubscribe` ou `Precedence: bulk/list` → refus), `calendar_lookahead_hours=24`, `calendar_recent_update_minutes=10`. **Pas de règle « expéditeur favori » en v1** : vérifié 2026-09-03, ni `relation_favorites` (`name_key`, `display_name`) ni `relation_aliases` (`alias_key`) ne portent d'adresse e-mail ; la règle exigerait une résolution nom → adresse par Google Contacts à chaque réveil. Elle est notée comme évolution dans ADR-261, jamais improvisée.
- [ ] Tests : table de cas (IMPORTANT sans promo → passe ; promo → refus ; favori sans IMPORTANT → passe ; rien → refus ; événement propre → refus ; invitation d'un tiers dans 3 h → passe ; mise à jour vieille de 2 h → refus). Commit `feat(push): deterministic wake pre-filter for mail and calendar`.

### Task 4.3 : le runner accepte une liste d'utilisateurs

**Files:**
- Modify: `apps/api/src/infrastructure/proactive/runner.py:54-98` (`build_candidate_users_query(enabled_field, batch_size, user_ids: Sequence[UUID] | None = None)` → `.where(User.id.in_(user_ids))` quand fourni), `:177-215` (`ProactiveTaskRunner(..., user_ids=None, skip_probabilistic_gate=False)`), `:817+` (`execute_proactive_task(..., user_ids=None, skip_probabilistic_gate=False)`), `:382-420` : le lissage probabiliste « minimum garanti » (`should_send_notification`) est **contourné quand `skip_probabilistic_gate` est vrai** — un réveil est un événement, pas un tick à lisser ; toutes les portes DURES (fenêtre horaire, quota journalier, cooldown global 1 h, cooldown inter-types, activité) restent appliquées et sont ce qui borne le budget. Vérifié 2026-09-03 : sans ce contournement, un réveil légitime serait sauté au hasard par `probabilistic_skip`.
- Test: `tests/unit/infrastructure/proactive/test_runner_user_ids.py` — la requête porte `IN` quand `user_ids` est donné, jamais sinon (asserts sur le SQL compilé, comme `test_candidate_query`) ; `test_runner_wake_gate.py` — avec `skip_probabilistic_gate=True`, `should_send_notification` n'est jamais appelé mais `EligibilityChecker.check` l'est toujours ; un refus d'éligibilité reste un refus.
- [ ] Commit `feat(proactive): the runner can target explicit users`.

### Task 4.4 : contexte « FRESH » et trigger

**Files:**
- Create: `apps/api/src/domains/heartbeat/wake_context.py` — `async def fresh_messages(client, payload, rules) -> list[dict[str,str]]` (metadata `from/subject/date/snippet`, ≤ `heartbeat_context_emails_max`), `async def fresh_events(client, payload, user_email, now) -> list[dict]`.
- Modify: `apps/api/src/domains/heartbeat/schemas.py` — `HeartbeatContext.wake_trigger: str | None = None` ; dans `to_prompt_context`, quand il est posé, la section e-mails/agenda est précédée de `FRESH (arrived minutes ago — this is why you were woken):` ; `has_meaningful_context` inchangé.
- Modify: `apps/api/src/domains/heartbeat/context_aggregator.py` — `__init__(self, db, wake: WakePayload | None = None)` ; dans `_fetch_emails`, si `self.wake and self.wake.provider == "google_gmail"` → `return await fresh_messages(...)` (le delta ordinaire n'est pas consommé) ; idem `_fetch_calendar` pour `google_calendar` ; `context.wake_trigger = self.wake.provider`. (≤ 8 lignes ajoutées ; le fichier doit rester sous son plafond : extraire `_fetch_recent_other_notifications` vers `context_sources.py` si nécessaire.)
- Modify: `apps/api/src/domains/heartbeat/proactive_task.py` — `HeartbeatProactiveTask(wake: WakePayload | None = None)` ; `ContextAggregator(db, wake=self.wake)` ; à la persistance (`on_notification_sent`, ligne ~487) : `trigger="push" if self.wake else "tick"`.
- Modify: `apps/api/src/domains/heartbeat/repository.py:63` (`create(..., trigger)`), `schemas.py` (réponse historique : `trigger`).
- Test: `tests/unit/domains/heartbeat/test_wake_context.py`, `test_context_aggregator_wake.py` (avec réveil Gmail, `_fetch_emails` n'appelle pas `delta_messages_or_none`), `test_proactive_task.py` (trigger persisté).
- [ ] Commit `feat(heartbeat): a push wake feeds the decision a FRESH section and stamps the trigger`.

### Task 4.5 : job de balayage

**Files:**
- Create: `apps/api/src/infrastructure/scheduler/heartbeat_wake_sweep.py`
- Modify: `apps/api/src/infrastructure/startup/schedulers.py:723+` — enregistrement `IntervalTrigger(seconds=settings.push_wake_sweep_interval_seconds, jitter=jitter_seconds_for(seconds=...))`, gardé par `push_channels_enabled and push_wake_enabled and heartbeat_enabled`, `max_instances=1`, `misfire_grace_time=60`, `next_run_time=now+60s`.
- Test: `tests/unit/infrastructure/scheduler/test_heartbeat_wake_sweep.py`, `tests/unit/infrastructure/startup/test_scheduler_jitter.py` (le job porte un jitter — le test existant l'exige).

```python
async def run_heartbeat_wake_sweep() -> dict[str, int]:
    """Serve the wakes queued by push notifications (ADR-261).

    For each queued user: wake cooldown (NX) → source refused? → compute
    the fresh delta → deterministic pre-filter → run the heartbeat task for
    THIS user only, under the full EligibilityChecker. Every exit is counted
    (``push_wakes_total{provider,outcome}``); nothing here bypasses a gate.
    """
    if not (settings.push_channels_enabled and settings.push_wake_enabled):
        return {"served": 0, "skipped": 0}
    redis = await get_redis_cache()
    served = skipped = 0
    for wake in await pop_wakes(redis, settings.push_wake_max_users_per_sweep):
        outcome = await _serve_one(redis, wake)
        push_wakes_total.labels(provider=wake.provider, outcome=outcome).inc()
        served += outcome == "notified"
        skipped += outcome != "notified"
    return {"served": served, "skipped": skipped}
```

`_serve_one` : outcomes bornés `cooldown`, `source_disabled`, `no_signal`, `ineligible`, `no_target`, `notified`, `error` ; `source_disabled` lit `is_source_enabled(user, "emails" | "calendar")` ; Drive est traité par 4.6 (pas de heartbeat) ; `execute_proactive_task(task=HeartbeatProactiveTask(wake=wake), eligibility_checker=_create_heartbeat_eligibility_checker(), batch_size=1, user_ids=[wake.user_id])`.

- Métriques : `push_wakes_total{provider,outcome}`, `push_wake_latency_seconds` (histogramme enqueued_at → notification) — panneaux dans `13-proactive-heartbeat.json` (avec `or vector(0)`).
- Tests : cooldown respecté ; source refusée → `source_disabled` ; pré-filtre négatif → `no_signal` ; deux workers sur le même réveil → un seul traitement (SPOP atomique, test intégration Redis) ; tempête (100 réveils du même utilisateur) → une charge (NX) ; runner appelé avec `user_ids=[uid]` et `batch_size=1`.
- [ ] Commit `feat(scheduler): short wake sweep serving push-triggered heartbeats`.

### Task 4.6 : Drive → réindexation incrémentale (P2)

**Files:**
- Modify: `apps/api/src/domains/connectors/clients/google_drive_client.py:415+` — `async def list_changes(self, page_token: str, page_size: int = 100) -> dict[str, Any]` (`GET /changes`, `fields=nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,modifiedTime,parents,trashed))`).
- Create: `apps/api/src/domains/rag_spaces/drive_ingest.py` — extraction des lignes 555-660 de `drive_sync.py` en `async def ingest_drive_file(db, client, *, space_id, source_id, user_id, drive_file) -> IngestOutcome` et `async def remove_drive_document(db, *, space_id, source_id, user_id, file_id) -> bool` ; `sync_folder_background` les appelle (le fichier gelé rétrécit).
- Create dans le même module : `async def sync_changed_files(user_id, changes) -> dict[str,int]` — groupe les changements par `parents` ∩ dossiers liés (`RAGDriveSourceRepository.get_all_for_user`, nouvelle méthode), verrou `try_acquire_sync_lock(source_id)` par source, ingest/remove, `process_document` sous sémaphore, `heartbeat_source` pendant le travail, libération.
- Modify: `heartbeat_wake_sweep._serve_one` — `provider == "google_drive"` → `changes = client.list_changes(wake.page_token)` (pagination), `sync_changed_files`, puis `channel.page_token = newStartPageToken` (commit) ; outcome `reindexed`/`no_linked_folder`.
- Métriques : `rag_drive_push_reindex_total{outcome}` → panneau `18-rag-spaces.json`.
- Tests : `test_drive_ingest.py` (parité : `sync_folder_background` et `sync_changed_files` produisent le même document pour le même fichier — test de contrat), `test_google_drive_client_changes.py`, sweep Drive (fichier hors dossier lié ignoré ; `removed`/`trashed` supprime ; verrou occupé → `locked`, réveil ré-enfilé une fois).
- [ ] Commit `feat(rag): Drive push notifications reindex only the changed files of linked folders`.

### Task 4.7 : agenda → départ et badge (P3)

**Files:**
- Modify: `apps/api/src/domains/push_channels/cache_invalidation.py` — pour `google_calendar`, supprimer aussi `heartbeat:departure:{uid}:*` (SCAN borné).
- Frontend : `apps/web/src/components/notifications/*` — badge quand `trigger === 'push'` (i18n `notifications.trigger_push_mail`, `trigger_push_calendar` ×6) ; type `HeartbeatNotification.trigger`.
- Tests : `test_cache_invalidation.py` (départ invalidé), vitest du badge.
- [ ] Commit `feat(heartbeat): calendar push refreshes departure advice; push-triggered notifications say so`.

### Task 4.8 : ADR-261 et documentation
- `docs/architecture/ADR-261-Push-Driven-Heartbeat-Wake-And-Incremental-Drive-Sync.md` ; `GOOGLE_PUSH_CHANNELS.md` (consommateurs réels : invalidation, réveil, Drive) ; `HEARTBEAT_AUTONOME.md` (réveil, FRESH, trigger, présence) ; `.env.*` ; guides how/why ×6 (une phrase) ; `ADR_INDEX.md`, `docs/INDEX.md`.
- [ ] Commit `docs(adr): ADR-261 push-driven wake`.

---

## 6. Lot 6 — Source « Mail » opt-in par libellé (ADR-262)

### Task 6.1 : modèle et migration
- Modify: `apps/api/src/domains/rag_spaces/models.py` — `RAGMailSyncStatus` (= valeurs de `RAGDriveSyncStatus`, réutiliser la classe), `class RAGMailSource(BaseModel)` miroir de `RAGDriveSource` (`label_id`, `label_name`, `thread_count`, `synced_thread_count`, `last_history_id: int | None`, champs de bail), `RAGDocumentSourceType.MAIL = "mail"`, `RAGDocument.mail_source_id` (FK SET NULL), `mail_thread_id: str | None`, `mail_last_message_at: datetime | None` ; index unique `(space_id, label_id)`.
- Migration `f1a2b3c4d5e6` (down `a7c3e9b1d5f2`), `task db:migrate:replay-check`.
- Enregistrement : `alembic/env.py`, `infrastructure/database/registry.py`, `startup/registries.py::import_domain_models` (le module models existe déjà : rien à ajouter, vérifier).
- Test : `tests/unit/domains/rag_spaces/test_models_mail_source.py`.
- [ ] Commit `feat(rag): mail source model (ADR-262)`.

### Task 6.2 : rendu et ingestion
- Modify: `apps/api/src/domains/connectors/clients/google_gmail_client.py` — le client n'a AUCUNE méthode « fil » (vérifié 2026-09-03 : aucun appel à `/threads`). Ajouter `async def get_thread(self, thread_id: str, *, format: str = GMAIL_FORMAT_FULL) -> dict[str, Any]` (`GET /users/me/threads/{id}`, `format`, pas de cache : le contenu part dans un document, pas dans un prompt) et `async def list_threads(self, *, label_ids: list[str], max_results: int, page_token: str | None) -> dict[str, Any]` (`GET /users/me/threads`, `labelIds`) ; tous deux passent par `_make_request` et `apply_max_items_limit` comme `get_history`.
- Create: `apps/api/src/domains/rag_spaces/mail_sync.py` — `render_thread_markdown(thread: dict) -> str` (pur : `# {subject}`, puis par message `## {date} — {from} → {to}` et le corps texte décodé depuis `payload.parts` `text/plain` d'abord, `text/html` converti sinon ; pièces jointes : noms seulement, jamais de contenu ; taille bornée `RAG_MAIL_MAX_THREAD_CHARS=60000`) ; `async def sync_label_background(space_id, source_id, user_id)` (miroir de `sync_folder_background` : verrou, `list_threads(label_ids=[label_id])` paginé et borné `RAG_MAIL_MAX_THREADS_PER_SYNC=200`, `get_thread` par fil, document PENDING `source_type=mail`, `process_document`) ; `async def apply_history(space_id, source_id, user_id, history: dict)` (`labelsAdded` avec le libellé → ingest ; `labelsRemoved` → suppression du document ; `messagesAdded` sur un fil déjà indexé → réingestion).
- Modify: `google_gmail_client.get_history(history_types=("messageAdded","labelAdded","labelRemoved"), label_id=...)` — le paramètre `labelId` de l'API remplace le `"INBOX"` codé en dur quand un libellé est donné.
- Modify: `heartbeat_wake_sweep._serve_one` — après le pré-filtre (indépendamment de son verdict), pour chaque `RAGMailSource` de l'utilisateur : `apply_history` depuis `source.last_history_id` ; outcome `mail_indexed`.
- Config : `core/config/rag_spaces.py` — `rag_spaces_mail_sync_enabled: bool = False`, bornes ci-dessus ; `.env.*`.
- Tests : rendu (golden Markdown, PII : aucune adresse dans le nom de fichier), ingestion (bornes, verrou, document créé PENDING), `apply_history` (ajout/retrait de libellé), sécurité (un libellé d'un autre utilisateur → 404 `hide_existence=True`).
- [ ] Commit `feat(rag): opt-in mail label source, incremental through the push delta`.

### Task 6.3 : API, service, UI
- Router : `POST/GET/DELETE /rag-spaces/{space_id}/mail-sources`, `POST …/{source_id}/sync`, `GET …/sync-status`, `GET /rag-spaces/{space_id}/mail-labels` (liste des libellés via `list_labels`), gardés par `rag_spaces_mail_sync_enabled` et `check_resource_ownership(hide_existence=True)`.
- Service : `RAGSpaceService.list_mail_sources`, `RAGMailSyncService` (link/unlink/status/lock) — miroir de `RAGDriveSyncService`.
- Frontend : `useMailSources.ts` (miroir de `useDriveSources`), `MailLabelPickerDialog.tsx`, section « Sources e-mail » dans la page détail d'espace, types `RAGMailSource` ; i18n ×6 sous `spaces.mail_sources.*` (title, link, unlink, sync, status_*, privacy_note : « Seuls les fils portant ce libellé sont indexés ; retirer le libellé retire le fil. »).
- Tests : `test_router_mail_sources.py`, vitest du dialogue et de la section (a11y : nom accessible, clavier), e2e hermétique du parcours lier → synchroniser → voir le document.
- Docs : ADR-262 ; il n'existe pas de document technique RAG dédié (vérifié 2026-09-03) — mettre à jour `docs/technical/DATABASE_SCHEMA.md` (table `rag_mail_sources`, colonnes `rag_documents`), `docs/technical/HYBRID_SEARCH.md` (types de source), `docs/technical/PII_LOGGING_SECURITY.md` (un fil indexé = contenu personnel dupliqué, opt-in par libellé, suppression en cascade), FAQ/how ×6.
- [ ] Commit `feat(rag): mail sources in the space detail`.

---

## 7. Lot 5 — Honnêteté visible, dashboards, docs de clôture
- Panneaux : `26-product-value.json` ou `13-proactive-heartbeat.json` — seeds du ledger (`recurrence_ledger_seeded` n'est qu'un log : ajouter `recurrence_ledger_seeded_total{origin}` dans `metrics_habits.py`), verrous évalués/tenus (`recurrence_locks_total{shape,outcome}`), présence (`habits_presence_recorded_total`), réveils (`push_wakes_total`, latence).
- `task ratchet:metrics` ; `apps/api/tests/unit/test_metric_coverage_ratchet_guard.py` vert.
- Amendement ADR-214 (§ sources humaines durables, § présence en lecture, § seed et provenance) ; ADR-238 (§ attente honnête : quand une proposition apparaît).
- Mémoire de session : corriger la mémoire habitudes (fait), consigner l'état du programme.
- [ ] Commit `docs: close the silent-loops programme surfaces`.

---

## 8. Plan de test consolidé (à dérouler en revue)

| # | Test | Lot | Type | Oracle |
|---|---|---|---|---|
| T1 | Familles : learning/runtime survivent, conversation/cache purgées, famille inconnue conservée et comptée | 0 | unit | `is_reset_purgeable`, compteur |
| T2 | Registre complet contre `core.constants` (boot) | 0 | garde | `RuntimeError` sur préfixe non déclaré |
| T3 | Reset réel (Redis + PostgreSQL) : ledger, ancre, adaptatif, lastgood, SSE présents après ; HITL/contacts/gmail cache absents ; `tests/agents/test_context_cleanup_on_reset.py` vert | 0 | intégration + agents | présence des clés |
| T4 | Suppression de compte : zéro clé utilisateur résiduelle, clés globales intactes | 0 | unit + intégration | SCAN après |
| T5 | « Tout oublier » supprime rollup, profil, habitudes, ledger, présence | 0/3 | unit | appels + clés |
| T6 | SQL rythme/seed : prédicat partagé, `scheduler`/`web_showroom`/`automation_run` exclus, `channel_` inclus ; bornes union 3 sources | 1 | contrat + PostgreSQL | jours exacts |
| T7 | Fixture prod-like (183 outcomes scheduler nocturnes + 5 web) : seed borné aux jours humains, aucun verrou | 1 | simulation | `evaluate_locks is None` |
| T8 | Reset intra-journée : heures des outcomes bankées au recalcul | 1 | intégration | égalité heure/heure |
| T9 | Run automatisé + ledger verrouillé → ni suggestion ni promotion ; run humain → suggestion + promotion + cooldown | 1 | unit | mocks |
| T10 | Présence : throttle horaire, deux workers, DST, changement de fuseau, feedback accepté flag OFF, visibilité refusée flag OFF, Redis KO fail-open | 3 | unit + intégration | une ligne, bonne date |
| T11 | Pouce → `feedback_at` + présence dans la même transaction ; rollback si le pouce échoue | 3 | unit + intégration | état final |
| T12 | Porte d'inactivité : présence récente sans login → notifié | 3 | unit | résultat `select_target` |
| T13 | Ping client : visible/focus/montée oui ; caché non ; throttle ; non authentifié non ; réseau KO silencieux | 3 | vitest | requêtes interceptées |
| T14 | Rejeu détecteur rollup prod + présence simulée : fenêtre matin oui, présence uniforme non | 3 | simulation | verdicts |
| T15 | Réveil : `processed` enfile, `debounced`/`ignored` non, flag OFF non ; une charge par (user, provider) | 4 | unit | Redis double |
| T16 | Pré-filtre : table de cas mail/agenda | 4 | unit | verdicts + raisons bornées |
| T17 | Balayage : cooldown, source refusée, pré-filtre négatif, éligibilité (bornes/quota/cooldown), deux workers SPOP, tempête | 4 | unit + intégration | outcomes comptés |
| T18 | Contexte FRESH : delta non consommé, section prompt présente, `trigger='push'` persisté | 4 | unit | assertions |
| T19 | Drive : `list_changes` paginé ; fichiers hors dossier lié ignorés ; suppression ; verrou occupé → ré-enfilé une fois ; parité ingest plein/incrémental | 4 | unit + intégration | documents exacts |
| T20 | Jitter : le job de balayage porte un jitter (garde existante) | 4 | garde | vert |
| T21 | Mail : rendu golden, bornes, verrou, `apply_history`, ownership `hide_existence` | 6 | unit + intégration | contenu, 404 |
| T22 | UI Mail : dialogue accessible, clavier, parcours e2e hermétique | 6 | vitest + Playwright | états |
| T23 | Métriques : chaque nouvelle métrique atteint un panneau | 5 | ratchet | baseline non agrandie |
| T24 | Migrations : replay down/up | 3, 6 | `task db:migrate:replay-check` | exit 0 |
| T25 | Portes : `task lint`, `test:backend:unit:fast`, `test:backend:integration`, `tests/agents/`, `test:frontend`, `test:frontend:coverage`, `ci:fast` | tous | gates | sorties citées |
| T26 | Prod (post-déploiement) : reset puis ledger présent ; seed borné ; latence push→notification sur un vrai e-mail IMPORTANT ; `trigger='push'` en base ; présence bankée après ouverture ; profil recalculé | tous | preuve runtime | requêtes citées |

## 9. Cas limites (chacun a un test ci-dessus)

- Redis indisponible : reset, présence, réveil, delta → fail-open, jamais un tour bloqué.
- `conversation.id ≠ user.id` : les motifs de SCAN gardent les deux identifiants ; la décision de purge est par famille, indifférente à cette égalité.
- Changement de fuseau / DST : occurrences et présence datées en local à l'instant de l'événement.
- Utilisateur `habits_enabled=false` : ping et pouce → no-op ; « Tout oublier » complet.
- Telegram (`channel_`) → `channel='web'` → humain ; showroom jamais ; actions programmées jamais, même sans résumé de tokens.
- Multi-workers : SPOP, SET NX, verrou de synchro ; scheduler leader.
- Canal purgé, watch Google vivant : `ignored_unknown`, jamais un réveil.
- Sans connecteur : aucune ancre, aucun réveil ; heartbeat inchangé.
- Tempête de push : debounce existant + charge unique par (user, provider) + cooldown de réveil.
- Ancre history.list expirée (404) : ré-ancrage, outcome `no_signal`, pas de réveil fantôme.
- Libellé Gmail supprimé côté Google : la source passe en `error` avec message explicite ; les documents restent jusqu'au retrait explicite.
- Suppression de compte / RGPD : purge totale (toutes familles utilisateur) et documents Mail supprimés en cascade (FK).

## 10. Ordre d'exécution et jalons
1. Lot 0 (tâches 0.1 → 0.4) — déployable seul, corrige immédiatement la perte d'apprentissage. **Jalon : reset en prod, ledger présent après.**
2. Lot 1 (1.1 → 1.5) — **Jalon : ledger prod nettoyé, candidats « En observation » honnêtes.**
3. Lot 3 (3.1 → 3.5) — flag OFF au déploiement, activation par le propriétaire après lecture des métriques de présence. **Jalon : J+14, verdict de rythme comparé.**
4. Lot 4 (4.1 → 4.8) — flag `PUSH_WAKE_ENABLED` OFF au déploiement, activation après T26. **Jalon : première notification `trigger='push'` en prod.**
5. Lot 6 (6.1 → 6.3) — flag `RAG_SPACES_MAIL_SYNC_ENABLED` OFF au déploiement. **Jalon : un libellé lié, un fil indexé, une recherche qui le retrouve.**
6. Lot 5 — clôture, dashboards, docs, release.

Chaque lot se termine par les portes de la section « Global Constraints » et par une revue de code à froid contre ce plan (couverture spec, placeholders, cohérence des signatures).
