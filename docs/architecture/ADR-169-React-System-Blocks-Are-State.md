# ADR-169: Les blocs système du tour ReAct sont de l'état, pas des messages

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA

## Contexte

`react_setup_node` construisait les blocs système du tour — prompt ReAct,
contexte mémoire, portrait utilisateur, catalogue de skills — sous forme de
`SystemMessage` **ajoutés à `state["messages"]`**.

Or `_window_messages_for_react` délègue le fenêtrage de l'historique à
`get_windowed_messages(include_system=True)`, qui **hisse tous les
`SystemMessage` en tête**, sans limite de fenêtre. Chaque tour ReAct ajoutait
donc une copie complète du prompt, et toutes les copies passées étaient
renvoyées au modèle à chaque appel.

Trois conséquences, toutes mesurées :

1. **Coût.** `react_agent_prompt.txt` = **840 tokens** (tiktoken cl100k_base).
   Après 3 tours : 2 520 tokens de prompts dupliqués ; après 5 : 4 200 ; après
   10 : 8 400 — **à chaque appel LLM de chaque itération** de la boucle. Mesuré
   sur le code réel : le bloc envoyé passe de 6 143 à 18 409 caractères entre 1
   et 5 tours.

2. **Cache de prompt détruit.** Le préfixe grossissait à chaque tour : aucun
   cache de préfixe fournisseur ne pouvait jamais faire mouche. Cela contredit
   frontalement la doctrine portée par `test_prompt_cache_hygiene.py`.

3. **Incompatibilité Anthropic.** Les anciens blocs hissés en tête et les
   nouveaux ajoutés en fin sont **non consécutifs**.
   `langchain_anthropic._format_messages` lève alors
   `ValueError: Received multiple non-consecutive system messages.`
   Reproduit sur le code réel de LIA : positions système `[0, 1, 5, 6]` dès le
   **2ᵉ tour ReAct** d'une conversation. Latent en pratique — `react_agent` vaut
   `qwen3.5-plus` par défaut — mais un administrateur qui bascule ce type LLM
   sur Claude casse le mode ReAct sans avertissement.

## Décision

Les blocs système du tour deviennent de l'**état** (`react_system_blocks:
list[str]`), jamais des messages. `react_call_model_node` les recompose **en
tête** de la liste envoyée au fournisseur, à chaque itération.

Un filtre de transition accompagne le changement : `_window_messages_for_react`
ne conserve, parmi les `SystemMessage` de l'historique, que ceux préfixés par
`COMPACTION_SUMMARY_MARKER`. Les checkpoints écrits avant ce changement cessent
ainsi de traîner leurs copies périmées.

Résultats mesurés sur 6 configurations (1/3/5 tours × avec/sans compaction) :

| Critère | Avant | Après |
|---|---|---|
| Messages système contigus | ❌ `[0,1,5,6]` | ✅ en tête |
| Formateur Anthropic | ❌ `ValueError` | ✅ accepté |
| Résumé de compaction préservé | ✅ | ✅ |
| Taille du bloc à 5 tours | 18 409 car. | **~3 150 car. (constant)** |
| Préfixe identique entre 1/3/5 tours | ❌ | ✅ **cacheable** |

## Conséquences

**Positives**
- Le prompt ReAct est transporté **exactement une fois**, quel que soit l'âge du fil.
- Le préfixe système redevient stable, donc réellement cacheable.
- Le mode ReAct devient utilisable avec un modèle Anthropic.
- Les checkpoints rétrécissent : les blocs ne s'accumulent plus dans `messages`.

**Négatives / limites assumées**
- Une clé d'état de plus, réécrite à chaque tour (migration 1.3 → 1.4, additive).
- Le filtre de transition est une dette temporaire : il ne sert que les
  checkpoints antérieurs. Il reste néanmoins utile comme garde — un futur nœud
  qui rajouterait un `SystemMessage` dans l'historique retomberait dans le même
  piège, et le filtre l'attrape.

## Alternatives écartées

- **`get_windowed_messages(include_system=False)` sur l'historique.** Corrigeait
  la non-contiguïté en une ligne. **Testé, puis rejeté** : il supprimait aussi le
  `SystemMessage` de compaction, seul porteur de la mémoire conversationnelle
  après compression. Le test l'a montré (`compaction summary preserved? False`)
  avant que le correctif ne soit écrit.
- **Recomposer les blocs à chaque itération plutôt que les stocker.** Ils sont
  déterministes depuis l'état, mais leur construction touche le catalogue de
  skills et le portrait utilisateur ; les recalculer N fois par tour aurait
  échangé un coût en tokens contre un coût en latence.
- **Ne rien faire côté Anthropic et documenter l'incompatibilité.** Aurait laissé
  intacts les deux défauts qui touchent **tous** les fournisseurs (coût, cache).

## Références

- Code : `nodes/react_nodes.py` (`react_setup_node`, `react_call_model_node`,
  `_window_messages_for_react`)
- État : `agents/models.py` (déclaration + migration 1.3 → 1.4)
- Tests : `tests/unit/domains/agents/nodes/test_react_system_blocks.py`
- Doctrine de cache : `tests/unit/domains/agents/prompts/test_prompt_cache_hygiene.py`
