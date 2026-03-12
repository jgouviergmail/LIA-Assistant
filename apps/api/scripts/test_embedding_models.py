#!/usr/bin/env python3
"""
Test script to compare embedding models for memory retrieval.

Compares:
- text-embedding-3-small (current production model)
- multilingual-e5-small (proposed replacement for asymmetric search)

Tests the specific use case: question → memory matching
where the memory stores a fact and the query is a question about it.

Usage:
    cd apps/api
    python scripts/test_embedding_models.py

Requirements:
    pip install sentence-transformers openai numpy
"""

import io
import sys

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pathlib import Path

import numpy as np

# Load .env from project root
try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded .env from {env_path}")
except ImportError:
    pass

# Test pairs: (memory_content, user_query, expected_match_description)
TEST_PAIRS = [
    # French - Personal facts
    ("Je me suis marié en 2008", "je me suis marié quand ?", "FR: marriage year"),
    ("Je me suis marié en 2008", "quelle est l'année de mon mariage ?", "FR: marriage year alt"),
    ("Je me suis marié en 2008", "mariage", "FR: single keyword"),
    # French - Preferences
    ("J'aime le chocolat", "qu'est-ce que j'aime manger ?", "FR: food preference"),
    ("J'aime le chocolat", "chocolat", "FR: exact keyword"),
    (
        "Je déteste les réunions le lundi",
        "quand est-ce que je n'aime pas les réunions ?",
        "FR: meeting preference",
    ),
    # French - Relationships
    ("Ma femme s'appelle Sophie", "comment s'appelle ma femme ?", "FR: wife name"),
    ("Mon frère habite à Lyon", "où habite mon frère ?", "FR: brother location"),
    # English - Personal facts
    ("I got married in 2008", "when did I get married?", "EN: marriage year"),
    ("I love chocolate", "what food do I like?", "EN: food preference"),
    ("My wife's name is Sophie", "what is my wife's name?", "EN: wife name"),
    # German
    ("Ich habe 2008 geheiratet", "wann habe ich geheiratet?", "DE: marriage year"),
    ("Ich liebe Schokolade", "was esse ich gerne?", "DE: food preference"),
    # Spanish
    ("Me casé en 2008", "¿cuándo me casé?", "ES: marriage year"),
    ("Me encanta el chocolate", "¿qué me gusta comer?", "ES: food preference"),
    # Italian
    ("Mi sono sposato nel 2008", "quando mi sono sposato?", "IT: marriage year"),
    ("Adoro il cioccolato", "cosa mi piace mangiare?", "IT: food preference"),
    # Chinese (Simplified)
    ("我2008年结婚了", "我什么时候结婚的？", "ZH: marriage year"),
    ("我喜欢巧克力", "我喜欢吃什么？", "ZH: food preference"),
]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    return float(np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr)))


def test_openai_embeddings(model: str = "text-embedding-3-small") -> dict[str, float]:
    """Test OpenAI embedding model on all pairs."""
    import os

    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(f"⚠️  OPENAI_API_KEY not set, skipping {model}")
        return {}

    client = OpenAI(api_key=api_key)
    results = {}

    print(f"\n{'='*60}")
    print(f"Testing: {model}")
    print(f"{'='*60}")

    for memory, query, desc in TEST_PAIRS:
        try:
            # Get embeddings
            response = client.embeddings.create(
                model=model, input=[memory, query], dimensions=256 if "3-small" in model else None
            )

            emb_memory = response.data[0].embedding
            emb_query = response.data[1].embedding

            score = cosine_similarity(emb_memory, emb_query)
            results[desc] = score

            status = "✅" if score >= 0.7 else "❌"
            print(f"{status} {desc}: {score:.4f}")

        except Exception as e:
            print(f"❌ {desc}: ERROR - {e}")
            results[desc] = 0.0

    return results


def test_e5_embeddings(
    model_name: str = "intfloat/multilingual-e5-small", use_prefixes: bool = True
) -> dict[str, float]:
    """Test E5 embedding model on all pairs."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("⚠️  sentence-transformers not installed, skipping E5 test")
        print("   Install with: pip install sentence-transformers")
        return {}

    print(f"\n{'='*60}")
    print(f"Testing: {model_name}")
    print(f"Prefixes: {'query:/passage:' if use_prefixes else 'None (symmetric)'}")
    print(f"{'='*60}")

    print("Loading model (first run may download ~500MB)...")
    model = SentenceTransformer(model_name)
    print("Model loaded.")

    results = {}

    for memory, query, desc in TEST_PAIRS:
        try:
            # Apply prefixes for asymmetric search
            if use_prefixes:
                memory_text = f"passage: {memory}"
                query_text = f"query: {query}"
            else:
                memory_text = memory
                query_text = query

            # Get embeddings
            emb_memory = model.encode(memory_text, normalize_embeddings=True)
            emb_query = model.encode(query_text, normalize_embeddings=True)

            score = cosine_similarity(emb_memory.tolist(), emb_query.tolist())
            results[desc] = score

            status = "✅" if score >= 0.7 else "❌"
            print(f"{status} {desc}: {score:.4f}")

        except Exception as e:
            print(f"❌ {desc}: ERROR - {e}")
            results[desc] = 0.0

    return results


def print_comparison(results: dict[str, dict[str, float]]) -> None:
    """Print a comparison table of all models."""
    print(f"\n{'='*80}")
    print("COMPARISON TABLE")
    print(f"{'='*80}")

    # Get all test descriptions
    all_tests = list(TEST_PAIRS)
    models = list(results.keys())

    # Header
    header = f"{'Test Case':<30}"
    for model in models:
        short_name = model.split("/")[-1][:15]
        header += f" | {short_name:>15}"
    print(header)
    print("-" * len(header))

    # Data rows
    for memory, query, desc in all_tests:
        row = f"{desc:<30}"
        for model in models:
            score = results[model].get(desc, 0.0)
            status = "✅" if score >= 0.7 else "❌"
            row += f" | {status} {score:>10.4f}"
        print(row)

    # Summary
    print("-" * len(header))
    print("\nSUMMARY:")
    for model in models:
        scores = list(results[model].values())
        if scores:
            avg = sum(scores) / len(scores)
            passing = sum(1 for s in scores if s >= 0.7)
            print(f"  {model}: avg={avg:.4f}, passing={passing}/{len(scores)} (threshold=0.7)")


def main():
    """Run all embedding model tests."""
    print("=" * 80)
    print("EMBEDDING MODEL COMPARISON FOR MEMORY RETRIEVAL")
    print("=" * 80)
    print(f"\nTest pairs: {len(TEST_PAIRS)}")
    print("Languages: FR, EN, DE, ES, IT, ZH")
    print("Threshold: 0.7 (current MEMORY_MIN_SEARCH_SCORE)")

    all_results = {}

    # Test 1: Current production model
    openai_results = test_openai_embeddings("text-embedding-3-small")
    if openai_results:
        all_results["text-embedding-3-small"] = openai_results

    # Test 2: E5-small without prefixes (symmetric mode)
    e5_small_sym = test_e5_embeddings("intfloat/multilingual-e5-small", use_prefixes=False)
    if e5_small_sym:
        all_results["e5-small (sym)"] = e5_small_sym

    # Test 3: E5-small with prefixes (asymmetric mode)
    e5_small_asym = test_e5_embeddings("intfloat/multilingual-e5-small", use_prefixes=True)
    if e5_small_asym:
        all_results["e5-small (asym)"] = e5_small_asym

    # Test 4: E5-base without prefixes (symmetric mode)
    e5_base_sym = test_e5_embeddings("intfloat/multilingual-e5-base", use_prefixes=False)
    if e5_base_sym:
        all_results["e5-base (sym)"] = e5_base_sym

    # Test 5: E5-base with prefixes (asymmetric mode)
    e5_base_asym = test_e5_embeddings("intfloat/multilingual-e5-base", use_prefixes=True)
    if e5_base_asym:
        all_results["e5-base (asym)"] = e5_base_asym

    # Print comparison
    if all_results:
        print_comparison(all_results)

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
