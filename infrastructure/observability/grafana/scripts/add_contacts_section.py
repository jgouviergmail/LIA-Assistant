#!/usr/bin/env python3
"""
Script to add Section 5: Contacts Agent & Task Orchestration to agents_langgraph.json dashboard.
"""

import json
import sys
from pathlib import Path

def add_contacts_section(dashboard_path: Path) -> None:
    """Add Section 5 with 10 panels for Contacts Agent metrics."""

    # Load existing dashboard
    with open(dashboard_path, 'r', encoding='utf-8') as f:
        dashboard = json.load(f)

    # Starting Y position for new section (after existing panels)
    start_y = 78

    # Add new template variables for the section
    new_variables = [
        {
            "name": "agent_name",
            "type": "query",
            "datasource": "$datasource",
            "query": "label_values(agent_node_executions_total, node_name)",
            "multi": True,
            "includeAll": True,
            "current": {
                "text": "All",
                "value": "$__all"
            },
            "label": "Agent Name",
            "refresh": 1
        },
        {
            "name": "tool_name",
            "type": "query",
            "datasource": "$datasource",
            "query": "label_values(agent_tool_invocations_total, tool_name)",
            "multi": True,
            "includeAll": True,
            "current": {
                "text": "All",
                "value": "$__all"
            },
            "label": "Tool Name",
            "refresh": 1
        },
        {
            "name": "operation",
            "type": "query",
            "datasource": "$datasource",
            "query": "label_values(contacts_api_calls_total, operation)",
            "multi": True,
            "includeAll": True,
            "current": {
                "text": "All",
                "value": "$__all"
            },
            "label": "Contacts Operation",
            "refresh": 1
        }
    ]

    # Add variables if not already present
    if 'templating' not in dashboard:
        dashboard['templating'] = {'list': []}

    existing_var_names = {v['name'] for v in dashboard['templating']['list']}
    for var in new_variables:
        if var['name'] not in existing_var_names:
            dashboard['templating']['list'].append(var)

    # Define Section 5 panels
    new_panels = [
        # Row 1: Title
        {
            "type": "row",
            "title": "🤝 CONTACTS AGENT & TASK ORCHESTRATION",
            "collapsed": False,
            "gridPos": {"h": 1, "w": 24, "x": 0, "y": start_y}
        },
        # Panel 1: Contacts Agent Executions
        {
            "id": 501,
            "type": "timeseries",
            "title": "Contacts Agent Executions (Success/Error)",
            "datasource": {"type": "prometheus", "uid": "$datasource"},
            "targets": [
                {
                    "expr": "sum(rate(agent_node_executions_total{node_name=\"contacts_agent\"}[5m])) by (status)",
                    "legendFormat": "{{status}}",
                    "refId": "A"
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "ops",
                    "color": {"mode": "palette-classic"}
                }
            },
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": start_y + 1}
        },
        # Panel 2: Contacts API Calls by Operation
        {
            "id": 502,
            "type": "timeseries",
            "title": "Contacts API Calls by Operation",
            "datasource": {"type": "prometheus", "uid": "$datasource"},
            "targets": [
                {
                    "expr": "sum(rate(contacts_api_calls_total{operation=~\"$operation\"}[5m])) by (operation, status)",
                    "legendFormat": "{{operation}} ({{status}})",
                    "refId": "A"
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "ops",
                    "color": {"mode": "palette-classic"}
                }
            },
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": start_y + 1}
        },
        # Panel 3: Contacts API Latency P95
        {
            "id": 503,
            "type": "timeseries",
            "title": "Contacts API Latency P95",
            "datasource": {"type": "prometheus", "uid": "$datasource"},
            "targets": [
                {
                    "expr": "histogram_quantile(0.95, sum(rate(contacts_api_latency_seconds_bucket{operation=~\"$operation\"}[5m])) by (le, operation))",
                    "legendFormat": "{{operation}}",
                    "refId": "A"
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "s",
                    "color": {"mode": "palette-classic"}
                }
            },
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": start_y + 9}
        },
        # Panel 4: Contacts Results Distribution
        {
            "id": 504,
            "type": "histogram",
            "title": "Contacts Results Distribution",
            "datasource": {"type": "prometheus", "uid": "$datasource"},
            "targets": [
                {
                    "expr": "sum(contacts_results_count_bucket{operation=~\"$operation\"}) by (le, operation)",
                    "legendFormat": "{{operation}}",
                    "refId": "A"
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "short",
                    "color": {"mode": "palette-classic"}
                }
            },
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": start_y + 9}
        },
        # Panel 5: Contacts Cache Hit Rate
        {
            "id": 505,
            "type": "gauge",
            "title": "Contacts Cache Hit Rate",
            "datasource": {"type": "prometheus", "uid": "$datasource"},
            "targets": [
                {
                    "expr": "sum(rate(contacts_cache_hits_total[5m])) / (sum(rate(contacts_cache_hits_total[5m])) + sum(rate(contacts_cache_misses_total[5m]))) * 100",
                    "refId": "A"
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "percent",
                    "min": 0,
                    "max": 100,
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"value": 0, "color": "red"},
                            {"value": 50, "color": "yellow"},
                            {"value": 80, "color": "green"}
                        ]
                    }
                }
            },
            "gridPos": {"h": 8, "w": 8, "x": 0, "y": start_y + 17}
        },
        # Panel 6: Task Orchestrator Plans Created
        {
            "id": 506,
            "type": "stat",
            "title": "Task Orchestrator Plans Created (24h)",
            "datasource": {"type": "prometheus", "uid": "$datasource"},
            "targets": [
                {
                    "expr": "sum(increase(task_orchestrator_plans_created_total[24h]))",
                    "refId": "A"
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "short",
                    "color": {"mode": "thresholds"}
                }
            },
            "gridPos": {"h": 8, "w": 8, "x": 8, "y": start_y + 17}
        },
        # Panel 7: Orchestrator Agents Distribution
        {
            "id": 507,
            "type": "barchart",
            "title": "Orchestrator Agents Count Distribution",
            "datasource": {"type": "prometheus", "uid": "$datasource"},
            "targets": [
                {
                    "expr": "sum(orchestration_plan_agents_count_bucket) by (le)",
                    "legendFormat": "{{le}} agents",
                    "refId": "A"
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "short",
                    "color": {"mode": "palette-classic"}
                }
            },
            "gridPos": {"h": 8, "w": 8, "x": 16, "y": start_y + 17}
        },
        # Panel 8: Orchestrator Execution Duration P95
        {
            "id": 508,
            "type": "timeseries",
            "title": "Orchestrator Execution Duration P95",
            "datasource": {"type": "prometheus", "uid": "$datasource"},
            "targets": [
                {
                    "expr": "histogram_quantile(0.95, sum(rate(task_orchestrator_execution_duration_seconds_bucket{intention=~\"$intention\"}[5m])) by (le, intention))",
                    "legendFormat": "{{intention}}",
                    "refId": "A"
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "s",
                    "color": {"mode": "palette-classic"}
                }
            },
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": start_y + 25}
        },
        # Panel 9: Agent Tools Invocations
        {
            "id": 509,
            "type": "timeseries",
            "title": "Agent Tools Invocations (Success/Failure)",
            "datasource": {"type": "prometheus", "uid": "$datasource"},
            "targets": [
                {
                    "expr": "sum(rate(agent_tool_invocations_total{tool_name=~\"$tool_name\",agent_name=~\"$agent_name\"}[5m])) by (tool_name, success)",
                    "legendFormat": "{{tool_name}} (success={{success}})",
                    "refId": "A"
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "ops",
                    "color": {"mode": "palette-classic"}
                }
            },
            "gridPos": {"h": 8, "w": 12, "x": 12, "y": start_y + 25}
        },
        # Panel 10: Agent Tools Duration P95
        {
            "id": 510,
            "type": "timeseries",
            "title": "Agent Tools Duration P95",
            "datasource": {"type": "prometheus", "uid": "$datasource"},
            "targets": [
                {
                    "expr": "histogram_quantile(0.95, sum(rate(agent_tool_duration_seconds_bucket{tool_name=~\"$tool_name\",agent_name=~\"$agent_name\"}[5m])) by (le, tool_name))",
                    "legendFormat": "{{tool_name}}",
                    "refId": "A"
                }
            ],
            "fieldConfig": {
                "defaults": {
                    "unit": "s",
                    "color": {"mode": "palette-classic"}
                }
            },
            "gridPos": {"h": 8, "w": 24, "x": 0, "y": start_y + 33}
        }
    ]

    # Add new panels to dashboard
    if 'panels' not in dashboard:
        dashboard['panels'] = []

    dashboard['panels'].extend(new_panels)

    # Save updated dashboard
    with open(dashboard_path, 'w', encoding='utf-8') as f:
        json.dump(dashboard, f, indent=2, ensure_ascii=False)

    print(f"[OK] Added Section 5 with {len(new_panels)} panels to {dashboard_path}")
    print(f"   - New variables: {len(new_variables)}")
    print(f"   - Starting Y position: {start_y}")
    print(f"   - Total panels now: {len(dashboard['panels'])}")

if __name__ == "__main__":
    dashboard_path = Path(__file__).parent.parent / "dashboards" / "agents_langgraph.json"

    if not dashboard_path.exists():
        print(f"[ERROR] Dashboard not found: {dashboard_path}")
        sys.exit(1)

    # Backup original
    backup_path = dashboard_path.with_suffix('.json.backup')
    import shutil
    shutil.copy2(dashboard_path, backup_path)
    print(f"[BACKUP] Created: {backup_path}")

    # Add section
    add_contacts_section(dashboard_path)
