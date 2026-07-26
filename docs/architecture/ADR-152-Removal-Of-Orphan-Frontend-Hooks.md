# ADR-152 : Suppression de trois hooks frontend orphelins

**Status**: ✅ IMPLEMENTED (2026-07-25)
**Date**: 2026-07-25
**Deciders**: jgouvier + Claude
**Technical Story**: Campagne de couverture de tests (séance 2). En cherchant des cibles de test à forte valeur côté frontend, trois hooks sont apparus avec **zéro consommateur** : les tester aurait fabriqué de la couverture sur du code que personne n'exécute.

Cet ADR consigne la décision exigée par la règle systémique de `CLAUDE.md` : *« Dead code is deleted, not kept "for later" … Wire it or remove it — record the decision in a short ADR. »*

## Constat

Recherche exhaustive sur `apps/web/src`, `apps/web/e2e` et `docs/` — les seules occurrences hors définition étaient les ré-exports de `src/hooks/index.ts` :

| Module | Lignes | Consommateurs | Verdict |
|---|---|---|---|
| `src/hooks/useDraftActions.ts` | 187 | 0 | protocole **disparu** du backend |
| `src/types/draft.ts` | 325 | 1 (le hook ci-dessus) | orphelin par ricochet |
| `src/hooks/usePaginatedQuery.ts` | 190 | 0 | jamais câblé, défaut latent |
| `src/hooks/useFormHandler.ts` | 159 | 0 | supplanté par `useApiMutation` |

### `useDraftActions` — un protocole que le backend ne connaît plus

Le hook sérialisait `{"type": "draft_action", draft_id, action, updated_content}` dans un message de chat. `grep -rn '"draft_action"' apps/api/src` ne renvoie **rien** : ce format n'est plus interprété nulle part. [ADR-132](ADR-132-HITL-Approval-Cards.md) l'avait déjà identifié comme orphelin (« Lot 6 jamais câblé … `useDraftActions` orphelin ») et l'a remplacé par `ChatRequest.hitl_decision` → `build_structured_decision`, rendu par `HitlActionCard`. Le hook n'était donc pas seulement mort : il était **cassé**. `src/types/draft.ts` n'existait que pour lui.

### `usePaginatedQuery` — jamais câblé, et déjà porteur d'un défaut

Enveloppe de `useApiQuery` avec tri et pagination. `setSort`/`toggleSort` remettent `page` à 1, mais un changement de la prop `searchQuery` ne le fait pas alors qu'il fait partie des `deps` de la requête : un utilisateur en page 5 qui lance une recherche aurait demandé la page 5 d'un résultat qui n'en a qu'une, et lu « aucun résultat ». Corriger un composant que personne n'utilise n'a pas de valeur ; le supprimer en a.

### `useFormHandler` — supplanté, et pédagogiquement faux

Gestion générique `error` / `isLoading` autour d'une soumission. Le codebase utilise `useApiMutation` pour cela. Son exemple de docstring appelle `fetch` directement, ce que la convention frontend interdit explicitement (« components never call `fetch` directly — use the typed hooks »). Le garder, c'est laisser un exemple qui enseigne l'anti-pattern.

## Décision

Supprimer les quatre fichiers et leurs ré-exports de `src/hooks/index.ts`.

**Ce que la suppression ne coûte pas** : `pnpm exec tsc --noEmit --incremental false` passe sans un seul diagnostic après retrait — rien dans l'application ne référençait ces modules, directement ou par le baril.

**Ce qu'elle rapporte** : 861 lignes de moins à maintenir, un dénominateur de couverture qui ne compte plus de code mort, et un `hooks/index.ts` dont chaque entrée correspond à un hook réellement monté.

## Alternative écartée

**Câbler `usePaginatedQuery`** dans les sections d'administration paginées. Écartée : ces sections gèrent déjà leur pagination, la migration serait une refonte à risque sans bénéfice fonctionnel, et le hook devrait d'abord être corrigé (reset de page sur recherche). Si le besoin d'un socle de pagination partagé réapparaît, il sera écrit depuis les usages réels plutôt que ressuscité depuis une abstraction jamais confrontée à un appelant.

## Conséquences

- Un futur besoin de pagination générique repart d'une page blanche — c'est le prix assumé.
- Le contrat d'approbation HITL n'a plus qu'un seul chemin frontend (`HitlActionCard`), conforme à ADR-132.
