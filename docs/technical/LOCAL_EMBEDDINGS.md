# Local E5 Embeddings

> **Technical Documentation** - Zero-Cost Semantic Infrastructure
>
> Version: 1.1
> Date: 2025-12-27
> Related: [ADR-049](../architecture/ADR-049-Local-E5-Embeddings.md) | [SEMANTIC_ROUTER.md](SEMANTIC_ROUTER.md)

---

## Overview

> **Note (v1.9.3)**: This document covers E5-small embeddings used by the **Memory** system (long-term psychological profile). The **Journals** system now uses OpenAI `text-embedding-3-small` (1536 dims) via pgvector — see [JOURNALS.md](JOURNALS.md) for details.

Local E5 Embeddings remplace OpenAI text-embedding-3-small par un modèle local HuggingFace pour le système de mémoire. Cette approche élimine les coûts API tout en améliorant la précision de +48% sur les benchmarks Q/A.

### Key Features

- **Zero API Cost** : Inférence 100% locale
- **+48% Accuracy** : 0.90 vs 0.61 sur Q/A matching
- **100+ Languages** : Multilingual natif
- **ARM64 Native** : Fonctionne sur Raspberry Pi 5
- **LangChain Compatible** : Interface drop-in replacement

---

## Model Details

### intfloat/multilingual-e5-small

| Property | Value |
|----------|-------|
| Provider | HuggingFace (intfloat) |
| Dimensions | 384 |
| Languages | 100+ |
| Size | ~470MB |
| Architecture | Transformer encoder |
| Training | Contrastive learning on 1B+ pairs |

### Comparison with OpenAI

| Metric | OpenAI text-embedding-3-small | Local E5-small |
|--------|-------------------------------|----------------|
| Dimensions | 1536 | 384 |
| Cost | $0.02/1M tokens | $0 |
| Latency | 100-300ms (API) | 50ms (local) |
| Q/A Score | 0.61 | **0.90** |
| Offline | No | **Yes** |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  LOCAL EMBEDDINGS STACK                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    APPLICATION LAYER                        │ │
│  │                                                              │ │
│  │   Memory System              Semantic Router                 │ │
│  │   (semantic_store.py)        (tool_selector.py)             │ │
│  │         │                           │                        │ │
│  │         └───────────┬───────────────┘                        │ │
│  │                     ▼                                        │ │
│  │         ┌─────────────────────┐                              │ │
│  │         │ LocalE5Embeddings   │                              │ │
│  │         │ (Wrapper Singleton) │                              │ │
│  │         └─────────────────────┘                              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                            │                                     │
│                            ▼                                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    MODEL LAYER                              │ │
│  │                                                              │ │
│  │   ┌──────────────────────────────────────────────────────┐  │ │
│  │   │ SentenceTransformer (Thread-Safe Singleton)          │  │ │
│  │   │                                                        │  │ │
│  │   │  ┌──────────────────┐   ┌────────────────────────┐   │  │ │
│  │   │  │ Tokenizer        │   │ Transformer Model       │   │  │ │
│  │   │  │ (BPE ~50K vocab) │──▶│ (12 layers, 384 hidden) │   │  │ │
│  │   │  └──────────────────┘   └────────────────────────┘   │  │ │
│  │   │                                     │                  │  │ │
│  │   │                                     ▼                  │  │ │
│  │   │                          ┌──────────────────┐         │  │ │
│  │   │                          │ Mean Pooling     │         │  │ │
│  │   │                          │ + Normalization  │         │  │ │
│  │   │                          └──────────────────┘         │  │ │
│  │   │                                     │                  │  │ │
│  │   │                                     ▼                  │  │ │
│  │   │                          ┌──────────────────┐         │  │ │
│  │   │                          │ 384-dim Vector   │         │  │ │
│  │   │                          │ (normalized)     │         │  │ │
│  │   │                          └──────────────────┘         │  │ │
│  │   └──────────────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Usage

### Basic Usage

```python
from src.infrastructure.llm.local_embeddings import (
    get_local_embeddings,
    LocalE5Embeddings,
)

# Get singleton instance
embeddings = get_local_embeddings()

# Embed single query
vector = embeddings.embed_query("Je me suis marié en 2008")
print(f"Dimensions: {len(vector)}")  # 384

# Embed multiple documents (batch)
docs = [
    "Mon mariage était en été",
    "J'ai deux enfants",
    "Mon travail est passionnant",
]
vectors = embeddings.embed_documents(docs)
print(f"Batch size: {len(vectors)}")  # 3
```

### Async Usage (Recommended)

```python
# Async methods for non-blocking operations
vector = await embeddings.aembed_query("search query")
vectors = await embeddings.aembed_documents(["doc1", "doc2"])
```

### With LangGraph Store

```python
from langgraph.store.postgres import AsyncPostgresStore
from src.infrastructure.llm.local_embeddings import get_local_embeddings

# Create store with local embeddings
store = AsyncPostgresStore(
    connection_string=settings.database_url,
    embedding=get_local_embeddings(),
    embedding_dimensions=384,
)

# Semantic search
results = await store.asearch(
    namespace=("user-123", "memories"),
    query="when did I get married?",
    limit=10,
)
```

---

## Configuration

### Environment Variables

```bash
# .env
MEMORY_EMBEDDING_MODEL=intfloat/multilingual-e5-small
MEMORY_EMBEDDING_DIMENSIONS=384
```

### Settings

```python
# apps/api/src/core/config/agents.py

memory_enabled: bool = True
memory_embedding_model: str = "intfloat/multilingual-e5-small"
memory_embedding_dimensions: int = 384
```

---

## Startup Preloading

Le modèle prend ~9s à charger sur Raspberry Pi 5. Pour éviter la latence sur la première requête, préchargez au démarrage.

### In FastAPI Lifespan

```python
# apps/api/src/main.py

from contextlib import asynccontextmanager
from src.infrastructure.llm.local_embeddings import preload_embedding_model

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Preload E5 model (~9s on Pi 5)
    preload_embedding_model()

    yield  # Application runs

    # Cleanup if needed

app = FastAPI(lifespan=lifespan)
```

### Conditional Preloading

```python
def preload_embedding_model() -> None:
    """
    Preload model during startup.

    Skips if:
    - memory_enabled = False
    - memory_use_local_embeddings = False
    """
    if not settings.memory_enabled:
        logger.info("e5_preload_skipped", reason="memory_disabled")
        return

    embeddings = get_local_embeddings()
    embeddings._get_model()  # Trigger load
    logger.info("e5_preload_completed")
```

---

## Performance

### Benchmarks

| Operation | Time (Pi 5) | Time (x86_64) |
|-----------|-------------|---------------|
| Model Load | ~9s | ~3s |
| Single Embed | ~50ms | ~20ms |
| Batch 10 | ~100ms | ~40ms |
| Batch 100 | ~500ms | ~200ms |

### Memory Usage

| Component | Size |
|-----------|------|
| Model weights | ~350MB |
| Tokenizer | ~120MB |
| Runtime overhead | ~100MB |
| **Total** | **~570MB** |

---

## Thread Safety

### Singleton Pattern

```python
# Thread-safe singleton implementation
_model_lock = threading.Lock()
_embedding_model: SentenceTransformer | None = None

def _get_model(self) -> SentenceTransformer:
    global _embedding_model

    if _embedding_model is not None:
        return _embedding_model

    with _model_lock:
        # Double-check after lock
        if _embedding_model is not None:
            return _embedding_model

        # Load model (thread-safe)
        model = SentenceTransformer(self.model_name, device="cpu")
        _embedding_model = model
        return model
```

### Concurrent Requests

```python
# Multiple async requests share the same model
async def handle_requests():
    embeddings = get_local_embeddings()

    # These run concurrently, share model
    results = await asyncio.gather(
        embeddings.aembed_query("query 1"),
        embeddings.aembed_query("query 2"),
        embeddings.aembed_query("query 3"),
    )
```

---

## Docker Deployment

### Dockerfile.prod

```dockerfile
FROM python:3.12.7-slim-bookworm

# No CUDA needed - CPU-only inference
# PyTorch installs CPU wheels by default (no --index-url cuda)
RUN pip install --no-cache-dir sentence-transformers>=3.0.0
```

### requirements.txt

```txt
# Local Embedding Model - E5 for semantic memory search
# PyTorch is pulled as dependency - pip installs CPU-only by default
# ARM64 (Raspberry Pi): CPU-only wheels automatically
sentence-transformers>=3.0.0
```

### Model Caching

```dockerfile
# Optional: Pre-download model during build
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"
```

---

## Troubleshooting

### Model Download Fails

```bash
# Check HuggingFace cache location
echo $HF_HOME  # Default: ~/.cache/huggingface

# Manual download
python -c "
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('intfloat/multilingual-e5-small')
print('Downloaded successfully')
"
```

### Out of Memory

```python
# Reduce batch size for constrained memory
vectors = []
for batch in chunks(documents, size=10):
    vectors.extend(embeddings.embed_documents(batch))
```

### Slow First Request

```python
# Preload at startup to avoid first-request latency
# See "Startup Preloading" section above
preload_embedding_model()
```

---

## API Reference

### Classes

#### `LocalE5Embeddings`

```python
class LocalE5Embeddings:
    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-small",
        dimensions: int = 384,
    )

    def embed_query(self, text: str) -> list[float]
    def embed_documents(self, texts: list[str]) -> list[list[float]]

    async def aembed_query(self, text: str) -> list[float]
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]
```

### Functions

```python
# Get singleton instance
def get_local_embeddings() -> LocalE5Embeddings

# Preload model at startup
def preload_embedding_model() -> None

# Reset singleton (testing only)
def reset_embedding_model() -> None
```

---

## Benchmark Results

### Q/A Memory Matching Test

```
Test Setup:
  Memory: "Je me suis marié en 2008"
  Queries: ["je me suis marié quand ?", "when did I get married?"]

OpenAI text-embedding-3-small:
  FR→FR: 0.58
  EN→FR: 0.64
  Average: 0.61

Local E5 multilingual-e5-small:
  FR→FR: 0.92
  EN→FR: 0.88
  Average: 0.90

Improvement: +48% accuracy
```

### Running Benchmarks

```bash
# Run benchmark script
cd apps/api
python scripts/test_embedding_models.py
```

---

## Related Documentation

- [ADR-049: Local E5 Embeddings](../architecture/ADR-049-Local-E5-Embeddings.md)
- [ADR-048: Semantic Tool Router](../architecture/ADR-048-Semantic-Tool-Router.md)
- [ADR-037: Semantic Memory Store](../architecture/ADR-037-Semantic-Memory-Store.md)
- [SEMANTIC_ROUTER.md](SEMANTIC_ROUTER.md)
- [LONG_TERM_MEMORY.md](LONG_TERM_MEMORY.md)
