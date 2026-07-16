# Grafana Dashboards - LIA

**Derniere mise a jour** : 2026-07-17
**Total Dashboards** : 25 (595 panels)
**Compatibilite** : Grafana 11.3, schemaVersion 38

> **Document de reference** : le catalogue complet (25 dashboards, panels, datasources,
> variables de template, conventions de rendu, troubleshooting, maintenance) est maintenu
> dans **[docs/technical/GRAFANA_DASHBOARDS.md](../technical/GRAFANA_DASHBOARDS.md)**.
> Ce README ne conserve que la lecture par audience (tiers) : il dupliquait auparavant le
> catalogue complet et avait derive trois fois — la duplication est supprimee a dessein.

---

## Architecture en Tiers

Les 25 dashboards sont organises en 5 tiers selon l'audience cible :

| Tier | Audience | Dashboards | Objectif |
|------|----------|------------|----------|
| 1 - Vue d'ensemble | Tous | 01, 02 | Sante globale, SLOs, budget d'erreurs |
| 2 - Plateforme | Ops / Dev | 03, 04, 05, 06 | Infra, HTTP, couts LLM, logs/traces |
| 3 - Fonctionnalites | Feature Dev | 07, 08, 09, 10, 11, 12, 13, 18, 19, 20, 21, 22, 23, 24, 25 | Agents, HITL, conversations, OAuth/MCP, voix, canaux, proactif, RAG, sub-agents, ReAct/browser, sante, compaction, journaux, telephonie, briefing |
| 4 - Avance | SRE | 14, 15, 16 | Registry/checkpoints, LangGraph deep (latence par etage TTFT), sante des recording rules et du registre d'outils |
| 5 - Analytics | Product | 17 | Engagement utilisateurs, geolocalisation |

Points d'entree recommandes : **01 - Application Overview** en cas d'incident (puis
navigation via le tag `lia`), **02 - SLO Tracking** pour le suivi de fiabilite,
**05 - LLM Tokens & Cost** pour le suivi des couts.

## Acces rapide

| Besoin | Voir |
|--------|------|
| Catalogue detaille des 25 dashboards | [GRAFANA_DASHBOARDS.md — Catalogue](../technical/GRAFANA_DASHBOARDS.md#catalogue-des-dashboards) |
| Datasources et variables de template | [GRAFANA_DASHBOARDS.md — Variables et Datasources](../technical/GRAFANA_DASHBOARDS.md#variables-et-datasources) |
| Panel "NO DATA", datasource, scraping | [GRAFANA_DASHBOARDS.md — Troubleshooting](../technical/GRAFANA_DASHBOARDS.md#troubleshooting) |
| Ajouter un panel / un dashboard, conventions | [GRAFANA_DASHBOARDS.md — Maintenance](../technical/GRAFANA_DASHBOARDS.md#maintenance) |
| Stack observabilite complete (Prometheus, Loki, Tempo, alerting) | [README_OBSERVABILITY.md](./README_OBSERVABILITY.md) |
