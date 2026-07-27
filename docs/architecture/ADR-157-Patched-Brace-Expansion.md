# ADR-157: Corriger `brace-expansion` par un patch d'interop plutôt que par une simple montée de version

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA

## Contexte

Alerte Dependabot **#192** sur la branche par défaut, sévérité **high** :
`GHSA-mh99-v99m-4gvg` / `CVE-2026-14257` — déni de service par expansion
d'accolades non bornée. `expand()` borne le **nombre** de résultats (`max`,
100 000 par défaut) mais pas leur **longueur** : en chaînant N groupes, le
compte reste sous `max` tandis que chaque résultat grandit d'un caractère par
groupe. `'{a,b}'.repeat(1500)` — 7,5 Ko d'entrée — fait construire
`max × 1500` caractères et tue le processus Node par un **abandon OOM V8
non rattrapable** (`try/catch` n'y peut rien).

L'alerte traînait, neutralisée dans `pnpm.auditConfig.ignoreGhsas`. Ce qui
suit a été **mesuré**, pas supposé.

### Ce que la version installée faisait réellement

Le dépôt forçait `brace-expansion@^2.1.2` par `pnpm.overrides`. Or ce paquet
est un **publish bâclé** :

| Fichier | Contenu | Atteignable ? |
|---|---|---|
| `index.js` (`main`) | ancien code, **aucune borne de longueur** | **oui**, c'est ce que `require()` charge |
| `dist/commonjs/index.js` | code borné (`EXPANSION_MAX_LENGTH`) | non — aucun champ `exports` n'y mène |

Pire, ce `dist/` est inexécutable dans le contexte du paquet : il appelle
`balanced_match_1.balanced(...)` (export nommé, `balanced-match@4`) alors que
`brace-expansion@2.1.2` déclare `balanced-match: ^1.0.0`, qui exporte une
fonction par défaut → `TypeError: balanced_match_1.balanced is not a function`.

**Reproduction du DoS** sur le point d'entrée réellement chargé, tas contraint
à 512 Mo : `exit 134` (SIGABRT, erreur fatale V8). L'alerte n'était donc **pas**
un faux positif, et la suppression d'audit masquait un défaut réel.

### Pourquoi `overrides: ^5.0.8` ne suffit pas

`5.0.8` est la **seule** version corrigée : aucune publication sur les lignes
1.x–4.x après le 2026-07-23. Mais elle ne publie plus que l'export **nommé**
`expand` (`exports.expand = expand`, aucun `module.exports = fn`), alors que
les deux `minimatch` de l'arbre la chargent en export par défaut :

| Consommateur | Chargement | Attend |
|---|---|---|
| `minimatch@3.1.5` | `var expand = require('brace-expansion'); expand(p)` | fonction par défaut |
| `minimatch@9.0.9` | `__importDefault(require(...)).default(p)` | fonction par défaut |
| `minimatch@10.x` (absent du graphe) | `require(...).expand` | export nommé |

Vérifié, pas supposé : avec `^5.0.8` nu, ESLint meurt avant d'analyser un seul
fichier — `TypeError: expand is not a function` à `minimatch.js:271`.

Les sept consommateurs de `minimatch` sont de l'outillage ESLint (`eslint`,
`@eslint/config-array`, `@eslint/eslintrc`, `@typescript-eslint/typescript-estree`,
`eslint-plugin-{import,jsx-a11y,react}`). **ESLint est donc le test
d'intégration réel de ce changement.**

## Décision

Monter l'override à **`^5.0.8`** — le vrai correctif amont — et rétablir
l'interop CJS par un **patch pnpm de 4 lignes de code** :

```js
module.exports = expand;
module.exports.expand = expand;
module.exports.EXPANSION_MAX = exports.EXPANSION_MAX;
module.exports.EXPANSION_MAX_LENGTH = exports.EXPANSION_MAX_LENGTH;
```

`__esModule` n'est **pas** posé : le helper `__importDefault` de minimatch@9
enveloppe alors la fonction en `{ default: fn }` comme pour tout module CJS
ordinaire. Les trois formes de chargement fonctionnent simultanément.

Le point capital : **on ne porte pas à la main une correction de sécurité**.
Le code qui borne la longueur est celui de l'amont, tel quel ; le patch ne
touche qu'à la surface d'export.

`pnpm.auditConfig.ignoreGhsas` est **supprimé** : la vulnérabilité est
réellement corrigée, et garder la suppression masquerait le prochain avis sur
ce paquet.

### Conséquences opérationnelles

- `patches/brace-expansion@5.0.8.patch` est versionné, et `pnpm-lock.yaml`
  enregistre son **hash** : un patch altéré fait échouer l'installation.
- `pnpm install --frozen-lockfile` **échoue en dur** si le répertoire manque
  (`ENOENT ... patches/brace-expansion@5.0.8.patch`, exit 127) — vérifié. Les
  deux Dockerfiles web (`Dockerfile.dev`, `Dockerfile.prod`) copient désormais
  `patches/` avant l'installation ; sans cela le build casse. La CI part d'un
  `actions/checkout` complet, donc rien à y faire.
- Le conteneur `lia-web-dev` doit être **reconstruit**, pas seulement
  redémarré : son `Dockerfile` et son lockfile ont changé.

## Preuves

| Propriété | Mesure |
|---|---|
| DoS reproduit avant | `exit 134` (SIGABRT/OOM), tas 512 Mo, `'{a,b}'.repeat(1500)` |
| DoS neutralisé après | retour en **1,15 s / 282 Mo**, résultat borné tronqué |
| Aucun changement de comportement | **3 032 motifs** (corpus glob réaliste + tirage aléatoire déterministe) s'étendent à l'identique entre 2.1.2 et 5.0.8 patché |
| Sélection de fichiers ESLint inchangée | ratchet react-hooks **34 violations sur 29 fichiers**, chiffre identique avant/après |
| Chaîne réelle | `eslint → minimatch@3.1.5 → brace-expansion` résout vers la copie **patchée** |
| Audit | `pnpm audit` vert **sans** suppression |
| Porte complète | `task lint:frontend` vert (ESLint + 3 ratchets + `tsc` non incrémental) |

## Alternatives écartées

- **Laisser en l'état, documenter « outillage seulement »** — le DoS est réel
  et reproductible ; un motif glob vient de la configuration du dépôt
  aujourd'hui, mais un plugin qui lirait un motif de fichier utilisateur suffit
  à le rendre atteignable. Une vulnérabilité connue et neutralisée dans l'audit
  est une dette qui ne se signale plus.
- **`overrides: ^5.0.8` nu** — casse ESLint (mesuré).
- **Porter la borne à la main dans `index.js` de 2.1.2** — nous rendrait
  propriétaires d'un correctif de sécurité écrit par nous, sur du code que nous
  ne maintenons pas. Un portage subtilement faux est pire que pas de correctif.
- **Forcer `minimatch@10` partout** — l'API de `minimatch@3` est une fonction
  (`require('minimatch')(path, pattern)`), celle de 9/10 des exports nommés :
  l'override casserait les six consommateurs qui utilisent la forme historique.
- **Router `dist/commonjs` de 2.1.2 par un patch** — ce build est mort : il
  attend une API de `balanced-match` que le paquet ne déclare pas.

## Non-récurrence

`apps/web/src/__tests__/brace-expansion-patch.guard.test.ts` (14 tests) épingle
les trois propriétés : la borne existe et **tronque réellement**, les trois
formes de chargement CJS répondent, et la sémantique d'expansion est inchangée
sur les motifs glob du dépôt. Prouvé rouge en retirant le shim : 10 tests
tombent, dont les deux formes par défaut et toute la table de sémantique.

## Références

- Avis : `GHSA-mh99-v99m-4gvg`, `CVE-2026-14257`
- Patch : `patches/brace-expansion@5.0.8.patch`
- Garde : `apps/web/src/__tests__/brace-expansion-patch.guard.test.ts`
- Doctrine des lockfiles : [ADR-112](ADR-112-Python-Dependency-Locking.md)
- Une garde exécutable par classe de défaut : [ADR-095](ADR-095-Systemic-Guards-Wave2-Audit.md)
