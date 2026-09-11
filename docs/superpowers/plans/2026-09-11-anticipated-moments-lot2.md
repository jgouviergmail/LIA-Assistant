# Lot 2 — Le contrôle, avant l'exploitation

**Spécification** : [2026-09-11-anticipated-moments-design.md](../specs/2026-09-11-anticipated-moments-design.md) §11
**Lot précédent** : [lot 1](2026-09-11-anticipated-moments-lot1.md) — socle livré, vert.
**Méthode** : TDD strict. Inline, aucun sous-agent, aucune action git.

---

## Pourquoi ce lot vient maintenant

Le lot 1 ship un genre de moment et un seul interrupteur : celui de
l'exploitant. Une personne dont le déploiement a la capacité allumée ne peut
aujourd'hui **rien refuser** — et le lot 4 ajoute trois genres de plus. Livrer
les genres avant leur contrôle, c'est trois nouvelles raisons d'être interrompu
sans le moyen d'en refuser une : exactement ce que la leçon d'ADR-214 (« L3, le
contrôle, avant L4, l'exploitation ») interdit.

---

## Périmètre, et ce qui en sort

**Dans le lot** :

1. `users.moment_kinds_disabled` — le refus par genre, en ensemble de REFUS
   (jamais une liste d'autorisations), sur la doctrine ADR-197 : `NULL` veut
   dire « jamais exprimé », donc un genre ajouté plus tard est ON jusqu'à ce que
   quelqu'un le refuse, et les comptes existants ne changent pas de
   comportement.
2. L'API des réglages heartbeat publie et accepte ce refus, plus le vocabulaire
   et les dépendances (ADR-184 : ce qui est appliqué est publié).
3. Le balayage OBÉIT au refus — sans quoi l'interrupteur serait un mensonge.
4. Le panneau de réglages rend un interrupteur par genre.
5. L'historique nomme le déclencheur `moment` à côté de `push`.

**Hors du lot, et c'est un arbitrage, pas un oubli — les puces de réponse.**
La règle 23 demande au modèle une question OUVERTE (« comment ça s'est
passé ? »). Une puce répond à une question fermée ; sous une question ouverte
elle proposerait une réponse que la personne n'a pas pensée, ou pire, la
réduirait à deux boutons. La personne répond en texte libre et
`_inject_proactive_messages` donne au graphe le contexte de la question — c'est
le lot 0 qui l'a prouvé. Les puces reviendront si un genre à question fermée
apparaît (une échéance : « je m'en occupe » / « reporte »), pas avant.

---

## T2.1 — La préférence, côté données

- `users.moment_kinds_disabled` : `JSONB`, nullable, aucun défaut serveur.
- Migration, `down_revision = b4f2a1c9d3e7`, symétrique.
- `moments/preferences.py` : `disabled_kinds_for(user) -> frozenset[str]` et
  `sanitize_disabled_kinds(values) -> list[str]`, calqués sur
  `heartbeat/source_policy.py` — un genre inconnu est SILENCIEUSEMENT écarté à
  l'écriture (un vocabulaire renommé ne doit pas bloquer une sauvegarde), et
  jamais lu comme un refus.

**Tests** : `NULL` égale tout permis ; un refus tient ; un genre inconnu ne
passe pas l'assainissement ; l'ensemble est un REFUS, jamais une autorisation.

---

## T2.2 — Le balayage obéit

Dans `_detect_for` et dans `_serve_one`, un genre refusé n'est ni détecté ni
servi. Le détecter serait payer une lecture calendrier pour une ligne que rien
ne servira ; le servir serait ignorer la préférence.

**Tests** : un genre refusé n'appelle pas son détecteur ; un moment déjà filé
sur un genre depuis refusé n'est pas servi et se règle en `cancelled` (la
personne a changé d'avis : ce n'est pas un échec).

---

## T2.3 — L'API publie ce qu'elle applique

`HeartbeatSettingsResponse` gagne `moment_kinds_disabled`, `all_moment_kinds`
et `moment_kind_dependencies` ; `HeartbeatSettingsUpdate` accepte le premier.

**Tests** : la réponse publie le vocabulaire du registre, pas une copie ; un
`PATCH` remplace l'ensemble en entier ; une valeur inconnue est écartée.

---

## T2.4 — Le panneau

Le composant `HeartbeatSourceSwitches` fait déjà exactement ce travail pour les
sources, avec quatre subtilités payées en production (indisponible n'est pas
refusé ; l'avertissement de dépendance ; le remplacement complet ; le verrou
d'écriture). **Il est généralisé, pas copié** : `RefusalSwitches`, paramétré par
les éléments, le préfixe i18n et la table d'icônes. Les quatorze tests existants
deviennent le filet de la généralisation et restent verts sans être réécrits.

**Tests** : les quatorze existants, plus un jeu pour les genres (un
interrupteur nommé par genre ; « requiert Calendrier » quand le connecteur
manque).

---

## T2.5 — L'historique nomme le déclencheur

`heartbeat.history.trigger_moment` × 6, rendu comme `trigger_push`.

---

## T2.6 — Portes

`task lint`, `task test:backend:unit:fast`, `task test:frontend`,
`task test:frontend:coverage`, parité i18n, cliquets. Preuve runtime : un genre
refusé n'est pas détecté.
