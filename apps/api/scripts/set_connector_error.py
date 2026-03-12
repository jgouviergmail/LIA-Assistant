#!/usr/bin/env python
"""Set a connector status to ERROR for testing the health check modal."""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()


async def main(connector_type: str = "google_drive"):
    import asyncpg

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL not found")
        return

    # Convert to asyncpg format
    db_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    conn = await asyncpg.connect(db_url)

    # Find connector
    row = await conn.fetchrow(
        """
        SELECT c.id, c.connector_type, c.status, u.email
        FROM connectors c
        JOIN users u ON c.user_id = u.id
        WHERE c.connector_type = $1
        AND c.status = 'active'
        LIMIT 1
    """,
        connector_type,
    )

    if row:
        print(f"Found: {row['id']} | {row['connector_type']} | {row['status']} | {row['email']}")

        # Set status to ERROR
        await conn.execute("UPDATE connectors SET status = $1 WHERE id = $2", "error", row["id"])
        print("✓ Status set to ERROR - modal should appear on dashboard refresh")
    else:
        print(f"No active {connector_type} connector found")

    await conn.close()


if __name__ == "__main__":
    connector_type = sys.argv[1] if len(sys.argv) > 1 else "google_drive"
    asyncio.run(main(connector_type))
