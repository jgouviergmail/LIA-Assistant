#!/usr/bin/env python3
"""
Script to publish/update Grafana dashboards via the API.

Usage:
    python scripts/publish_grafana_dashboards.py [--grafana-url URL] [--api-key KEY]

Environment variables:
    GRAFANA_URL: Grafana URL (default: http://localhost:3001)
    GRAFANA_API_KEY: Grafana API key (if authentication is required)
    GRAFANA_USER: Username (default: admin)
    GRAFANA_PASSWORD: Password (default: admin)
"""

import os
import sys
import json
import argparse
from pathlib import Path

try:
    import requests
except ImportError:
    print("[ERROR] requests module not found")
    print("Install with: pip install requests")
    sys.exit(1)


def log_info(msg):
    print(f"[INFO] {msg}")


def log_success(msg):
    print(f"[SUCCESS] {msg}")


def log_error(msg):
    print(f"[ERROR] {msg}")


def log_warn(msg):
    print(f"[WARN] {msg}")


def load_dashboard(filepath):
    """Load dashboard JSON file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log_error(f"Failed to load {filepath}: {e}")
        return None


def publish_dashboard(grafana_url, auth, dashboard_data):
    """Publish dashboard to Grafana via API"""

    # Prepare payload
    payload = {
        "dashboard": dashboard_data,
        "overwrite": True,
        "message": "Updated via publish_grafana_dashboards.py script"
    }

    # Remove id and version to allow creation/update
    if "id" in payload["dashboard"]:
        del payload["dashboard"]["id"]
    if "version" in payload["dashboard"]:
        del payload["dashboard"]["version"]

    # Set dashboard to not be editable from UI (optional)
    # payload["dashboard"]["editable"] = True

    url = f"{grafana_url}/api/dashboards/db"

    try:
        if auth.get("api_key"):
            headers = {
                "Authorization": f"Bearer {auth['api_key']}",
                "Content-Type": "application/json"
            }
            response = requests.post(url, json=payload, headers=headers, timeout=10)
        else:
            response = requests.post(
                url,
                json=payload,
                auth=(auth['username'], auth['password']),
                timeout=10
            )

        if response.status_code in [200, 201]:
            result = response.json()
            return True, result
        else:
            return False, f"HTTP {response.status_code}: {response.text}"

    except requests.exceptions.Timeout:
        return False, "Timeout connecting to Grafana"
    except requests.exceptions.ConnectionError:
        return False, "Connection error - is Grafana running?"
    except Exception as e:
        return False, str(e)


def check_grafana_health(grafana_url, auth):
    """Check if Grafana is accessible"""
    try:
        url = f"{grafana_url}/api/health"

        if auth.get("api_key"):
            headers = {"Authorization": f"Bearer {auth['api_key']}"}
            response = requests.get(url, headers=headers, timeout=5)
        else:
            response = requests.get(
                url,
                auth=(auth['username'], auth['password']),
                timeout=5
            )

        if response.status_code == 200:
            data = response.json()
            return True, data
        else:
            return False, f"HTTP {response.status_code}"

    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Publish Grafana dashboards")
    parser.add_argument(
        "--grafana-url",
        default=os.getenv("GRAFANA_URL", "http://localhost:3001"),
        help="Grafana URL (default: http://localhost:3001)"
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("GRAFANA_API_KEY"),
        help="Grafana API key (optional, uses basic auth if not provided)"
    )
    parser.add_argument(
        "--username",
        default=os.getenv("GRAFANA_USER", "admin"),
        help="Grafana username for basic auth (default: admin)"
    )
    parser.add_argument(
        "--password",
        default=os.getenv("GRAFANA_PASSWORD", "admin"),
        help="Grafana password for basic auth (default: admin)"
    )
    parser.add_argument(
        "--dashboard",
        help="Specific dashboard file to publish (optional, publishes all if not specified)"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("PUBLISH GRAFANA DASHBOARDS")
    print("=" * 70)
    print()

    # Setup authentication
    auth = {}
    if args.api_key:
        auth["api_key"] = args.api_key
        log_info(f"Using API key authentication")
    else:
        auth["username"] = args.username
        auth["password"] = args.password
        log_info(f"Using basic authentication (user: {args.username})")

    log_info(f"Grafana URL: {args.grafana_url}")

    # Check Grafana health
    log_info("Checking Grafana health...")
    healthy, health_data = check_grafana_health(args.grafana_url, auth)

    if not healthy:
        log_error(f"Grafana not accessible: {health_data}")
        log_warn("Please ensure:")
        log_warn("  1. Grafana is running (docker-compose ps grafana)")
        log_warn("  2. Grafana is accessible at the specified URL")
        log_warn("  3. Credentials are correct")
        print()
        print("To start Grafana:")
        print("  docker-compose up -d grafana")
        print()
        return 1

    log_success("Grafana is healthy")
    print()

    # Find dashboards to publish
    dashboards_dir = Path("infrastructure/observability/grafana/dashboards")

    if args.dashboard:
        # Publish specific dashboard
        dashboard_files = [Path(args.dashboard)]
    else:
        # Publish all dashboards
        dashboard_files = list(dashboards_dir.glob("*.json"))

    if not dashboard_files:
        log_error("No dashboard files found")
        return 1

    log_info(f"Found {len(dashboard_files)} dashboard(s) to publish")
    print()

    # Publish dashboards
    published = 0
    failed = 0

    for filepath in dashboard_files:
        log_info(f"Publishing: {filepath.name}")

        # Load dashboard
        dashboard_data = load_dashboard(filepath)
        if not dashboard_data:
            failed += 1
            continue

        title = dashboard_data.get("title", "Unknown")
        log_info(f"  Title: {title}")
        log_info(f"  Panels: {len(dashboard_data.get('panels', []))}")

        # Publish to Grafana
        success, result = publish_dashboard(args.grafana_url, auth, dashboard_data)

        if success:
            log_success(f"  Published successfully")
            if isinstance(result, dict):
                log_info(f"  Dashboard UID: {result.get('uid', 'N/A')}")
                log_info(f"  Dashboard URL: {result.get('url', 'N/A')}")
            published += 1
        else:
            log_error(f"  Failed: {result}")
            failed += 1

        print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Published: {published}/{len(dashboard_files)}")
    print(f"Failed: {failed}/{len(dashboard_files)}")

    if published > 0:
        print()
        log_success("Dashboards published successfully!")
        print()
        print("Access your dashboards at:")
        print(f"  {args.grafana_url}/dashboards")
        print()
        print("HITL Tool Approval dashboard:")
        print(f"  {args.grafana_url}/d/hitl/07-hitl-tool-approval")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
