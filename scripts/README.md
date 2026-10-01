# Scripts LIA

> Documentation des scripts utilitaires, déploiement et monitoring.
>
> **Version**: 1.0
> **Date**: 2026-02-02

---

## Table des Matières

- [Setup & Installation](#setup--installation)
- [Voice Models](#voice-models)
- [Deployment](#deployment)
- [Monitoring](#monitoring)
- [Development](#development)
- [Utilities](#utilities)

---

## Setup & Installation

### setup-dev.sh

**Télécharge les modèles ML et configure l'environnement de développement.**

```bash
chmod +x scripts/setup-dev.sh
./scripts/setup-dev.sh
```

**Actions:**
- Rappelle que le modèle STT backend (Whisper Small) est inclus dans l'image Docker
- Rappelle que les modèles du mot de réveil sont versionnés dans
  `apps/web/public/models/wake/` (ADR-329) : rien à télécharger ; `pnpm run dev`
  et `pnpm run build` copient le binaire ONNX Runtime dans `public/ort/`

**Note:** L'entraînement des modèles du mot de réveil vit dans `scripts/wake-word/`
(son README : données, licences, mesures).

---

### install-hooks.sh

**Installe les hooks Git pour le projet.**

```bash
./scripts/install-hooks.sh
```

---

## Voice Models

### download-whisper-model.sh

**Télécharge le modèle Whisper Small INT8 pour le STT backend (Python).**

```bash
./scripts/download-whisper-model.sh [target_dir]
```

**Arguments:**
- `target_dir` - Répertoire cible (défaut: `apps/api/models/whisper-small`)

**Modèle:**
- **Source**: HuggingFace `csukuangfj/sherpa-onnx-whisper-small`
- **Taille**: ~375 MB (INT8 quantized)
- **Langues**: 99+ (FR, EN, DE, ES, IT, ZH, et plus)

**Fichiers téléchargés:**
- `encoder.onnx` (~112 MB)
- `decoder.onnx` (~262 MB)
- `tokens.txt` (~817 KB)

**Configuration `.env`:**
```bash
VOICE_STT_MODEL_PATH=apps/api/models/whisper-small
```

---

## Deployment

### deploy/deploy.sh

**Déploiement général (Linux/Unix).**

```bash
./scripts/deploy/deploy.sh
```

---

### deploy/deploy-prod.ps1

**Déploiement production (Windows PowerShell).**

```powershell
.\scripts\deploy\deploy-prod.ps1
```

---

### deploy/prepare-prod.ps1

**Prépare l'environnement de production (Windows).**

```powershell
.\scripts\deploy\prepare-prod.ps1
```

---

### deploy/generate-secrets.sh

**Génère les secrets pour le déploiement.**

```bash
./scripts/deploy/generate-secrets.sh
```

---

## Monitoring

### monitoring/deploy_hitl_metrics.sh

**Déploie les métriques HITL dans Grafana/Prometheus.**

```bash
./scripts/monitoring/deploy_hitl_metrics.sh
```

---

### monitoring/reset_prometheus_data.sh

**Réinitialise les données Prometheus (ATTENTION: perte de données).**

```bash
./scripts/monitoring/reset_prometheus_data.sh
```

---

### monitoring/reset_observability_data.sh

**Réinitialise toutes les données d'observabilité.**

```bash
./scripts/monitoring/reset_observability_data.sh
```

---

### monitoring/validate_grafana_provisioning.sh

**Valide la configuration Grafana.**

```bash
./scripts/monitoring/validate_grafana_provisioning.sh
```

---

### monitoring/apply-monitoring-fixes.sh

**Applique les correctifs de monitoring.**

```bash
./scripts/monitoring/apply-monitoring-fixes.sh
```

---

## Development

### run-tests-exhaustive.sh

**Exécute tous les tests de manière exhaustive.**

```bash
./scripts/run-tests-exhaustive.sh
```

---

### validate_new_connector.sh

**Valide un nouveau connecteur OAuth.**

```bash
./scripts/validate_new_connector.sh
```

---

## Utilities

### optim/benchmark.sh / benchmark.ps1

**Exécute les benchmarks de performance.**

```bash
./scripts/optim/benchmark.sh
```

```powershell
.\scripts\optim\benchmark.ps1
```

---

### utils/fix-claude-session.ps1

**Corrige les sessions Claude Code (Windows).**

```powershell
.\scripts\utils\fix-claude-session.ps1
```

---

## Structure des Dossiers

```
scripts/
├── deploy/               # Scripts de déploiement
│   ├── deploy.sh         # Déploiement Unix
│   ├── deploy-prod.ps1   # Déploiement Windows
│   ├── prepare-prod.ps1  # Préparation production
│   └── generate-secrets.sh
├── monitoring/           # Scripts d'observabilité
│   ├── deploy_hitl_metrics.sh
│   ├── reset_prometheus_data.sh
│   └── validate_grafana_provisioning.sh
├── optim/                # Benchmarking
│   ├── benchmark.sh
│   └── benchmark.ps1
├── utils/                # Utilitaires divers
│   └── fix-claude-session.ps1
├── download-whisper-model.sh      # Modèle STT backend
├── wake-word/                      # Entraînement du mot de réveil (ADR-329)
├── setup-dev.sh                   # Setup environnement dev
├── install-hooks.sh               # Git hooks
├── run-tests-exhaustive.sh        # Tests complets
├── validate_new_connector.sh      # Validation connecteur
└── README.md                      # Ce fichier
```

---

## Prérequis

- **wget** ou **curl** pour téléchargement de fichiers
- **bash** (Unix) ou **PowerShell** (Windows)
- **Docker** et **docker-compose** pour certains scripts

---

## Références

- [VOICE_MODE.md](../docs/technical/VOICE_MODE.md) - Documentation mode vocal
- [ADR-054: Voice Input Architecture](../docs/architecture/ADR-054-Voice-Input-Architecture.md)
- [Sherpa-onnx](https://k2-fsa.github.io/sherpa/onnx/) - Documentation modèles

---

**Fin de README.md** - Scripts LIA.
