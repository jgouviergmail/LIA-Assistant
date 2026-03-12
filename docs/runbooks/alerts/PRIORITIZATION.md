# Alert Prioritization for Runbook Creation

**Date**: 2025-11-22
**Total Alerts**: 43
**Target Runbooks**: 13 (30% coverage of critical/high-impact alerts)

---

## 🎯 Prioritization Criteria

Alerts are prioritized based on:

1. **Severity** (40% weight):
   - Critical: 10 points
   - Warning: 5 points
   - Info: 2 points

2. **User Impact** (30% weight):
   - Direct user-facing: 10 points
   - Indirect (performance degradation): 7 points
   - Internal only: 3 points

3. **Troubleshooting Complexity** (20% weight):
   - High complexity (needs detailed runbook): 10 points
   - Medium complexity: 6 points
   - Low complexity (obvious fix): 3 points

4. **Historical Frequency** (10% weight):
   - Expected high frequency: 10 points
   - Medium frequency: 6 points
   - Rare: 3 points

**Total Score**: Max 100 points

---

## 📊 Complete Alert Scoring

| # | Alert Name | Severity | User Impact | Complexity | Frequency | Total | Tier |
|---|------------|----------|-------------|------------|-----------|-------|------|
| 1 | **HighErrorRate** | 10 | 10 | 10 | 10 | **40** | **1** |
| 2 | **CriticalLatencyP99** | 10 | 10 | 8 | 8 | **36** | **1** |
| 3 | **CriticalDatabaseConnections** | 10 | 10 | 9 | 7 | **36** | **1** |
| 4 | **DiskSpaceCritical** | 10 | 8 | 6 | 8 | **32** | **1** |
| 5 | **LLMAPIFailureRateHigh** | 10 | 10 | 7 | 6 | **33** | **1** |
| 6 | **ContainerDown** | 10 | 10 | 8 | 6 | **34** | **2** |
| 7 | **DatabaseDown** | 10 | 10 | 6 | 3 | **29** | **2** |
| 8 | **ServiceDown** | 10 | 10 | 6 | 3 | **29** | **2** |
| 9 | **AgentsRouterLatencyHigh** | 10 | 8 | 9 | 7 | **34** | **2** |
| 10 | **CheckpointSaveSlowCritical** | 10 | 7 | 10 | 6 | **33** | **2** |
| 11 | **PKCEValidationFailures** | 10 | 7 | 10 | 4 | **31** | **2** |
| 12 | **DailyCostBudgetExceeded** | 10 | 3 | 8 | 6 | **27** | **2** |
| 13 | **HighDatabaseConnections** | 5 | 7 | 8 | 8 | **28** | **3** |
| 14 | **AgentsStreamingErrorRateHigh** | 10 | 8 | 7 | 6 | **31** | **3** |
| 15 | **HighConversationResetRate** | 5 | 8 | 9 | 7 | **29** | **3** |
| 16 | HighLatencyP95 | 5 | 8 | 6 | 8 | 27 | 3 |
| 17 | RedisDown | 10 | 7 | 6 | 3 | 26 | 3 |
| 18 | StateTokenValidationFailures | 10 | 7 | 9 | 3 | 29 | 3 |
| 19 | HighOAuthFailureRate | 5 | 8 | 7 | 6 | 26 | 3 |
| 20 | DiskSpaceHigh | 5 | 3 | 6 | 8 | 22 | 4 |
| ... | (remaining 23 alerts) | ... | ... | ... | ... | <22 | 4-5 |

---

## 🏆 Selected Alerts for Runbooks (Top 15)

### Tier 1 - Critical User Impact (Score 32-40)
**Priority**: IMMEDIATE - Ces alerts ont impact direct sur utilisateurs et nécessitent action immédiate.

1. **HighErrorRate** (40 pts)
   - **Why**: Direct user errors, frequent, complex troubleshooting
   - **Impact**: Users voient erreurs 500, fonctionnalités cassées
   - **Complexity**: Multiple causes possibles (DB, LLM, code bugs)

2. **CriticalLatencyP99** (36 pts)
   - **Why**: Severe UX degradation, SLA breach
   - **Impact**: Users expérience timeouts, abandons
   - **Complexity**: Network, DB, LLM API, code performance

3. **CriticalDatabaseConnections** (36 pts)
   - **Why**: Saturation imminente = service outage
   - **Impact**: Nouvelles requêtes rejected, cascading failures
   - **Complexity**: Pool sizing, leaks, query performance

4. **LLMAPIFailureRateHigh** (33 pts)
   - **Why**: Core functionality (agents) indisponible
   - **Impact**: Agents ne peuvent pas répondre aux users
   - **Complexity**: External API, quotas, network, config

5. **DiskSpaceCritical** (32 pts)
   - **Why**: Imminent crash si non résolu rapidement
   - **Impact**: Database corruption, logs perdus, service down
   - **Complexity**: Identifier quoi purger sans casser service

---

### Tier 2 - Critical System Health (Score 29-34)
**Priority**: HIGH - Impact système critique mais moins immédiat sur users.

6. **ContainerDown** (34 pts)
   - **Why**: Service component offline
   - **Impact**: Feature/endpoint indisponible
   - **Complexity**: Crash diagnosis, logs analysis

7. **AgentsRouterLatencyHigh** (34 pts)
   - **Why**: Routing bottleneck impacte tous les agents
   - **Impact**: Slow agent responses, user frustration
   - **Complexity**: Router logic, prompts, token limits

8. **CheckpointSaveSlowCritical** (33 pts)
   - **Why**: State persistence failing = data loss risk
   - **Impact**: Conversations perdues, user frustration
   - **Complexity**: DB performance, checkpoint size, serialization

9. **PKCEValidationFailures** (31 pts)
   - **Why**: Security breach attempts ou config issue
   - **Impact**: Legitimate users bloqués OU attackers getting in
   - **Complexity**: OAuth flow debugging, security analysis

10. **DatabaseDown** (29 pts)
    - **Why**: Complete service outage
    - **Impact**: Tout l'application indisponible
    - **Complexity**: DB recovery, backup restore

11. **ServiceDown** (29 pts)
    - **Why**: Main service container crashed
    - **Impact**: Application complètement inaccessible
    - **Complexity**: Root cause analysis, recovery

12. **DailyCostBudgetExceeded** (27 pts)
    - **Why**: Financial impact direct
    - **Impact**: Budget overrun, need CFO escalation
    - **Complexity**: Identify runaway costs, implement controls

---

### Tier 3 - Important Warnings (Score 26-29)
**Priority**: MEDIUM - Warnings importantes qui peuvent escalader en critical.

13. **AgentsStreamingErrorRateHigh** (31 pts)
    - **Why**: Streaming UX cassé
    - **Impact**: Users ne voient pas réponses progressives
    - **Complexity**: SSE, network, browser compat

14. **HighConversationResetRate** (29 pts)
    - **Why**: User experience dégradée
    - **Impact**: Users perdent contexte conversations
    - **Complexity**: State management, memory issues

15. **HighDatabaseConnections** (28 pts)
    - **Why**: Early warning avant saturation
    - **Impact**: Performance degradation imminente
    - **Complexity**: Connection leak hunting

---

## 📋 Runbook Creation Order

Based on prioritization, create runbooks in this order:

### Phase 1 - Immediate (Tier 1: 5 runbooks)
1. ✅ HighErrorRate.md
2. ✅ CriticalLatencyP99.md
3. ✅ CriticalDatabaseConnections.md
4. ✅ LLMAPIFailureRateHigh.md
5. ✅ DiskSpaceCritical.md

### Phase 2 - High Priority (Tier 2: 7 runbooks)
6. ✅ ContainerDown.md
7. ✅ AgentsRouterLatencyHigh.md
8. ✅ CheckpointSaveSlowCritical.md
9. ✅ PKCEValidationFailures.md
10. ✅ DatabaseDown.md
11. ✅ ServiceDown.md
12. ✅ DailyCostBudgetExceeded.md

### Phase 3 - Medium Priority (Tier 3: 3 runbooks)
13. ✅ AgentsStreamingErrorRateHigh.md
14. ✅ HighConversationResetRate.md
15. ✅ HighDatabaseConnections.md

**Total**: 15 runbooks (vs 13 initialement prévu - extended pour meilleure coverage)

---

## 🔗 Diagnostic Scripts Mapping

Chaque runbook sera accompagné d'un script diagnostic automatisé:

| Runbook | Script | Primary Component |
|---------|--------|-------------------|
| HighErrorRate | `diagnose_api_errors.sh` | API |
| CriticalLatencyP99 | `diagnose_api_latency.sh` | API |
| CriticalDatabaseConnections | `diagnose_db_connections.sh` | PostgreSQL |
| LLMAPIFailureRateHigh | `diagnose_llm_api.sh` | LLM/External |
| DiskSpaceCritical | `diagnose_disk_space.sh` | Infrastructure |
| ContainerDown | `diagnose_container_health.sh` | Docker |
| AgentsRouterLatencyHigh | `diagnose_agents_performance.sh` | Agents |
| CheckpointSaveSlowCritical | `diagnose_checkpoint_performance.sh` | Conversations |
| PKCEValidationFailures | `diagnose_oauth_security.sh` | Auth |
| DatabaseDown | `diagnose_database_health.sh` | PostgreSQL |
| ServiceDown | `diagnose_service_health.sh` | Docker |
| DailyCostBudgetExceeded | `diagnose_llm_costs.sh` | LLM/Cost |
| AgentsStreamingErrorRateHigh | `diagnose_agents_streaming.sh` | Agents/SSE |
| HighConversationResetRate | `diagnose_conversations.sh` | Conversations |
| HighDatabaseConnections | `diagnose_db_connections.sh` | PostgreSQL (reuse) |

**Unique Scripts**: 13 (some runbooks share scripts)

---

## 🎯 Success Criteria

Pour considérer Phase 1.3 complète:

- [ ] 15 runbooks créés (tous complets, testés)
- [ ] 13 scripts diagnostics créés (fonctionnels)
- [ ] 1 README principal avec index
- [ ] Tous les liens inter-runbooks fonctionnels
- [ ] Toutes les commandes bash testées
- [ ] Review par au moins 1 personne
- [ ] GitHub issue #31 mise à jour

---

## 📊 Coverage Analysis

**Alert Coverage**:
- Runbooks: 15 / 43 alerts = **35% coverage**
- Critical alerts: 12 / 14 critical alerts = **86% coverage**
- User-facing alerts: 10 / 12 user-facing = **83% coverage**

**Component Coverage**:
- API: 2 runbooks (HighErrorRate, CriticalLatencyP99)
- Database: 3 runbooks (Connections, Down, HighConnections)
- Infrastructure: 3 runbooks (Disk, Container, Service)
- Agents: 3 runbooks (Router, Streaming, Performance)
- LLM: 2 runbooks (API Failures, Costs)
- Auth: 1 runbook (PKCE)
- Conversations: 2 runbooks (Checkpoint, Resets)

**Excellent distribution** couvrant tous les composants critiques.

---

**Next Step**: Créer premier runbook (HighErrorRate) en suivant template standard.
