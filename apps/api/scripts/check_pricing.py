#!/usr/bin/env python
"""
Check LLM Model Pricing in Database.

Verification script to ensure LLM model prices are correctly
configured in the database (llm_model_pricing table).

**Objective:**
    - Verify that Alembic migrations have created pricing records
    - List active models with their prices (input/output per million tokens)
    - Detect pricing configuration issues before deployment

**How it works:**
    1. Connect to the database via get_db_context()
    2. SELECT query on llm_model_pricing WHERE is_active = true
    3. Formatted display of the first 15 models

**Usage:**
    cd apps/api
    python scripts/check_pricing.py

**Prerequisites:**
    - DATABASE_URL configured in .env
    - Alembic migrations executed (alembic upgrade head)

**Exit codes:**
    0 - Pricings found in DB
    (no explicit error, but message if DB is empty)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from src.domains.llm.models import LLMModelPricing
from src.infrastructure.database import get_db_context


async def main():
    """Check pricing."""
    async with get_db_context() as db:
        result = await db.execute(select(LLMModelPricing).where(LLMModelPricing.is_active))
        pricings = result.scalars().all()

        if not pricings:
            print("❌ AUCUN pricing en DB!")
            print("→ Il faut initialiser les pricings avec les migrations Alembic")
        else:
            print(f"✅ {len(pricings)} pricings trouvés:")
            for p in pricings[:15]:
                print(
                    f"  - {p.model_name}: "
                    f"${p.input_price_per_1m_tokens}/M in, "
                    f"${p.output_price_per_1m_tokens}/M out"
                )


if __name__ == "__main__":
    asyncio.run(main())
