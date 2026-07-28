# ADR-170: Budget de calcul et garde anti-stagnation de la boucle ReAct

**Statut**: ✅ IMPLEMENTED (2026-07-27)
**Date**: 2026-07-27
**Décideurs**: Équipe LIA

## Contexte

### A — Le temps d'attente humain était facturé à la boucle

`route_from_react_call_model` comparait `time.time() - react_start_time` à
`react_agent_timeout_seconds` (défaut **120 s**). `react_start_time` est posé une
fois par `react_setup_node` et remis à `None` **uniquement par le routeur, en
début de tour**.

Or `react_execute_tools_node` appelle `interrupt()` pour les outils HITL. Un
`interrupt()` lève : le nœud ne retourne jamais, donc aucune mise à jour d'état
n'est persistée et aucun horodatage n'est rafraîchi. La reprise passe par
`Command(resume=…)`, qui **ré-entre au nœud interrompu** — le routeur, où vit la
remise à zéro, ne rejoue pas.

Vérifié sur un graphe LangGraph réel : `router re-ran on resume? False`,
`start_time refreshed? False`, **2,01 s d'horloge murale pour 0,0102 s de
calcul**.

Conséquence pour l'utilisateur : dès qu'une approbation dépassait 120 s, le tour
repris était coupé au routage suivant. Le dernier `AIMessage` portait encore ses
`tool_calls` et aucun contenu, donc `react_agent_result.final_message` revenait
**vide**, le bypass ReAct du nœud de réponse ne se déclenchait pas, et la réponse
était **re-synthétisée par un second appel LLM**. Travail multi-étapes perdu,
coût doublé, métrique enregistrée en `"empty"` — et `react_agent_duration_seconds`
incluait le temps de réflexion humain, faussant les tableaux de latence.

### B — Rien ne détectait la stagnation

Deux plafonds existaient (itérations, temps) ; aucun ne remarque qu'un agent
appelle **exactement le même outil avec exactement les mêmes arguments** en
boucle. Recherche exhaustive sur `src/` et `tests/` (`no_progress`,
`repeated_action`, `identical`, `call_signature`, `seen_calls`, `stagnat`,
`oscillat`) : aucun résultat. Un agent bloqué brûlait le budget entier, les
tokens de l'utilisateur et le quota fournisseur, puis terminait sur un timeout
au lieu d'une réponse.

## Décision

### A — Le budget compte le temps de **calcul**, pas l'horloge murale

Nouvelle clé `react_elapsed_seconds`, incrémentée par `react_call_model_node` de
sa propre durée. Le temps passé en interruption est **structurellement exclu** :
un nœud interrompu ne retourne pas, donc ne charge rien.

`react_start_time` est conservé, mais ne pilote plus le routage : il sert à
dériver `uncharged_wall_seconds = mur − calcul`, journalisé en finalisation et
à l'épuisement du budget. Le nom ne revendique délibérément aucune des deux
composantes : l'attente d'approbation sur un tour interrompu, la surcharge de
graphe sinon (écritures de checkpoint, ordonnancement, routage). Mesuré en
conteneur : **~0,5 s sur un tour sans aucune interruption** — l'appeler
« hitl_wait » aurait fait lire de la surcharge de graphe comme de l'hésitation
utilisateur.

### B — Garde de non-progression

`utils/loop_guard.py` compte les appels d'outil **strictement identiques** dans
le tour. Le 4ᵉ est refusé par un `ToolMessage` récupérable qui dit quoi faire
d'autre ; le 5ᵉ termine le tour. Seuils en `Settings`, documentés dans les deux
`.env`.

Deux propriétés portent la conception :

- **Empreinte HMAC avec le secret serveur.** Seuls le digest et un compteur sont
  stockés : jamais le nom d'outil, jamais les arguments. La table vit dans le
  checkpoint, donc dans PostgreSQL, et les arguments transportent les données de
  l'utilisateur ; un SHA-256 nu d'arguments à faible entropie serait réversible
  par force brute. La clé étant partagée entre workers, le digest reste
  comparable après une reprise HITL sur un autre process — une clé par process
  (la forme habituelle de ce patron) réinitialiserait la garde à chaque reprise.
- **Placement après le saut d'idempotence.** C'est ce qui la rend replay-safe :
  une exécution interrompue ne retourne pas, ses incréments sont écartés avec le
  reste de son travail partiel, et à la reprise seuls les appels sans
  `ToolMessage` sont comptés — exactement une fois. Compter avant le saut
  facturerait deux fois un tour repris et pourrait bloquer un appel légitime.

Le dictionnaire (digest → compteur) attrape aussi l'oscillation A,B,A,B…, qu'un
compteur à créneau unique manquerait ; il est plafonné à 64 signatures.

## Conséquences

**Positives**
- Une approbation lente ne coupe plus le tour ; le travail restant s'exécute.
- Une boucle stérile s'arrête en 5 appels au lieu de brûler 15 itérations.
- `uncharged_wall_seconds` expose ce que la boucle ne facture pas, gratuitement.
- Les tableaux de latence ReAct cessent d'inclure le temps humain.

**Négatives / limites assumées**
- La portion de calcul effectuée avant une interruption est perdue (le nœud n'a
  pas retourné). Fail-open de quelques secondes, jamais fail-closed.
- Un checkpoint antérieur reprend avec un budget neuf et une table vide
  (migration additive) : un tour repris n'est jamais coupé par un état qu'il n'a
  pas eu.
- Deux appels identiques légitimement espacés dans le tour restent sous le seuil
  de 4 ; au-delà, un flux légitime serait refusé. Les seuils sont paramétrables
  et la métrique `react_repeated_calls_total{tool_name,verdict}` permet de
  calibrer avant de durcir.

## Alternatives écartées

- **Repositionner `react_start_time` à la reprise.** Impossible : `interrupt()`
  lève, le nœud ne retourne jamais, aucune mise à jour d'état n'est persistée. On
  ne *peut pas* horodater l'entrée en interruption depuis le nœud.
- **Augmenter le timeout.** Déplace le seuil sans corriger la cause ; une
  approbation peut prendre des heures.
- **Registre anti-boucle en dict de module** (la forme de référence du patron).
  Viole la règle « un singleton ne stocke pas d'état par requête » : multi-worker,
  et la reprise HITL peut atterrir sur un autre process.
- **Ne mémoriser que la dernière empreinte** (créneau unique). Plus économe, mais
  une oscillation A,B,A,B… ne déclenche jamais.

## Références

- Code : `nodes/routing.py::route_from_react_call_model`,
  `nodes/react_nodes.py`, `utils/loop_guard.py`
- État : `agents/models.py` (migration 1.3 → 1.4, partagée avec ADR-169)
- Tests : `tests/unit/domains/agents/utils/test_loop_guard.py`,
  `tests/unit/domains/agents/nodes/test_routing_react.py`
- Métriques : `react_repeated_calls_total`, `react_tool_executions_before_interrupt_total`
