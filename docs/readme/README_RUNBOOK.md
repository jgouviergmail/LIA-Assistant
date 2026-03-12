# LIA Runbooks

**Version**: 1.0
**Last Updated**: 2025-11-22
**Maintainer**: SRE Team

---

## Overview

This directory contains operational runbooks for troubleshooting and resolving incidents in the LIA production environment. Each runbook provides:

- Alert definition and thresholds
- User-facing and ops-facing symptoms
- Diagnostic procedures with copy-paste ready commands
- Immediate mitigation strategies
- Root cause analysis and permanent fixes
- Escalation paths and incident response guidance

---

## Quick Reference

### Alert → Runbook Mapping

| Alert Name | Severity | Component | Impact | Runbook |
|------------|----------|-----------|--------|---------|
| **HighErrorRate** | Critical | API | Users see 5xx errors | [HighErrorRate.md](./alerts/HighErrorRate.md) |
| **CriticalDatabaseConnections** | Critical | Database | Pool exhaustion → outage | [CriticalDatabaseConnections.md](./alerts/CriticalDatabaseConnections.md) |
| **LLMAPIFailureRateHigh** | Critical | LLM | Core functionality down | [LLMAPIFailureRateHigh.md](./alerts/LLMAPIFailureRateHigh.md) |
| **CriticalLatencyP99** | Critical | API | Severe UX degradation | [CriticalLatencyP99.md](./alerts/CriticalLatencyP99.md) |
| **DiskSpaceCritical** | Critical | Infrastructure | Imminent crash | [DiskSpaceCritical.md](./alerts/DiskSpaceCritical.md) |
| **ContainerDown** | Critical | Infrastructure | Service component offline | [ContainerDown.md](./alerts/ContainerDown.md) |
| **AgentsRouterLatencyHigh** | Warning | Agents | Delayed routing | [AgentsRouterLatencyHigh.md](./alerts/AgentsRouterLatencyHigh.md) |
| **CheckpointSaveSlowCritical** | Warning | Agents | Slow state persistence | [CheckpointSaveSlowCritical.md](./alerts/CheckpointSaveSlowCritical.md) |
| **PKCEValidationFailures** | Warning | Authentication | Auth failures | [PKCEValidationFailures.md](./alerts/PKCEValidationFailures.md) |
| **DatabaseDown** | Critical | Database | Total outage | [DatabaseDown.md](./alerts/DatabaseDown.md) |
| **ServiceDown** | Critical | API | Total outage | [ServiceDown.md](./alerts/ServiceDown.md) |
| **DailyCostBudgetExceeded** | Warning | LLM | Budget overrun | [DailyCostBudgetExceeded.md](./alerts/DailyCostBudgetExceeded.md) |
| **AgentsStreamingErrorRateHigh** | Warning | Agents | Streaming UX broken | [AgentsStreamingErrorRateHigh.md](./alerts/AgentsStreamingErrorRateHigh.md) |
| **HighConversationResetRate** | Warning | Agents | Context loss | [HighConversationResetRate.md](./alerts/HighConversationResetRate.md) |
| **HighDatabaseConnections** | Warning | Database | Preventive alert | [HighDatabaseConnections.md](./alerts/HighDatabaseConnections.md) |

---

## Runbooks by Component

### API (FastAPI)
- [HighErrorRate.md](./alerts/HighErrorRate.md) - Error rate >3%
- [CriticalLatencyP99.md](./alerts/CriticalLatencyP99.md) - P99 latency >1.5s
- [ServiceDown.md](./alerts/ServiceDown.md) - API unreachable

### Database (PostgreSQL)
- [CriticalDatabaseConnections.md](./alerts/CriticalDatabaseConnections.md) - Pool >85%
- [HighDatabaseConnections.md](./alerts/HighDatabaseConnections.md) - Pool >70%
- [DatabaseDown.md](./alerts/DatabaseDown.md) - PostgreSQL unreachable

### LLM (Anthropic Claude)
- [LLMAPIFailureRateHigh.md](./alerts/LLMAPIFailureRateHigh.md) - API failures >3%
- [DailyCostBudgetExceeded.md](./alerts/DailyCostBudgetExceeded.md) - Budget overrun

### Agents (LangGraph)
- [AgentsRouterLatencyHigh.md](./alerts/AgentsRouterLatencyHigh.md) - Router P95 >2s
- [CheckpointSaveSlowCritical.md](./alerts/CheckpointSaveSlowCritical.md) - Checkpoint P95 >3s
- [AgentsStreamingErrorRateHigh.md](./alerts/AgentsStreamingErrorRateHigh.md) - Streaming errors >3%
- [HighConversationResetRate.md](./alerts/HighConversationResetRate.md) - Resets >10%

### Authentication (OAuth/PKCE)
- [PKCEValidationFailures.md](./alerts/PKCEValidationFailures.md) - PKCE failures >5%

### Infrastructure (Docker/System)
- [DiskSpaceCritical.md](./alerts/DiskSpaceCritical.md) - Disk <10% free
- [ContainerDown.md](./alerts/ContainerDown.md) - Container offline

---

## Runbooks by Severity

### Critical (Immediate Action Required)
1. [HighErrorRate.md](./alerts/HighErrorRate.md)
2. [CriticalDatabaseConnections.md](./alerts/CriticalDatabaseConnections.md)
3. [LLMAPIFailureRateHigh.md](./alerts/LLMAPIFailureRateHigh.md)
4. [CriticalLatencyP99.md](./alerts/CriticalLatencyP99.md)
5. [DiskSpaceCritical.md](./alerts/DiskSpaceCritical.md)
6. [ContainerDown.md](./alerts/ContainerDown.md)
7. [DatabaseDown.md](./alerts/DatabaseDown.md)
8. [ServiceDown.md](./alerts/ServiceDown.md)

### Warning (Monitor and Plan)
1. [AgentsRouterLatencyHigh.md](./alerts/AgentsRouterLatencyHigh.md)
2. [CheckpointSaveSlowCritical.md](./alerts/CheckpointSaveSlowCritical.md)
3. [PKCEValidationFailures.md](./alerts/PKCEValidationFailures.md)
4. [DailyCostBudgetExceeded.md](./alerts/DailyCostBudgetExceeded.md)
5. [AgentsStreamingErrorRateHigh.md](./alerts/AgentsStreamingErrorRateHigh.md)
6. [HighConversationResetRate.md](./alerts/HighConversationResetRate.md)
7. [HighDatabaseConnections.md](./alerts/HighDatabaseConnections.md)

---

## Diagnostic Scripts

Automated diagnostic scripts are available in `../../infrastructure/observability/scripts/`:

| Script | Purpose | Runbook |
|--------|---------|---------|
| `diagnose_api_errors.sh` | API error diagnostics | [HighErrorRate.md](./alerts/HighErrorRate.md) |
| `diagnose_api_latency.sh` | API latency analysis | [CriticalLatencyP99.md](./alerts/CriticalLatencyP99.md) |
| `diagnose_db_connections.sh` | Database connection pool | [CriticalDatabaseConnections.md](./alerts/CriticalDatabaseConnections.md) |
| `diagnose_llm_api.sh` | LLM API health | [LLMAPIFailureRateHigh.md](./alerts/LLMAPIFailureRateHigh.md) |
| `diagnose_disk_space.sh` | Disk space analysis | [DiskSpaceCritical.md](./alerts/DiskSpaceCritical.md) |
| `diagnose_container_health.sh` | Container status | [ContainerDown.md](./alerts/ContainerDown.md) |
| `diagnose_agents_performance.sh` | Agent routing performance | [AgentsRouterLatencyHigh.md](./alerts/AgentsRouterLatencyHigh.md) |
| `diagnose_checkpoint_performance.sh` | Checkpoint save latency | [CheckpointSaveSlowCritical.md](./alerts/CheckpointSaveSlowCritical.md) |
| `diagnose_oauth_security.sh` | OAuth/PKCE validation | [PKCEValidationFailures.md](./alerts/PKCEValidationFailures.md) |
| `diagnose_database_health.sh` | PostgreSQL health | [DatabaseDown.md](./alerts/DatabaseDown.md) |
| `diagnose_service_health.sh` | API service health | [ServiceDown.md](./alerts/ServiceDown.md) |
| `diagnose_llm_costs.sh` | LLM cost analysis | [DailyCostBudgetExceeded.md](./alerts/DailyCostBudgetExceeded.md) |
| `diagnose_agents_streaming.sh` | Streaming error diagnostics | [AgentsStreamingErrorRateHigh.md](./alerts/AgentsStreamingErrorRateHigh.md) |

### Usage

```bash
# Navigate to scripts directory
cd infrastructure/observability/scripts

# Make scripts executable (first time only)
chmod +x *.sh

# Run diagnostics
./diagnose_api_errors.sh          # Basic diagnostics
./diagnose_api_errors.sh --detailed  # Extended analysis
```

---

## For On-Call Engineers

### When You Get Paged

1. **Check AlertManager**: Identify the specific alert firing
2. **Find the runbook**: Use the table above to locate the appropriate runbook
3. **Quick health check**: Run the corresponding diagnostic script (if available)
4. **Follow the runbook**: Execute diagnostic steps, then mitigation
5. **Communicate**: Update incident channel with status
6. **Escalate if needed**: Follow escalation path in runbook

### Example Incident Response Flow

```
1. Alert: HighErrorRate fires
2. Find runbook: docs/runbooks/alerts/HighErrorRate.md
3. Run diagnostics: ./diagnose_api_errors.sh
4. Quick check shows: DB connection pool at 95%
5. Immediate mitigation: Kill idle connections (runbook section 5.1)
6. Root cause: Connection leak in new code deployment
7. Permanent fix: Rollback deployment, fix code (runbook section 5.2)
8. Post-incident: Create incident report (runbook section 11)
```

---

## Runbook Structure

All runbooks follow a consistent 15-section structure:

1. **Alert Definition** - PromQL query, thresholds, labels
2. **Symptoms** - What users/ops see
3. **Possible Causes** - Ranked by likelihood with verification
4. **Diagnostic Steps** - Quick check (<2min) + deep dive (5-10min)
5. **Resolution Steps** - Immediate mitigation + root cause fix
6. **Related Dashboards & Queries** - Grafana links, PromQL
7. **Related Runbooks** - Cross-references
8. **Common Patterns & Known Issues** - Historical knowledge
9. **Escalation** - When + who + template
10. **Post-Incident Actions** - Immediate/short-term/long-term
11. **Incident Report Template** - Structured documentation
12. **Additional Resources** - Links to docs, tools
13. **Runbook Metadata** - Version, last updated, reviewers
14. **Validation Checklist** - Production readiness
15. **Notes** - Safety warnings, performance considerations

---

## Monitoring & Alerting

### Prometheus
- **URL**: `http://localhost:9090`
- **Alerts**: `http://localhost:9090/alerts`
- **Targets**: `http://localhost:9090/targets`

### Grafana
- **URL**: `http://localhost:3000`
- **Default credentials**: admin/admin
- **Key dashboards**:
  - Infrastructure Overview: `http://localhost:3000/d/infrastructure-overview`
  - Database Monitoring: `http://localhost:3000/d/database-monitoring`
  - LLM Cost Monitoring: `http://localhost:3000/d/llm-costs`

### AlertManager
- **URL**: `http://localhost:9093`
- **Configuration**: `infrastructure/observability/alertmanager/alertmanager.yml`

---

## LIA Architecture Reference

### Components
- **API**: FastAPI (Python 3.12+) on port 8000
- **Database**: PostgreSQL 16 with SQLAlchemy ORM
- **Cache/Rate Limiting**: Redis
- **LLM**: Anthropic Claude (Opus/Sonnet/Haiku)
- **Agents**: LangGraph multi-agent orchestration
- **Monitoring**: Prometheus + Grafana
- **Alerting**: AlertManager

### Key Directories
```
apps/api/src/
├── core/              # Configuration, dependencies
├── domains/
│   ├── agents/        # LangGraph agents
│   ├── auth/          # OAuth/PKCE
│   └── connectors/    # Google API clients
└── infrastructure/
    ├── database/      # PostgreSQL, sessions
    ├── llm/           # Anthropic client, caching
    ├── observability/ # Metrics, logging, tracing
    └── rate_limiting/ # Redis rate limiter
```

### Common Commands

**Check services**:
```bash
docker-compose ps
docker-compose logs [service] --tail=100
```

**Database**:
```bash
docker-compose exec postgres psql -U lia
```

**Redis**:
```bash
docker-compose exec redis redis-cli
```

**Metrics**:
```bash
curl http://localhost:8000/metrics
curl "http://localhost:9090/api/v1/query?query=[promql]"
```

---

## Contributing to Runbooks

### When to Update a Runbook
- After resolving an incident with new learnings
- When discovering new root causes
- After implementing permanent fixes
- When alert thresholds change

### Update Process
1. Read the runbook before the incident (if possible)
2. Follow the runbook during the incident
3. Document deviations or gaps
4. Update runbook after incident resolution
5. Submit changes for peer review
6. Update "Last Updated" and "Change History"

### Quality Standards
- All commands must be copy-paste ready
- All code examples must be complete (no placeholders)
- All PromQL queries must be tested
- All SQL queries must work on PostgreSQL 16
- All bash commands must handle errors gracefully

---

## Escalation Contacts

### Level 1 - On-Call Engineer (0-15 minutes)
- **Who**: Primary on-call SRE
- **When**: Initial incident response
- **Channel**: #incidents Slack channel

### Level 2 - Senior Engineer / Team Lead (15-30 minutes)
- **Who**: Infrastructure Lead, Database Admin, Security Lead
- **When**: Complex issues, unclear root cause, multiple systems affected
- **Channel**: Escalation via PagerDuty

### Level 3 - Executive (30+ minutes)
- **Who**: CTO, VP Engineering
- **When**: Business impact decisions, major outages, data loss risk
- **Channel**: Direct phone escalation

---

## Resources

### Internal Documentation
- [Architecture Overview](../architecture/README.md)
- [Database Schema](../database/schema.md)
- [API Documentation](../api/README.md)
- [Deployment Guide](../deployment/README.md)

### External Links
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [PostgreSQL Manual](https://www.postgresql.org/docs/16/index.html)
- [Anthropic API Reference](https://docs.anthropic.com/)
- [LangGraph Documentation](https://python.langchain.com/docs/langgraph)

### Incident Management
- **Incident Channel**: #incidents (Slack)
- **Post-Mortem Template**: [templates/post-mortem.md](../templates/post-mortem.md)
- **Incident Reports**: [incidents/](../incidents/)

---

## Maintenance

### Runbook Review Schedule
- **Monthly**: Review all runbooks for accuracy
- **Quarterly**: Update alert thresholds based on SLIs
- **After Major Incidents**: Update affected runbooks immediately
- **After Deployments**: Verify commands still work

### Validation Checklist
Before marking a runbook as production-ready:
- [ ] Alert definition verified in `alerts.yml.template`
- [ ] All commands tested in staging
- [ ] All SQL queries tested against PostgreSQL 16
- [ ] Prometheus queries validated
- [ ] Grafana dashboard links confirmed
- [ ] Escalation contacts verified
- [ ] Diagnostic script created (if applicable)
- [ ] Peer review completed (2+ reviewers)
- [ ] Security review completed (if scripts modify data)

---

## Support

For questions or issues with runbooks:
- **Slack**: #sre-team
- **Email**: sre@lia.example.com
- **GitHub**: [Issues](https://github.com/jgouviergmail/LIA-Assistant/issues)

---

**Last reviewed**: 2025-11-22
**Next review**: 2025-12-22
**Maintained by**: SRE Team
