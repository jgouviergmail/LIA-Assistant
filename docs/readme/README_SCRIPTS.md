# Scripts - LIA

**Dernière mise à jour** : 2025-11-14

---

## 📁 Organisation

```
scripts/
├── README.md                    # Ce fichier
├── _old/                        # Scripts obsolètes (archivés)
├── grafana/                     # Scripts Grafana dashboards
├── monitoring/                  # Scripts observabilité
├── agents/                      # Scripts agents (inventory, etc.)
└── optim/                       # Scripts d'optimisation et d'analyse
    └── utils/                   # Utilitaires partagés
```

---

## 📂 Scripts par Catégorie

### 🗄️ `_old/` - Scripts Obsolètes

Scripts ONE-TIME déjà exécutés ou obsolètes. Archivés pour référence.

| Script | Description | Raison Archivage |
|--------|-------------|------------------|
| `add_hitl_panels.py` | Ajoute panels HITL au dashboard Grafana | ONE-TIME (déjà exécuté) |

---

### 📊 `grafana/` - Scripts Grafana

Scripts pour gestion des dashboards Grafana.

| Script | Description | Usage |
|--------|-------------|-------|
| `publish_grafana_dashboards.py` | Publie dashboards vers Grafana | `python scripts/grafana/publish_grafana_dashboards.py` |
| `validate_dashboards.py` | Valide JSON dashboards | `python scripts/grafana/validate_dashboards.py` |
| `analyze_dashboard.py` | Analyse structure dashboard | `python scripts/grafana/analyze_dashboard.py` |

**Prérequis** :
- Grafana API accessible
- Credentials configurés

---

### 🔍 `monitoring/` - Scripts Observabilité

Scripts pour validation et monitoring de l'observabilité.

| Script | Description | Usage |
|--------|-------------|-------|
| `validate_langfuse_integration.py` | Valide intégration Langfuse v3 | `python scripts/monitoring/validate_langfuse_integration.py` |

**Prérequis** :
- Langfuse API credentials dans `.env`
- Au moins 1 LLM call généré (traces)

**Note** : Cache hits ne génèrent pas de traces Langfuse (by design).

---

### 🤖 `agents/` - Scripts Agents

Scripts pour analyse et inventaire des agents.

| Script | Description | Usage |
|--------|-------------|-------|
| `list_tools.py` | Inventaire automatique des tools LangChain | `python scripts/agents/list_tools.py` |

**Output** :
- `docs/agents/tool_inventory.json`
- `docs/agents/tool_inventory.md`

**Méthode** : AST parsing des décorateurs `@tool`

---

### 🧠 `patterns/` - Scripts Pattern Learning

Scripts pour la gestion et l'entraînement du système Plan Pattern Learning.

| Script | Description | Usage |
|--------|-------------|-------|
| `manage_plan_patterns.py` | CLI gestion patterns (list, stats, delete, export, import, seed) | `python apps/api/scripts/manage_plan_patterns.py --help` |
| `train_pattern_learner.py` | Entraînement via queries automatiques | `python apps/api/scripts/train_pattern_learner.py --help` |

---

#### Commandes de Gestion (manage_plan_patterns.py)

```bash
# Lister patterns
task patterns:list              # Tous les patterns (triés par confiance)
task patterns:list:suggerable   # Patterns suggérables (≥75% confiance)
task patterns:list:bypassable   # Patterns bypassables (≥90% confiance)

# Détails et statistiques
task patterns:stats             # Statistiques globales
task patterns:show -- "get_contacts→filter"  # Détails d'un pattern

# Gestion
task patterns:delete -- "PATTERN_KEY"        # Supprimer un pattern
task patterns:reset                          # ⚠️ Supprimer TOUS les patterns

# Import/Export
task patterns:export -- output.json          # Export JSON
task patterns:import -- input.json           # Import JSON

# Seeding manuel
task patterns:seed -- "get_contacts→filter --domains contacts --intent search"
```

---

#### Commandes d'Entraînement (train_pattern_learner.py)

**Prérequis** :
```bash
task patterns:train:auth        # Vérifier authentification API
```

**Entraînement manuel** :
```bash
task patterns:train -- -q "recherche jean" -q "trouve marie" --repeat 20
task patterns:train:file -- queries.txt --repeat 10
```

**Entraînement par domaine (SAFE - queries read-only)** :

| Commande | Domaine |
|----------|---------|
| `task patterns:train:contacts` | Contacts Google |
| `task patterns:train:emails` | Emails Gmail |
| `task patterns:train:calendar` | Calendar Google |
| `task patterns:train:tasks` | Tasks Google |
| `task patterns:train:drive` | Drive Google |
| `task patterns:train:places` | Places/Maps |
| `task patterns:train:routes` | Routes/Itinéraires |
| `task patterns:train:weather` | Météo |
| `task patterns:train:perplexity` | Recherche Perplexity |
| `task patterns:train:wikipedia` | Wikipedia |
| `task patterns:train:multi` | Multi-domaines |

**Entraînement groupé** :
```bash
task patterns:train:mono        # Tous mono-domaines (SAFE)
task patterns:train:all         # Tous domaines (SAFE)
task patterns:train:all -- --repeat 50  # Avec répétition personnalisée
```

**Entraînement avec mutations (⚠️ UNSAFE - modifie données réelles)** :

| Commande | Action |
|----------|--------|
| `task patterns:train:contacts:unsafe` | Crée/modifie/supprime contacts |
| `task patterns:train:calendar:unsafe` | Crée/modifie/supprime événements |
| `task patterns:train:tasks:unsafe` | Crée/modifie tâches |
| `task patterns:train:multi:unsafe` | Multi-domaines avec mutations (envoie emails!) |
| `task patterns:train:all:unsafe` | ⚠️ TOUS domaines avec mutations |

---

#### Prérequis

- **Redis** : Patterns stockés en Redis (hash `plan:patterns:*`)
- **API** : LIA API en cours d'exécution (pour training)
- **Auth** : Token d'authentification valide (`task patterns:train:auth`)
- **Variables `.env`** : Voir configuration dans [PLAN_PATTERN_LEARNER.md](../technical/PLAN_PATTERN_LEARNER.md)

**Documentation complète** :
- [PLAN_PATTERN_LEARNER.md](../technical/PLAN_PATTERN_LEARNER.md) - Architecture et API
- [PATTERN_LEARNER_TRAINING.md](../technical/PATTERN_LEARNER_TRAINING.md) - Système d'entraînement

---

### 🔧 `optim/` - Scripts d'Optimisation

Scripts pour analyse exhaustive du code et optimisation.

**Créés durant Phase 0-1 de l'optimisation (2025-11-14).**

| Script | Description | Output | Durée |
|--------|-------------|--------|-------|
| `analyze_unused_files.py` | Détecte fichiers non importés | `docs/optim/01_UNUSED_FILES.md` | ~1h |
| `analyze_unused_code.py` | Détecte fonctions/classes non utilisées | `docs/optim/02_UNUSED_CODE.md` | ~2-3h |
| `analyze_constants.py` | Audit constantes (utilisées/inutilisées) | `docs/optim/03_UNUSED_CONSTANTS.md` | ~1h |
| `analyze_magic_values.py` | Détecte magic strings/numbers | `docs/optim/08_MISSING_CONSTANTS.md` | ~1h |
| `analyze_code_duplication.py` | Détecte code dupliqué (pylint) | `docs/optim/05_CODE_DUPLICATION.md` | ~1-2h |
| `analyze_env.py` | Audit .env (clés inutilisées/manquantes) | `docs/optim/09_ENV_AUDIT.md` | ~30min |
| `analyze_performance.py` | Détecte opportunités optimisation | `docs/optim/07_OPTIMIZATION.md` | ~1-2h |

**Prérequis** :
- Python 3.12+
- Environnement virtuel activé (`apps/api/.venv`)
- Dépendances : `pylint`, `radon` (optionnel)

**Utilisation Typique** :
```bash
# Activer environnement virtuel
cd apps/api
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Exécuter analyses
python ../../scripts/optim/analyze_unused_files.py
python ../../scripts/optim/analyze_unused_code.py
# ... etc.

# Tous les rapports générés dans docs/optim/
```

---

### 🛠️ `optim/utils/` - Utilitaires Partagés

Utilitaires génériques réutilisables par les scripts d'optimisation.

| Fichier | Description | Fonctions Principales |
|---------|-------------|----------------------|
| `ast_parser.py` | Parsing AST générique | `parse_file()`, `extract_functions()`, `extract_classes()`, `extract_constants()` |
| `grep_helper.py` | Opérations grep cross-platform | `grep_in_directory()`, `count_occurrences()`, `find_files_importing()` |
| `report_generator.py` | Génération rapports markdown | `generate_markdown_table()`, `generate_finding_report()` |

**Philosophie** :
- Simples (stdlib Python seulement)
- Réutilisables (pas de logique métier)
- Bien documentés (docstrings)
- Testés (si possible)

---

## 🎯 Workflow d'Optimisation

### Phase 0 : Setup
1. ✅ Structure `/docs/optim/` créée
2. ✅ Scripts réorganisés
3. ⏳ Baseline métriques (en cours)

### Phase 1 : Analyse Automatisée
1. ⏳ Création utilitaires (`optim/utils/`)
2. ⏳ Création scripts d'analyse
3. ⏳ Exécution scripts → rapports

### Phase 2 : Vérification Manuelle
- Revue manuelle de chaque finding
- Classification : SAFE_TO_DELETE / KEEP / UNCERTAIN
- Documentation décisions

### Phase 3-6 : Best Practices, Généralisation, Consolidation
- Voir `/docs/optim/00_METHODOLOGY.md`

---

## 📖 Documentation

### Méthodologie Complète
Voir [`/docs/optim/00_METHODOLOGY.md`](../docs/optim/00_METHODOLOGY.md)

### Rapports d'Analyse
Tous dans [`/docs/optim/`](../docs/optim/)

### Itérations
Trackées dans [`/docs/optim/iterations/`](../docs/optim/iterations/)

---

## ⚠️ Principes Importants

### Avant d'Exécuter un Script
1. ✅ Lire la méthodologie (`docs/optim/00_METHODOLOGY.md`)
2. ✅ Comprendre ce que le script fait
3. ✅ Vérifier prérequis (environnement virtuel, dépendances)
4. ✅ Backup si modification de code (git branch)

### Avant de Supprimer du Code
1. ✅ Analyse automatisée d'abord
2. ✅ Vérification manuelle OBLIGATOIRE
3. ✅ Tests passent à 100%
4. ✅ Coverage maintenu ou amélioré
5. ✅ Si doute → KEEP (pas de suppression hasardeuse)

### Versions Figées
**CRITIQUE** : Aucun upgrade de dépendances durant optimisation.

Utiliser versions validées :
- `langfuse==3.9.0`
- `langchain==1.1.2`
- `langchain-core==1.1.1`
- `langgraph==1.0.4`
- etc.

---

## 🤝 Contribution

### Ajouter un Nouveau Script

1. **Choisir catégorie** : `grafana/`, `monitoring/`, `agents/`, `optim/`
2. **Créer script** avec docstring claire
3. **Ajouter entrée** dans ce README.md
4. **Documenter usage** et prérequis
5. **Tester** avant commit

### Archiver un Script Obsolète

1. **Déplacer** vers `_old/`
2. **Mettre à jour** ce README.md
3. **Documenter** raison archivage
4. **Commit** avec message explicite

---

## 📞 Support

Pour questions ou problèmes avec scripts :
1. Lire documentation dans script (docstring)
2. Consulter `/docs/optim/00_METHODOLOGY.md`
3. Vérifier prérequis et environnement

---

**Auteur** : Claude Code (Sonnet 4.5)
**Maintenance** : Développeur solo
**Dernière révision** : 2025-11-14
