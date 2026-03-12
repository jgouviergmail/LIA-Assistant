# SSE Streaming Performance Benchmark

> **Version**: 5.5 | **Status**: Active | **Dernière mise à jour**: 2025-01

Scripts pour mesurer et analyser les performances du streaming SSE des agents LangGraph.

## 🎯 Objectifs

Mesurer les métriques de performance critiques :
- **Time to First Token (TTFT)** : Latence avant le premier token
- **Time to Last Token (TTLT)** : Temps total de génération
- **Tokens per Second** : Débit de génération
- **Router Latency** : Temps de décision du router
- **Total Response Time** : Temps total end-to-end

## 🚀 Utilisation Rapide

### Option 1 : Script Wrapper (Recommandé)

Depuis la racine du projet :

```bash
./scripts/benchmark.sh
```

**Ce script fait automatiquement** :
1. Vérifie que l'API tourne
2. Crée un utilisateur de test si nécessaire
3. S'authentifie automatiquement
4. Exécute les 4 benchmarks
5. Affiche les résultats agrégés

### Option 2 : Exécution Manuelle

Depuis le container API :

```bash
# Avec utilisateur de test (créé automatiquement)
docker compose -f docker-compose.dev.yml exec api python scripts/run_benchmark.py --test-user

# Avec vos propres credentials
docker compose -f docker-compose.dev.yml exec api python scripts/run_benchmark.py \
  --email votre@email.com \
  --password VotrePassword
```

## 📊 Interprétation des Résultats

### Exemple de Sortie

```
========================================
SSE STREAMING PERFORMANCE BENCHMARK
========================================

[1/4] Testing: Bonjour...
  ✅ Router Latency: 245ms
  ✅ Time to First Token: 389ms
  ✅ Time to Last Token: 1456ms
  ✅ Total Tokens: 87
  ✅ Tokens/sec: 82.3
  ✅ Total Time: 1502ms

...

========================================
AGGREGATE RESULTS
========================================

Successful Requests: 4/4
Average Router Latency: 267ms
Average Time to First Token: 412ms
Average Time to Last Token: 1823ms
Average Tokens: 124
Average Tokens/sec: 67.8
Average Total Time: 1891ms

--------------------------------------------------------------------------------
SLA ANALYSIS (Target: TTFT < 1000ms, Tokens/sec > 20)
--------------------------------------------------------------------------------
TTFT < 1000ms: 4/4 (100.0%)
Tokens/sec > 20: 4/4 (100.0%)

========================================
✅ VERDICT: ALL SLA TARGETS MET
========================================
```

### Métriques Clés

| Métrique | Cible | Description | Impact Utilisateur |
|----------|-------|-------------|--------------------|
| **TTFT** | < 1000ms | Latence avant 1er token | Perception réactivité |
| **Tokens/sec** | > 20 | Vitesse génération | Fluidité lecture |
| **Router Latency** | < 500ms | Temps décision routing | Latence initiale |
| **Total Time** | Variable | Temps complet réponse | Satisfaction globale |

### Verdicts

- ✅ **ALL SLA TARGETS MET** : Performances optimales
- ⚠️ **MOST SLA TARGETS MET (>80%)** : Performances acceptables, à surveiller
- ❌ **SLA TARGETS NOT MET** : Investigation requise

## 🔍 Cas d'Usage

### 1. Validation Avant Déploiement

```bash
# Avant merge
./scripts/benchmark.sh > baseline.txt

# Après modifications code
./scripts/benchmark.sh > after_changes.txt

# Comparer
diff baseline.txt after_changes.txt
```

**Objectif** : S'assurer qu'aucune régression de performance.

### 2. Optimisation LLM Config

```bash
# Test 1 : Config actuelle
./scripts/benchmark.sh

# Modifier .env (ex: RESPONSE_LLM_TEMPERATURE=0.5)
docker compose -f docker-compose.dev.yml restart api

# Test 2 : Nouvelle config
./scripts/benchmark.sh
```

**Objectif** : Trouver le meilleur compromis vitesse/qualité.

### 3. Load Testing (Simple)

```bash
# Exécuter 10 fois
for i in {1..10}; do
  echo "=== RUN $i ==="
  ./scripts/benchmark.sh
  sleep 5
done
```

**Objectif** : Vérifier stabilité sous charge répétée.

### 4. Comparaison Modèles

```bash
# Test gpt-4.1-mini
RESPONSE_LLM_MODEL=gpt-4.1-mini ./scripts/benchmark.sh > mini.txt

# Test gpt-4.1-mini
RESPONSE_LLM_MODEL=gpt-4.1-mini ./scripts/benchmark.sh > gpt4o.txt

# Comparer
diff mini.txt gpt4o.txt
```

**Objectif** : Évaluer trade-off coût/performance.

## 🛠️ Personnalisation

### Modifier les Messages de Test

Éditer `apps/api/scripts/benchmark_sse_streaming.py` :

```python
TEST_MESSAGES = [
    "Bonjour",
    "Quel temps fait-il?",
    "Explique-moi la photosynthèse",
    "Rédige un email professionnel",
    # Ajoutez vos messages ici
]
```

### Ajuster les SLA Cibles

Modifier les seuils dans `apps/api/scripts/run_benchmark.py` :

```python
# SLA Analysis
ttft_sla_met = sum(1 for m in successful_metrics if m.time_to_first_token_ms < 1000)  # Modifier 1000
tokens_sla_met = sum(1 for m in successful_metrics if m.tokens_per_second > 20)       # Modifier 20
```

### Tester Endpoint Différent

```bash
docker compose -f docker-compose.dev.yml exec api python scripts/run_benchmark.py \
  --test-user \
  --api-url http://autre-api:8000
```

## 📈 Intégration CI/CD

Ajouter job GitHub Actions pour tracking automatique :

```yaml
benchmark-performance:
  name: Performance Benchmark
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Start services
      run: docker compose -f docker-compose.dev.yml up -d

    - name: Wait for API
      run: sleep 10

    - name: Run benchmark
      run: |
        docker compose -f docker-compose.dev.yml exec -T api \
          python scripts/run_benchmark.py --test-user > benchmark.txt

    - name: Check SLA
      run: |
        if grep -q "ALL SLA TARGETS MET" benchmark.txt; then
          echo "✅ Performance SLA met"
        else
          echo "❌ Performance SLA not met"
          exit 1
        fi

    - name: Upload results
      uses: actions/upload-artifact@v4
      with:
        name: benchmark-results
        path: benchmark.txt
```

## 🐛 Troubleshooting

### Erreur "API container is not running"

```bash
# Démarrer l'API
docker compose -f docker-compose.dev.yml up -d

# Vérifier statut
docker compose -f docker-compose.dev.yml ps
```

### Erreur "Failed to create test user"

```bash
# Vérifier logs PostgreSQL
docker compose -f docker-compose.dev.yml logs postgres

# Vérifier migration DB
docker compose -f docker-compose.dev.yml exec api alembic current
```

### Erreur "HTTP 401 Unauthorized"

```bash
# Vérifier Redis (sessions)
docker compose -f docker-compose.dev.yml logs redis

# Nettoyer sessions Redis
docker compose -f docker-compose.dev.yml exec redis redis-cli FLUSHDB
```

### Résultats incohérents

Causes possibles :
- Cache réseau : Attendre 30s entre tests
- Load variable : Redémarrer containers
- OpenAI API throttling : Utiliser API key avec quota

## 📚 Ressources

- [ADR-009: LangGraph Event Filtering](../../docs/adr/009-langgraph-event-filtering-strategy.md)
- [PROMPTOPS Documentation](../../docs/PROMPTOPS.md)
- [OpenAI Performance Best Practices](https://platform.openai.com/docs/guides/production-best-practices/improving-latencies)

---

**Dernière mise à jour** : 2025-10-20
