#!/usr/bin/env python3
"""
Manual test script for the OAuth Health Check system.

Usage:
    # Simulate a token expiring in N minutes
    python scripts/test_oauth_health.py simulate-warning <connector_id> --minutes 30

    # Simulate an expired token
    python scripts/test_oauth_health.py simulate-critical <connector_id>

    # Restore a token (healthy)
    python scripts/test_oauth_health.py restore <connector_id>

    # Manually trigger the health check job
    python scripts/test_oauth_health.py run-job

    # Check a user's health status
    python scripts/test_oauth_health.py check-health <user_id>
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from uuid import UUID

import typer

# Add src to path
sys.path.insert(0, "apps/api")

app = typer.Typer(help="OAuth Health Check Test Utilities")


@app.command()
def simulate_warning(
    connector_id: str,
    minutes: int = typer.Option(30, help="Minutes until expiration"),
):
    """Simulate a token expiring soon (triggers WARNING)."""
    asyncio.run(_simulate_expiration(connector_id, minutes))


@app.command()
def simulate_critical(connector_id: str):
    """Simulate an expired token (triggers CRITICAL)."""
    asyncio.run(_simulate_expiration(connector_id, -60))  # Expired 1 hour ago


@app.command()
def restore(connector_id: str):
    """Restore a connector to healthy state (token valid for 1 hour)."""
    asyncio.run(_simulate_expiration(connector_id, 120))  # Valid for 2 hours


@app.command()
def run_job():
    """Manually trigger the OAuth health check job."""
    asyncio.run(_run_health_job())


@app.command()
def check_health(user_id: str):
    """Check health status of all connectors for a user."""
    asyncio.run(_check_user_health(user_id))


async def _simulate_expiration(connector_id: str, minutes_until_expiry: int):
    """Modify connector credentials to simulate expiration."""
    from src.core.security import decrypt_data, encrypt_data
    from src.domains.connectors.repository import ConnectorRepository
    from src.domains.connectors.schemas import ConnectorCredentials
    from src.infrastructure.database import get_db_context

    async with get_db_context() as db:
        repo = ConnectorRepository(db)
        connector = await repo.get_by_id(UUID(connector_id))

        if not connector:
            typer.echo(f"❌ Connector {connector_id} not found")
            raise typer.Exit(1)

        # Decrypt current credentials
        credentials_json = decrypt_data(connector.credentials_encrypted)
        credentials = ConnectorCredentials.model_validate_json(credentials_json)

        # Modify expires_at
        new_expires_at = datetime.now(UTC) + timedelta(minutes=minutes_until_expiry)
        credentials.expires_at = new_expires_at

        # Re-encrypt and save
        new_credentials_json = credentials.model_dump_json()
        connector.credentials_encrypted = encrypt_data(new_credentials_json)

        await db.commit()

        status = "WARNING" if minutes_until_expiry > 0 else "CRITICAL"
        typer.echo(f"✅ Connector {connector_id} modified")
        typer.echo(f"   Type: {connector.connector_type.value}")
        typer.echo(f"   New expires_at: {new_expires_at}")
        typer.echo(f"   Expected status: {status}")


async def _run_health_job():
    """Run the health check job manually."""
    from src.infrastructure.scheduler.oauth_health import check_oauth_health_all_users

    typer.echo("🔄 Running OAuth health check job...")
    stats = await check_oauth_health_all_users()

    typer.echo("\n📊 Results:")
    typer.echo(f"   Checked: {stats['checked']}")
    typer.echo(f"   Healthy: {stats['healthy']}")
    typer.echo(f"   Warning: {stats['warning']}")
    typer.echo(f"   Critical: {stats['critical']}")
    typer.echo(f"   Notified: {stats['notified']}")


async def _check_user_health(user_id: str):
    """Check health of all connectors for a user."""
    from src.domains.connectors.service import ConnectorService
    from src.infrastructure.database import get_db_context

    async with get_db_context() as db:
        service = ConnectorService(db)
        health = await service.check_connector_health(UUID(user_id))

        typer.echo(f"\n🔍 Health check for user {user_id}")
        typer.echo(f"   Has issues: {health.has_issues}")
        typer.echo(f"   Critical: {health.critical_count}")
        typer.echo(f"   Warning: {health.warning_count}")
        typer.echo(f"   Checked at: {health.checked_at}")

        if health.connectors:
            typer.echo("\n📋 Connectors:")
            for c in health.connectors:
                emoji = "🟢" if c.severity == "info" else "🟡" if c.severity == "warning" else "🔴"
                expires = f" (expires in {c.expires_in_minutes} min)" if c.expires_in_minutes else ""
                typer.echo(f"   {emoji} {c.display_name}: {c.health_status}{expires}")


if __name__ == "__main__":
    app()
