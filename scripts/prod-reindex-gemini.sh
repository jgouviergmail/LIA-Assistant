#!/bin/bash
# =============================================================================
# v1.14.1 — Post-deployment reindex: OpenAI → Gemini embeddings
#
# Run this AFTER deploying v1.14.1 and running alembic upgrade head.
# Reindexes all embeddings (memories, journals, interests) with Gemini
# gemini-embedding-001 + dual-vector strategy (keyword_embedding).
#
# RAG reindex is triggered separately via admin API (requires auth).
#
# Usage:
#   ssh jgo@192.168.0.14 -p 2222
#   cd /path/to/LIA
#   bash scripts/prod-reindex-gemini.sh
#
# Prerequisites:
#   - v1.14.1 deployed and running
#   - alembic upgrade head completed (keyword_embedding columns exist)
#   - GOOGLE_GEMINI_API_KEY set in .env
#   - API container running as lia-api-prod
# =============================================================================

set -euo pipefail

CONTAINER="lia-api-prod"
SCRIPT="scripts/reindex_embeddings.py"

echo "=============================================="
echo "  v1.14.1 — Gemini Embedding Reindex (PROD)"
echo "=============================================="
echo ""

# Preflight checks
echo "[1/6] Preflight checks..."

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "❌ Container ${CONTAINER} not running. Aborting."
    exit 1
fi

# Verify migration was applied
KEYWORD_COL=$(docker exec "${CONTAINER}" python -c "
from sqlalchemy import text
from src.infrastructure.database.session import sync_engine
with sync_engine.connect() as conn:
    result = conn.execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='memories' AND column_name='keyword_embedding'\"))
    print('ok' if result.fetchone() else 'missing')
" 2>/dev/null || echo "error")

if [ "$KEYWORD_COL" != "ok" ]; then
    echo "❌ keyword_embedding column not found. Run 'alembic upgrade head' first."
    exit 1
fi

echo "✅ Container running, migration applied"
echo ""

# Reindex memories (content + keyword_embedding)
echo "[2/6] Reindexing memories..."
docker exec "${CONTAINER}" python "${SCRIPT}" --only-memories --batch-size 50
echo ""

# Reindex journals (content + keyword_embedding)
echo "[3/6] Reindexing journals..."
docker exec "${CONTAINER}" python "${SCRIPT}" --only-journals --batch-size 50
echo ""

# Reindex interests
echo "[4/6] Reindexing interests..."
docker exec "${CONTAINER}" python "${SCRIPT}" --skip-store --skip-memories --skip-journals --batch-size 50
echo ""

# RAG reindex reminder
echo "[5/6] RAG Spaces reindex..."
echo "⚠️  RAG reindex requires admin API call. Run manually:"
echo "   curl -X POST https://your-domain/api/v1/rag-spaces/admin/reindex \\"
echo "     -H 'Cookie: session_id=YOUR_SESSION_COOKIE'"
echo ""

# Verify
echo "[6/6] Verification..."
docker exec "${CONTAINER}" python -c "
import asyncio
async def check():
    from src.infrastructure.database.session import get_db_context
    from sqlalchemy import text
    async with get_db_context() as db:
        # Memories
        r = await db.execute(text('''
            SELECT count(*) as total,
                   count(embedding) as with_emb,
                   count(keyword_embedding) as with_kw
            FROM memories
        '''))
        row = r.fetchone()
        print(f'  Memories: {row[0]} total, {row[1]} with embedding, {row[2]} with keyword_embedding')

        # Journals
        r = await db.execute(text('''
            SELECT count(*) as total,
                   count(embedding) as with_emb,
                   count(keyword_embedding) as with_kw
            FROM journal_entries
        '''))
        row = r.fetchone()
        print(f'  Journals: {row[0]} total, {row[1]} with embedding, {row[2]} with keyword_embedding')

        # Interests
        r = await db.execute(text('''
            SELECT count(*) as total,
                   count(embedding) as with_emb
            FROM user_interests
        '''))
        row = r.fetchone()
        print(f'  Interests: {row[0]} total, {row[1]} with embedding')

asyncio.run(check())
" 2>/dev/null

echo ""
echo "=============================================="
echo "  ✅ Reindex complete"
echo "=============================================="
