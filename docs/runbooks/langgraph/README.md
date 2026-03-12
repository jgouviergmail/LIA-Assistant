# LangGraph Framework Observability - Runbooks

**Phase**: 2.5 - LangGraph Framework Observability
**Créé**: 2025-11-22
**Maintainer**: Équipe Observability

---

## 📋 Index des Runbooks

### Alertes Critiques (P0-P1)

| Alert | Runbook | Severity | Composant | Impact SLA |
|-------|---------|----------|-----------|------------|
| `LangGraphLowSuccessRate` | [low-success-rate.md](./low-success-rate.md) | Critical | langgraph | Oui |
| `LangGraphHighLatencyP95` | [high-latency.md](./high-latency.md) | Critical | langgraph | Oui |
| `LangGraphHighErrorRate` | [high-error-rate.md](./high-error-rate.md) | Critical | langgraph | Oui |
| `LangGraphRecursionError` | [recursion-error.md](./recursion-error.md) | Critical | langgraph | Oui |
| `LangGraphSystemDegraded` | [system-degraded.md](./system-degraded.md) | Critical | langgraph | Oui |
| `LangGraphStateSizeCritical` | [state-size-critical.md](./state-size-critical.md) | Critical | langgraph | Non |

### Alertes Warning (P2-P5)

| Alert | Runbook | Severity | Composant |
|-------|---------|----------|-----------|
| `LangGraphRouterFallbackAbuse` | [router-fallback-abuse.md](./router-fallback-abuse.md) | Warning | langgraph |
| `LangGraphStatePollution` | [state-pollution.md](./state-pollution.md) | Warning | langgraph |
| `LangGraphSubGraphLowSuccessRate` | [subgraph-low-success.md](./subgraph-low-success.md) | Warning | langgraph |
| `LangGraphReActLoopExcessiveIterations` | [react-loop-excessive.md](./react-loop-excessive.md) | Warning | langgraph |
| `LangGraphStreamingErrors` | [streaming-errors.md](./streaming-errors.md) | Warning | langgraph |

---

## 🎯 Quick Navigation

### Par Priorité (P1-P5)

- **P1 - Graph Execution**: [low-success-rate.md](./low-success-rate.md), [high-latency.md](./high-latency.md), [high-error-rate.md](./high-error-rate.md)
- **P2 - Node Transitions**: [router-fallback-abuse.md](./router-fallback-abuse.md)
- **P3 - State Management**: [state-size-critical.md](./state-size-critical.md), [state-pollution.md](./state-pollution.md)
- **P4 - SubGraphs**: [subgraph-low-success.md](./subgraph-low-success.md), [react-loop-excessive.md](./react-loop-excessive.md)
- **P5 - Streaming**: [streaming-errors.md](./streaming-errors.md)

### Par Symptôme

- **Latence élevée**: [high-latency.md](./high-latency.md), [subgraph-high-latency.md](./subgraph-high-latency.md)
- **Erreurs fréquentes**: [high-error-rate.md](./high-error-rate.md), [recursion-error.md](./recursion-error.md)
- **Performance dégradée**: [system-degraded.md](./system-degraded.md), [performance-degraded.md](./performance-degraded.md)
- **Problèmes mémoire**: [state-size-critical.md](./state-size-critical.md)

---

## 🚨 Escalation Générale

### Critères d'Escalation

Escalader immédiatement si:
- **Success rate** < 80% pendant >10 minutes
- **P95 latency** > 60s pendant >10 minutes
- **Error rate** > 5/s pendant >5 minutes
- **GraphRecursionError** détecté (boucle infinie)
- **Multiple alertes** firing simultanément

### Chemins d'Escalation

**Niveau 1 - On-Call Engineer** (0-15min):
- Slack: `#ops-alerts`
- PagerDuty: Automatic escalation

**Niveau 2 - Team Lead** (15-30min):
- Slack: `#incidents-critical`
- Phone: On-call rotation

**Niveau 3 - Senior Architect** (30min+):
- Email: `architecture@lia.com`
- Phone: Emergency contact list

---

## 📊 Dashboards & Outils

### Grafana Dashboard Principal
**11 - LangGraph Framework Observability**
- URL: `http://localhost:3000/d/langgraph-framework-observability`
- Sections: 5 (Graph Execution, Node Transitions, State, SubGraphs, Streaming)
- Panels: 40+

### Prometheus Queries Utiles

```promql
# Graph success rate (dernières 5 minutes)
(
  sum(rate(langgraph_graph_executions_total{status="success"}[5m]))
  /
  sum(rate(langgraph_graph_executions_total[5m]))
) * 100

# P95 latency graph
histogram_quantile(0.95,
  rate(langgraph_graph_duration_seconds_bucket[5m])
)

# Error rate
sum(rate(langgraph_graph_executions_total{status="error"}[5m]))

# Top error types
topk(5,
  sum by (error_type) (rate(langgraph_graph_errors_total[5m]))
)
```

### Logs Queries

```bash
# Graph execution errors (dernières 30 minutes)
docker-compose logs api --since=30m | grep "langgraph_graph_execution" | grep -i error

# SubGraph failures
docker-compose logs api --since=30m | grep "subgraph.*error"

# State size warnings
docker-compose logs api --since=30m | grep "state_size_bytes.*warning"
```

---

## 🛠️ Diagnostic Tools

### Script Diagnostic Automatisé

```bash
# Diagnostic complet LangGraph
cd infrastructure/observability/scripts
./diagnose_langgraph.sh

# Diagnostic spécifique composant
./diagnose_langgraph.sh --component=graph-execution
./diagnose_langgraph.sh --component=subgraphs
./diagnose_langgraph.sh --component=state
```

### Métriques Check Rapide

```bash
# Check graph success rate
curl -s "http://localhost:9090/api/v1/query?query=sum(rate(langgraph_graph_executions_total{status=\"success\"}[5m]))/sum(rate(langgraph_graph_executions_total[5m]))*100" | jq '.data.result[0].value[1]'

# Check P95 latency
curl -s "http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(langgraph_graph_duration_seconds_bucket[5m]))" | jq '.data.result[0].value[1]'
```

---

## 📚 Documentation Connexe

### Architecture
- [Phase 2.5 Complete Documentation](../../SESSION_5_PHASE_2_5_COMPLETE.md)
- [LangGraph Architecture](../../../architecture/langgraph-framework.md)

### Métriques
- [metrics_langgraph.py](../../../../apps/api/src/infrastructure/observability/metrics_langgraph.py)

### Tests
- [test_metrics_langgraph_execution.py](../../../../apps/api/tests/unit/infrastructure/observability/test_metrics_langgraph_execution.py)
- [test_metrics_langgraph_subgraphs.py](../../../../apps/api/tests/unit/infrastructure/observability/test_metrics_langgraph_subgraphs.py)

---

## 🔄 Maintenance

### Update Frequency
- **Après chaque incident**: Mettre à jour runbook concerné avec learnings
- **Monthly review**: Vérifier tous les runbooks pour accuracy
- **Quarterly audit**: Deep review avec équipe pour améliorations

### Runbook Validation
Chaque runbook doit avoir:
- ✅ Alert definition à jour
- ✅ Commandes testées fonctionnelles
- ✅ Liens dashboards/queries validés
- ✅ Au moins 1 dry-run effectué
- ✅ Review par 2+ personnes équipe

---

## 📝 Template

Pour créer un nouveau runbook, utiliser:
```bash
cp docs/runbooks/alerts/TEMPLATE.md docs/optim_monitoring/runbooks/langgraph/[new-runbook].md
```

---

## 📞 Contact

**Questions sur les runbooks**:
- Slack: `#observability`
- Email: `observability@lia.com`

**Feedback & Améliorations**:
- GitHub Issues: [lia/issues](https://github.com/lia/issues)
- Label: `observability`, `phase-2.5`

---

**Dernière mise à jour**: 2025-11-22
**Version**: 1.0.0
