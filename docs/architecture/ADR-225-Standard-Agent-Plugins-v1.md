# ADR-225 : support du standard Agent Plugins v1.0.0 — profil « skills + streamable-http MCP »

**Statut**: ✅ IMPLEMENTED (2026-08-17)
**Date**: 2026-08-17
**Origine**: demande propriétaire — implémenter le standard https://agent-plugins.org/specification

## Contexte

Agent Plugins v1.0.0 (agent-plugins.org, TSC : AWS, Cursor, Microsoft, OpenAI,
Vercel) standardise l'empaquetage d'extensions d'agents en **plugins
portables** : un répertoire avec un manifeste `plugin.json` obligatoire
(schéma fermé, `$schema` + `name` requis), des skills découverts sous
`skills/*/SKILL.md` (format agentskills.io) et des serveurs MCP déclarés dans
`mcp.json` (variants fermés `stdio` / `streamable-http` / `sse`). ChatGPT,
Codex, Cursor, GitHub Copilot, Kiro et VS Code le supportent au lancement :
tout plugin publié pour ces clients devient installable par un client
conformant sans adaptation.

L'analyse préalable (7 simulations contre le code, toutes concluantes, rejouées
sur HEAD v1.30.6) a établi :

- le loader de skills LIA implémente déjà agentskills.io — un skill de plugin
  conforme parse tel quel (`domains/skills/loader.py`) ;
- le MCP utilisateur est streamable-http HTTPS uniquement — ce qui suffit à la
  conformité (§ Transport support : au moins un de `stdio`/`streamable-http`) ;
- importer un zip de plugin aujourd'hui est un **faux succès silencieux** :
  `_stage_zip` extrait le premier `SKILL.md` trouvé et jette `plugin.json`,
  `mcp.json` et les autres skills (plus un défaut Windows : le préfixe calculé
  via `Path.parent` en antislashs ne matche jamais les membres zip POSIX) ;
- les noms de plugin admettent les points (`acme.tools`), rejetés par le
  validateur de noms de skills — le nom de plugin exige son propre contrat ;
- `user_mcp_servers` n'a pas de headers HTTP fixes arbitraires, exigés par la
  spec pour les serveurs distants (`headers`), alors que le pool les supporte
  côté admin.

## Décision

**LIA devient un client Agent Plugins conformant sous le profil incrémental
§11.2 : composants « skills » et serveurs MCP « streamable-http ».** Sept lots,
TDD, chacun sans régression sur l'existant.

1. **ADR (ce document)** — positionnement, déviations, arbitrages.
2. **Validation pure** (`domains/plugins/`) — `plugin.json` : schéma fermé
   (champ inconnu → signalé et ignoré, `extensions` non-objet → signalé et
   ignoré, toute autre violation → rejet du plugin, §5.2) ; `mcp.json` :
   schéma fermé, variants fermés, `$schema` cohérent avec `plugin.json`
   (§10.1), entrée invalide → sautée, transport non supporté → sauté (§7.2.2).
   Raisons de rejet = taxonomie de codes stables (pas de string-matching),
   traduites en aval. Le pattern de nom est celui du schéma officiel
   (`plugin.schema.json`), prouvé équivalent au texte normatif.
3. **Pipeline d'import** — un zip contenant `plugin.json` est routé vers le
   pipeline plugin (staging, gardes S1–S4 réutilisées, découverte des skills
   aux **enfants immédiats** de `skills/` §7.1, import par-skill via
   `_finalize` transactionnel, mapping `mcp.json` → serveurs user MCP).
   Échecs par-composant non-fatals + **rapport d'import** exhaustif
   (chargé / sauté / raison) — exigence SHOULD de la spec et doctrine LIA
   anti-faux-succès. Correction du défaut de préfixe Windows au passage.
4. **Persistance** — table `user_plugins` + FK nullable `plugin_id` sur
   `skills` et `user_mcp_servers` (migration additive) ; racine du plugin
   conservée sous `data/plugins/users/{uid}/{nom}/`, skills matérialisés dans
   l'arbre skills existant.
5. **API** — import (upload zip, URL via le fetch durci SSRF existant), liste,
   détail, désinstallation groupée.
6. **Frontend** — section « Plugins » des réglages (import, liste, rapport,
   désinstallation), badges de provenance dans la galerie de skills et la
   liste MCP, i18n ×6, enregistrée dans la recherche des réglages.
7. **Docs** — INDEX, technical doc, README, CHANGELOG ; ratchets relevés.

### Arbitrages actés (propriétaire, 2026-08-17)

- **A** — périmètre v1 : plugins **utilisateur** uniquement (l'admin
  réutilisera le même pipeline ultérieurement).
- **B** — collision de nom de skill (unicité globale de `skills.name`) : le
  skill est **sauté avec raison**, le plugin s'installe partiellement.
- **C** — les `headers` fixes de `mcp.json` sont persistés dans une colonne
  non-secrète `extra_headers` de `user_mcp_servers` et passés en headers par
  défaut du `httpx2.AsyncClient` éphémère (l'auth écrase à nom égal — la
  précédence exacte de §7.2.1).
- **D** — la racine du plugin est conservée sur disque (inspection, mise à
  jour) ; les skills sont matérialisés comme skills utilisateur normaux
  (activation, injection, sandbox inchangés).
- **E** — transport `sse` (OPTIONAL) non supporté : entrées sautées avec
  raison.
- **F** — la suppression individuelle d'un composant appartenant à un plugin
  est bloquée (renvoi vers la désinstallation du plugin) ; l'activation /
  désactivation individuelle reste libre.

### Déviations documentées (client-defined, sans perte de conformité)

- **stdio non supporté** : LIA est un serveur multi-utilisateur — lancer des
  sous-processus arbitraires est exclu. Entrées `stdio` valides → sautées
  « transport non supporté » (§7.2.2 r.4). Conséquence : `PLUGIN_ROOT` /
  `PLUGIN_DATA` (§9) sans objet — aucun sous-processus de plugin n'est lancé.
- **HTTPS strict, loopback inclus** : la spec admet `http://localhost` ; côté
  serveur LIA, une URL loopback désigne le serveur lui-même (SSRF). Ces
  entrées sont sautées avec une raison explicite de politique de sécurité.
- **Secrets** : la spec interdit aux plugins d'embarquer des credentials
  (`headers`, `env`) ; l'authentification d'un serveur importé se configure
  après coup dans les réglages MCP (mécanismes existants, OAuth compris).

## Conséquences

- Les quotas existants s'appliquent aux composants importés (20 skills,
  20 serveurs MCP par utilisateur, valeurs settings) ; le quota est
  pré-vérifié globalement avant toute écriture — pas d'installation
  semi-complète par épuisement en cours de route.
- Un composant importé se comporte ensuite exactement comme son équivalent
  manuel (activation, HITL outils MCP, exécution sandbox) : aucun nouveau
  chemin d'exécution, aucun impact sur le graphe LangGraph.
- La version de spec supportée est épinglée par identifiants canoniques
  (`$schema`) sans jamais récupérer le schéma au chargement (§5.2) ; une
  version future exigera une reconnaissance explicite.
